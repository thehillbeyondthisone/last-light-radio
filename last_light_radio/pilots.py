"""Approved-library bridge, deterministic preview manifests and CPU exports."""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

from PIL import ImageChops, ImageStat

from .generation import utc_now
from .motion_profiles import profiles
from .pilot_media import encode_pilot, inspect_video, prepare_clip, rgb
from .scheduler import format_event_log, schedule
from .store import canonical_bytes, sha256
from .studio import StudioError, text

FPS = 24
POLICIES = {"quiet": {"gap": 18, "idle": 48, "action": 100, "transition": 180},
            "balanced": {"gap": 10, "idle": 35, "action": 75, "transition": 150},
            "active": {"gap": 5, "idle": 22, "action": 55, "transition": 120}}


def _pose(profile, name):
    return profile.get("source_poses", {}).get(name, profile[name])["sha256"]


def _root(profile):
    return profile.get("master", profile["background"])["sha256"]


def library(studio, scene_id):
    scene = studio.scene(scene_id)
    recovered = {p.get("reference_candidate_id"): p for p in profiles(studio) if p.get("reference_candidate_id")}
    usable, excluded = [], []
    for candidate in studio.candidates():
        if candidate["status"] != "approved":
            continue
        metadata = candidate["metadata"]
        profile = metadata.get("motion", {}).get("profile") or recovered.get(candidate["id"])
        if profile is None:
            if candidate["scene_id"] == scene_id:
                excluded.append({"id": candidate["id"], "label": candidate["label"], "reason": "No pinned pose/crop recipe; configure motion states before pilot use."})
            continue
        if _root(profile) != scene["master_hash"]:
            continue
        review = candidate["reviews"][-1] if candidate["reviews"] else None
        reason = None
        if not review or review["decision"] != "approved" or review["entry_anchor"] != profile["start_state"] or review["exit_anchor"] != profile["end_state"]:
            reason = "Review anchors must match this recipe's named start/end states."
        output = metadata["outputs"][0]
        properties = output["properties"]
        if properties.get("container") != "mp4" or properties["effective_fps"] != FPS or (properties["width"], properties["height"]) != (scene["width"], scene["height"]):
            reason = "Pilot clips must be MP4 at 24fps with the original scene dimensions."
        if reason:
            excluded.append({"id": candidate["id"], "label": candidate["label"], "reason": reason})
        else:
            usable.append({"candidate": candidate, "profile": profile})
    # Keep only poses reachable from this master; other approved state plates
    # remain visible as exclusions rather than guessed into a scene.
    reachable = {scene["master_hash"]}
    while True:
        expanded = reachable | {_pose(row["profile"], "last") for row in usable if _pose(row["profile"], "first") in reachable}
        if expanded == reachable:
            break
        reachable = expanded
    result = []
    for row in usable:
        if _pose(row["profile"], "first") in reachable:
            result.append(row)
        else:
            excluded.append({"id": row["candidate"]["id"], "label": row["candidate"]["label"], "reason": "Starting pose is unreachable from this master with approved transitions."})
    return scene, sorted(result, key=lambda row: row["candidate"]["id"]), excluded


def catalog(studio):
    result = []
    for scene in studio.scenes():
        _, rows, excluded = library(studio, scene["id"])
        result.append({"scene_id": scene["id"], "approved_count": len(rows), "excluded": excluded,
                       "clips": [{"id": r["candidate"]["id"], "label": r["candidate"]["label"],
                                  "actor": r["profile"]["actor"], "start_state": r["profile"]["start_state"],
                                  "end_state": r["profile"]["end_state"]} for r in rows]})
    return result


