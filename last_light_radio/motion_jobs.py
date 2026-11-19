"""Recovered actor-crop H3 generation and deterministic masked assembly.

The historical workflow is kept byte-for-byte. Each request pins the actual
graph, two uploaded endpoint crops, source plates and mask. Only this module's
start function submits; polling/reassembly never retries a POST.
"""

from __future__ import annotations

import copy
import io
import json
import math
import re
import subprocess
import tempfile
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageChops

from .comfy import ComfyError, inspect_workflow, load_bindings, prepare_workflow, workflow_sha256
from .generation import execution_timing, job_folder, latest_event, load_request, record_event, utc_now
from .store import ProjectStore, canonical_bytes, sha256
from .video_tools import ffmpeg_path

PRODUCTION = Path(__file__).resolve().parents[1] / "workflows/h3/production"
PIPELINE = "actor_motion_v1"


def production_graph() -> dict:
    data = (PRODUCTION / "workflow_api.json").read_bytes()
    provenance = json.loads((PRODUCTION / "provenance.json").read_text())
    if sha256(data) != provenance["raw_sha256"]:
        raise ComfyError("TEMPLATE_CHECKSUM_MISMATCH", "The preserved production workflow changed on disk")
    return json.loads(data)


def _png(image: Image.Image) -> bytes:
    stream = io.BytesIO()
    image.save(stream, "PNG")
    return stream.getvalue()


def _asset(store: ProjectStore, reference: dict, *, mask=False) -> Image.Image:
    if not isinstance(reference, dict) or not all(isinstance(reference.get(k), str) for k in ("id", "path", "sha256")):
        raise ComfyError("INVALID_MOTION_PROFILE", "Motion source references require id, path and sha256")
    store.verify_master(reference)
    try:
        with Image.open(store.resolve(reference["path"])) as image:
            if image.width * image.height > 40_000_000 or getattr(image, "n_frames", 1) != 1:
                raise ComfyError("INVALID_MOTION_SOURCE", "Motion inputs must be single still images of at most 40 megapixels")
            if mask and (image.format != "PNG" or image.mode != "L"):
                raise ComfyError("INVALID_MOTION_MASK", "The recovered compositor requires a full-scene grayscale PNG mask")
            image.load()
            return image.copy() if mask else image.convert("RGB")
    except OSError as error:
        raise ComfyError("INVALID_MOTION_SOURCE", "A motion source image could not be decoded") from error


