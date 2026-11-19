"""Small, portable JSON project contracts for the offline first milestone.

Validation deliberately does not open motion media. The asset store verifies the
immutable master on disk; mock variants are metadata, never production assets.
"""

from __future__ import annotations

import copy
import json
import math
import re
from pathlib import Path, PurePosixPath, PureWindowsPath


class ValidationError(ValueError):
    """A persisted project does not satisfy the first milestone contract."""


def canonical_json(value: object) -> str:
    """Stable UTF-8-ready JSON without wall-clock or machine-specific metadata."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False)


def _fail(path: str, message: str) -> None:
    raise ValidationError(f"{path}: {message}")


def _json(value: object, path: str = "project") -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            _fail(path, "nonfinite numbers are forbidden")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _json(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                _fail(path, "JSON object keys must be strings")
            _json(item, f"{path}.{key}")
        return
    _fail(path, "must contain JSON values only")


def _object(value: object, path: str) -> dict:
    if not isinstance(value, dict):
        _fail(path, "expected an object")
    return value


def _string(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(path, "expected a nonempty string")
    return value


def _integer(value: object, path: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        _fail(path, f"expected an integer >= {minimum} (booleans are not integers)")
    return value


def _weight(value: object, path: str) -> None:
    try:
        valid = type(value) in (int, float) and math.isfinite(value) and value > 0
    except OverflowError:
        valid = False
    if not valid:
        _fail(path, "expected a finite positive weight")


def _list(value: object, path: str) -> list:
    if not isinstance(value, list):
        _fail(path, "expected a list")
    return value


def _strings(value: object, path: str) -> list:
    result = _list(value, path)
    for item in result:
        _string(item, path)
    if len(result) != len(set(result)):
        _fail(path, "duplicate values")
    return result


def _path(value: object, path: str) -> None:
    text = _string(value, path)
    posix, windows = PurePosixPath(text), PureWindowsPath(text)
    if (posix.is_absolute() or windows.drive or windows.is_absolute() or "\\" in text
            or any(part in ("..", ".") for part in text.split("/")) or "" in text.split("/")):
        _fail(path, "expected a normalized relative path using forward slashes")


def _sha(value: object, path: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        _fail(path, "expected a lowercase SHA-256 digest")


def _records(project: dict, key: str) -> dict:
    result = {}
    for index, record in enumerate(_list(project.get(key), key)):
        _object(record, f"{key}[{index}]")
        identity = _string(record.get("id"), f"{key}[{index}].id")
        if identity in result:
            _fail(key, f"duplicate id {identity}")
        result[identity] = record
    return result


def _reference(identity: object, records: dict, path: str) -> None:
    if not isinstance(identity, str) or identity not in records:
        _fail(path, f"unknown reference {identity!r}")


def _state(state: object, entities: dict, path: str) -> dict:
    _object(state, path)
    for identity, properties in state.items():
        _reference(identity, entities, path)
        _object(properties, f"{path}.{identity}")
        for name, value in properties.items():
            _string(name, path)
            if isinstance(value, (dict, list)) or value is None:
                _fail(path, "state properties must be non-null scalar JSON values")
    return state


def _contains(state: dict, required: dict) -> bool:
    return all(entity in state and key in state[entity]
               and type(state[entity][key]) is type(value)
               and state[entity][key] == value
               for entity, props in required.items() for key, value in props.items())


def validate_project(project: dict) -> dict:
    """Validate records/references and return an independent JSON-compatible copy."""
    _json(project)
    _object(project, "project")
    if type(project.get("schema_version")) is not int or project["schema_version"] != 1:
        _fail("schema_version", "only schema version 1 is supported")
    if type(project.get("fixture")) is not bool:
        _fail("fixture", "expected an explicit boolean")
    world = _object(project.get("world"), "world")
    world_id = _string(world.get("id"), "world.id")
    _string(world.get("title"), "world.title")
    revision = _integer(world.get("canon_revision"), "world.canon_revision")
    _object(world.get("facts"), "world.facts")
    locations = _records(project, "locations")
    entities = _records(project, "entities")
    scenes = _records(project, "scenes")
    behaviors = _records(project, "behaviors")
    variants = _records(project, "variants")
    episodes = _records(project, "episodes")
    patches = _records(project, "canon_patches")
    if not locations or not scenes or len(episodes) != 1:
        _fail("project", "this slice requires locations, scenes and exactly one draft episode")
    for collection, records in (("locations", locations), ("entities", entities),
                                ("scenes", scenes), ("episodes", episodes),
                                ("canon_patches", patches)):
        for record in records.values():
            if record.get("world_id") != world_id:
                _fail(f"{collection}.{record['id']}.world_id", "must refer to this world")
    for entity in entities.values():
        _string(entity.get("label"), f"entity.{entity['id']}.label")
        if entity.get("kind") not in ("human", "animal", "object", "environment"):
            _fail(f"entity.{entity['id']}.kind", "unknown entity kind")
        for identity in _strings(entity.get("location_ids"), "entity.location_ids"):
            _reference(identity, locations, "entity.location_ids")
    for location in locations.values():
        _string(location.get("title"), "location.title")
        for identity in _strings(location.get("adjacent_location_ids", []), "location.adjacency"):
            _reference(identity, locations, "location.adjacency")
    master_ids = set()
    for scene in scenes.values():
        _reference(scene.get("location_id"), locations, "scene.location_id")
        master = _object(scene.get("master"), "scene.master")
        master_id = _string(master.get("id"), "scene.master.id")
        if master_id in master_ids:
            _fail("scene.master.id", "master IDs must be unique")
        master_ids.add(master_id)
        _path(master.get("path"), "scene.master.path")
        _sha(master.get("sha256"), "scene.master.sha256")
        for identity in _strings(scene.get("present_entities"), "scene.present_entities"):
            _reference(identity, entities, "scene.present_entities")
            if scene["location_id"] not in entities[identity]["location_ids"]:
                _fail("scene.present_entities", "entity is not affiliated with the scene location")
        _state(scene.get("initial_state"), entities, "scene.initial_state")
        anchors = {}
        for anchor in _list(scene.get("anchors"), "scene.anchors"):
            _object(anchor, "scene.anchor")
            identity = _string(anchor.get("id"), "scene.anchor.id")
            if identity in anchors:
                _fail("scene.anchors", "duplicate anchor id")
            if type(anchor.get("hold_safe")) is not bool:
                _fail("scene.anchor.hold_safe", "must be an explicit boolean")
            anchors[identity] = anchor
        _reference(scene.get("initial_anchor"), anchors, "scene.initial_anchor")
        _strings(scene.get("restrictions", []), "scene.restrictions")
    for behavior in behaviors.values():
        _reference(behavior.get("scene_id"), scenes, "behavior.scene_id")
        _reference(behavior.get("actor_id"), entities, "behavior.actor_id")
        if behavior.get("kind") not in ("idle", "action", "transition", "recovery"):
            _fail("behavior.kind", "unsupported behavior kind")
        _state(behavior.get("preconditions"), entities, "behavior.preconditions")
        _state(behavior.get("state_effects"), entities, "behavior.state_effects")
        _weight(behavior.get("weight"), "behavior.weight")
        for key in ("cooldown_frames", "min_gap_frames", "initial_delay_frames"):
            _integer(behavior.get(key), f"behavior.{key}")
        resources = _strings(behavior.get("resources"), "behavior.resources")
        if "frame.full_scene" not in resources or f"actor.{behavior['actor_id']}" not in resources:
            _fail("behavior.resources", "full-frame and actor locks are required in this slice")
        for window in _list(behavior.get("time_windows"), "behavior.time_windows"):
            _object(window, "behavior.time_window")
            start = _integer(window.get("start_frame"), "window.start_frame")
            end = _integer(window.get("end_frame"), "window.end_frame", 1)
            if end <= start:
                _fail("behavior.time_windows", "window must have positive duration")
    for variant in variants.values():
        _reference(variant.get("behavior_id"), behaviors, "variant.behavior_id")
        behavior = behaviors[variant["behavior_id"]]
        if variant.get("scene_id") != behavior["scene_id"]:
            _fail("variant.scene_id", "must match its behavior scene")
        scene = scenes[variant["scene_id"]]
        if (variant.get("master_id") != scene["master"]["id"]
                or variant.get("master_sha256") != scene["master"]["sha256"]):
            _fail("variant.master", "must match the immutable scene master")
        anchors = {item["id"]: item for item in scene["anchors"]}
        _reference(variant.get("start_anchor"), anchors, "variant.start_anchor")
        _reference(variant.get("end_anchor"), anchors, "variant.end_anchor")
        _state(variant.get("start_state"), entities, "variant.start_state")
        _state(variant.get("end_state"), entities, "variant.end_state")
        if not _contains(variant["start_state"], behavior["preconditions"]):
            _fail("variant.start_state", "must include its behavior preconditions")
        if not _contains(variant["end_state"], behavior["state_effects"]):
            _fail("variant.end_state", "must include its behavior result state")
        _integer(variant.get("fps"), "variant.fps", 1)
        _integer(variant.get("duration_frames"), "variant.duration_frames", 1)
        _weight(variant.get("weight"), "variant.weight")
        if variant.get("status") not in ("candidate", "approved", "rejected", "archived"):
            _fail("variant.status", "unknown review status")
        media = _object(variant.get("media"), "variant.media")
        if media.get("kind") == "mock":
            if not project["fixture"]:
                _fail("variant.media.kind", "mock assets are allowed only in explicit fixtures")
        elif media.get("kind") == "video":
            _path(media.get("path"), "variant.media.path")
            _sha(media.get("sha256"), "variant.media.sha256")
        else:
            _fail("variant.media.kind", "expected mock or video")
        _object(variant.get("provenance"), "variant.provenance")
        if media["kind"] == "mock" and variant["provenance"].get("generator") != "fixture":
            _fail("variant.provenance", "mock provenance must identify the fixture generator")
        if media["kind"] == "video":
            _sha(variant["provenance"].get("workflow_sha256"), "variant.provenance.workflow_sha256")
    for episode in episodes.values():
        if episode.get("status") != "draft":
            _fail("episode.status", "only draft episodes are implemented")
        if type(episode.get("world_revision")) is not int or episode["world_revision"] != revision:
            _fail("episode.world_revision", "must pin this exact canon revision")
        _reference(episode.get("scene_id"), scenes, "episode.scene_id")
        _integer(episode.get("fps"), "episode.fps", 1)
        _integer(episode.get("duration_frames"), "episode.duration_frames", 1)
        _integer(episode.get("seed"), "episode.seed")
        _integer(episode.get("minimum_hold_frames", 0), "episode.minimum_hold_frames")
        _string(episode.get("in_world_time"), "episode.in_world_time")
    for patch in patches.values():
        if patch.get("status") != "draft":
            _fail("canon_patch.status", "canon promotion is not implemented; patches must remain draft")
        if type(patch.get("base_revision")) is not int or patch["base_revision"] != revision:
            _fail("canon_patch.base_revision", "must pin this exact canon revision")
        _reference(patch.get("episode_id"), episodes, "canon_patch.episode_id")
        _list(patch.get("proposed_changes"), "canon_patch.proposed_changes")
    return copy.deepcopy(project)


def load_project(path: str | Path) -> dict:
    """Read a project without silently accepting duplicate JSON properties."""
    def pairs(items: list) -> dict:
        result = {}
        for key, value in items:
            if key in result:
                _fail("project", f"duplicate JSON property {key!r}")
            result[key] = value
        return result

    try:
        with Path(path).open("r", encoding="utf-8-sig") as stream:
            return validate_project(json.load(stream, object_pairs_hook=pairs))
    except json.JSONDecodeError as error:
        raise ValidationError(f"Invalid project JSON: {error}") from error
