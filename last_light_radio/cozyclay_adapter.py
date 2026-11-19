"""Validated CozyClay keyframe packages become local, unsubmitted H3 recipes.

The package's video is preserved as a human reference. The recovered H3 graph
accepts endpoint stills and text; this module invents no video/depth bindings.
"""

from __future__ import annotations

import io
import json
import math
import re
import stat
import warnings
import zipfile
from pathlib import PurePosixPath

from PIL import Image, ImageChops

from .motion_jobs import prepare_motion_inputs
from .motion_profiles import INT8_VAE, ORIGINAL_VAE, public_profiles
from .recipes import RESTRICTIONS, png, prepare_recipe
from .store import canonical_bytes, sha256
from .studio import StudioError, text

MAX_ZIP_BYTES = 64 * 1024 * 1024
MAX_EXPANDED_BYTES = 96 * 1024 * 1024
MAX_MEMBER_BYTES = 48 * 1024 * 1024
REQUIRED = {"first.png", "last.png", "camera.json", "prompt.txt"}
OPTIONAL = {"clip.mp4", "clip.webm", "README.txt"}
CAMERA_EPSILON = 1e-12


class CozyClayError(StudioError):
    """A visible import failure, before any render can be submitted."""


def _fail(message):
    raise CozyClayError(message)


