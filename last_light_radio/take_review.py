"""Read-only, advisory diagnostics for two owned motion takes.

Numbers describe RGB differences, never visual quality or approval eligibility.
Decoded delivery frames and saved lossless assembly samples remain distinct.
"""

from __future__ import annotations

import io
import math
import subprocess
import threading

from PIL import Image, ImageChops, ImageOps, ImageStat

from .motion_profiles import profiles
from .pilot_media import boundary_frames, inspect_video
from .store import canonical_bytes, sha256
from .studio import StudioError, text
from .video_tools import ffmpeg_path


_DECODE_SLOTS = threading.BoundedSemaphore(2)
_DECODE_WAIT_SECONDS = 5


def _verify(store, reference, label):
    if not isinstance(reference, dict) or not all(isinstance(reference.get(key), str) for key in ("path", "sha256")):
        raise StudioError(f"{label} has no pinned media reference", 409)
    store.verify_master({"id": label, **reference})


def _rgb(store, reference, label):
    _verify(store, reference, label)
    with Image.open(store.resolve(reference["path"])) as image:
        if getattr(image, "n_frames", 1) != 1:
            raise StudioError(f"{label} must be a single still", 409)
        return ImageOps.exif_transpose(image).convert("RGB")


def _media(studio, identity):
    candidate = studio.candidate(text(identity, "Take", 100))
    scene = studio.scene(candidate["scene_id"])
    _verify(studio.store, scene["master"], "scene master")
    metadata = candidate["metadata"]
    if metadata.get("master", {}).get("sha256") != scene["master"]["sha256"]:
        raise StudioError("Take and scene master hashes disagree", 409)
    outputs = metadata.get("outputs", [])
    if len(outputs) != 1:
        raise StudioError("Take inspection requires one unambiguous assembled output", 409)
    output = outputs[0]
    _verify(studio.store, output, "assembled take")
    properties = output.get("properties", {})
    count, fps = properties.get("frame_count"), properties.get("effective_fps")
    if type(count) is not int or not 2 <= count <= 300 or type(fps) not in (int, float) or not math.isfinite(fps) or not 1 <= fps <= 120:
        raise StudioError("Take inspection requires pinned timing of 2–300 frames and 1–120 fps", 409)
    size = (properties.get("width"), properties.get("height"))
    if any(type(value) is not int or value < 1 for value in size) or size[0] * size[1] > 40_000_000:
        raise StudioError("Take inspection requires pinned image dimensions", 409)
    scene_size = (scene["width"], scene["height"])
    if size not in (scene_size, (scene_size[0] + scene_size[0] % 2, scene_size[1] + scene_size[1] % 2)):
        raise StudioError("Assembled take dimensions do not match its scene", 409)
    return candidate, output, count, fps, size, scene_size


def _webp_frames(store, output, count, size, indices):
    with Image.open(store.resolve(output["path"])) as image:
        if image.format != "WEBP" or image.n_frames != count or image.size != size:
            raise StudioError("Decoded WebP geometry or frame count differs from the take record", 409)
        result = {}
        # Decode every frame so a corrupt middle frame cannot hide behind endpoints.
        for index in range(count):
            image.seek(index)
            image.load()
            if index in indices:
                result[index] = image.convert("RGB")
        return [result[index] for index in indices]


def _decode(studio, output, count, fps, size):
    container = output["properties"].get("container")
    if container == "mp4":
        path = studio.store.resolve(output["path"])
        try:
            inspect_video(path, count, fps, size, timeout=90)
            frames = boundary_frames(path, count, size)
        except subprocess.SubprocessError as error:
            raise StudioError("The assembled-video inspection failed or timed out; retry this take", 409) from error
    elif container == "webp":
        frames = _webp_frames(studio.store, output, count, size, [0, count - 1])
    else:
        raise StudioError("Take inspection supports assembled MP4 or animated WebP media", 409)
    _verify(studio.store, output, "assembled take after decoding")
    return frames


def decoded_frame(studio, candidate_id, index):
    """Return an exact zero-based assembled frame as PNG without caching/writes."""
    _, output, count, _, size, _ = _media(studio, candidate_id)
    if type(index) is not int or not 0 <= index < count:
        raise StudioError(f"Frame must be a whole number from 0 to {count - 1}")
    if not _DECODE_SLOTS.acquire(timeout=_DECODE_WAIT_SECONDS):
        raise StudioError("Frame inspection is busy decoding other frames; pause scrubbing and retry", 503)
    try:
        return _decoded_png(studio, output, count, size, index)
    finally:
        # A canceled browser request does not terminate a running decoder. Keep
        # its slot until the decode finishes (or raises) to bound CPU/memory use.
        _DECODE_SLOTS.release()