def _project(scene, clips, seed, density, duration_seconds):
    root = scene["master_hash"]
    policy = POLICIES[density]
    anchors = {root, *(clip["first_pose"] for clip in clips), *(clip["last_pose"] for clip in clips)}
    project = {"schema_version": 1, "fixture": False,
               "world": {"id": "studio-pilot", "title": "Local visual pilot", "canon_revision": 0, "facts": {}},
               "locations": [{"id": "local-scene", "world_id": "studio-pilot", "title": scene["title"], "adjacent_location_ids": []}],
               "entities": [{"id": "picture", "world_id": "studio-pilot", "label": "Exclusive scene picture", "kind": "environment", "location_ids": ["local-scene"]}],
               "scenes": [{"id": scene["id"], "world_id": "studio-pilot", "location_id": "local-scene", "master": scene["master"],
                           "present_entities": ["picture"], "initial_state": {"picture": {"pose": root}}, "initial_anchor": f"pose.{root}",
                           "anchors": [{"id": f"pose.{p}", "hold_safe": True} for p in sorted(anchors)], "restrictions": ["exclusive full picture", "hold actual current decoded frame"]}],
               "behaviors": [], "variants": [], "canon_patches": [],
               "episodes": [{"id": "visual-pilot", "world_id": "studio-pilot", "status": "draft", "world_revision": 0,
                             "scene_id": scene["id"], "fps": FPS, "duration_frames": round(duration_seconds * FPS), "seed": seed,
                             "minimum_hold_frames": policy["gap"] * FPS, "in_world_time": "unspecified; no chronology authored"}]}
    groups = {}
    for clip in clips:
        role = clip["role"]
        kind = "transition" if clip["first_pose"] != clip["last_pose"] else "idle" if "idle" in role else "action"
        key = (clip["actor"], kind, clip["first_pose"], clip["last_pose"])
        behavior_id = sha256(canonical_bytes(key))[:24]
        if key not in groups:
            recovery = kind == "transition" and clip["last_pose"] == root
            delay = 0 if recovery else 12 if kind == "idle" else 35 if kind == "action" else 90
            behavior = {"id": behavior_id, "scene_id": scene["id"], "actor_id": "picture", "kind": "recovery" if recovery else kind,
                        "preconditions": {"picture": {"pose": clip["first_pose"]}}, "state_effects": {"picture": {"pose": clip["last_pose"]}},
                        "weight": 0.8 if recovery else 3 if kind == "idle" else 1,
                        "cooldown_frames": 0 if recovery else policy[kind] * FPS, "min_gap_frames": 0,
                        "initial_delay_frames": delay * FPS, "resources": ["frame.full_scene", "actor.picture"], "time_windows": []}
            groups[key] = behavior
            project["behaviors"].append(behavior)
        project["variants"].append({"id": clip["id"], "behavior_id": behavior_id, "scene_id": scene["id"],
                                    "master_id": scene["master"]["id"], "master_sha256": root, "status": "approved", "weight": 1,
                                    "start_anchor": f"pose.{clip['first_pose']}", "end_anchor": f"pose.{clip['last_pose']}",
                                    "start_state": {"picture": {"pose": clip["first_pose"]}}, "end_state": {"picture": {"pose": clip["last_pose"]}},
                                    "fps": FPS, "duration_frames": clip["frames"], "media": {"kind": "video", **clip["output"]},
                                    "provenance": {"workflow_sha256": clip["workflow_sha256"], "approval_version": clip["approval_version"], "actor": clip["actor"]}})
    return project