def prepare_motion_inputs(store: ProjectStore, profile: dict) -> dict:
    """Prepare exact recovered crops or an explicit authored letterbox transform."""
    if not isinstance(profile, dict):
        raise ComfyError("INVALID_MOTION_PROFILE", "Choose a recovered motion profile")
    if profile.get("master"):
        store.verify_master(profile["master"])
    for reference in profile.get("source_poses", {}).values():
        store.verify_master(reference)
    for name in ("id", "name", "scene_id", "actor", "role", "start_state", "end_state"):
        if not isinstance(profile.get(name), str) or not profile[name].strip():
            raise ComfyError("INVALID_MOTION_PROFILE", "Motion profile is missing a named state or actor", field=name)
    first, last = (_asset(store, profile.get(name)) for name in ("first", "last"))
    mask = _asset(store, profile.get("mask"), mask=True)
    background_ref = profile.get("background", profile["first"])
    background = _asset(store, background_ref)
    if first.size != last.size or first.size != mask.size or first.size != background.size:
        raise ComfyError("MOTION_GEOMETRY_MISMATCH", "Both state plates and the actor mask must have identical full-scene dimensions")
    crop = profile.get("crop", {})
    if not isinstance(crop, dict) or any(type(crop.get(k)) is not int for k in ("x", "y", "width", "height")):
        raise ComfyError("INVALID_MOTION_CROP", "Crop requires integer x, y, width and height")
    x, y, width, height = (crop[k] for k in ("x", "y", "width", "height"))
    transform = profile.get("conditioning_transform")
    if min(width, height) < 1 or min(x, y) < 0 or x + width > first.width or y + height > first.height:
        raise ComfyError("INVALID_MOTION_CROP", "The actor crop must be contained in its state plates")
    if transform is None and (width != 768 or height != 768):
        raise ComfyError("INVALID_MOTION_CROP", "The recovered production recipe uses an exact 768-square crop")
    if transform is not None:
        if not isinstance(transform, dict) or transform.get("version") != 1 or transform.get("source_box") != [x, y, x + width, y + height] or transform.get("conditioning_size") != [768, 768]:
            raise ComfyError("INVALID_MOTION_TRANSFORM", "The saved crop transform does not match the source geometry")
        fitted = transform.get("fitted_box")
        if not isinstance(fitted, list) or len(fitted) != 4 or any(type(v) is not int for v in fitted) or not (0 <= fitted[0] < fitted[2] <= 768 and 0 <= fitted[1] < fitted[3] <= 768):
            raise ComfyError("INVALID_MOTION_TRANSFORM", "The saved conditioning fit is invalid")
    frames, fps = profile.get("frames"), profile.get("fps")
    if type(frames) is not int or not 2 <= frames <= 300 or type(fps) not in (int, float) or not math.isfinite(fps) or not 1 <= fps <= 120:
        raise ComfyError("INVALID_MOTION_TIMING", "Choose 2–300 frames and a finite frame rate from 1 to 120")
    box = (x, y, x + width, y + height)
    mask_crop = mask.crop(box)
    if not mask_crop.getbbox():
        raise ComfyError("EMPTY_MOTION_MASK", "The actor mask has no visible pixels inside its crop")
    effective = Image.new("L", first.size, 0)
    effective.paste(mask_crop, (x, y))
    difference = ImageChops.difference(first, last)
    r, g, b = difference.split()
    maximum = ImageChops.lighter(ImageChops.lighter(r, g), b)
    outside = effective.point(lambda value: 255 if value == 0 else 0)
    outside_difference = ImageChops.multiply(maximum, outside)
    policy = {
        "version": 1, "color_policy": "direct_rgb_no_palette_correction",
        "mask_policy": "authored_painted_mask" if profile.get("authoring", {}).get("geometry") == "painted_mask" else "authored_polygon_gaussian_feather" if transform else "recovered_feathered_grayscale_clipped_to_actor_crop",
        "background_policy": "fixed_canonical_background" if "background" in profile else "fixed_first_state_plate",
        "background": background_ref,
        "outside_mask_endpoint_difference_bbox": outside_difference.getbbox(),
        "protected_pixel_guarantee": "lossless assembled pixels with effective mask=0 equal the selected deterministic background; MP4 is lossy",
        "historical_algorithm_status": "reconstruction; original color-preserving revision-2 correction and endpoint blend not recovered",
        "generated_endpoints_replaced": False,
    }
    first_crop, last_crop = first.crop(box), last.crop(box)
    if transform:
        from .recipes import fit_crop
        first_crop, last_crop = (fit_crop(image, transform) for image in (first_crop, last_crop))
        policy.update({"conditioning_transform": transform, "hold_policy": profile["hold_policy"],
                       "historical_algorithm_status": "authored_recipe; direct RGB alpha with an explicit reversible spatial mapping",
                       "encoded_edge_padding": {"right": first.width % 2, "bottom": first.height % 2}})
    return {"first": first, "last": last, "background": background, "mask": mask_crop, "effective_mask": effective,
            "first_crop": first_crop, "last_crop": last_crop, "policy": policy}


def composite_actor_frame(first: Image.Image, last: Image.Image, frame: Image.Image,
                          mask_crop: Image.Image, crop: dict, index: int, count: int, policy: dict) -> Image.Image:
    """Pure RGB alpha assembly; generated motion never affects another region."""
    transform = policy.get("conditioning_transform")
    expected = (768, 768) if transform else (crop["width"], crop["height"])
    if frame.mode != "RGB" or frame.size != expected:
        raise ComfyError("MOTION_FRAME_GEOMETRY", "Generated frame dimensions must match the exact prepared actor crop")
    if transform:
        from .recipes import restore_crop
        frame = restore_crop(frame, transform, (crop["width"], crop["height"]))
    background = first.copy()
    background.paste(frame, (crop["x"], crop["y"]), mask_crop)
    return background