def _decoded_png(studio, output, count, size, index):
    if output["properties"].get("container") == "webp":
        frame = _webp_frames(studio.store, output, count, size, [index])[0]
    elif output["properties"].get("container") == "mp4":
        try:
            result = subprocess.run([ffmpeg_path(), "-v", "error", "-nostdin", "-i", str(studio.store.resolve(output["path"])),
                                     "-map", "0:v:0", "-vf", f"select=eq(n\\,{index})", "-frames:v", "1", "-fps_mode", "passthrough",
                                     "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"], capture_output=True, timeout=90)
        except subprocess.SubprocessError as error:
            raise StudioError("Exact assembled-frame decoding failed or timed out; retry this take", 409) from error
        if result.returncode or result.stderr.strip() or len(result.stdout) != size[0] * size[1] * 3:
            raise StudioError("Could not decode the exact requested assembled frame", 409)
        frame = Image.frombytes("RGB", size, result.stdout)
    else:
        raise StudioError("Exact frame inspection supports assembled MP4 or animated WebP media", 409)
    _verify(studio.store, output, "assembled take after decoding")
    buffer = io.BytesIO()
    frame.save(buffer, "PNG")
    return buffer.getvalue()


def _profile(studio, candidate):
    profile = candidate["metadata"].get("motion", {}).get("profile")
    if profile is None:
        matches = [row for row in profiles(studio) if row.get("reference_candidate_id") == candidate["id"]]
        if len(matches) != 1:
            raise StudioError("Take has no unambiguous pinned motion recipe; conditioning inspection is unavailable", 409)
        profile = matches[0]
    for part in ("first", "last", "mask", "background"):
        _verify(studio.store, profile.get(part), f"motion {part}")
    for reference in profile.get("source_poses", {}).values():
        _verify(studio.store, reference, "source pose")
    _verify(studio.store, profile.get("master", profile["background"]), "canonical scene")
    if any(not isinstance(profile.get(key), str) or not profile[key].strip() for key in ("id", "actor", "start_state", "end_state")):
        raise StudioError("Motion recipe lacks an actor or named entry/exit state", 409)
    return profile


def _pose(profile, part):
    return profile.get("source_poses", {}).get(part, profile[part])["sha256"]


def _root(profile):
    return profile.get("master", profile["background"])["sha256"]


def _region(region, size):
    region = region if region is not None else {"x": 0, "y": 0, "width": size[0], "height": size[1]}
    if not isinstance(region, dict) or any(type(region.get(key)) is not int for key in ("x", "y", "width", "height")):
        raise StudioError("Diagnostic region needs whole pixel x, y, width and height")
    x, y, width, height = (region[key] for key in ("x", "y", "width", "height"))
    if min(x, y) < 0 or min(width, height) < 1 or x + width > size[0] or y + height > size[1]:
        raise StudioError("Diagnostic region must fit inside the original scene")
    return {"x": x, "y": y, "width": width, "height": height}


def _difference(left, right, region):
    x, y, width, height = (region[key] for key in ("x", "y", "width", "height"))
    box = (x, y, x + width, y + height)
    delta = ImageChops.difference(left.crop(box), right.crop(box))
    channels = delta.split()
    maximum = ImageChops.lighter(ImageChops.lighter(channels[0], channels[1]), channels[2])
    histogram = maximum.histogram()
    changed = width * height - histogram[0]
    return {"pixels": width * height, "changed_pixels": changed,
            "mean_absolute_error": round(sum(ImageStat.Stat(delta).mean) / 3, 6),
            "max_channel_difference": max(value for value, total in enumerate(histogram) if total),
            "exact_match": changed == 0}