def _finite(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _json(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                _fail(f"Duplicate camera metadata key: {key}")
            result[key] = value
        return result
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=unique,
                           parse_constant=lambda value: _fail(f"Nonfinite camera value: {value}"))
    except (UnicodeError, ValueError, RecursionError) as error:
        raise CozyClayError("Camera metadata must be bounded UTF-8 JSON with unique keys") from error
    if not isinstance(value, dict):
        _fail("Camera metadata must be a JSON object")
    return value


def _png_size(data):
    if len(data) > 20 * 1024 * 1024:
        _fail("Endpoint PNG exceeds the 20 MB still-image limit")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if image.format != "PNG" or getattr(image, "n_frames", 1) != 1:
                    _fail("Both endpoints must be single PNG still images")
                if not 1 <= image.width * image.height <= 40_000_000:
                    _fail("Endpoint dimensions exceed the 40-megapixel limit")
                image.load()
                if image.convert("RGBA").getchannel("A").getextrema() != (255, 255):
                    _fail("Endpoint plates must be opaque")
                return image.convert("RGB")
    except (OSError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise CozyClayError("An endpoint could not be decoded as a safe PNG") from error


def _read(data, expected_sha256=None):
    if not isinstance(data, bytes) or not data or len(data) > MAX_ZIP_BYTES:
        _fail("Choose a nonempty CozyClay ZIP of at most 64 MB")
    digest = sha256(data)
    if expected_sha256 is not None and expected_sha256 != digest:
        _fail("CozyClay package checksum changed; inspect the selected package again")
    members, folder, seen, expanded = {}, None, set(), 0
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
            if not 4 <= len(infos) <= 9:
                _fail("A keyframe ZIP must contain one shot with 4–8 files")
            for info in infos:
                name = info.filename
                path = PurePosixPath(name)
                parts = path.parts
                if (len(name) > 200 or info.orig_filename != name or "\\" in name or ":" in name
                        or path.is_absolute() or any(ord(c) < 32 for c in name)
                        or any(p in {".", ".."} for p in name.split("/"))
                        or stat.S_ISLNK(info.external_attr >> 16) or info.flag_bits & 1):
                    _fail("Unsafe, encrypted or symlink member in CozyClay ZIP")
                if name.casefold() in seen:
                    _fail("Duplicate member in CozyClay ZIP")
                seen.add(name.casefold())
                if info.is_dir():
                    if len(parts) != 1 or info.file_size or (folder is not None and parts[0] != folder):
                        _fail("Only one shot folder is allowed")
                    folder = parts[0]
                    continue
                if len(parts) != 2 or not re.fullmatch(r"[A-Za-z0-9_-]+", parts[0]):
                    _fail("Every package file must be inside one named shot folder")
                if folder is None:
                    folder = parts[0]
                if parts[0] != folder:
                    _fail("Import exactly one shot folder at a time")
                leaf = parts[1]
                if leaf not in REQUIRED | OPTIONAL:
                    _fail("Duplicate or unsupported member in CozyClay ZIP")
                expanded += info.file_size
                limit = 128 * 1024 if leaf in {"camera.json", "prompt.txt", "README.txt"} else MAX_MEMBER_BYTES
                if (info.file_size > limit or expanded > MAX_EXPANDED_BYTES
                        or (info.file_size > 1024 * 1024 and info.file_size > max(1, info.compress_size) * 200)):
                    _fail("CozyClay ZIP exceeds bounded expansion or compression limits")
                with archive.open(info) as stream:
                    member = stream.read(limit + 1)
                if len(member) != info.file_size or len(member) > limit:
                    _fail("CozyClay member length does not match its ZIP metadata")
                members[leaf] = member
    except (zipfile.BadZipFile, NotImplementedError, RuntimeError, OSError, EOFError) as error:
        raise CozyClayError("CozyClay ZIP could not be read safely") from error
    if not REQUIRED <= members.keys() or {"clip.mp4", "clip.webm"} <= members.keys():
        _fail("Require first.png, last.png, camera.json, prompt.txt and at most one reference clip")
    first, last = (_png_size(members[name]) for name in ("first.png", "last.png"))
    if first.size != last.size:
        _fail("First and last endpoint dimensions must match")
    camera = _json(members["camera.json"])
    start, end, fps = (camera.get(name) for name in ("startFrame", "endFrame", "fps"))
    if type(start) is not int or type(end) is not int or start < 0 or end < start or fps != 24 or isinstance(fps, bool):
        _fail("Use an inclusive nonnegative frame range at exactly 24fps")
    count = end - start + 1
    if count not in {39, 90, 124} or camera.get("kind") == "still":
        _fail("Current H3 recipes require exactly 39, 90 or 124 source frames; no automatic retiming")
    size = camera.get("size")
    if size is not None and size != {"width": first.width, "height": first.height}:
        _fail("Camera export dimensions disagree with the endpoint images")
    frame_range = camera.get("frameRange")
    if frame_range is not None and frame_range != {"start": start, "end": end}:
        _fail("Camera frame ranges disagree")
    framing = camera.get("framing", {})
    for key in ("start", "end"):
        value = framing.get(key) if isinstance(framing, dict) else None
        if (not isinstance(value, dict) or not isinstance(value.get("pos"), dict)
                or any(not _finite(value["pos"].get(axis)) for axis in ("x", "y", "z"))
                or any(not _finite(value.get(axis)) for axis in ("yaw", "pitch", "fovDeg"))
                or not 0 < value["fovDeg"] < 180):
            _fail("Camera metadata requires finite start/end position, angles and lens")
    start_framing, end_framing = framing["start"], framing["end"]
    differences = [abs(start_framing["pos"][axis] - end_framing["pos"][axis]) for axis in ("x", "y", "z")]
    differences.extend(abs(start_framing[axis] - end_framing[axis]) for axis in ("yaw", "pitch", "fovDeg"))
    if any(value > CAMERA_EPSILON for value in differences):
        _fail("Moving-camera endpoints are outside the current fixed-scene H3 adapter")
    moves = camera.get("cameraMove", {})
    if not isinstance(moves, dict) or any(type(v) is not bool or v for v in moves.values()):
        _fail("Disable all declared camera moves before importing")
    try:
        prompt = members["prompt.txt"].decode("utf-8").strip()
    except UnicodeError as error:
        raise CozyClayError("The source prompt must be UTF-8 text") from error
    if not prompt or "\x00" in prompt or len(prompt + RESTRICTIONS) > 4000:
        _fail("Source prompt must be nonempty and fit the native 4000-character motion limit")
    return {"sha256": digest, "folder": folder, "members": members, "camera": camera,
            "prompt": prompt, "size": first.size, "frames": count,
            "returning": ImageChops.difference(first, last).getbbox() is None}


def inspect_keyframe_pack(data: bytes, *, expected_sha256=None) -> dict:
    """Validate and report without filesystem writes, network access or submission."""
    pack = _read(data, expected_sha256)
    return {"schema_version": 1, "package_sha256": pack["sha256"], "shot_folder": pack["folder"],
            "width": pack["size"][0], "height": pack["size"][1], "frames": pack["frames"],
            "fps": 24, "duration_seconds": pack["frames"] / 24, "returning_endpoints": pack["returning"],
            "camera": pack["camera"], "source_prompt": pack["prompt"],
            "members": {name: {"sha256": sha256(value), "bytes": len(value)} for name, value in pack["members"].items()},
            "requires_fixed_camera_acknowledgement": True,
            "camera_endpoint_component_epsilon": CAMERA_EPSILON,
            "limitations": ["Interior camera keys are absent from native camera.json; fixed-camera acknowledgement is required.",
                            "Reference video, depth and normals are not supplied to this recovered H3 graph."],
            "submitted": False}


def _options(payload, pack):
    if not isinstance(payload, dict):
        _fail("Recipe options must be an object")
    allowed = {"name", "actor", "start_state", "end_state", "seed", "polygon", "feather", "context", "vae_name", "template_id", "motion_direction"}
    if set(payload) - allowed:
        _fail("Unsupported CozyClay recipe option")
    result = dict(payload)
    for key in ("name", "actor", "start_state", "end_state"):
        result[key] = text(result.get(key), key.replace("_", " "), 100)
    seed = result.get("seed")
    if type(seed) is not int or not 0 <= seed <= 2_147_483_647:
        _fail("Choose a whole-number recipe seed from 0 to 2147483647")
    if result.get("vae_name") not in {INT8_VAE, ORIGINAL_VAE}:
        _fail("Choose the recovered FP16 or explicit INT8 video VAE")
    template = result.setdefault("template_id", "action" if pack["returning"] else "transition")
    if template not in {"idle", "action", "transition"}:
        _fail("Choose an idle, action or transition recipe")
    same_state = result["start_state"] == result["end_state"]
    if (template == "transition" and (pack["returning"] or same_state)
            or template != "transition" and (not pack["returning"] or not same_state)):
        _fail("Returning actions need identical endpoint pixels/states; transitions need different endpoints and states")
    points, (width, height) = result.get("polygon"), pack["size"]
    if (not isinstance(points, list) or not 3 <= len(points) <= 256
            or any(not isinstance(p, list) or len(p) != 2 or any(type(v) is not int for v in p)
                   or not 0 <= p[0] < width or not 0 <= p[1] < height for p in points)):
        _fail("Outline the moving region with 3–256 integer image-pixel points")
    area = abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(points, points[1:] + points[:1]))) / 2
    feather, context = result.setdefault("feather", 0), result.setdefault("context", 0.25)
    if area < 16 or type(feather) is not int or not 0 <= feather <= 64 or not _finite(context) or not 0 <= context <= 1:
        _fail("Choose a visible motion region, 0–64px feather and 0–1 context margin")
    direction = result.pop("motion_direction", None)
    if direction is not None:
        direction = text(direction, "H3 motion direction", 1500)
    if "reference" in pack["prompt"].lower() and not direction:
        _fail("This source prompt delegates motion to reference video; supply explicit H3 motion_direction because video conditioning is unsupported")
    lines = [line for line in pack["prompt"].splitlines() if not line.startswith(("CAMERA:", "MOTION:"))]
    if direction:
        lines.append("MOTION: " + direction)
    elif any(line.startswith("MOTION:") for line in pack["prompt"].splitlines()):
        lines.extend(line for line in pack["prompt"].splitlines() if line.startswith("MOTION:"))
    lines.append("CAMERA: fixed throughout; no camera movement or cuts.")
    final_prompt = "\n".join(lines) + RESTRICTIONS
    if len(final_prompt) > 4000:
        _fail("Adapted H3 prompt exceeds the native 4000-character limit")
    result.update({"frames": pack["frames"], "prompt": final_prompt})
    return result


