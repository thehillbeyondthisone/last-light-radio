"""Read-only import of the recovered earlier Last Light Radio library.

Primary media, database records and review history are copied. Regenerable raw
frame/chunk/benchmark caches remain at the source and are inventoried, not copied.
"""

import hashlib
import json
import os
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from .generation import utc_now
from .store import canonical_bytes, sha256
from .studio import StudioError


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def archive_file(store, source: Path, relative: str, expected: str | None = None) -> dict:
    target = store.resolve(relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        digest = file_hash(source)
        if file_hash(target) != digest or (expected and digest != expected):
            raise StudioError(f"Archived file checksum mismatch: {source.name}", 409)
        return {"path": relative, "sha256": digest, "bytes": target.stat().st_size}
    descriptor, temporary = tempfile.mkstemp(dir=target.parent, prefix=".import-")
    temporary = Path(temporary)
    digest = hashlib.sha256()
    try:
        with os.fdopen(descriptor, "wb") as output, source.open("rb") as input_stream:
            for chunk in iter(lambda: input_stream.read(1024 * 1024), b""):
                output.write(chunk); digest.update(chunk)
            output.flush(); os.fsync(output.fileno())
        value = digest.hexdigest()
        if expected and expected != value:
            raise StudioError(f"Original asset checksum mismatch: {source.name}", 409)
        if os.name == "nt":
            os.rename(temporary, target)
        else:
            os.link(temporary, target)
        return {"path": relative, "sha256": value, "bytes": target.stat().st_size}
    finally:
        temporary.unlink(missing_ok=True)


def import_library(studio, source_path: str) -> dict:
    source = Path(source_path).resolve()
    database = source / "last_light_radio.db"
    if not database.is_file():
        raise StudioError("This folder does not contain last_light_radio.db")
    if source == studio.store.root or source.is_relative_to(studio.store.root):
        raise StudioError("Choose the earlier library, not the current working store")
    wal = source / "last_light_radio.db-wal"
    if wal.exists() and wal.stat().st_size:
        raise StudioError("The earlier database has pending WAL changes. Close its original application before importing a consistent snapshot.", 409)
    db_hash = file_hash(database)
    library_id = db_hash[:24]
    prior = studio.setting("legacy_imports", [])
    for report in prior:
        if report["id"] == library_id:
            return {**report, "message": "This library snapshot is already imported."}
    prefix = f"legacy/{library_id}"
    manifest = []

    def safe_path(value) -> Path:
        path = Path(value)
        path = (source / path).resolve() if not path.is_absolute() else path.resolve()
        if not path.is_relative_to(source) or not path.is_file():
            raise StudioError(f"Referenced media is missing or outside the selected library: {path.name}", 409)
        return path

    def copy_file(value, expected=None):
        path = safe_path(value)
        relative = f"{prefix}/archive/{path.relative_to(source).as_posix()}"
        record = archive_file(studio.store, path, relative, expected)
        if record not in manifest:
            manifest.append(record)
        return record

    # immutable=1 prevents SQLite from modifying the source's database/sidecars.
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro&immutable=1", uri=True)) as db:
        db.row_factory = sqlite3.Row
        required = {"scenes", "assets", "shots", "candidates", "sequences"}
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        if not required.issubset(tables):
            raise StudioError("This earlier library uses an unsupported schema")
        snapshot = {}
        for name in tables:
            quoted = '"' + name.replace('"', '""') + '"'
            snapshot[name] = [dict(row) for row in db.execute(f"SELECT * FROM {quoted}")]
    studio.store.write_once(f"{prefix}/database_records.json", canonical_bytes(snapshot))
    copy_file(database, db_hash)
    assets = {item["id"]: item for item in snapshot["assets"]}
    old_scenes = {item["id"]: item for item in snapshot["scenes"]}
    shots = {item["id"]: item for item in snapshot["shots"]}
    scene_map = {}
    for asset in assets.values():
        copy_file(asset["path"], asset["sha256"])
        if asset["kind"] in {"canonical", "state", "continuity"}:
            title = old_scenes[asset["scene_id"]]["name"]
            if asset["kind"] != "canonical":
                title += " · " + (asset["state_name"] or asset["role"]).replace("_", " ").title()
            scene = studio.import_scene(safe_path(asset["path"]).read_bytes(), Path(asset["path"]).name,
                                        title, f"Imported from the earlier library. Source role: {asset['role']}.")
            scene_map[asset["id"]] = scene["id"]
    for folder in ("composites", "evidence", "exports"):
        if (source / folder).is_dir():
            for file in (source / folder).glob("*"):
                if file.is_file():
                    copy_file(file)
    for sequence in snapshot["sequences"]:
        if sequence.get("manifest_path"):
            copy_file(sequence["manifest_path"])
    imported = []
    failures = []
    for record in snapshot["candidates"]:
        shot = shots[record["shot_id"]]
        scene_id = scene_map.get(shot["first_asset_id"])
        if not scene_id:
            raise StudioError("A candidate's starting master is missing from the earlier library", 409)
        directory = safe_path(record["directory"]) if Path(record["directory"]).is_file() else Path(record["directory"]).resolve()
        if not directory.is_relative_to(source):
            raise StudioError("Candidate directory escapes the selected library")
        for name in ("workflow.json", "provenance.json", "first.png", "last.png", "preview.mp4"):
            if (directory / name).is_file():
                copy_file(directory / name)
        identity = hashlib.sha256(f"{db_hash}:candidate:{record['id']}".encode()).hexdigest()[:32]
        if record["status"] != "completed" or not record["preview_path"]:
            failures.append(record)
            with studio.db() as db:
                db.execute("INSERT OR IGNORE INTO jobs VALUES (?,?,?,?,?,?,?,?,?)",
                           (identity, scene_id, shot["role"].replace("_", " "), shot["prompt"], record["seed"], "failed",
                            json.dumps({"code": "IMPORTED_FAILED_JOB", "message": "Earlier failed render retained in the library archive"}),
                            record["created_at"], f"legacy:{library_id}:{record['id']}"))
            continue
        metadata = json.loads(record["metadata_json"])
        video = metadata.get("full_scene_composite") or record["preview_path"]
        video_record = copy_file(video)
        workflow_file = directory / "workflow.json"
        workflow = json.loads(workflow_file.read_text(encoding="utf-8-sig")) if workflow_file.is_file() else {}
        workflow_ref = studio.store.save_snapshot(workflow, kind="workflows")
        frames = int(metadata.get("frame_count") or shot["frame_count"])
        fps = float(metadata.get("fps", 24))
        candidate = {"schema_version": 1, "local_job_id": identity, "legacy": True,
                     "legacy_library_id": library_id, "legacy_record": record, "legacy_shot": shot,
                     "master": studio.scene(scene_id)["master"], "prompt_id": record["prompt_id"],
                     "workflow": workflow_ref, "workflow_sha256": sha256(canonical_bytes(workflow)),
                     "parameters": {"seed": record["seed"], "motion_prompt": shot["prompt"], "fps": fps, "frames": frames},
                     "execution": {"runtime_seconds": record["elapsed_seconds"]},
                     "outputs": [{**video_record, "properties": {"container": "mp4", "frame_count": frames,
                                  "duration_seconds": frames / fps, "effective_fps": fps, "metadata_source": "legacy_database"}}]}
        studio.register_candidate(scene_id, shot["role"].replace("_", " ").title(), candidate)
        decision = record["review_decision"]
        if decision in {"approved", "rejected"}:
            with studio.db() as db:
                db.execute("INSERT OR IGNORE INTO reviews(candidate_id,version,decision,notes,entry_anchor,exit_anchor,created,request_id) VALUES (?,?,?,?,?,?,?,?)",
                           (identity, 1, decision, "Imported review: " + record["review_notes"], shot["start_state"], shot["end_state"],
                            record["reviewed_at"] or record["created_at"], f"legacy-review:{library_id}:{record['id']}"))
                db.execute("UPDATE candidates SET status=?,version=1 WHERE id=? AND version=0", (decision, identity))
            if decision == "approved":
                output = studio.candidate(identity)["metadata"]["outputs"][0]
                archive_file(studio.store, studio.store.resolve(output["path"]), f"approved/{identity}/{output['sha256']}.mp4", output["sha256"])
        imported.append(identity)
    if file_hash(database) != db_hash or (wal.exists() and wal.stat().st_size):
        raise StudioError("The original database changed during import. Close its application and retry.", 409)
    report = {"id": library_id, "source": str(source), "database_sha256": db_hash,
              "imported_at": utc_now(), "scene_count": len(scene_map), "candidate_count": len(imported),
              "failed_candidates_retained": len(failures), "sequence_count": len(snapshot["sequences"]),
              "files": manifest, "cache_note": "Raw candidate frames, render chunks and benchmark caches remain at source; primary media, provenance, masks, exports and sequence manifests were copied."}
    studio.store.write_once(f"{prefix}/import_manifest.json", canonical_bytes(report))
    studio.set_setting("legacy_imports", [*prior, report])
    return {**report, "message": f"Imported {len(scene_map)} scenes and {len(imported)} clips; earlier decisions and exports preserved."}