def compare_takes(studio, a_id, b_id, region=None):
    """Compare compatible contracts without changing candidates or review state."""
    if a_id == b_id:
        raise StudioError("Choose two different takes")
    rows = [_media(studio, identity) for identity in (a_id, b_id)]
    recipes = [_profile(studio, row[0]) for row in rows]
    a, b = recipes
    if _root(a) != _root(b) or rows[0][5] != rows[1][5]:
        raise StudioError("Take comparison requires the same canonical scene", 409)
    if a["actor"].casefold() != b["actor"].casefold():
        raise StudioError("Take comparison requires the same subject", 409)
    if any(a[key] != b[key] for key in ("start_state", "end_state")) or any(_pose(a, part) != _pose(b, part) for part in ("first", "last")):
        raise StudioError("Take comparison requires compatible named states and conditioning poses", 409)
    if rows[0][3] != rows[1][3]:
        raise StudioError("Take comparison requires the same frame rate", 409)
    size = rows[0][5]
    region = _region(region, size)
    result = {"schema_version": 1, "advisory_only": True, "scene_id": _root(a)[:32],
              "width": size[0], "height": size[1], "region": region, "takes": {}, "checks": [],
              "same_motion": a.get("family_id", a["id"]) == b.get("family_id", b["id"]),
              "warnings": ["RGB differences are advisory measurements; creator review determines visual quality and approval."]}
    boundaries = []
    pinned_candidates = []
    for key, row, profile in zip(("a", "b"), rows, recipes):
        candidate, output, count, fps, encoded_size, _ = row
        pinned_candidates.append(canonical_bytes(candidate))
        decoded = [frame.crop((0, 0, *size)) for frame in _decode(studio, output, count, fps, encoded_size)]
        boundaries.append(decoded)
        conditioning = [_rgb(studio.store, profile[part], f"{key} conditioning {part}") for part in ("first", "last")]
        if any(frame.size != size for frame in conditioning):
            raise StudioError("Conditioning plates do not match the scene dimensions", 409)
        motion = candidate["metadata"].get("motion", {})
        samples = motion.get("lossless_samples", {})
        pins = {"output_sha256": output["sha256"], "metadata_sha256": sha256(canonical_bytes(candidate["metadata"])),
                "profile_sha256": sha256(canonical_bytes(profile)), "canonical_sha256": _root(profile),
                "first_sha256": profile["first"]["sha256"], "last_sha256": profile["last"]["sha256"],
                "review_version": candidate["version"]}
        result["takes"][key] = {"id": candidate["id"], "label": candidate["label"], "status": candidate["status"],
                                 "version": candidate["version"], "source": "decoded_video" if output["properties"]["container"] == "mp4" else "decoded_webp",
                                 "fps": fps, "frame_count": count, "profile_id": profile["id"], "profile_revision": profile.get("revision", 1),
                                 "family_id": profile.get("family_id", profile["id"]), "actor": profile["actor"],
                                 "start_state": profile["start_state"], "end_state": profile["end_state"], "pins": pins,
                                 "frames": {"entry": f"/api/candidates/{candidate['id']}/frames/0", "exit": f"/api/candidates/{candidate['id']}/frames/{count - 1}"}}
        checks = [(f"{key}_loop", f"{key.upper()} first → last decoded frame", decoded[0], decoded[1]),
                  (f"{key}_entry_conditioning", f"{key.upper()} first decoded frame → first conditioning plate", decoded[0], conditioning[0]),
                  (f"{key}_exit_conditioning", f"{key.upper()} last decoded frame → last conditioning plate", decoded[1], conditioning[1])]
        if samples:
            for part, expected, decoded_frame_image in (("start", 0, decoded[0]), ("end", count - 1, decoded[1])):
                reference = samples.get(part)
                if not isinstance(reference, dict) or reference.get("frame_index") != expected:
                    raise StudioError("Saved lossless boundary sample has a missing or incorrect frame index", 409)
                sample = _rgb(studio.store, reference, f"{key} lossless {part}")
                if sample.size != size:
                    raise StudioError("Saved lossless boundary does not match the scene dimensions", 409)
                pins[f"lossless_{part}_sha256"] = reference["sha256"]
                checks.append((f"{key}_{part}_encoding", f"{key.upper()} decoded {part} → saved lossless assembly", decoded_frame_image, sample))
        else:
            result["warnings"].append(f"{key.upper()} has no pinned lossless assembly samples; measurements use actual decoded delivery frames.")
        if candidate["status"] != "approved":
            result["warnings"].append(f"{key.upper()} is {candidate['status']}; previewing it does not make it eligible for production.")
        for identity, label, left, right in checks:
            result["checks"].append({"id": identity, "label": label, **_difference(left, right, region)})
    result["checks"].append({"id": "a_exit_b_entry", "label": "A actual last frame → B actual first frame",
                             **_difference(boundaries[0][1], boundaries[1][0], region)})
    if a["end_state"] != b["start_state"] or _pose(a, "last") != _pose(b, "first"):
        result["warnings"].append("A exit and B entry have different state/pose contracts; the measured direct join is not a legal production transition.")
    if not result["same_motion"]:
        result["warnings"].append("The takes have compatible state contracts but belong to different motion families.")
    # Refuse a report if media, metadata, recipe pointers or reviews changed while decoding.
    for row, profile, pinned in zip(rows, recipes, pinned_candidates):
        current = studio.candidate(row[0]["id"])
        if canonical_bytes(current) != pinned or canonical_bytes(_profile(studio, current)) != canonical_bytes(profile):
            raise StudioError("A take or review changed during comparison; inspect the refreshed versions", 409)
        _verify(studio.store, row[1], "assembled take after comparison")
    return result
