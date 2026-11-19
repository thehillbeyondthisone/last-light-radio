"""Creator-authored, immutable actor recipes for the recovered H3 pipeline."""

from __future__ import annotations

import io
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageOps

from .motion_profiles import INT8_VAE, ORIGINAL_VAE, public_profiles
from .store import canonical_bytes, sha256
from .studio import StudioError, text

TEMPLATES = [
    {"id": "idle", "name": "Quiet idle", "description": "A little movement, returning to the same pose.",
     "direction": "Add only a small, natural idle movement to {actor}, then settle back into the starting pose."},
    {"id": "action", "name": "One small action", "description": "Describe one action that returns to rest.",
     "direction": "Animate one restrained action by {actor}, then return to the starting pose. Describe the action here."},
    {"id": "transition", "name": "Change pose", "description": "Move between two supplied poses and named states.",
     "direction": "Have {actor} move naturally from the first supplied pose to the last supplied pose, then settle."},
]
RESTRICTIONS = " Keep the camera locked. Preserve identity, proportions, props, lighting and palette. No new objects, text, camera motion or cuts. Only the selected region may move."


def png(image):
    stream = io.BytesIO()
    image.save(stream, "PNG")
    return stream.getvalue()


def scene_image(studio, scene):
    studio.store.verify_master(scene["master"])
    with Image.open(studio.store.resolve(scene["master"]["path"])) as image:
        return ImageOps.exif_transpose(image).convert("RGB")


def fit_crop(image, transform):
    """Letterbox with replicated edges; never stretch an actor's proportions."""
    left, top, right, bottom = transform["fitted_box"]
    fitted = image.resize((right - left, bottom - top), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (768, 768))
    canvas.paste(fitted, (left, top))
    # Padding is conditioning context only, removed before scene compositing.
    if left:
        canvas.paste(fitted.crop((0, 0, 1, fitted.height)).resize((left, fitted.height)), (0, top))
    if right < 768:
        canvas.paste(fitted.crop((fitted.width - 1, 0, fitted.width, fitted.height)).resize((768 - right, fitted.height)), (right, top))
    if top:
        canvas.paste(canvas.crop((0, top, 768, top + 1)).resize((768, top)), (0, 0))
    if bottom < 768:
        canvas.paste(canvas.crop((0, bottom - 1, 768, bottom)).resize((768, 768 - bottom)), (0, bottom))
    return canvas


def restore_crop(image, transform, size):
    return image.crop(tuple(transform["fitted_box"])).resize(size, Image.Resampling.LANCZOS)


