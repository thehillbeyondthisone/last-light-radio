"""Persistent subject sequences. Only reviewed, returning, disjoint regions layer."""

from __future__ import annotations

import io
import json
import random

from PIL import Image, ImageChops, ImageDraw

from .generation import utc_now
from .motion_profiles import profiles
from .pilots import FPS, _pose, _root, library
from .pilot_media import prepare_clip
from .store import canonical_bytes, sha256
from .studio import StudioError, text

VERSION = "subject-sequence-v1"


def catalog(studio, scene_id):
    scene, rows, excluded = library(studio, scene_id)
    usable = []
    for row in rows:
        p, c = row["profile"], row["candidate"]
        if (_pose(p, "first") != scene["master_hash"] or _pose(p, "last") != scene["master_hash"]
                or p["start_state"] != p["end_state"]):
            excluded.append({"id": c["id"], "label": c["label"],
                             "reason": "This editor uses returning actions only; pose and location changes are deferred."})
            continue
        usable.append(row)
    return scene, usable, excluded


def state(studio, scene_id):
    scene, rows, excluded = catalog(studio, scene_id)
    saved = studio.setting(f"editor.{scene_id}")
    names = {s["actor"].casefold(): s["actor"] for s in saved["config"]["subjects"]} if saved else {}
    for actor in sorted({p["actor"] for p in profiles(studio) if _root(p) == scene["master_hash"]}
                        | {row["profile"]["actor"] for row in rows}):
        names.setdefault(actor.casefold(), actor)
    actors = sorted(names.values())
    default = {"scene_id": scene_id, "title": f"{scene['title']} · Episode", "fps": FPS,
               "duration_frames": 14400, "seed": 7, "placements": [], "ambience": [],
               "subjects": [{"actor": actor, "mode": "continuous", "seed": 7,
                             "pool": [r["candidate"]["id"] for r in rows
                                      if r["profile"]["actor"].casefold() == actor.casefold() and "idle" in r["profile"]["role"].lower()]}
                            for actor in actors]}
    saved = saved or {"revision": 0, "config": default, "sequence_id": None}
    known_subjects = {subject["actor"].casefold() for subject in saved["config"]["subjects"]}
    added = [subject for subject in default["subjects"] if subject["actor"].casefold() not in known_subjects]
    if added:
        # Profiles can introduce subjects after the sequence was saved. Surface
        # them in setup without changing the persisted revision or old manifest.
        saved = {**saved, "config": {**saved["config"], "subjects": saved["config"]["subjects"] + added}}
    return {**saved, "actors": actors,
            "clips": [{"id": r["candidate"]["id"], "label": r["candidate"]["label"],
                       "actor": names[r["profile"]["actor"].casefold()], "role": r["profile"]["role"],
                       "frames": r["candidate"]["metadata"]["outputs"][0]["properties"]["frame_count"],
                       "state": r["profile"]["start_state"]} for r in rows], "excluded": excluded}


