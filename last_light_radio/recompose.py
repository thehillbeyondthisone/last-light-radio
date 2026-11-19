"""Rebuild an actor take from owned PNGs after a mask-only recipe revision."""

from __future__ import annotations

import copy
import io
import json

from PIL import Image

from .generation import job_folder, load_request, record_event, utc_now
from .motion_jobs import _encode_mp4, _png, composite_actor_frame, prepare_motion_inputs
from .motion_profiles import get_profile
from .store import canonical_bytes, sha256
from .studio import StudioError
from .video_tools import verify_video

VERSION = "mask_recomposition_v1"


def validate_mask_revision(source, revised):
    """Changing the frame mapping would move/rescale the already generated pixels."""
    keys = ("scene_id", "actor", "role", "start_state", "end_state", "crop", "conditioning_transform",
            "frames", "fps", "prompt", "seed", "vae_name", "workflow_template_sha256", "source_poses")
    if any(source.get(key) != revised.get(key) for key in keys):
        raise StudioError("Recomposition needs the same poses, crop, timing and generation settings; only the motion mask may change")
    if any(source[part]["sha256"] != revised[part]["sha256"] for part in ("first", "last", "background")):
        raise StudioError("Recomposition cannot replace the source plates or background")


def recompose(studio, source_id, recipe_id):
    """Append an unapproved derivative; never submit, replace or approve a render."""
    source = studio.candidate(source_id)
    metadata = source["metadata"]
    if metadata.get("pipeline") not in {"actor_motion_v1", VERSION} or not metadata.get("motion", {}).get("raw_frames"):
        raise StudioError("Choose an original completed actor take with saved PNG frames")
    profile = get_profile(studio, recipe_id)
    validate_mask_revision(metadata["motion"]["profile"], profile)
    prior = metadata.get("recomposition")
    request = studio.store.read_snapshot(prior["source_generation_request"]) if prior else load_request(studio.store, source_id)
    if prior:
        validate_mask_revision(request["motion_profile"], metadata["motion"]["profile"])
    elif request["motion_profile"] != metadata["motion"]["profile"]:
        raise StudioError("Source candidate and saved generation request disagree")
    inputs = prepare_motion_inputs(studio.store, profile)
    raw = metadata["motion"]["raw_frames"]
    count = profile["frames"]
    if len(raw) != count or [row["index"] for row in raw] != list(range(count)):
        raise StudioError("The saved raw frame sequence is incomplete or out of order")
    for reference in [*metadata["outputs"], *raw, metadata["motion"]["raw_preview"], *request["prepared_inputs"].values()]:
        studio.store.verify_master({"id": "recomposition-source", **reference})
    signature = {"version": VERSION, "source_candidate_id": source_id, "recipe_id": recipe_id,
                 "source_media_sha256": metadata["outputs"][0]["sha256"]}
    identity = sha256(canonical_bytes(signature))[:32]
    with studio.db() as db:
        exists = db.execute("SELECT 1 FROM candidates WHERE id=?", (identity,)).fetchone()
    if exists:
        existing = studio.candidate(identity)
        for reference in [*existing["metadata"]["outputs"], *existing["metadata"]["motion"]["lossless_samples"].values()]:
            studio.store.verify_master({"id": "existing-recomposition", **reference})
        return existing
    saved = studio.store.resolve(f"candidates/{identity}/candidate.json")
    if saved.is_file():
        recovered = json.loads(saved.read_text())
        if any(recovered.get("recomposition", {}).get(key) != value for key, value in signature.items()) or recovered.get("motion", {}).get("profile") != profile:
            raise StudioError("The saved recomposition does not match this area revision")
        for reference in [*recovered["outputs"], *recovered["motion"]["lossless_samples"].values()]:
            studio.store.verify_master({"id": "recovered-recomposition", **reference})
        studio.register_candidate(source["scene_id"], profile["name"] + " · corrected area", recovered)
        record_event(studio.store, identity, "downloaded", pipeline=VERSION, recovered=True)
        return studio.candidate(identity)
    # This is a CPU assembly log, separate from the original owned GPU job.
    record_event(studio.store, identity, "compositing", pipeline=VERSION, **signature)
    samples = {}

    def assembled():
        for index, reference in enumerate(raw):
            with Image.open(io.BytesIO(studio.store.resolve(reference["path"]).read_bytes())) as image:
                image.load()
                frame = composite_actor_frame(inputs["background"], inputs["last"], image.convert("RGB"),
                                              inputs["mask"], profile["crop"], index, count, inputs["policy"])
            for key, position in (("start", 0), ("middle", count // 2), ("end", count - 1)):
                if index == position:
                    data = _png(frame)
                    path = f"candidates/{identity}/lossless_samples/{key}.png"
                    studio.store.write_once(path, data)
                    samples[key] = {"path": path, "sha256": sha256(data), "frame_index": index}
            yield frame

    try:
        output = _encode_mp4(studio.store, f"candidates/{identity}/assembled.mp4", assembled(), inputs["background"].size, profile["fps"])
        verify_video(studio.store.resolve(output["path"]))
        output["properties"] = {**metadata["outputs"][0]["properties"], "pixel_decode_verified": True}
        candidate = copy.deepcopy(metadata)
        candidate.update({"local_job_id": identity, "pipeline": VERSION, "created_at_utc": utc_now(),
                          "review_status": "candidate", "quality_review": "pending_creator_review", "canon_approved": False,
                          "outputs": [output], "recomposition": {**signature, "gpu_submitted": False,
                          "source_generation_request": studio.store.save_snapshot(request, kind="jobs")}})
        motion = candidate["motion"]
        motion.update({"profile": profile, "profile_id": profile["id"], "mask": profile["mask"],
                       "composite_policy": inputs["policy"], "samples": samples, "lossless_samples": samples})
        # The generation inputs remain pinned to their original request. Record
        # the revised assembly mask separately; it was never sent to the model.
        motion["assembly_mask"] = profile["mask"]
        studio.store.write_once(f"candidates/{identity}/candidate.json", canonical_bytes(candidate))
        studio.store.write_once(f"{job_folder(identity)}/recomposition.json", canonical_bytes(candidate["recomposition"]))
        studio.register_candidate(source["scene_id"], profile["name"] + " · corrected area", candidate)
        record_event(studio.store, identity, "downloaded", pipeline=VERSION, outputs=1, raw_frames_reused=count)
        return studio.candidate(identity)
    except Exception as error:
        record_event(studio.store, identity, "assembly_failed", pipeline=VERSION, error={"message": str(error)})
        raise