def import_keyframe_pack(studio, data: bytes, payload: dict, *, fixed_camera_acknowledged=False,
                         expected_sha256=None, producer=None) -> dict:
    """Save native immutable assets/recipe; never contact ComfyUI or approve media.

    Provenance is inserted before the native recipe ID and snapshot are hashed.
    The small publication sequence mirrors recipes.save_recipe; preparation,
    crops, masks, motion validation and public records use the native helpers.
    """
    pack = _read(data, expected_sha256)
    if fixed_camera_acknowledged is not True:
        _fail("Acknowledge that the source camera is fixed throughout; package endpoints alone do not prove it")
    options = _options(payload, pack)
    if producer is not None and (not isinstance(producer, dict) or set(producer) != {"version", "commit"}
                                 or not isinstance(producer["version"], str) or len(producer["version"]) > 50
                                 or not isinstance(producer["commit"], str) or not re.fullmatch(r"[0-9a-f]{40}", producer["commit"])):
        _fail("Producer provenance requires a version and exact 40-character commit")
    with studio.lock:
        first = studio.import_scene(pack["members"]["first.png"], "first.png", options["name"][:85] + " — first")
        last = first if pack["returning"] else studio.import_scene(pack["members"]["last.png"], "last.png", options["name"][:85] + " — last")
        options.update({"scene_id": first["id"], "first_scene_id": first["id"], "last_scene_id": last["id"]})
        profile, images, _ = prepare_recipe(studio, options)
        base = f"imports/cozyclay/{pack['sha256']}"
        package_path = f"{base}/source.zip"
        studio.store.write_once(package_path, data)
        member_refs = {}
        for name, member in pack["members"].items():
            relative = f"{base}/{name}"
            studio.store.write_once(relative, member)
            member_refs[name] = {"path": relative, "sha256": sha256(member), "bytes": len(member)}
        profile["source_package"] = {"schema_version": 1, "format": "cozyclay.keyframe-pack",
                                     "package": {"path": package_path, "sha256": pack["sha256"]},
                                     "producer": producer, "shot_folder": pack["folder"], "members": member_refs,
                                     "camera": pack["camera"], "source_prompt": pack["prompt"],
                                     "motion_direction": payload.get("motion_direction"),
                                     "fixed_camera_acknowledged": True, "camera_validation": "endpoints_within_1e-12_and_operator_acknowledgement",
                                     "reference_clip_usage": "retained_for_human_review_only; unsupported_H3_input"}
        for key, image in images.items():
            image_data = png(image)
            digest = sha256(image_data)
            relative = f"recipes/assets/{digest}.png"
            studio.store.write_once(relative, image_data)
            profile[key] = {"id": f"asset.{digest}", "path": relative, "sha256": digest}
        profile["id"] = sha256(canonical_bytes(profile))[:32]
        profile["family_id"] = profile["id"]
        prepare_motion_inputs(studio.store, profile)
        reference = studio.store.save_snapshot(profile)
        refs = studio.setting("motion_profile_refs", [])
        if reference not in refs:
            studio.set_setting("motion_profile_refs", [*refs, reference])
        public = next(row for row in public_profiles(studio) if row["id"] == profile["id"])
    return {"profile": public, "package": inspect_keyframe_pack(data), "submitted": False}