def integer(value, label, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise StudioError(f"{label} must be a whole number from {minimum} to {maximum}")
    return value


def validate_config(studio, payload):
    scene_id = text(payload.get("scene_id"), "Scene", 100)
    scene, rows, excluded = catalog(studio, scene_id)
    by_id = {r["candidate"]["id"]: r for r in rows}
    duration = integer(payload.get("duration_frames", 14400), "Sequence length", 24, 14400)
    seed = integer(payload.get("seed", 7), "Sequence seed", 0, 2147483647)
    subjects, placements = payload.get("subjects"), payload.get("placements")
    if not isinstance(subjects, list) or len(subjects) > 16 or not isinstance(placements, list) or len(placements) > 500:
        raise StudioError("Choose subject settings and at most 500 action placements")
    known = {actor.casefold(): actor for actor in state(studio, scene_id)["actors"]}
    clean, seen = [], set()
    for subject in subjects:
        if not isinstance(subject, dict):
            raise StudioError("Each subject needs its own settings")
        actor = text(subject.get("actor"), "Subject", 100)
        actor = known.get(actor.casefold(), actor)
        pool, mode = subject.get("pool"), subject.get("mode")
        if actor.casefold() not in known or actor in seen or not isinstance(mode, str) or mode not in {"continuous", "spaced", "still"}:
            raise StudioError("Choose distinct known subjects and valid idle pacing")
        if not isinstance(pool, list) or len(pool) > 100 or any(not isinstance(c, str) for c in pool) or len(set(pool)) != len(pool):
            raise StudioError("Choose distinct approved idle takes")
        for identity in pool:
            if identity not in by_id or by_id[identity]["profile"]["actor"].casefold() != actor.casefold():
                raise StudioError("An idle take is unapproved, incompatible or belongs to another subject", 409)
        seen.add(actor)
        clean.append({"actor": actor, "mode": mode, "seed": integer(subject.get("seed", seed), "Idle seed", 0, 2147483647), "pool": pool})
    fixed, ids = [], set()
    for item in placements:
        if not isinstance(item, dict):
            raise StudioError("Each action needs a take and start frame")
        identity = text(item.get("id"), "Placement ID", 100)
        candidate_id = text(item.get("candidate_id"), "Action take", 100)
        if identity in ids or candidate_id not in by_id:
            raise StudioError("A placed take is unapproved, incompatible, missing or duplicated", 409)
        p, c = by_id[candidate_id]["profile"], by_id[candidate_id]["candidate"]
        actor = known[p["actor"].casefold()]
        if actor not in seen or "idle" in p["role"].lower():
            raise StudioError("Place actions on a subject's Motions track; configure idles in Subject setup")
        start = integer(item.get("start_frame"), "Action start frame", 0, duration - 1)
        frames = c["metadata"]["outputs"][0]["properties"]["frame_count"]
        if type(frames) is not int or frames < 1 or start + frames > duration:
            raise StudioError("The complete action take must fit inside this sequence")
        if any(other["actor"] == actor and start < other["end_frame"] and start + frames > other["start_frame"] for other in fixed):
            raise StudioError(f"Two placed actions overlap on {actor}'s Motions track", 409)
        fixed.append({"id": identity, "candidate_id": candidate_id, "actor": actor, "start_frame": start, "end_frame": start + frames})
        ids.add(identity)
    config = {"scene_id": scene_id, "title": text(payload.get("title"), "Sequence title", 100),
           "duration_frames": duration, "fps": FPS, "seed": seed, "subjects": clean,
           "placements": sorted(fixed, key=lambda v: (v["start_frame"], v["actor"], v["id"])), "ambience": payload.get("ambience", [])}
    if "texture" in payload:
        from .texture import settings
        value = settings(payload["texture"])
        if value is not None:
            config["texture"] = value
    if payload.get("audio_tracks"):
        from .audio_tracks import validate_tracks
        config["audio_tracks"] = validate_tracks(studio, payload["audio_tracks"], duration, FPS)
    elif "audio_tracks" in payload and payload["audio_tracks"] != []:
        raise StudioError("Audio tracks must be a list")
    return scene, by_id, excluded, config


def support_mask(studio, profile, size):
    """Already composited video keeps its feather; use binary support, not alpha twice."""
    studio.store.verify_master(profile["mask"])
    with Image.open(studio.store.resolve(profile["mask"]["path"])) as original:
        mask = original.convert("L")
    if mask.size != size:
        raise StudioError("The subject mask does not match the scene dimensions", 409)
    crop = profile["crop"]
    x, y, w, h = (crop[k] for k in ("x", "y", "width", "height"))
    if any(type(v) is not int for v in (x, y, w, h)) or x < 0 or y < 0 or w < 1 or h < 1 or x + w > size[0] or y + h > size[1]:
        raise StudioError("The subject crop is outside the scene", 409)
    boundary = Image.new("L", size)
    ImageDraw.Draw(boundary).rectangle((x, y, x + w - 1, y + h - 1), fill=255)
    mask = ImageChops.multiply(mask, boundary).point(lambda n: 255 if n else 0)
    if not mask.getbbox():
        raise StudioError("The subject mask has no usable pixels", 409)
    refs = []
    for image in (mask, Image.new("RGBA", size, "white")):
        if image.mode == "RGBA":
            image.putalpha(mask)
        buffer = io.BytesIO()
        image.save(buffer, "PNG")
        data = buffer.getvalue()
        ref = {"path": f"exports/subject-masks/{sha256(data)}.png", "sha256": sha256(data)}
        studio.store.write_once(ref["path"], data)
        refs.append(ref)
    return mask, refs[0], refs[1]


def schedule_subject(config, subject, clips, master):
    actor = subject["actor"]
    rng = random.Random(f"{VERSION}:{config['seed']}:{actor}:{subject['seed']}")
    fixed = [p for p in config["placements"] if p["actor"] == actor]
    events, cursor, previous, layer, last = [], 0, master, None, None

    def hold(end, reason):
        nonlocal cursor
        if end > cursor:
            events.append({"kind": "hold", "origin": "hold", "actor": actor, "start_frame": cursor, "end_frame": end,
                           "label": "Hold current pose", "frame_image": previous, "layer_clip_id": layer, "reason": reason})
            cursor = end

    def play(identity, origin, placement_id=None):
        nonlocal cursor, previous, layer, last
        clip = clips[identity]
        events.append({"kind": "clip", "origin": origin, "actor": actor, "start_frame": cursor, "end_frame": cursor + clip["frames"],
                       "variant_id": identity, "layer_clip_id": identity, "label": clip["label"],
                       "entry_image": clip["boundaries"]["entry"], "exit_image": clip["boundaries"]["exit"],
                       "placement_id": placement_id, "reason": "Creator placed action" if origin == "motion" else "Seeded approved idle pool"})
        cursor += clip["frames"]
        previous, layer, last = clip["boundaries"]["exit"], identity, identity

    def fill(end):
        while cursor < end:
            choices = sorted(c for c in subject["pool"] if clips[c]["frames"] <= end - cursor) if subject["mode"] != "still" else []
            if len(choices) > 1:
                choices = [c for c in choices if c != last]
            if not choices:
                hold(end, "Hold selected" if subject["mode"] == "still" else "No complete approved idle fits this gap")
                break
            play(rng.choice(choices), "idle")
            if subject["mode"] == "spaced":
                hold(min(end, cursor + rng.randint(4, 8) * FPS), "Quiet interval between idles")

    for placement in fixed:
        fill(placement["start_frame"])
        play(placement["candidate_id"], "motion", placement["id"])
    fill(config["duration_frames"])
    return {"actor": actor, "events": events}


def plan(studio, payload):
    expected = integer(payload.get("expected_revision"), "Saved sequence revision", 0, 2147483647)
    scene_id = text(payload.get("scene_id"), "Scene", 100)
    if studio.setting(f"editor.{scene_id}", {"revision": 0})["revision"] != expected:
        raise StudioError("This sequence changed in another window. Reopen the saved sequence before editing.", 409)
    scene, rows, excluded, config = validate_config(studio, payload)
    chosen = {c for s in config["subjects"] if s["mode"] != "still" for c in s["pool"]} | {p["candidate_id"] for p in config["placements"]}
    size = (scene["width"], scene["height"])
    names = {s["actor"].casefold(): s["actor"] for s in config["subjects"]}
    clips, supports = {}, {}
    for identity in sorted(chosen):
        c, p = rows[identity]["candidate"], rows[identity]["profile"]
        for key in ("first", "last", "background", "mask"):
            studio.store.verify_master(p[key])
        mask, mask_ref, display_ref = support_mask(studio, p, size)
        actor = names[p["actor"].casefold()]
        supports[actor] = ImageChops.lighter(supports[actor], mask) if actor in supports else mask
        output = c["metadata"]["outputs"][0]
        inspected = prepare_clip(studio.store, output, FPS, size)
        clips[identity] = {"id": identity, "label": c["label"], "actor": actor, "role": p["role"],
                           "approval_version": c["version"], "source_metadata_sha256": sha256(canonical_bytes(c["metadata"])),
                           "output": output, "frames": inspected["frame_count"], "boundaries": inspected["boundaries"],
                           "mask": mask_ref, "display_mask": display_ref, "source_mask": p["mask"],
                           "profile": studio.store.save_snapshot(p)}
    actors = sorted(supports)
    for i, actor in enumerate(actors):
        for other in actors[i + 1:]:
            if ImageChops.multiply(supports[actor], supports[other]).getbbox():
                raise StudioError(f"{actor} and {other} have overlapping motion masks. Adjust their regions before combining these takes.", 409)
    tracks = [schedule_subject(config, s, clips, scene["master"]) for s in config["subjects"]]
    events = []
    for track in tracks:
        for event in track["events"]:
            event["index"] = len(events)
            events.append(event)
    from .ambience import pin
    ambience = pin(studio, scene, list(clips.values()), config["ambience"], config["seed"])
    # Conservative fixed-plume rule: suspend procedural steam during any placed
    # action. The master contains its own plume; removing it would alter canon.
    pauses = [[e["start_frame"], e["end_frame"]] for e in events
              if e["kind"] == "clip" and "idle" not in clips[e["variant_id"]]["role"].lower()]
    manifest = {"schema_version": 1, "kind": "studio_subject_sequence", "renderer_version": VERSION,
                "title": config["title"], "scene_id": scene["id"], "master": scene["master"],
                "width": size[0], "height": size[1], "fps": FPS, "duration_frames": config["duration_frames"],
                "seed": config["seed"], "audio": "none", "tracks": tracks, "events": events, "clips": list(clips.values()),
                "config": config, "ambience": ambience, "steam_pauses": pauses, "excluded": excluded,
                "canon_changes": [], "canon_approved": False, "join_review_required": True,
                "compositing_policy": "disjoint binary support of already feathered approved scene videos"}
    if "texture" in config:
        from .texture import pin as pin_texture
        manifest["texture"] = pin_texture(config["texture"])
    if config.get("audio_tracks"):
        from .audio_tracks import pin as pin_audio
        manifest["audio_tracks"] = pin_audio(studio, config["audio_tracks"])
        manifest["audio"] = "mixed" if any(t["enabled"] for t in config["audio_tracks"]) else "none"
    manifest["manifest_hash"] = sha256(canonical_bytes(manifest))
    identity = manifest["manifest_hash"][:32]
    from .pilots import get, validate_approvals
    with studio.lock, studio.db() as db:
        # Compare-and-swap the revision in the same SQLite write transaction as
        # the new head, including across separate local Studio processes.
        db.execute("BEGIN IMMEDIATE")
        key = f"editor.{scene['id']}"
        previous = db.execute("SELECT value FROM settings WHERE name=?", (key,)).fetchone()
        current = json.loads(previous[0]) if previous else {"revision": 0}
        if current["revision"] != expected:
            raise StudioError("This sequence changed in another window. Reopen the saved sequence before editing.", 409)
        validate_approvals(studio, manifest)
        ref = studio.store.save_snapshot(manifest)
        db.execute("INSERT OR IGNORE INTO pilots(id,scene_id,title,manifest,status,progress,error,created) VALUES(?,?,?,?,?,?,?,?)",
                   (identity, scene["id"], config["title"], json.dumps(ref), "draft", 0, None, utc_now()))
        folder = f"exports/pilots/{identity}"
        studio.store.write_once(f"{folder}/episode_manifest.json", canonical_bytes(manifest))
        lines = [f"# {config['title']}", "", "Draft subject sequence; joins require creator review.", ""]
        lines.extend(f"- {e['start_frame']}–{e['end_frame']} | {e['actor']} | {e['label']} | {e['reason']}" for e in events)
        studio.store.write_once(f"{folder}/event_log.md", ("\n".join(lines) + "\n").encode())
        saved = {"revision": expected + 1, "config": config, "sequence_id": identity}
        studio.store.save_snapshot(saved)
        db.execute("INSERT INTO settings(name,value) VALUES(?,?) ON CONFLICT(name) DO UPDATE SET value=excluded.value",
                   (key, json.dumps(saved)))
    return {**saved, "sequence": get(studio, identity)}


def validate_manifest(studio, manifest):
    from .audio_tracks import validate_pinned
    validate_pinned(studio, manifest.get("audio_tracks", []))
    if manifest.get("renderer_version") != VERSION:
        raise StudioError("The saved subject renderer is unavailable", 409)
    for clip in manifest["clips"]:
        for key in ("mask", "display_mask", "source_mask"):
            studio.store.verify_master({"id": "subject-mask", **clip[key]})
        profile = studio.store.read_snapshot(clip["profile"])
        for key in ("first", "last", "background", "mask"):
            studio.store.verify_master(profile[key])


def mask_media(studio, sequence_id, clip_id):
    from .pilots import get
    manifest = get(studio, sequence_id)["manifest"]
    clip = next((c for c in manifest["clips"] if c["id"] == clip_id), None)
    if manifest.get("kind") != "studio_subject_sequence" or clip is None:
        raise StudioError("Subject mask not found", 404)
    studio.store.verify_master({"id": "display-mask", **clip["display_mask"]})
    return studio.store.resolve(clip["display_mask"]["path"])