def plan(studio, payload, *, duration_seconds=600):
    title = text(payload.get("title"), "Pilot title", 100)
    seed = payload.get("seed", 7)
    density = payload.get("density", "quiet")
    if (type(seed) is not int or not 0 <= seed <= 2_147_483_647
            or not isinstance(density, str) or density not in POLICIES):
        raise StudioError("Choose a whole seed and a quiet, balanced or active motion density")
    scene, rows, excluded = library(studio, text(payload.get("scene_id"), "Scene", 100))
    selected = payload.get("candidate_ids")
    if selected is not None:
        if not isinstance(selected, list) or any(not isinstance(v, str) for v in selected) or len(selected) != len(set(selected)):
            raise StudioError("Choose distinct approved clips")
        if set(selected) - {r["candidate"]["id"] for r in rows}:
            raise StudioError("A selected clip is unapproved, incompatible, or no longer available", 409)
        rows = [r for r in rows if r["candidate"]["id"] in selected]
    if not rows:
        raise StudioError("This scene has no compatible approved clips. Approve a motion take first.", 409)
    studio.store.verify_master(scene["master"])
    clips = []
    for row in rows:
        c, p = row["candidate"], row["profile"]
        for part in ("first", "last", "mask", "background"):
            studio.store.verify_master(p[part])
        metadata = c["metadata"]
        if metadata.get("workflow"):
            studio.store.read_snapshot(metadata["workflow"])
        output = metadata["outputs"][0]
        inspected = prepare_clip(studio.store, output, FPS, (scene["width"], scene["height"]))
        clips.append({"id": c["id"], "label": c["label"], "approval_version": c["version"], "review": c["reviews"][-1],
                      "actor": p["actor"], "role": p["role"], "first_pose": _pose(p, "first"), "last_pose": _pose(p, "last"),
                      "start_state": p["start_state"], "end_state": p["end_state"], "frames": inspected["frame_count"],
                      "output": output, "boundaries": inspected["boundaries"], "inspection": inspected,
                      "mask": p["mask"], "workflow_sha256": metadata["workflow_sha256"],
                      "source_scene_id": c["scene_id"], "source_metadata_sha256": sha256(canonical_bytes(metadata))})
    project = _project(scene, clips, seed, density, duration_seconds)
    scheduled = schedule(project, seed, duration_seconds, FPS)
    by_id = {clip["id"]: clip for clip in clips}
    events, previous, joins = [], scene["master"], []
    for original in scheduled["events"]:
        event = {key: original[key] for key in ("kind", "start_frame", "end_frame", "entry_anchor", "exit_anchor", "reason")}
        event["source_schedule_indices"] = [original["index"]]
        if original["kind"] == "clip":
            clip = by_id[original["variant_id"]]
            event.update({"variant_id": clip["id"], "label": clip["label"], "actor": clip["actor"],
                          "entry_image": clip["boundaries"]["entry"], "exit_image": clip["boundaries"]["exit"],
                          "start_state": clip["start_state"], "end_state": clip["end_state"]})
            before, after = rgb(studio.store, previous), rgb(studio.store, event["entry_image"])
            delta = ImageChops.difference(before, after)
            joins.append({"at_frame": event["start_frame"], "candidate_id": clip["id"],
                          "whole_frame_mean_absolute_rgb_0_255": sum(ImageStat.Stat(delta).mean) / 3,
                          "exact_rgb_match": delta.getbbox() is None,
                          "source": previous, "target": event["entry_image"]})
            previous = event["exit_image"]
        else:
            event.update({"label": "Static hold", "frame_image": previous, "source": original["source"]})
            if events and events[-1]["kind"] == "hold" and events[-1]["frame_image"] == previous:
                events[-1]["end_frame"] = event["end_frame"]
                events[-1]["source_schedule_indices"].extend(event["source_schedule_indices"])
                continue
        event["index"] = len(events)
        events.append(event)
    if not any(e["kind"] == "clip" for e in events):
        raise StudioError("No approved clip is reachable from this master within the pilot", 409)
    manifest = {"schema_version": 1, "kind": "studio_visual_pilot", "status": "draft", "renderable": True,
                "title": title, "scene_id": scene["id"], "master": scene["master"], "seed": seed, "density": density,
                "fps": FPS, "duration_frames": scheduled["duration_frames"], "width": scene["width"], "height": scene["height"],
                "audio": "none", "hold_policy": "actual_current_decoded_frame", "exclusive_full_picture": True,
                "canon_approved": False, "world_revision": None, "canon_changes": [], "clips": clips, "events": events,
                "joins": joins, "join_review_required": True, "excluded": excluded,
                "project": studio.store.save_snapshot(project), "schedule": studio.store.save_snapshot(scheduled),
                "scheduler_version": scheduled["scheduler_version"], "input_hash": scheduled["input_hash"]}
    from .ambience import pin
    ambience = pin(studio, scene, clips, payload.get("ambience"), seed)
    if ambience:
        manifest["ambience"] = ambience
    manifest["manifest_hash"] = sha256(canonical_bytes(manifest))
    identity = manifest["manifest_hash"][:32]
    reference = studio.store.save_snapshot(manifest)
    with studio.lock, studio.db() as db:
        validate_approvals(studio, manifest)
        db.execute("INSERT OR IGNORE INTO pilots(id,scene_id,title,manifest,status,progress,error,created) VALUES(?,?,?,?,?,?,?,?)",
                   (identity, scene["id"], title, json.dumps(reference), "draft", 0, None, utc_now()))
    folder = f"exports/pilots/{identity}"
    studio.store.write_once(f"{folder}/episode_manifest.json", canonical_bytes(manifest))
    studio.store.write_once(f"{folder}/event_log.md", format_event_log(scheduled).encode())
    return get(studio, identity)


