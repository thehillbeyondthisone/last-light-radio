"""Validate creator-painted masks and append spatially compatible revisions."""

import base64
import binascii
import copy
import io

from PIL import Image, ImageChops

from .store import canonical_bytes, sha256
from .studio import StudioError


def decode_mask(encoded, size):
    if not isinstance(encoded, str) or len(encoded) > 28_000_000:
        raise StudioError("Paint a motion area smaller than 20 MB")
    try:
        data = base64.b64decode(encoded, validate=True)
        with Image.open(io.BytesIO(data)) as image:
            if image.format != "PNG" or image.size != size or getattr(image, "n_frames", 1) != 1:
                raise StudioError("The painted area must be a PNG at the scene's exact dimensions")
            image.load()
            mask = image.convert("L")
            if "A" in image.getbands():
                mask = ImageChops.multiply(mask, image.getchannel("A"))
    except (binascii.Error, OSError, ValueError, Image.DecompressionBombError) as error:
        if isinstance(error, StudioError):
            raise
        raise StudioError("The painted area could not be read") from error
    if sum(mask.histogram()[1:]) < 16:
        raise StudioError("Paint a visible moving area before continuing")
    return mask


def save_mask_revision(studio, source_id, encoded):
    from .motion_jobs import prepare_motion_inputs
    from .motion_profiles import public_profiles
    from .recipes import png
    from .recompose import VERSION
    source = studio.candidate(source_id)
    metadata = source["metadata"]
    if metadata.get("pipeline") not in {"actor_motion_v1", VERSION} or not metadata.get("motion", {}).get("raw_frames"):
        raise StudioError("This take has no saved motion frames to adjust. Make an actor take first.")
    profile = copy.deepcopy(metadata["motion"]["profile"])
    inputs = prepare_motion_inputs(studio.store, profile)
    mask = decode_mask(encoded, inputs["background"].size)
    crop = profile["crop"]
    bounds = mask.getbbox()
    if bounds[0] < crop["x"] or bounds[1] < crop["y"] or bounds[2] > crop["x"] + crop["width"] or bounds[3] > crop["y"] + crop["height"]:
        raise StudioError("The adjustment goes beyond the saved motion's frame. Keep it inside the marked boundary, or make a new take with more room.")
    data = png(mask)
    digest = sha256(data)
    if digest == profile["mask"]["sha256"]:
        return next(row for row in public_profiles(studio) if row["id"] == profile["id"])
    path = f"recipes/assets/{digest}.png"
    studio.store.write_once(path, data)
    parent_id = profile["id"]
    profile["mask"] = {"id": f"asset.{digest}", "path": path, "sha256": digest}
    profile.update({"origin": "authored", "parent_id": parent_id, "family_id": profile.get("family_id", parent_id),
                    "revision": profile.get("revision", 1) + 1,
                    "mask_edit": {"version": 1, "source_candidate_id": source_id, "previous_mask_sha256": metadata["motion"]["mask"]["sha256"]}})
    profile["authoring"] = {"template_id": profile.get("authoring", {}).get("template_id", profile["role"]),
                            "geometry": "painted_mask", "feather": 0, "context": profile.get("authoring", {}).get("context", 0.12)}
    profile.pop("id")
    profile["id"] = sha256(canonical_bytes(profile))[:32]
    prepare_motion_inputs(studio.store, profile)
    reference = studio.store.save_snapshot(profile)
    with studio.lock:
        refs = studio.setting("motion_profile_refs", [])
        if reference not in refs:
            studio.set_setting("motion_profile_refs", [*refs, reference])
    return next(row for row in public_profiles(studio) if row["id"] == profile["id"])


def source_sample(studio, identity, part):
    """Show saved generated pixels in scene coordinates before the assembly mask."""
    from .motion_jobs import prepare_motion_inputs
    from .recipes import png, restore_crop
    candidate = studio.candidate(identity)
    motion = candidate["metadata"].get("motion", {})
    raw = motion.get("raw_frames", [])
    positions = {"start": 0, "middle": len(raw) // 2, "end": len(raw) - 1}
    if not raw or part not in positions:
        raise StudioError("This take has no source-frame preview", 404)
    profile = motion["profile"]
    inputs = prepare_motion_inputs(studio.store, profile)
    reference = raw[positions[part]]
    studio.store.verify_master({"id": "source-preview", **reference})
    with Image.open(studio.store.resolve(reference["path"])) as image:
        frame = image.convert("RGB")
    crop = profile["crop"]
    if profile.get("conditioning_transform"):
        frame = restore_crop(frame, profile["conditioning_transform"], (crop["width"], crop["height"]))
    if frame.size != (crop["width"], crop["height"]):
        raise StudioError("The saved source frame has unexpected dimensions")
    picture = inputs["background"].copy()
    picture.paste(frame, (crop["x"], crop["y"]))
    return png(picture)