def verify_source_package(studio, profile: dict) -> dict:
    """Verify preserved source bytes against the provenance pinned in a recipe."""
    source = profile.get("source_package", {})
    if source.get("schema_version") != 1 or source.get("format") != "cozyclay.keyframe-pack":
        _fail("Recipe does not pin a supported CozyClay source package")
    package = source["package"]
    studio.store.verify_master({**package, "id": "source." + package["sha256"]})
    data = studio.store.resolve(package["path"]).read_bytes()
    report = inspect_keyframe_pack(data, expected_sha256=package["sha256"])
    for name, reference in source["members"].items():
        studio.store.verify_master({**reference, "id": "source." + reference["sha256"]})
        if report["members"].get(name) != {"sha256": reference["sha256"], "bytes": reference["bytes"]}:
            _fail("Preserved source member provenance disagrees with the package")
    return report


def main(argv=None):
    """Import-only CLI; generation remains a separate explicit native action."""
    import argparse
    import sys
    from pathlib import Path
    from .studio import Studio

    parser = argparse.ArgumentParser(description="Inspect or import a native CozyClay keyframe ZIP as an unsubmitted local H3 recipe.")
    parser.add_argument("pack", type=Path, help="One native CozyClay keyframe ZIP")
    parser.add_argument("--inspect-only", action="store_true", help="Validate/report without creating a store or saving assets")
    parser.add_argument("--store", type=Path, help="Local Last Light Radio store; use a separate experimental directory for trials")
    parser.add_argument("--name", help="Saved motion recipe name")
    parser.add_argument("--actor", help="Moving actor or object label")
    parser.add_argument("--start-state", help="Named entry state")
    parser.add_argument("--end-state", help="Named exit state")
    parser.add_argument("--seed", type=int, help="Generation seed, 0–2147483647")
    parser.add_argument("--vae", choices=("int8", "fp16"), help="Explicit choice of the recovered video VAE")
    region = parser.add_mutually_exclusive_group()
    region.add_argument("--polygon", help="Moving-region pixel points as a JSON array")
    region.add_argument("--polygon-file", type=Path, help="JSON file containing moving-region pixel points")
    parser.add_argument("--feather", type=int, default=0, help="Mask feather in source pixels, 0–64")
    parser.add_argument("--context", type=float, default=0.25, help="Crop context margin, 0–1")
    parser.add_argument("--motion-direction", help="Explicit H3 action text; required when the source prompt relies on reference video")
    parser.add_argument("--fixed-camera", action="store_true", help="Acknowledge that the entire source camera is fixed, including interior keys")
    parser.add_argument("--expected-sha256", help="Refuse if source package differs from the inspected checksum")
    parser.add_argument("--producer-version", help="Optional recorded CozyClay producer version")
    parser.add_argument("--producer-commit", help="Optional recorded exact producer commit")
    args = parser.parse_args(argv)
    try:
        if args.pack.stat().st_size > MAX_ZIP_BYTES:
            _fail("Choose a CozyClay ZIP of at most 64 MB")
        data = args.pack.read_bytes()
        inspection = inspect_keyframe_pack(data, expected_sha256=args.expected_sha256)
        if args.inspect_only:
            result = inspection
        else:
            required = {"store": args.store, "name": args.name, "actor": args.actor, "start-state": args.start_state,
                        "end-state": args.end_state, "seed": args.seed, "vae": args.vae,
                        "polygon or polygon-file": args.polygon if args.polygon is not None else args.polygon_file}
            missing = [name for name, value in required.items() if value is None]
            if missing:
                _fail("Import requires: " + ", ".join(missing))
            if not args.fixed_camera:
                _fail("Import requires --fixed-camera acknowledgement")
            raw_polygon = args.polygon_file.read_text(encoding="utf-8") if args.polygon_file else args.polygon
            payload = {"name": args.name, "actor": args.actor, "start_state": args.start_state,
                       "end_state": args.end_state, "seed": args.seed, "vae_name": INT8_VAE if args.vae == "int8" else ORIGINAL_VAE,
                       "polygon": json.loads(raw_polygon), "feather": args.feather, "context": args.context}
            if args.motion_direction is not None:
                payload["motion_direction"] = args.motion_direction
            _options(payload, _read(data, args.expected_sha256))
            producer = None
            if args.producer_version is not None or args.producer_commit is not None:
                producer = {"version": args.producer_version, "commit": args.producer_commit}
            result = import_keyframe_pack(Studio(args.store), data, payload, fixed_camera_acknowledged=True,
                                          expected_sha256=args.expected_sha256, producer=producer)
        print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
        return 0
    except (ValueError, OSError, KeyError) as error:
        print(json.dumps({"error": str(error), "submitted": False}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
