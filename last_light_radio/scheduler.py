"""Deterministic frame scheduling; no model calls, GPU, file IO, or canon writes."""

from __future__ import annotations

import copy
import hashlib
import math
import random
from decimal import Decimal

from .domain import canonical_json, validate_project


SCHEDULER_VERSION = "0.2.0"


class SchedulingError(ValueError):
    """A safe, exact-duration timeline cannot be made from the supplied library."""


def _matches(state: dict, required: dict) -> bool:
    return all(entity in state and key in state[entity]
               and type(state[entity][key]) is type(value)
               and state[entity][key] == value
               for entity, props in required.items() for key, value in props.items())


def _weighted(items: list, rng: random.Random) -> dict:
    # Normalize first so finite large weights cannot overflow their sum.
    largest = max(item["weight"] for item in items)
    weights = [item["weight"] / largest for item in items]
    threshold = rng.random() * math.fsum(weights)
    for item, weight in zip(items, weights):
        threshold -= weight
        if threshold < 0:
            return item
    return items[-1]


def schedule(project: dict, seed: int = 7, duration_seconds: int | float = 600,
             fps: int = 24) -> dict:
    """Schedule the project's draft episode as one exclusive full-frame lane.

    Clips are never trimmed or retimed. Windows contain the entire clip. Cooldown
    and minimum gap both count from the previous end of the same behavior. Holds
    use the current frame source and require an explicitly hold-safe anchor.
    """
    project = validate_project(project)
    if type(seed) is not int or seed < 0:
        raise SchedulingError("seed must be a nonnegative integer")
    if type(fps) is not int or fps <= 0:
        raise SchedulingError("fps must be a positive integer")
    if (type(duration_seconds) not in (int, float)
            or not math.isfinite(duration_seconds) or duration_seconds <= 0):
        raise SchedulingError("duration_seconds must be finite and positive")
    frames = Decimal(str(duration_seconds)) * fps
    if frames != frames.to_integral_value():
        raise SchedulingError("duration_seconds must be an exact whole number of frames")
    total_frames = int(frames)
    episode = project["episodes"][0]
    if episode["fps"] != fps:
        raise SchedulingError("episode fps must equal scheduler fps; automatic retiming is unsupported")
    scene = next(item for item in project["scenes"] if item["id"] == episode["scene_id"])
    anchors = {item["id"]: item for item in scene["anchors"]}
    behaviors = sorted((item for item in project["behaviors"] if item["scene_id"] == scene["id"]),
                       key=lambda item: item["id"])
    variants = sorted(project["variants"], key=lambda item: item["id"])
    rng = random.Random(seed)
    state = copy.deepcopy(scene["initial_state"])
    anchor = scene["initial_anchor"]
    current_source = {"kind": "master", "master_id": scene["master"]["id"],
                      "path": scene["master"]["path"], "sha256": scene["master"]["sha256"]}
    last_end, last_variant = {}, {}
    picture_ready = 0
    events = []
    frame = 0
    while frame < total_frames:
        eligible = []
        skipped = []
        future_boundaries = {total_frames}
        for behavior in behaviors:
            identity = behavior["id"]
            reasons = []
            if behavior["actor_id"] not in scene["present_entities"]:
                reasons.append("actor_absent")
            if any(entity not in scene["present_entities"] for entity in behavior["preconditions"]):
                reasons.append("required_entity_absent")
            if not _matches(state, behavior["preconditions"]):
                reasons.append("precondition_mismatch")
            ready = (last_end[identity] + max(behavior["cooldown_frames"], behavior["min_gap_frames"])
                     if identity in last_end else behavior["initial_delay_frames"])
            if ready > frame:
                reasons.append("cooldown_or_gap")
                future_boundaries.add(min(ready, total_frames))
            if picture_ready > frame:
                reasons.append("minimum_picture_hold")
                future_boundaries.add(min(picture_ready, total_frames))
            windows = behavior["time_windows"]
            for window in windows:
                if window["start_frame"] > frame:
                    future_boundaries.add(min(window["start_frame"], total_frames))
            if windows and not any(window["start_frame"] <= frame < window["end_frame"]
                                   for window in windows):
                reasons.append("outside_time_window")
            if reasons:
                skipped.extend({"behavior_id": identity, "code": code} for code in reasons)
                continue
            pool = []
            candidates = [item for item in variants if item["behavior_id"] == identity]
            if not candidates:
                skipped.append({"behavior_id": identity, "code": "no_variants"})
            for variant in candidates:
                reasons = []
                if variant["status"] != "approved":
                    reasons.append("variant_not_approved")
                if variant["fps"] != fps:
                    reasons.append("fps_mismatch")
                if variant["start_anchor"] != anchor:
                    reasons.append("visual_anchor_mismatch")
                if not _matches(state, variant["start_state"]):
                    reasons.append("variant_state_mismatch")
                end = frame + variant["duration_frames"]
                if end > total_frames:
                    reasons.append("does_not_fit_remaining_frames")
                if windows and not any(window["start_frame"] <= frame and end <= window["end_frame"]
                                       for window in windows):
                    reasons.append("clip_crosses_time_window")
                if reasons:
                    skipped.extend({"behavior_id": identity, "variant_id": variant["id"], "code": code}
                                   for code in reasons)
                else:
                    pool.append(variant)
            alternate = [item for item in pool if item["id"] != last_variant.get(identity)]
            if alternate and len(alternate) < len(pool):
                skipped.append({"behavior_id": identity, "variant_id": last_variant[identity],
                                "code": "anti_repeat"})
                pool = alternate
            if pool:
                eligible.append({**behavior, "eligible_variants": pool})
        before = copy.deepcopy(state)
        if eligible:
            chosen = _weighted(eligible, rng)
            variant = _weighted(chosen["eligible_variants"], rng)
            end = frame + variant["duration_frames"]
            for entity, properties in variant["end_state"].items():
                state.setdefault(entity, {}).update(properties)
            previous_anchor = anchor
            anchor = variant["end_anchor"]
            current_source = {"kind": "variant_frame", "variant_id": variant["id"],
                              "frame": variant["duration_frames"] - 1,
                              "media": copy.deepcopy(variant["media"])}
            last_end[chosen["id"]] = end
            picture_ready = end + episode.get("minimum_hold_frames", 0)
            repeated = last_variant.get(chosen["id"]) == variant["id"]
            last_variant[chosen["id"]] = variant["id"]
            event = {"kind": "clip", "behavior_id": chosen["id"], "actor_id": chosen["actor_id"],
                     "variant_id": variant["id"], "media": copy.deepcopy(variant["media"]),
                     "resources": sorted(chosen["resources"]), "entry_anchor": previous_anchor,
                     "exit_anchor": anchor, "reason": "seeded_weighted_selection",
                     "anti_repeat_relaxed": repeated,
                     "provenance": copy.deepcopy(variant["provenance"])}
        else:
            if not anchors[anchor]["hold_safe"]:
                raise SchedulingError(f"Cannot hold unsafe anchor {anchor!r} at frame {frame}; "
                                      "supply a compatible approved recovery clip")
            end = min(boundary for boundary in future_boundaries if boundary > frame)
            event = {"kind": "hold", "resources": ["frame.full_scene"],
                     "entry_anchor": anchor, "exit_anchor": anchor,
                     "source": copy.deepcopy(current_source),
                     "reason": "no_eligible_clip_safe_hold"}
            if not skipped:
                skipped.append({"code": "no_behaviors_for_scene"})
        event.update({"index": len(events), "start_frame": frame, "end_frame": end,
                      "lane": "full_frame", "state_before": before,
                      "state_after": copy.deepcopy(state), "skipped": skipped})
        events.append(event)
        frame = end
    pinned_inputs = {"project": project, "seed": seed, "duration_frames": total_frames, "fps": fps,
                     "scheduler_version": SCHEDULER_VERSION}
    manifest = {"schema_version": 1, "scheduler_version": SCHEDULER_VERSION,
                "status": "draft", "fixture": project["fixture"],
                "renderable": False, "media_validation_required": True,
                "world_id": project["world"]["id"],
                "world_revision": episode["world_revision"], "episode_id": episode["id"],
                "in_world_time": episode["in_world_time"], "scene_id": scene["id"],
                "master": copy.deepcopy(scene["master"]), "seed": seed, "fps": fps,
                "duration_frames": total_frames,
                "input_hash": hashlib.sha256(canonical_json(pinned_inputs).encode("utf-8")).hexdigest(),
                "events": events, "final_state": state, "final_anchor": anchor,
                "canon_patches": copy.deepcopy(project["canon_patches"])}
    manifest["manifest_hash"] = hashlib.sha256(canonical_json(manifest).encode("utf-8")).hexdigest()
    return manifest