def _validate_models(graph: dict, definitions: dict):
    for node_id, input_name in (("1", "unet_name"), ("2", "clip_name"), ("3", "vae_name"), ("6", "lora_name")):
        node = graph[node_id]
        declaration = definitions.get(node["class_type"], {}).get("input", {})
        spec = {**declaration.get("required", {}), **declaration.get("optional", {})}.get(input_name, [])
        selected = node["inputs"][input_name]
        choices = spec[0] if spec and isinstance(spec[0], list) else None
        if choices is not None and selected not in choices:
            raise ComfyError("MISSING_MODEL", "The selected production model is absent; restore it or explicitly select and record a variant", model=selected, node_id=node_id, available=choices)


def start_motion_generation(store: ProjectStore, client, profile: dict, motion_prompt: str,
                            seed: int, *, local_job_id: str | None = None) -> dict:
    local_id = local_job_id or uuid4().hex
    folder = job_folder(local_id)
    if store.resolve(folder).exists():
        raise ComfyError("JOB_EXISTS", "This local job already has a durable record; resume instead of submitting again")
    if not isinstance(motion_prompt, str) or not motion_prompt.strip() or len(motion_prompt) > 4000 or type(seed) is not int or not 0 <= seed <= 2**64 - 1:
        raise ComfyError("INVALID_MOTION_PARAMETERS", "Supply a motion prompt and a nonnegative integer seed")
    # Resolve FFmpeg before any GPU work, rather than discovering it afterwards.
    ffmpeg_path()
    profile = copy.deepcopy(profile)
    if profile.get("workflow_template_sha256") and profile["workflow_template_sha256"] != sha256((PRODUCTION / "workflow_api.json").read_bytes()):
        raise ComfyError("RECIPE_WORKFLOW_CHANGED", "This recipe's saved workflow differs from the installed template")
    inputs = prepare_motion_inputs(store, profile)
    graph = production_graph()
    bindings = load_bindings(PRODUCTION / "bindings.json")
    prefix = f"LastLightRadio/{local_id}/frame"
    overrides = {"first_image": "pending-first.png", "last_image": "pending-last.png", "motion_prompt": motion_prompt,
                 "width": inputs["first_crop"].width, "height": inputs["first_crop"].height,
                 "frames": profile["frames"], "seed": seed, "filename_prefix": prefix}
    variant = {"exact_recovered_model_recipe": True, "changes": {}}
    if "vae_name" in profile:
        if not isinstance(profile["vae_name"], str) or not profile["vae_name"].strip():
            raise ComfyError("INVALID_MOTION_PARAMETERS", "An explicit VAE variant must name its installed model file")
        overrides["vae_name"] = profile["vae_name"]
        if profile["vae_name"] != graph["3"]["inputs"]["vae_name"]:
            variant = {"exact_recovered_model_recipe": False, "changes": {"3.inputs.vae_name": {
                "template": graph["3"]["inputs"]["vae_name"], "selected": profile["vae_name"],
                "reason": "explicit_profile_override; no automatic fallback"}}}
    preview = prepare_workflow(graph, bindings, overrides)
    probe = client.probe()
    if not probe["connected"]:
        raise ComfyError("WORKER_OFFLINE", "Connection probe failed before production submission", errors=probe["errors"])
    _validate_models(preview, probe["object_info"])
    report = inspect_workflow(preview, probe["object_info"])
    if not report["valid"]:
        raise ComfyError("INVALID_WORKFLOW", "Production workflow is incompatible with this worker", errors=report["errors"])
    prepared_refs = {}
    for name, image in (("first", inputs["first_crop"]), ("last", inputs["last_crop"]), ("mask", inputs["mask"]), ("effective_mask", inputs["effective_mask"])):
        data = _png(image)
        relative = f"{folder}/prepared/{name}.png"
        store.write_once(relative, data)
        prepared_refs[name] = {"id": f"asset.{sha256(data)}", "path": relative, "sha256": sha256(data)}
    record_event(store, local_id, "uploading", pipeline=PIPELINE)
    try:
        uploads = {name: client.upload_image(store.resolve(prepared_refs[name]["path"]).read_bytes(), name + ".png", f"LastLightRadio/{local_id}") for name in ("first", "last")}
        overrides.update({"first_image": uploads["first"]["path"], "last_image": uploads["last"]["path"]})
        prepared = prepare_workflow(graph, bindings, overrides)
        request = {"schema_version": 1, "kind": "live_generation_request", "pipeline": PIPELINE,
                   "local_job_id": local_id, "created_at_utc": utc_now(), "base_url": client.base_url,
                   "client_id": str(uuid4()), "master": profile.get("master", profile["first"]), "motion_profile": profile,
                   "prepared_inputs": prepared_refs, "uploads": uploads, "composite_policy": inputs["policy"],
                   "workflow": store.save_snapshot(prepared, kind="workflows"), "workflow_sha256": workflow_sha256(prepared),
                   "template_sha256": workflow_sha256(graph), "template_raw_sha256": sha256((PRODUCTION / "workflow_api.json").read_bytes()),
                   "bindings": bindings, "execution_variant": variant,
                   "node_definitions": store.save_snapshot({name: probe["object_info"][name] for name in report["node_classes"]}, kind="workflows"),
                   "parameters": {"motion_prompt": motion_prompt, "seed": seed, "frames": profile["frames"], "fps": profile["fps"],
                                  "width": inputs["first_crop"].width, "height": inputs["first_crop"].height, "filename_prefix": prefix,
                                  "vae_name": prepared["3"]["inputs"]["vae_name"]},
                   "system_stats_before": probe["system_stats"], "review_status": "candidate", "canon_approved": False,
                   "purpose": "creator_requested_actor_motion_generation"}
        store.write_once(f"{folder}/request.json", canonical_bytes(store.save_snapshot(request, kind="jobs")))
        record_event(store, local_id, "submitting", workflow_sha256=request["workflow_sha256"])
        try:
            response = client.submit(prepared, client_id=request["client_id"], local_job_id=local_id)
        except Exception as error:
            details = error.to_dict() if isinstance(error, ComfyError) else {"message": str(error)}
            record_event(store, local_id, "submission_unknown" if details.get("code") == "SUBMISSION_AMBIGUOUS" else "submission_failed", error=details)
            raise
        accepted = {"local_job_id": local_id, "prompt_id": response["prompt_id"], "client_id": request["client_id"],
                    "base_url": client.base_url, "workflow_sha256": request["workflow_sha256"], "response": response}
        store.write_once(f"{folder}/accepted.json", canonical_bytes(accepted))
        record_event(store, local_id, "queued", prompt_id=response["prompt_id"])
        return {"local_job_id": local_id, "prompt_id": response["prompt_id"], "status": "queued", "output_root": str(store.root), "master": profile["first"]}
    except Exception as error:
        if isinstance(error, ComfyError):
            error.details.update({"local_job_id": local_id, "output_root": str(store.root)})
        raise