def prepare_recipe(studio, payload):
    """Validate before writes or GPU work; all coordinates use oriented master pixels."""
    scene = studio.scene(text(payload.get("scene_id"), "Scene", 100))
    name = text(payload.get("name"), "Recipe name", 100)
    actor = text(payload.get("actor"), "Actor or region name", 100)
    template_id = payload.get("template_id")
    if template_id not in {row["id"] for row in TEMPLATES}:
        raise StudioError("Choose a motion template")
    start = text(payload.get("start_state"), "Start state", 100)
    end = text(payload.get("end_state"), "End state", 100)
    creative = None
    if payload.get("creative_direction") is not None:
        from .motion_starters import compile_direction
        compiled, creative = compile_direction(actor, payload["creative_direction"])
        prompt = text(payload.get("prompt", compiled), "Motion direction", 4000)
    else:
        prompt = text(payload.get("prompt"), "Motion direction", 4000)
    seed, frames = payload.get("seed"), payload.get("frames")
    if type(seed) is not int or not 0 <= seed <= 2_147_483_647:
        raise StudioError("Seed must be a whole number from 0 to 2147483647")
    if type(frames) is not int or frames not in {39, 90, 124}:
        raise StudioError("Choose 39, 90 or 124 frames for the H3 recipe")
    vae = payload.get("vae_name", studio.setting("production_vae_name", ORIGINAL_VAE))
    if vae not in {ORIGINAL_VAE, INT8_VAE}:
        raise StudioError("Choose the recovered FP16 or explicit INT8 video VAE")
    first_scene = studio.scene(text(payload.get("first_scene_id", scene["id"]), "First pose", 100))
    last_scene = studio.scene(text(payload.get("last_scene_id", first_scene["id"]), "Last pose", 100))
    if template_id != "transition" and (first_scene["id"] != last_scene["id"] or start != end):
        raise StudioError("An idle or returning action needs the same pose and state at both ends")
    if template_id == "transition" and (first_scene["id"] == last_scene["id"] or start == end):
        raise StudioError("A pose change needs a different ending image and named end state")
    background = scene_image(studio, scene)
    first, last = (scene_image(studio, row) for row in (first_scene, last_scene))
    if first.size != background.size or last.size != background.size:
        raise StudioError("Pose images must have the same oriented dimensions and framing as the master")
    width, height = background.size
    points = payload.get("polygon")
    painted = payload.get("mask_base64") is not None
    if not painted and (not isinstance(points, list) or not 3 <= len(points) <= 256):
        raise StudioError("Outline the moving region with 3–256 points")
    for point in ([] if painted else points):
        if not isinstance(point, list) or len(point) != 2 or any(type(v) is not int for v in point):
            raise StudioError("Outline points must be pairs of whole image-pixel coordinates")
        if not 0 <= point[0] < width or not 0 <= point[1] < height:
            raise StudioError("The outline must stay inside the scene")
    area = 16 if painted else abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(points, points[1:] + points[:1]))) / 2
    if area < 16:
        raise StudioError("Outline a visible region of at least 16 square pixels")
    feather, context = payload.get("feather", 8), payload.get("context", 0.25)
    if type(feather) is not int or not 0 <= feather <= 64:
        raise StudioError("Feathering must be 0–64 image pixels")
    if type(context) not in (int, float) or not math.isfinite(context) or not 0 <= context <= 1:
        raise StudioError("Context margin must be between 0 and 1")
    if painted:
        from .motion_masks import decode_mask
        mask = decode_mask(payload["mask_base64"], background.size)
    else:
        mask = Image.new("L", background.size, 0)
        ImageDraw.Draw(mask).polygon([tuple(p) for p in points], fill=255)
    if feather:
        mask = mask.filter(ImageFilter.GaussianBlur(feather))
    bounds = mask.getbbox()
    margin = round(max(bounds[2] - bounds[0], bounds[3] - bounds[1]) * context)
    x, y = max(0, bounds[0] - margin), max(0, bounds[1] - margin)
    right, bottom = min(width, bounds[2] + margin), min(height, bounds[3] + margin)
    crop = {"x": x, "y": y, "width": right - x, "height": bottom - y}
    scale = min(768 / crop["width"], 768 / crop["height"])
    fitted_w = max(1, min(768, round(crop["width"] * scale)))
    fitted_h = max(1, min(768, round(crop["height"] * scale)))
    left, top = (768 - fitted_w) // 2, (768 - fitted_h) // 2
    transform = {"version": 1, "source_box": [x, y, right, bottom], "conditioning_size": [768, 768],
                 "fitted_box": [left, top, left + fitted_w, top + fitted_h],
                 "padding": "edge_replication", "resampling": "lanczos"}
    parent_id = payload.get("parent_id")
    parent = None
    if parent_id:
        from .motion_profiles import get_profile
        parent = get_profile(studio, text(parent_id, "Previous recipe", 100))
        if parent["scene_id"] != scene["id"]:
            raise StudioError("A recipe revision must belong to the same master scene")
    authoring = {"template_id": template_id, "polygon": points, "feather": feather, "context": context}
    if painted:
        authoring = {"template_id": template_id, "geometry": "painted_mask", "feather": feather, "context": context}
    profile = {"schema_version": 3, "origin": "authored", "name": name, "scene_id": scene["id"],
               "first_scene_id": first_scene["id"], "last_scene_id": last_scene["id"], "actor": actor,
               "role": template_id, "start_state": start, "end_state": end, "frames": frames, "fps": 24,
               "seed": seed, "prompt": prompt, "crop": crop, "conditioning_transform": transform,
               "master": scene["master"], "source_poses": {"first": first_scene["master"], "last": last_scene["master"]},
               "authoring": authoring, "hold_policy": "hold_actual_current_frame",
               "original_vae_name": ORIGINAL_VAE,
               "vae_name": vae,
               "workflow_template_sha256": sha256((Path(__file__).resolve().parents[1] / "workflows/h3/production/workflow_api.json").read_bytes()),
               "parent_id": parent_id or None, "revision": parent.get("revision", 1) + 1 if parent else 1}
    images = {"first": first, "last": last, "background": background, "mask": mask}
    if creative:
        profile["creative_direction"] = creative
    return profile, images, parent


def preview_recipe(studio, payload):
    import base64
    profile, images, _ = prepare_recipe(studio, payload)
    crop = profile["conditioning_transform"]["source_box"]
    tint = Image.new("RGB", images["background"].size, "#c4cfc5")
    protected = Image.blend(images["background"], tint, 0.70)
    overlay = Image.composite(images["background"], protected, images["mask"])
    overlay.thumbnail((1200, 900))
    mask_preview = images["mask"].copy()
    mask_preview.thumbnail((900, 900))
    previews = {"overlay": overlay, "mask": mask_preview,
                **{part: fit_crop(images[part].crop(tuple(crop)), profile["conditioning_transform"]) for part in ("first", "last")}}
    return {"crop": profile["crop"], "conditioning_transform": profile["conditioning_transform"],
            "output_size": list(images["background"].size), "hold_policy": profile["hold_policy"],
            "images": {key: "data:image/png;base64," + base64.b64encode(png(image)).decode("ascii") for key, image in previews.items()}}


def save_recipe(studio, payload):
    from .motion_jobs import prepare_motion_inputs
    with studio.lock:
        profile, images, parent = prepare_recipe(studio, payload)
        for key, image in images.items():
            data = png(image)
            digest = sha256(data)
            relative = f"recipes/assets/{digest}.png"
            studio.store.write_once(relative, data)
            profile[key] = {"id": f"asset.{digest}", "path": relative, "sha256": digest}
        profile["id"] = sha256(canonical_bytes(profile))[:32]
        profile["family_id"] = parent.get("family_id", parent["id"]) if parent else profile["id"]
        prepare_motion_inputs(studio.store, profile)
        reference = studio.store.save_snapshot(profile)
        refs = studio.setting("motion_profile_refs", [])
        if reference not in refs:
            studio.set_setting("motion_profile_refs", [*refs, reference])
        return next(item for item in public_profiles(studio) if item["id"] == profile["id"])
