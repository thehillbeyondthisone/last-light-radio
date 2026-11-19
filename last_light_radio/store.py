"""Content-addressed masters and append-only JSON snapshots.

Immutability is enforced by this API and verified on read. Filesystem owners can
still modify files outside the app; a changed checksum is reported as corruption.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any


class StoreError(ValueError):
    """An unsafe path, missing asset, or changed immutable record."""


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                       separators=(",", ":")) + "\n").encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


class ProjectStore:
    """Portable relative paths within a creator-selected project directory."""

    DIRECTORIES = ("masters", "candidates", "approved", "exports", "backups", "records", "manifests")

    def __init__(self, root: str | Path, *, create: bool = True):
        self.root = Path(root).resolve()
        if create:
            self.root.mkdir(parents=True, exist_ok=True)
            for directory in self.DIRECTORIES:
                self.resolve(directory).mkdir(exist_ok=True)
        elif not self.root.is_dir():
            raise StoreError("Project directory does not exist")

    def resolve(self, relative: str | Path) -> Path:
        relative = Path(relative)
        if relative.is_absolute() or ".." in relative.parts or ":" in str(relative):
            raise StoreError("Project paths must be relative and cannot traverse directories")
        path = (self.root / relative).resolve()
        if not path.is_relative_to(self.root):
            raise StoreError("Project path escapes the project directory")
        return path

    def write_once(self, relative: str | Path, data: bytes) -> Path:
        path = self.resolve(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Publish a fully flushed file without clobbering existing data. Windows
        # rename fails if the target exists; POSIX needs a non-replacing link.
        descriptor, temporary_name = tempfile.mkstemp(prefix=".llr-", suffix=".tmp", dir=path.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            if temporary.read_bytes() != data:
                raise StoreError("Staged immutable write failed verification")
            try:
                if os.name == "nt":
                    os.rename(temporary, path)
                else:
                    os.link(temporary, path)
            except FileExistsError:
                if path.read_bytes() != data:
                    raise StoreError(f"Refusing to overwrite immutable record: {relative}") from None
        finally:
            temporary.unlink(missing_ok=True)
        return path

    def write_file_once(self, relative, source, expected_sha256=None):
        path = self.resolve(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix='.llr-', suffix='.tmp', dir=path.parent)
        temporary = Path(name)
        try:
            digest = hashlib.sha256()
            with os.fdopen(descriptor, 'wb') as output, Path(source).open('rb') as incoming:
                for block in iter(lambda: incoming.read(1024*1024), b''):
                    digest.update(block); output.write(block)
                output.flush(); os.fsync(output.fileno())
            actual = digest.hexdigest()
            if (expected_sha256 is not None and actual != expected_sha256) or file_sha256(temporary) != actual:
                raise StoreError('Staged immutable file checksum mismatch')
            try:
                if os.name == 'nt': os.rename(temporary, path)
                else: os.link(temporary, path)
            except FileExistsError:
                if file_sha256(path) != actual:
                    raise StoreError(f'Refusing to overwrite immutable record: {relative}') from None
            return path
        finally:
            temporary.unlink(missing_ok=True)

    def import_master(self, source: str | Path) -> dict:
        source = Path(source)
        if not source.is_file():
            raise StoreError(f"Master image not found: {source}")
        extension = source.suffix.lower()
        if extension not in {".png", ".jpg", ".jpeg", ".webp", ".ppm", ".gif"}:
            raise StoreError("Unsupported master image extension")
        data = source.read_bytes()
        if not data:
            raise StoreError("Master image is empty")
        digest = sha256(data)
        relative = f"masters/{digest}/MASTER{extension}"
        self.write_once(relative, data)
        return {"id": f"asset.{digest}", "path": relative, "sha256": digest}

    def verify_master(self, master: dict) -> None:
        path = self.resolve(master["path"])
        if not path.is_file():
            raise StoreError(f"Missing master: {master['path']}")
        if file_sha256(path) != master["sha256"]:
            raise StoreError(f"Master checksum mismatch: {master['id']}")

    def save_snapshot(self, record: dict, *, kind: str = "projects") -> dict:
        if kind not in {"projects", "jobs", "workflows"}:
            raise StoreError("Unsupported snapshot kind")
        data = canonical_bytes(record)
        digest = sha256(data)
        relative = f"records/{kind}/{digest}.json"
        self.write_once(relative, data)
        return {"sha256": digest, "path": relative}

    def read_snapshot(self, reference: dict) -> dict:
        path = self.resolve(reference["path"])
        data = path.read_bytes()
        if sha256(data) != reference["sha256"]:
            raise StoreError("Snapshot checksum mismatch")
        return json.loads(data)

    def save_manifest(self, manifest: dict, event_log: str, report: str) -> dict:
        data = canonical_bytes(manifest)
        digest = sha256(data)
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise StoreError("Invalid manifest digest")
        self.write_once(f"manifests/{digest}.json", data)
        folder = f"exports/{digest}"
        paths = {
            "manifest": self.write_once(f"{folder}/episode_manifest.json", data),
            "event_log": self.write_once(f"{folder}/event_log.md", event_log.encode("utf-8")),
            "report": self.write_once(f"{folder}/schedule.html", report.encode("utf-8")),
        }
        return {"sha256": digest, **{key: str(value) for key, value in paths.items()}}