def _png_references(outputs: dict, request: dict) -> list[dict]:
    node_id = request["bindings"]["output"]["node_id"]
    records = outputs.get(node_id, {}).get("images") if isinstance(outputs, dict) and isinstance(outputs.get(node_id), dict) else None
    if not isinstance(records, list) or len(records) != request["parameters"]["frames"]:
        raise ComfyError("MOTION_FRAME_COUNT", "SaveImage must return exactly the requested number of PNG frames", expected=request["parameters"]["frames"], actual=len(records) if isinstance(records, list) else None)
    folder, stem = request["parameters"]["filename_prefix"].rsplit("/", 1)
    numbered = []
    for record in records:
        if not isinstance(record, dict) or record.get("type") != "output" or not isinstance(record.get("subfolder"), str):
            raise ComfyError("FOREIGN_MOTION_OUTPUT", "Production frame references must belong to this owned output folder")
        filename = record.get("filename", "")
        match = re.fullmatch(re.escape(stem) + r"_(\d{5,})_?\.png", filename) if isinstance(filename, str) else None
        if record["subfolder"].replace("\\", "/") != folder or not match:
            raise ComfyError("FOREIGN_MOTION_OUTPUT", "Production frame reference is outside this job's exact output prefix")
        numbered.append((int(match[1]), {"filename": filename, "subfolder": folder, "type": "output"}))
    numbered.sort(key=lambda item: item[0])
    indexes = [item[0] for item in numbered]
    if len(set(indexes)) != len(indexes) or indexes != list(range(indexes[0], indexes[0] + len(indexes))):
        raise ComfyError("MOTION_FRAME_SEQUENCE", "Production PNG frames must be unique and contiguous")
    return [item[1] for item in numbered]


