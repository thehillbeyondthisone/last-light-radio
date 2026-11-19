"""Persistent local scene, job and review library for the creator interface."""

from __future__ import annotations

import io
import json
import sqlite3
import threading
import warnings
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageOps

from .comfy import ComfyError, inspect_workflow, load_bindings
from .generation import load_request, poll_generation, start_generation, utc_now
from .live import LiveComfyClient
from .media import inspect_webp
from .store import ProjectStore, canonical_bytes, sha256

IMAGE_LIMIT = 20 * 1024 * 1024
ROOT = Path(__file__).resolve().parents[1]
ACTIVE = {"pending", "submitting", "queued", "running", "unknown"}


class StudioError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def text(value, label: str, maximum: int = 2000, required: bool = True) -> str:
    if not isinstance(value, str) or len(value) > maximum or (required and not value.strip()):
        raise StudioError(f"{label} must be {'a nonempty' if required else 'a'} string of at most {maximum} characters")
    return value.strip()


class Studio:
    def __init__(self, root: str | Path, *, client_factory=LiveComfyClient):
        self.store = ProjectStore(root)
        self.database = self.store.resolve("studio.sqlite3")
        self.client_factory = client_factory
        self.lock = threading.RLock()
        self.job_lock = threading.Lock()
        self.pilot_lock = threading.Lock()
        self.stop_event = threading.Event()
        with self.db() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS scenes (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL,
                    master TEXT NOT NULL, width INTEGER, height INTEGER, fixture INTEGER,
                    created TEXT NOT NULL, master_hash TEXT UNIQUE NOT NULL);
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, scene_id TEXT NOT NULL, label TEXT NOT NULL,
                    prompt TEXT NOT NULL, seed INTEGER NOT NULL, status TEXT NOT NULL,
                    error TEXT, created TEXT NOT NULL, request_id TEXT UNIQUE NOT NULL);
                CREATE TABLE IF NOT EXISTS candidates (
                    id TEXT PRIMARY KEY, scene_id TEXT NOT NULL, label TEXT NOT NULL,
                    metadata TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'candidate',
                    version INTEGER NOT NULL DEFAULT 0, created TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS reviews (
                    id INTEGER PRIMARY KEY, candidate_id TEXT NOT NULL, version INTEGER NOT NULL,
                    decision TEXT NOT NULL, notes TEXT NOT NULL, entry_anchor TEXT NOT NULL,
                    exit_anchor TEXT NOT NULL, created TEXT NOT NULL, request_id TEXT UNIQUE NOT NULL,
                    UNIQUE(candidate_id, version));
                CREATE TABLE IF NOT EXISTS settings (name TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS pilots (
                    id TEXT PRIMARY KEY, scene_id TEXT NOT NULL, title TEXT NOT NULL,
                    manifest TEXT NOT NULL, status TEXT NOT NULL, progress REAL NOT NULL DEFAULT 0,
                    error TEXT, created TEXT NOT NULL);
            """)

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.database, timeout=10)
        try:
            db.row_factory = sqlite3.Row
            with db:
                yield db
        finally:
            db.close()

    def setting(self, name: str, default=None):
        with self.db() as db:
            row = db.execute("SELECT value FROM settings WHERE name=?", (name,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_setting(self, name: str, value):
        with self.db() as db:
            db.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (name, json.dumps(value)))

    def worker_url(self) -> str:
        default = None
        config = ROOT / ".local/worker.json"
        if config.is_file():
            default = json.loads(config.read_text()).get("base_url")
        url = self.setting("worker_url", default)
        if not url:
            raise StudioError("Connect your ComfyUI worker before generating a clip")
        return url

    def connect_worker(self, url: str) -> dict:
        url = text(url, "Worker URL", 500)
        client = self.client_factory(url, timeout=8)
        report = client.probe()
        compatibility = inspect_workflow(self.graph(), report.get("object_info")) if report["connected"] else None
        summary = {"connected": report["connected"], "url": client.base_url,
                   "devices": (report.get("system_stats") or {}).get("devices", []),
                   "node_count": len(report.get("node_classes", [])), "checked_at": utc_now(),
                   "workflow_valid": bool(compatibility and compatibility["valid"]),
                   "errors": report["errors"] + (compatibility["errors"] if compatibility else [])}
        from .motion_profiles import ORIGINAL_VAE, INT8_VAE
        definitions = report.get("object_info") or {}
        vae_input = definitions.get("VAELoader", {}).get("input", {}).get("required", {}).get("vae_name", [[]])
        available = vae_input[0] if isinstance(vae_input[0], list) else []
        self.set_setting("production_available_vaes", [name for name in available if name in {ORIGINAL_VAE, INT8_VAE}])
        production_file = ROOT / "workflows/h3/production/workflow_api.json"
        if production_file.is_file() and definitions:
            production_graph = json.loads(production_file.read_text(encoding="utf-8-sig"))
            production_graph["3"]["inputs"]["vae_name"] = self.setting("production_vae_name", ORIGINAL_VAE)
            checked = inspect_workflow(production_graph, definitions)
            summary["production_workflow_valid"] = checked["valid"]
            summary["production_errors"] = checked["errors"]
        self.set_setting("worker_url", client.base_url)
        self.set_setting("worker_report", summary)
        return summary

    @staticmethod
    def graph() -> dict:
        return json.loads((ROOT / "workflows/h3/workflow_api.json").read_text(encoding="utf-8-sig"))

    def import_scene(self, data: bytes, filename: str, title: str, description: str = "", *, fixture=False) -> dict:
        title = text(title, "Scene name", 100)
        description = text(description, "Description", 1000, False)
        if not isinstance(data, bytes) or not data or len(data) > IMAGE_LIMIT:
            raise StudioError("Choose a PNG, JPEG or WebP still smaller than 20 MB")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(data)) as image:
                    width, height = image.size
                    if image.format not in {"PNG", "JPEG", "WEBP"} or getattr(image, "n_frames", 1) != 1:
                        raise StudioError("A scene master must be a single PNG, JPEG or WebP still")
                    if width * height > 40_000_000:
                        raise StudioError("Scene images must be at most 40 megapixels")
                    extension = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}[image.format]
                    image.load()
                    oriented = ImageOps.exif_transpose(image)
                    width, height = oriented.size
                    thumb = oriented.convert("RGB")
                    thumb.thumbnail((600, 420))
        except (OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
            raise StudioError("The selected file could not be decoded as a safe still image") from error
        digest = sha256(data)
        scene_id = digest[:32]
        path = f"masters/{digest}/MASTER{extension}"
        master = {"id": f"asset.{digest}", "path": path, "sha256": digest}
        self.store.write_once(path, data)
        buffer = io.BytesIO()
        thumb.save(buffer, "JPEG", quality=88)
        self.store.write_once(f"masters/{digest}/thumbnail.jpg", buffer.getvalue())
        with self.db() as db:
            db.execute("INSERT OR IGNORE INTO scenes VALUES (?,?,?,?,?,?,?,?,?)",
                       (scene_id, title, description, json.dumps(master), width, height, int(fixture), utc_now(), digest))
        return self.scene(scene_id)

    def scene(self, scene_id: str) -> dict:
        with self.db() as db:
            row = db.execute("SELECT * FROM scenes WHERE id=?", (scene_id,)).fetchone()
        if not row:
            raise StudioError("Scene not found", 404)
        result = dict(row)
        result["master"] = json.loads(result["master"])
        result["fixture"] = bool(result["fixture"])
        result.update({"image_url": f"/api/scenes/{scene_id}/master", "thumbnail_url": f"/api/scenes/{scene_id}/thumbnail"})
        return result

    def scenes(self) -> list[dict]:
        with self.db() as db:
            ids = [row[0] for row in db.execute("SELECT id FROM scenes ORDER BY created DESC")]
        return [self.scene(identity) for identity in ids]

    def register_candidate(self, scene_id: str, label: str, metadata: dict, source: ProjectStore | None = None):
        scene = self.scene(scene_id)
        identity = metadata["local_job_id"]
        if metadata["master"]["sha256"] != scene["master"]["sha256"]:
            raise StudioError("Candidate master does not match this scene", 409)
        with self.db() as db:
            if db.execute("SELECT 1 FROM candidates WHERE id=?", (identity,)).fetchone():
                return
        source = source or self.store
        metadata = json.loads(json.dumps(metadata))
        for name in ("workflow", "history"):
            if name in metadata:
                metadata[name] = self.store.save_snapshot(source.read_snapshot(metadata[name]),
                                                         kind="workflows" if name == "workflow" else "jobs")
        metadata["master"] = scene["master"]
        for index, output in enumerate(metadata["outputs"]):
            data = source.resolve(output["path"]).read_bytes()
            if sha256(data) != output["sha256"]:
                raise StudioError("Candidate checksum failed", 409)
            is_video = output.get("properties", {}).get("container") == "mp4"
            if is_video:
                if len(data) < 12 or data[4:8] != b"ftyp":
                    raise StudioError("Imported clip is not an MP4 file")
                properties = dict(output["properties"])
                if properties.get("frame_count", 0) < 2 or properties.get("effective_fps", 0) <= 0:
                    raise StudioError("Imported video timing is invalid")
                properties.setdefault("duration_seconds", properties["frame_count"] / properties["effective_fps"])
            else:
                properties = inspect_webp(data)
            extension = ".mp4" if is_video else ".webp"
            relative = f"candidates/{identity}/{index:02d}-{output['sha256']}{extension}"
            self.store.write_once(relative, data)
            output["path"] = relative
            output["properties"] = properties
            if index == 0:
                if is_video:
                    from .video_tools import sample_video
                    frames = properties["frame_count"]
                    for key, frame in (("start", 0), ("middle", frames // 2), ("end", frames - 1)):
                        sample = sample_video(self.store.resolve(relative), frame / properties["effective_fps"])
                        with Image.open(io.BytesIO(sample)) as image:
                            properties.update({"width": image.width, "height": image.height})
                        self.store.write_once(f"candidates/{identity}/previews/{key}.png", sample)
                    properties["pixel_decode_verified"] = bool(properties.get("pixel_decode_verified", False))
                    continue
                with Image.open(io.BytesIO(data)) as image:
                    for frame in range(image.n_frames):
                        image.seek(frame)
                        image.load()
                        key = {0: "start", image.n_frames // 2: "middle", image.n_frames - 1: "end"}.get(frame)
                        if key:
                            buffer = io.BytesIO()
                            image.convert("RGB").save(buffer, "PNG")
                            self.store.write_once(f"candidates/{identity}/previews/{key}.png", buffer.getvalue())
                    output["properties"]["pixel_decode_verified"] = True
        self.store.write_once(f"candidates/{identity}/studio_provenance.json", canonical_bytes(metadata))
        with self.db() as db:
            db.execute("INSERT OR IGNORE INTO candidates(id,scene_id,label,metadata,created) VALUES (?,?,?,?,?)",
                       (identity, scene_id, label, json.dumps(metadata), utc_now()))

    def candidate(self, identity: str) -> dict:
        with self.db() as db:
            row = db.execute("SELECT * FROM candidates WHERE id=?", (identity,)).fetchone()
            reviews = [dict(item) for item in db.execute("SELECT * FROM reviews WHERE candidate_id=? ORDER BY version", (identity,))]
        if not row:
            raise StudioError("Candidate not found", 404)
        result = dict(row)
        result["metadata"] = json.loads(result["metadata"])
        result["reviews"] = reviews
        result["media_url"] = f"/api/candidates/{identity}/media"
        if result["metadata"].get("motion", {}).get("raw_preview"):
            result["crop_url"] = f"/api/candidates/{identity}/crop"
        result["frames"] = {key: f"/api/candidates/{identity}/frames/{key}" for key in ("start", "middle", "end")}
        result["can_adjust_area"] = result["metadata"].get("pipeline") in {"actor_motion_v1", "mask_recomposition_v1"} and bool(result["metadata"].get("motion", {}).get("raw_frames"))
        if result["can_adjust_area"]:
            result["source_frames"] = {key: f"/api/candidates/{identity}/source/{key}" for key in ("start", "middle", "end")}
        return result

    def candidates(self) -> list[dict]:
        with self.db() as db:
            ids = [row[0] for row in db.execute("SELECT id FROM candidates ORDER BY created DESC")]
        return [self.candidate(identity) for identity in ids]

    def approved_library(self) -> list[dict]:
        """Only latest approved revisions are eligible; old copies are history."""
        eligible = []
        for candidate in self.candidates():
            if candidate["status"] != "approved":
                continue
            self.store.verify_master(self.scene(candidate["scene_id"])["master"])
            for output in candidate["metadata"]["outputs"]:
                if sha256(self.store.resolve(output["path"]).read_bytes()) != output["sha256"]:
                    raise StudioError("An approved clip changed on disk; library use is blocked", 409)
            eligible.append(candidate)
        return eligible

    def review(self, identity: str, payload: dict) -> dict:
        decision = payload.get("decision")
        if decision not in {"approved", "rejected"}:
            raise StudioError("Choose approve or reject")
        notes = text(payload.get("notes", ""), "Review notes", 2000, decision == "rejected")
        entry = text(payload.get("entry_anchor", ""), "Start anchor", 200, decision == "approved")
        exit_anchor = text(payload.get("exit_anchor", ""), "End anchor", 200, decision == "approved")
        if decision == "approved" and payload.get("visual_checked") is not True:
            raise StudioError("Compare the candidate with the master before approving it")
        version = payload.get("expected_version")
        if type(version) is not int:
            raise StudioError("Review version is required")
        request_id = text(payload.get("request_id"), "Review request ID", 100)
        with self.lock:
            candidate = self.candidate(identity)
            with self.db() as db:
                old = db.execute("SELECT candidate_id FROM reviews WHERE request_id=?", (request_id,)).fetchone()
                if old:
                    if old[0] != identity:
                        raise StudioError("Review request ID belongs to another candidate", 409)
                    return self.candidate(identity)
            if candidate["version"] != version:
                raise StudioError("This candidate was reviewed in another window. Refresh before changing it.", 409)
            scene = self.scene(candidate["scene_id"])
            self.store.verify_master(scene["master"])
            for output in candidate["metadata"]["outputs"]:
                data = self.store.resolve(output["path"]).read_bytes()
                if sha256(data) != output["sha256"]:
                    raise StudioError("Candidate file changed; review is blocked", 409)
                if decision == "approved":
                    if output["properties"].get("container") == "mp4":
                        from .video_tools import verify_video
                        verify_video(self.store.resolve(output["path"]))
                    extension = Path(output["path"]).suffix
                    self.store.write_once(f"approved/{identity}/{output['sha256']}{extension}", data)
            with self.db() as db:
                db.execute("INSERT INTO reviews(candidate_id,version,decision,notes,entry_anchor,exit_anchor,created,request_id) VALUES (?,?,?,?,?,?,?,?)",
                           (identity, version + 1, decision, notes, entry, exit_anchor, utc_now(), request_id))
                db.execute("UPDATE candidates SET status=?,version=? WHERE id=?", (decision, version + 1, identity))
            return self.candidate(identity)

    def submit(self, payload: dict) -> dict:
        scene = self.scene(text(payload.get("scene_id"), "Scene", 100))
        prompt = text(payload.get("prompt"), "Motion direction", 4000)
        label = text(payload.get("label"), "Motion name", 100)
        seed = payload.get("seed")
        if type(seed) is not int or not 0 <= seed <= 2_147_483_647:
            raise StudioError("Seed must be a whole number from 0 to 2147483647")
        request_id = text(payload.get("request_id"), "Generation request ID", 100)
        from .motion_profiles import get_profile, ORIGINAL_VAE, INT8_VAE
        profile = None
        if payload.get("motion_profile_id"):
            profile = get_profile(self, text(payload["motion_profile_id"], "Motion preset", 100))
            if profile["scene_id"] != scene["id"]:
                raise StudioError("This preset belongs to another starting scene", 409)
            vae = text(payload.get("motion_vae_name", profile.get("vae_name", ORIGINAL_VAE)), "Video VAE", 200)
            if vae not in {ORIGINAL_VAE, INT8_VAE}:
                raise StudioError("Choose the recovered FP16 video VAE or the explicit INT8 video variant")
            available = self.setting("production_available_vaes", [])
            if available and vae not in available:
                raise StudioError("The selected video VAE is missing on the worker. Choose an installed VAE or install the original FP16 model.", 409)
            profile = {**profile, "vae_name": vae}
        self.worker_url()
        with self.lock, self.db() as db:
            old = db.execute("SELECT id FROM jobs WHERE request_id=?", (request_id,)).fetchone()
            if old:
                return self.job(old[0])
            identity = uuid4().hex
            if profile:
                from .motion_profiles import save_job_profile
                save_job_profile(self, identity, profile)
            db.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?)",
                       (identity, scene["id"], label, prompt, seed, "pending", None, utc_now(), request_id))
        return self.job(identity)

    def job(self, identity: str) -> dict:
        with self.db() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (identity,)).fetchone()
        if not row:
            raise StudioError("Job not found", 404)
        result = dict(row)
        result["error"] = json.loads(result["error"]) if result["error"] else None
        result["can_resume"] = self.store.resolve(f"records/live_jobs/{identity}/accepted.json").is_file()
        from .motion_profiles import job_profile
        profile = job_profile(self, identity)
        if profile:
            result["motion_profile_id"] = profile["id"]
            result["pipeline"] = "actor_motion_v1"
        from .film_generation import job_details
        result.update(job_details(self, identity))
        from .music_generation import job_details as music_job_details
        result.update(music_job_details(self, identity))
        return result

    def jobs(self) -> list[dict]:
        with self.db() as db:
            ids = [row[0] for row in db.execute("SELECT id FROM jobs ORDER BY created DESC LIMIT 100")]
        return [self.job(identity) for identity in ids]

    def resume(self, identity: str) -> dict:
        job = self.job(identity)
        if not job["can_resume"]:
            raise StudioError("No accepted prompt is recorded. Inspect the worker before submitting another job.", 409)
        if job["status"] == "success":
            return job
        with self.db() as db:
            db.execute("UPDATE jobs SET status='queued',error=NULL WHERE id=?", (identity,))
        return self.job(identity)

    def process_job(self, identity: str):
        from .music_generation import configuration as music_configuration, dispatch as dispatch_music
        if music_configuration(self, identity) is not None:
            dispatch_music(self, identity)
            return
        with self.job_lock:
            job = self.job(identity)
            try:
                from .film_generation import configuration, process_job as process_film_job
                if configuration(self, identity) is not None:
                    process_film_job(self, job)
                    return
                if job["status"] == "pending":
                    with self.db() as db:
                        db.execute("UPDATE jobs SET status='submitting' WHERE id=?", (identity,))
                    scene = self.scene(job["scene_id"])
                    self.store.verify_master(scene["master"])
                    client = self.client_factory(self.worker_url(), timeout=15)
                    from .motion_profiles import job_profile
                    profile = job_profile(self, identity)
                    if profile:
                        from .motion_jobs import start_motion_generation
                        start_motion_generation(self.store, client, profile, job["prompt"], job["seed"], local_job_id=identity)
                    else:
                        start_generation(self.store, client, self.graph(), load_bindings(ROOT / "workflows/h3/bindings.json"),
                                         self.store.resolve(scene["master"]["path"]), job["prompt"], job["seed"], local_job_id=identity)
                    with self.db() as db:
                        db.execute("UPDATE jobs SET status='queued' WHERE id=?", (identity,))
                    return
                request = load_request(self.store, identity)
                client = self.client_factory(request["base_url"], timeout=10)
                if request.get("pipeline") == "actor_motion_v1":
                    from .motion_jobs import poll_motion_generation
                    result = poll_motion_generation(self.store, client, identity)
                else:
                    result = poll_generation(self.store, client, identity)
                if result["status"] == "success":
                    self.register_candidate(job["scene_id"], job["label"], result["candidate"])
                with self.db() as db:
                    db.execute("UPDATE jobs SET status=?,error=? WHERE id=?",
                               (result["status"], json.dumps(result.get("error")) if result.get("error") else None, identity))
            except Exception as error:
                details = error.to_dict() if isinstance(error, ComfyError) else {"code": type(error).__name__, "message": str(error)}
                state = "submission_unknown" if details["code"] in {"SUBMISSION_AMBIGUOUS", "SUBMISSION_UNRESOLVED"} else "failed"
                with self.db() as db:
                    db.execute("UPDATE jobs SET status=?,error=? WHERE id=?", (state, json.dumps(details), identity))

    def worker_loop(self):
        while not self.stop_event.is_set():
            for job in self.jobs():
                if job["status"] in ACTIVE:
                    self.process_job(job["id"])
            self.stop_event.wait(3)

    def bootstrap_example(self):
        """Import the existing technical test, never create GPU work or approve it."""
        image = ROOT / "assets/test_scene/test_still.png"
        if not image.is_file():
            return
        scene = self.import_scene(image.read_bytes(), image.name, "The reading room", "A provisional scene for testing motion and continuity.", fixture=True)
        old_root = ROOT / "runs/h3-test"
        path = old_root / "candidates/0d42247f7f6b4e6da6ed5b034bb35b04/candidate.json"
        if path.is_file():
            self.register_candidate(scene["id"], "Reading idle Ã‚Â· first H3 test", json.loads(path.read_text()), ProjectStore(old_root, create=False))

    def state(self) -> dict:
        worker = self.setting("worker_report", {"connected": False, "url": self.setting("worker_url", ""), "checked_at": None})
        if not worker.get("url"):
            try:
                worker["url"] = self.worker_url()
            except StudioError:
                pass
        graph = self.graph()
        bindings = load_bindings(ROOT / "workflows/h3/bindings.json")
        parameters = {name: graph[binding["node_id"]]["inputs"][binding["input"]] for name, binding in bindings["inputs"].items()}
        imports = [{key: value for key, value in report.items() if key != "files"} for report in self.setting("legacy_imports", [])]
        from .motion_profiles import public_profiles, ORIGINAL_VAE
        from .recipes import TEMPLATES, RESTRICTIONS
        from .motion_starters import STARTERS
        from .pilots import catalog, listing
        from .ambience import catalog as ambience_catalog
        return {"scenes": self.scenes(), "candidates": self.candidates(), "jobs": self.jobs(), "imports": imports,
                "motion_profiles": public_profiles(self),
                "motion_templates": TEMPLATES, "motion_restrictions": RESTRICTIONS,
                "motion_starters": STARTERS,
                "pilot_catalog": catalog(self), "pilots": listing(self), "ambience_catalog": ambience_catalog(self),
                "sequences": [p for p in listing(self, all_kinds=True) if p.get("kind") == "studio_subject_sequence"],
                "production": {"default_vae_name": self.setting("production_vae_name", ORIGINAL_VAE),
                               "original_vae_name": ORIGINAL_VAE,
                               "available_vae_names": self.setting("production_available_vaes", [])},
                "worker": worker, "workflow": {"name": "MiniMax H3", "confirmed": bindings["confirmed"],
                                               "parameters": parameters}}

    def media(self, kind: str, identity: str, part: str) -> tuple[Path, str]:
        if kind == "scenes":
            scene = self.scene(identity)
            self.store.verify_master(scene["master"])
            if part == "master":
                return self.store.resolve(scene["master"]["path"]), "image/" + ("jpeg" if scene["master"]["path"].endswith(".jpg") else Path(scene["master"]["path"]).suffix[1:])
            if part == "thumbnail":
                return self.store.resolve(f"masters/{scene['master_hash']}/thumbnail.jpg"), "image/jpeg"
        elif kind == "candidates":
            candidate = self.candidate(identity)
            output = candidate["metadata"]["outputs"][0]
            data = self.store.resolve(output["path"]).read_bytes()
            if sha256(data) != output["sha256"]:
                raise StudioError("Candidate checksum failed", 409)
            if part == "media":
                return self.store.resolve(output["path"]), "video/mp4" if output["path"].endswith(".mp4") else "image/webp"
            if part == "crop":
                crop = candidate["metadata"].get("motion", {}).get("raw_preview")
                if crop:
                    self.store.verify_master({"id": "raw-preview", **crop})
                    return self.store.resolve(crop["path"]), "video/mp4"
            if part in {"start", "middle", "end"}:
                sample = candidate["metadata"].get("motion", {}).get("lossless_samples", {}).get(part)
                if sample:
                    self.store.verify_master({"id": f"lossless-{part}", **sample})
                    return self.store.resolve(sample["path"]), "image/png"
                return self.store.resolve(f"candidates/{identity}/previews/{part}.png"), "image/png"
        raise StudioError("Media not found", 404)