def validate_approvals(studio, manifest):
    from .ambience import validate
    validate(studio.store, manifest.get("ambience"))
    if manifest.get("kind") == "studio_subject_sequence":
        from .editor import validate_manifest
        validate_manifest(studio, manifest)
    studio.store.verify_master(manifest["master"])
    for clip in manifest["clips"]:
        current = studio.candidate(clip["id"])
        if current["status"] != "approved" or current["version"] != clip["approval_version"] or sha256(canonical_bytes(current["metadata"])) != clip["source_metadata_sha256"]:
            raise StudioError(f"Approval changed for {clip['label']}; rebuild the timeline before export", 409)
        studio.store.verify_master({"id": clip["id"], **clip["output"]})


def get(studio, identity):
    if not isinstance(identity, str) or not re.fullmatch(r"[0-9a-f]{32}", identity):
        raise StudioError("Pilot not found", 404)
    with studio.db() as db:
        row = db.execute("SELECT * FROM pilots WHERE id=?", (identity,)).fetchone()
    if row is None:
        raise StudioError("Pilot not found", 404)
    result = dict(row)
    result["manifest"] = studio.store.read_snapshot(json.loads(result["manifest"]))
    result["kind"] = result["manifest"].get("kind", "studio_visual_pilot")
    result["error"] = json.loads(result["error"]) if result["error"] else None
    result["approval_current"] = all((lambda c: c["status"] == "approved" and c["version"] == clip["approval_version"])(studio.candidate(clip["id"])) for clip in result["manifest"]["clips"])
    result["media_url"] = f"/api/pilots/{identity}/media" if result["status"] == "complete" else None
    result["manifest_url"] = f"/api/pilots/{identity}/manifest"
    result["log_url"] = f"/api/pilots/{identity}/log"
    return result


def listing(studio, *, all_kinds=False):
    with studio.db() as db:
        ids = [row[0] for row in db.execute("SELECT id FROM pilots ORDER BY created DESC")]
    records = [get(studio, identity) for identity in ids]
    return [{key: value for key, value in record.items() if key != "manifest"} for record in records
            if all_kinds or record["kind"] != "studio_subject_sequence"]


def queue_export(studio, identity):
    pilot = get(studio, identity)
    validate_approvals(studio, pilot["manifest"])
    if pilot["status"] not in {"complete", "queued", "exporting"}:
        with studio.db() as db:
            db.execute("UPDATE pilots SET status='queued',progress=0,error=NULL WHERE id=?", (identity,))
    return get(studio, identity)