def _encode_mp4(store: ProjectStore, relative: str, images, size: tuple[int, int], fps: float) -> dict:
    executable = ffmpeg_path()
    # Temporary output is never a published candidate. A fully encoded file is
    # atomically copied through write_once only after successful process exit.
    with tempfile.TemporaryDirectory(prefix="llr-encode-", dir=store.root) as temporary:
        output = Path(temporary) / "preview.mp4"
        args = [executable, "-v", "error", "-nostdin", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s:v", f"{size[0]}x{size[1]}",
                "-r", str(fps), "-i", "pipe:0", "-an", "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2:0:0,scale=in_range=full:out_range=limited:out_color_matrix=bt601,format=yuv420p",
                "-c:v", "libx264", "-preset", "slow", "-crf", "15", "-threads", "1", "-fflags", "+bitexact", "-flags:v", "+bitexact",
                "-color_range", "tv",
                "-movflags", "+faststart", str(output)]
        with tempfile.TemporaryFile() as errors:
            process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=errors)
            try:
                for image in images:
                    if image.size != size or image.mode != "RGB":
                        raise ComfyError("MOTION_ENCODE_GEOMETRY", "All assembled frames must retain the same RGB geometry")
                    process.stdin.write(image.tobytes())
                process.stdin.close()
                if process.wait(timeout=180):
                    errors.seek(0)
                    raise ComfyError("MOTION_ENCODE_FAILED", "FFmpeg could not encode the motion preview", reason=errors.read(1400).decode(errors="replace"))
            except BaseException:
                process.kill()
                process.wait()
                if not process.stdin.closed:
                    process.stdin.close()
                raise
        data = output.read_bytes()
        if len(data) < 12 or data[4:8] != b"ftyp":
            raise ComfyError("MOTION_ENCODE_FAILED", "Encoded preview is not an MP4 file")
        store.write_once(relative, data)
    return {"path": relative, "sha256": sha256(data), "bytes": len(data)}


