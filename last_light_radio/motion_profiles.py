"""Restore portable actor-motion presets from the imported library snapshot."""

from __future__ import annotations

import json
from pathlib import Path

from .comfy import ComfyError
from .store import canonical_bytes, sha256

ORIGINAL_VAE = "minimax_h3_video_vae_fp16.safetensors"
INT8_VAE = "minimax_h3_video_vae_int8_convrot.safetensors"


def restore_profiles(studio) -> list[dict]:
    """Use only working-store copies; never reopen or change the source library."""
    pointers = studio.setting("motion_profile_refs", [])
    by_id = {studio.store.read_snapshot(ref)["id"]: ref for ref in pointers}
    for library in studio.setting("legacy_imports", []):
        prefix = f"legacy/{library['id']}"
        records = json.loads(studio.store.resolve(f"{prefix}/database_records.json").read_text())
        assets = {row["id"]: row for row in records["assets"]}
        shots = {row["id"]: row for row in records["shots"]}
        archived = {row["sha256"]: row for row in library["files"]}
        for candidate in records["candidates"]:
            if candidate["status"] != "completed":
                continue
            shot = shots[candidate["shot_id"]]
            if shot["workflow_id"] != "minimax_h3_flf2v_8step_v1":
                continue
            identity = sha256(f"{library['database_sha256']}:shot:{shot['id']}".encode())[:32]
            if identity in by_id and "background" in studio.store.read_snapshot(by_id[identity]):
                continue

            def reference(asset_id):
                asset = assets[asset_id]
                record = archived.get(asset["sha256"])
                if not record:
                    raise ComfyError("MOTION_ASSET_MISSING", "A recovered pose or mask is absent from the working copy")
                ref = {"id": f"asset.{asset['sha256']}", "path": record["path"], "sha256": asset["sha256"]}
                studio.store.verify_master(ref)
                return ref

            first = reference(shot["first_asset_id"])
            last = reference(shot["last_asset_id"])
            background_id = next(row["id"] for row in assets.values()
                                 if row["kind"] == "canonical" and row["scene_id"] == shot["scene_id"])
            metadata = json.loads(candidate["metadata_json"])
            crop = json.loads(candidate["crop_json"])
            first_scene = studio.scene(first["sha256"][:32])
            last_scene = studio.scene(last["sha256"][:32])
            profile = {
                "schema_version": 2,
                "id": identity, "name": shot["role"].replace("_", " ").title(),
                "scene_id": first_scene["id"], "first_scene_id": first_scene["id"],
                "last_scene_id": last_scene["id"],
                "actor": "cat" if shot["role"].startswith("cat_") else "reader", "role": shot["role"],
                "start_state": shot["start_state"], "end_state": shot["end_state"],
                "first": first, "last": last, "background": reference(background_id),
                "mask": reference(candidate["mask_asset_id"]),
                "crop": crop, "frames": int(metadata.get("frame_count", shot["frame_count"])),
                "fps": float(metadata.get("fps", 24)), "seed": candidate["seed"], "prompt": shot["prompt"],
                "reference_candidate_id": sha256(f"{library['database_sha256']}:candidate:{candidate['id']}".encode())[:32],
                "source_library_id": library["id"], "source_shot_id": shot["id"],
                "original_vae_name": ORIGINAL_VAE,
            }
            by_id[identity] = studio.store.save_snapshot(profile)
    if list(by_id.values()) != pointers:
        studio.set_setting("motion_profile_refs", list(by_id.values()))
    return profiles(studio)


def profiles(studio) -> list[dict]:
    return [studio.store.read_snapshot(ref) for ref in studio.setting("motion_profile_refs", [])]


def get_profile(studio, identity: str) -> dict:
    for profile in profiles(studio):
        if profile["id"] == identity:
            for part in ("first", "last", "mask", "background"):
                studio.store.verify_master(profile[part])
            if profile.get("master"):
                studio.store.verify_master(profile["master"])
            for ref in profile.get("source_poses", {}).values():
                studio.store.verify_master(ref)
            return profile
    raise ComfyError("MOTION_PROFILE_MISSING", "Choose a saved motion recipe for this scene")


def public_profiles(studio) -> list[dict]:
    result = []
    for profile in profiles(studio):
        item = {key: value for key, value in profile.items() if key not in {"first", "last", "mask", "background", "master", "source_poses"}}
        for part in ("first", "last", "mask"):
            item[f"{part}_url"] = f"/api/motion/{profile['id']}/{part}"
        result.append(item)
    return result


def profile_media(studio, identity: str, part: str) -> Path:
    if part not in {"first", "last", "mask"}:
        raise ComfyError("MOTION_MEDIA_MISSING", "Unknown motion input")
    profile = get_profile(studio, identity)
    return studio.store.resolve(profile[part]["path"])


def save_job_profile(studio, identity: str, profile: dict):
    pointer = studio.store.save_snapshot(profile, kind="jobs")
    studio.store.write_once(f"records/studio_motion/{identity}.json", canonical_bytes(pointer))


def job_profile(studio, identity: str) -> dict | None:
    file = studio.store.resolve(f"records/studio_motion/{identity}.json")
    return studio.store.read_snapshot(json.loads(file.read_text())) if file.is_file() else None