def process_export(studio, identity):
    with studio.pilot_lock:
        pilot = get(studio, identity)
        if pilot["status"] != "queued":
            return
        manifest = pilot["manifest"]
        folder = f"exports/pilots/{identity}"
        def progress(value):
            with studio.db() as db:
                db.execute("UPDATE pilots SET progress=? WHERE id=?", (value, identity))
        try:
            validate_approvals(studio, manifest)
            published_report = studio.store.resolve(f"{folder}/export_report.json")
            published_video = studio.store.resolve(f"{folder}/pilot.mp4")
            if published_report.is_file() and published_video.is_file():
                saved = json.loads(published_report.read_text())
                if saved["manifest_hash"] != manifest["manifest_hash"] or sha256(published_video.read_bytes()) != saved["sha256"]:
                    raise ValueError("An existing export failed verification; the original file is preserved")
                with studio.db() as db:
                    db.execute("UPDATE pilots SET status='complete',progress=1,error=NULL WHERE id=?", (identity,))
                return
            with studio.db() as db:
                db.execute("UPDATE pilots SET status='exporting' WHERE id=?", (identity,))
            with tempfile.TemporaryDirectory(prefix="pilot-render-", dir=studio.store.root) as temporary:
                staged = Path(temporary) / "pilot.mp4"
                if manifest.get("kind") == "studio_subject_sequence":
                    from .subject_media import encode_subjects
                    report = encode_subjects(studio.store, manifest, staged, studio.stop_event, progress)
                else:
                    report = encode_pilot(studio.store, manifest, staged, studio.stop_event, progress)
                progress(0.92)
                encoded_size = (manifest["width"] + manifest["width"] % 2, manifest["height"] + manifest["height"] % 2)
                report["inspection"] = inspect_video(staged, manifest["duration_frames"], FPS, encoded_size)
                data = staged.read_bytes()
                report.update({"manifest_hash": manifest["manifest_hash"], "sha256": sha256(data), "bytes": len(data)})
                with studio.lock:
                    validate_approvals(studio, manifest)
                    studio.store.write_once(f"{folder}/export_report.json", canonical_bytes(report))
                    studio.store.write_once(f"{folder}/pilot.mp4", data)
                    with studio.db() as db:
                        db.execute("UPDATE pilots SET status='complete',progress=1,error=NULL WHERE id=?", (identity,))
        except Exception as error:
            state = "interrupted" if isinstance(error, InterruptedError) else "failed"
            with studio.db() as db:
                db.execute("UPDATE pilots SET status=?,error=? WHERE id=?", (state, json.dumps({"message": str(error)}), identity))


def worker_loop(studio):
    with studio.db() as db:
        db.execute("UPDATE pilots SET status='interrupted',error=? WHERE status='exporting'", (json.dumps({"message": "Studio restarted during export. Retry the same pinned timeline."}),))
    while not studio.stop_event.is_set():
        for pilot in listing(studio, all_kinds=True):
            if pilot["status"] == "queued":
                process_export(studio, pilot["id"])
        studio.stop_event.wait(2)


def media(studio, identity, part, index=None):
    pilot = get(studio, identity)
    folder = f"exports/pilots/{identity}"
    if part in {"entry", "exit", "hold"} and index is not None:
        events = pilot["manifest"]["events"]
        if not 0 <= index < len(events):
            raise StudioError("Timeline frame not found", 404)
        event = events[index]
        key = "frame_image" if part == "hold" else f"{part}_image"
        if key not in event:
            raise StudioError("Timeline frame not found", 404)
        reference = event[key]
        studio.store.verify_master({"id": "preview-frame", **reference})
        import mimetypes
        return studio.store.resolve(reference["path"]), mimetypes.guess_type(reference["path"])[0] or "image/png"
    if part == "manifest":
        return studio.store.resolve(f"{folder}/episode_manifest.json"), "application/json"
    if part == "log":
        return studio.store.resolve(f"{folder}/event_log.md"), "text/markdown"
    if part == "media" and pilot["status"] == "complete":
        report = json.loads(studio.store.resolve(f"{folder}/export_report.json").read_text())
        ref = {"id": "pilot-export", "path": f"{folder}/pilot.mp4", "sha256": report["sha256"]}
        studio.store.verify_master(ref)
        return studio.store.resolve(ref["path"]), "video/mp4"
    raise StudioError("Pilot media is not available", 404)


def ambience_media(studio, identity, kind):
    recipe = get(studio, identity)["manifest"].get("ambience")
    layer = next((layer for layer in recipe["layers"] if layer["kind"] == kind), None) if recipe else None
    if layer is None:
        raise StudioError("Ambience mask is not part of this pilot", 404)
    studio.store.verify_master({"id": "ambience-mask", **layer["mask"]})
    return studio.store.resolve(layer["mask"]["path"])