def _timecode(frame: int, fps: int) -> str:
    seconds, subframe = divmod(frame, fps)
    minutes, second = divmod(seconds, 60)
    hour, minute = divmod(minutes, 60)
    return f"{hour:02d}:{minute:02d}:{second:02d}:{subframe:02d}"


def format_event_log(manifest: dict) -> str:
    """Human-readable deterministic audit with state and eligibility explanations."""
    lines = ["# Last Light Radio — draft event log", "",
             f"Seed: {manifest['seed']} | World: {manifest['world_id']} revision {manifest['world_revision']}",
             f"Timebase: {manifest['fps']} fps | Frames: {manifest['duration_frames']}",
             f"Input SHA-256: {manifest['input_hash']}",
             f"Manifest SHA-256: {manifest['manifest_hash']}", ""]
    if manifest["fixture"]:
        lines += ["**MOCK FIXTURE ONLY: no real media, creator approval, or established canon.**", ""]
    for event in manifest["events"]:
        start = _timecode(event["start_frame"], manifest["fps"])
        end = _timecode(event["end_frame"], manifest["fps"])
        label = event.get("variant_id", "safe hold")
        lines += [f"- {start}–{end}: {label}; {event['reason']}",
                  f"  - Anchor: {event['entry_anchor']} → {event['exit_anchor']}",
                  f"  - Before: {canonical_json(event['state_before'])}",
                  f"  - After: {canonical_json(event['state_after'])}"]
        for skipped in event["skipped"]:
            target = skipped.get("variant_id", skipped.get("behavior_id", "scene"))
            lines.append(f"  - Skipped {target}: {skipped['code']}")
        if event.get("anti_repeat_relaxed"):
            lines.append("  - Anti-repeat relaxed: only the previous variant is currently eligible.")
    return "\n".join(lines) + "\n"