def poll_motion_generation(store: ProjectStore, client, job_id: str) -> dict:
    folder = job_folder(job_id)
    request = load_request(store, job_id)
    if request.get("pipeline") != PIPELINE:
        raise ComfyError("WRONG_GENERATION_PIPELINE", "This job does not use the actor motion pipeline")
    if client.base_url != request["base_url"]:
        raise ComfyError("WORKER_MISMATCH", "Resume with the same worker URL recorded for this job")
    inputs = prepare_motion_inputs(store, request["motion_profile"])
    for reference in request["prepared_inputs"].values():
        store.verify_master(reference)
    accepted_path = store.resolve(f"{folder}/accepted.json")
    if not accepted_path.is_file():
        raise ComfyError("SUBMISSION_UNRESOLVED", "No accepted prompt is recorded; resume never resubmits", local_job_id=job_id)
    accepted = json.loads(accepted_path.read_text())
    if any(accepted.get(key) != request.get(key) for key in ("local_job_id", "client_id", "base_url", "workflow_sha256")):
        raise ComfyError("INVALID_JOB_RECORD", "Accepted prompt does not match this request's ownership")
    candidate_path = store.resolve(f"candidates/{job_id}/candidate.json")
    if candidate_path.is_file():
        candidate = json.loads(candidate_path.read_text())
        references = candidate["outputs"] + candidate["motion"]["raw_frames"] + [candidate["motion"]["raw_preview"]] + list(candidate["motion"]["samples"].values())
        for reference in references:
            if sha256(store.resolve(reference["path"]).read_bytes()) != reference["sha256"]:
                raise ComfyError("CANDIDATE_CHECKSUM_MISMATCH", "An existing motion candidate or source frame changed on disk")
        return {"local_job_id": job_id, "prompt_id": accepted["prompt_id"], "status": "success", "candidate": candidate, "candidate_path": str(candidate_path)}
    previous = latest_event(store, job_id)
    try:
        result = client.poll(accepted["prompt_id"])
    except ComfyError as error:
        if previous.get("status") != "connection_error":
            record_event(store, job_id, "connection_error", error=error.to_dict())
        raise
    status = result["status"]
    if previous.get("status") != status:
        record_event(store, job_id, status, prompt_id=accepted["prompt_id"], error=result.get("error"))
    response = {"local_job_id": job_id, "prompt_id": accepted["prompt_id"], "status": status}
    if status == "failed":
        response.update({"error": result.get("error"), "failure_record": store.save_snapshot(result, kind="jobs")})
        return response
    if status != "success":
        return response
    graph = store.read_snapshot(request["workflow"])
    if workflow_sha256(graph) != request["workflow_sha256"]:
        raise ComfyError("WORKFLOW_CHECKSUM_MISMATCH", "Prepared production graph changed on disk")
    history_ref = store.save_snapshot(result, kind="jobs")
    prompt = result.get("history", {}).get("prompt")
    history_graph = prompt[2] if isinstance(prompt, list) and len(prompt) > 2 else None
    if history_graph is None or workflow_sha256(history_graph) != request["workflow_sha256"]:
        record_event(store, job_id, "provenance_mismatch", history=history_ref)
        raise ComfyError("HISTORY_WORKFLOW_MISMATCH", "Production assembly requires the exact executed workflow in history")
    raw_records = []
    try:
        references = _png_references(result["outputs"], request)
        for index, reference in enumerate(references):
            relative = f"candidates/{job_id}/raw_frames/{index:06d}.png"
            path = store.resolve(relative)
            checksum_path = store.resolve(relative + ".json")
            if path.is_file() and checksum_path.is_file():
                data = path.read_bytes()
                pinned = json.loads(checksum_path.read_text())
                if sha256(data) != pinned["sha256"] or pinned["reference"] != reference:
                    raise ComfyError("CANDIDATE_CHECKSUM_MISMATCH", "A downloaded motion frame changed before assembly")
            else:
                data = client.download_png_output(reference)
            with Image.open(io.BytesIO(data)) as image:
                if image.format != "PNG" or getattr(image, "n_frames", 1) != 1 or image.size != inputs["first_crop"].size or image.mode != "RGB":
                    raise ComfyError("MOTION_FRAME_GEOMETRY", "Every generated frame must be a static RGB PNG with the prepared crop's dimensions")
                image.load()
            record = {"path": relative, "sha256": sha256(data), "bytes": len(data), "reference": reference, "index": index}
            store.write_once(relative, data)
            store.write_once(relative + ".json", canonical_bytes(record))
            raw_records.append(record)
        store.write_once(f"candidates/{job_id}/raw_frames/manifest.json", canonical_bytes({"frame_count": len(raw_records), "frames": raw_records}))
    except (ComfyError, OSError, ValueError) as error:
        record_event(store, job_id, "download_failed", error=error.to_dict() if isinstance(error, ComfyError) else {"message": str(error)}, history=history_ref)
        raise
    record_event(store, job_id, "compositing", frames=len(raw_records))
    samples = {}
    count = len(raw_records)
    crop = request["motion_profile"]["crop"]
    def raw_images():
        for record in raw_records:
            with Image.open(store.resolve(record["path"])) as image:
                yield image.convert("RGB")
    def assembled_images():
        for index, image in enumerate(raw_images()):
            composite = composite_actor_frame(inputs["background"], inputs["last"], image, inputs["mask"], crop, index, count, inputs["policy"])
            for key, sample_index in (("start", 0), ("middle", count // 2), ("end", count - 1)):
                if index == sample_index:
                    data = _png(composite)
                    relative = f"candidates/{job_id}/lossless_samples/{key}.png"
                    store.write_once(relative, data)
                    samples[key] = {"path": relative, "sha256": sha256(data), "frame_index": index}
            yield composite
    try:
        fps = request["parameters"]["fps"]
        output = _encode_mp4(store, f"candidates/{job_id}/assembled.mp4", assembled_images(), inputs["first"].size, fps)
        raw_preview = _encode_mp4(store, f"candidates/{job_id}/raw_crop.mp4", raw_images(), inputs["first_crop"].size, fps)
    except (ComfyError, OSError, ValueError, subprocess.SubprocessError) as error:
        record_event(store, job_id, "assembly_failed", error=error.to_dict() if isinstance(error, ComfyError) else {"message": str(error)})
        raise
    output["properties"] = {"container": "mp4", "codec": "h264", "width": inputs["first"].width + inputs["first"].width % 2, "height": inputs["first"].height + inputs["first"].height % 2,
                            "source_width": inputs["first"].width, "source_height": inputs["first"].height,
                            "frame_count": count, "duration_ms": count / fps * 1000, "effective_fps": fps,
                            "requested_fps": fps, "pixel_decode_verified": False, "source_png_decode_verified": True, "encoder_completed": True, "lossy": True,
                            "color_space": "bt601", "color_range": "limited", "encoder": "libx264 slow crf15"}
    try:
        after = client.system_stats()
    except ComfyError as error:
        after = {"unavailable": error.to_dict()}
    profile = request["motion_profile"]
    candidate = {"schema_version": 1, "local_job_id": job_id, "prompt_id": accepted["prompt_id"], "pipeline": PIPELINE,
                 "created_at_utc": utc_now(), "review_status": "candidate", "canon_approved": False,
                 "master": request["master"], "base_url": request["base_url"], "workflow": request["workflow"],
                 "workflow_sha256": request["workflow_sha256"], "template_sha256": request["template_sha256"],
                 "bindings": request["bindings"], "parameters": request["parameters"], "execution_variant": request["execution_variant"],
                 "execution": execution_timing(result.get("history", {})), "history_workflow_verified": True,
                 "history": history_ref, "system_stats_before": request["system_stats_before"], "system_stats_after": after,
                 "peak_vram": None, "peak_vram_note": "Before/after snapshots do not measure peak VRAM",
                 "outputs": [output], "quality_review": "pending_creator_review",
                 "motion": {"profile": profile, "profile_id": profile["id"], "actor": profile["actor"], "role": profile["role"],
                            "crop": crop, "mask": profile["mask"], "first": profile["first"], "last": profile["last"],
                            "start_state": profile["start_state"], "end_state": profile["end_state"],
                            "reference_candidate_id": profile.get("reference_candidate_id"), "prepared_inputs": request["prepared_inputs"],
                            "compositing_policy": "Direct RGB alpha through the saved feathered actor mask, clipped to the crop, over a fixed canonical background; generated endpoints retained.",
                            "composite_policy": inputs["policy"], "raw_frames": raw_records, "raw_preview": raw_preview, "samples": samples, "lossless_samples": samples}}
    store.write_once(f"candidates/{job_id}/candidate.json", canonical_bytes(candidate))
    record_event(store, job_id, "downloaded", outputs=1, raw_frames=count)
    response.update({"candidate": candidate, "candidate_path": str(candidate_path)})
    return response
