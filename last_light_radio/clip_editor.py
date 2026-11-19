"""The separate LAN editor, backed by the existing Film media and job lifecycle."""

import sqlite3
import threading
from contextlib import closing, contextmanager
from ipaddress import IPv4Address, IPv4Network
from urllib.parse import urlencode

from . import film, film_generation, film_images, h3_joint_av_recipe
from .comfy import ComfyClient
from .server import make_server
from .studio import ROOT, Studio, StudioError, text


PRIVATE_NETWORKS = tuple(IPv4Network(block) for block in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))
ACTIVE_EXPORTS = {"queued", "exporting"}


def current_sequence(studio):
    with studio.lock:
        identity = studio.setting("clip_editor.sequence")
        if identity:
            return film.sequence(studio, identity)
        # Reuse a project/sequence if startup stopped before saving the pointer.
        projects = film._records(studio, "film.project.")
        project = film.project(studio, projects[0]["id"]) if projects else film.create_project(studio, {"title": "Clip Editor"})
        sequence = next(iter(project["sequences"]), None) or film.create_sequence(studio, project["id"], {"title": "My sequence"})
        studio.set_setting("clip_editor.sequence", sequence["id"])
        return sequence


def imported_clip(studio, identity):
    asset = film.asset(studio, identity)
    provenance = asset["provenance"]
    job_id = provenance.get("local_job_id")
    imported = studio.setting(f"film.generation.import.{job_id}", {})
    if imported.get("video_asset_id") != identity or not imported.get("audio_asset_id"):
        raise StudioError("Wait for this clip and its sound to finish importing", 409)
    return asset, imported["audio_asset_id"]


def snapshot(studio):
    sequence = current_sequence(studio)
    generation = film_generation.state(studio)
    clips = []
    for record in film._records(studio, "film.asset."):
        try:
            asset, _ = imported_clip(studio, record["id"])
        except StudioError:
            continue
        provenance = asset["provenance"]
        ref = (provenance.get("references") or provenance.get("generation_metadata", {}).get("references", {})).get("first_frame", {})
        clips.append({
            "id": asset["id"], "label": asset["label"], "frames": asset["frame_count"],
            "media_url": asset["media_url"], "image_id": ref.get("id"),
            "created": asset["created"],
        })
    export = dict(sequence["export"])
    if export["status"] == "complete":
        export["media_url"] = "/api/clips/sequence/media?" + urlencode({"revision": sequence["revision"]})
    return {
        "sequence": {
            "revision": sequence["revision"], "shots": sequence["shots"],
            "duration_frames": sequence["duration_frames"], "export": export,
        },
        "clips": sorted(clips, key=lambda item: item["created"], reverse=True),
        "jobs": [
            {key: job.get(key) for key in ("id", "label", "status", "error", "import_error", "video_asset_id", "can_resume")}
            for job in generation["jobs"]
        ],
        "recipe": generation["recipe"],
        "worker_configured": bool(generation["worker_url"]),
        **film_images.listing(studio),
    }


def save_cut(studio, payload):
    sequence = current_sequence(studio)
    entries = payload.get("shots")
    if not isinstance(entries, list) or len(entries) > 64:
        raise StudioError("The sequence supports up to 64 clips")
    shots, audio = [], []
    start = 0
    for entry in entries:
        if not isinstance(entry, dict):
            raise StudioError("Choose a generated clip")
        identity = text(entry.get("id"), "Placement ID", 80)
        asset, audio_id = imported_clip(studio, entry.get("asset_id"))
        duration = asset["frame_count"]
        shots.append({"id": identity, "asset_id": asset["id"], "duration_frames": duration})
        audio.append({"id": identity, "asset_id": audio_id, "role": "production",
                      "start_frame": start, "duration_frames": duration})
        start += duration
    film.save_sequence(studio, sequence["id"], {
        "expected_revision": payload.get("expected_revision"), "title": sequence["title"],
        "shots": shots, "audio_tracks": audio,
    }, allow_empty=True)


def generation_params(studio, payload):
    return {
        "recipe_id": h3_joint_av_recipe.RECIPE_ID, "worker_url": studio.worker_url(),
        "first_frame_id": text(payload.get("first_frame_id"), "Starting image", 100),
        "brief": payload.get("brief"), "seed": payload.get("seed"),
        "length_frames": h3_joint_av_recipe.frames(payload.get("length_frames")),
    }


def dispatch(handler, studio, parts, payload):
    route = parts[1:] if parts[:1] == ["api"] else []
    if payload is None:
        if route == ["clips"]:
            return handler.send_json(snapshot(studio))
        if route == ["clips", "sequence", "media"]:
            path, kind = film.export_media(studio, current_sequence(studio)["id"], "media")
            return handler.send_file(path, kind)
        if len(route) == 4 and route[0] == "film" and route[3] == "media":
            if route[1] == "images":
                image = film_images.verify(studio, route[2])
                return handler.send_file(studio.store.resolve(image["png"]["path"]), "image/png")
            if route[1] == "assets":
                imported_clip(studio, route[2])
                return handler.send_file(film.asset_media(studio, route[2]), "video/mp4")
    else:
        if route == ["clips", "images"]:
            provenance = {"kind": "clip_editor_upload"}
            if payload.get("converted_from_heif") is True:
                provenance["client_conversion"] = "HEIF to JPEG"
            return handler.send_json(film_images.import_image(studio, {
                **payload, "provenance": provenance,
            }, clip_upload=True), 201)
        if route == ["clips", "frames"]:
            imported_clip(studio, payload.get("video_asset_id"))
            return handler.send_json(film_images.from_frame(studio, payload), 201)
        if route == ["clips", "preflight"]:
            check = film_generation.preflight(studio, generation_params(studio, payload))
            check["warnings"] = [w for w in check["warnings"] if w.get("code") != "REFERENCE_UPLOAD_ON_GENERATE"]
            return handler.send_json(check)
        if route == ["clips", "generate"]:
            params = generation_params(studio, payload)
            job = film_generation.submit(studio, {
                **params, "label": text(params["brief"], "Motion prompt", 4000)[:80],
                "preflight_id": payload.get("preflight_id"), "request_id": payload.get("request_id"),
            })
            return handler.send_json(job, 202)
        if len(route) == 4 and route[:2] == ["clips", "jobs"]:
            if route[3] == "resume":
                return handler.send_json(film_generation.resume(studio, route[2]))
            if route[3] == "import":
                return handler.send_json(film_generation.import_completed(studio, route[2]), 201)
        if route == ["clips", "sequence"]:
            save_cut(studio, payload)
            return handler.send_json(snapshot(studio))
        if route == ["clips", "sequence", "export"]:
            seq = current_sequence(studio)
            if not seq["shots"]:
                raise StudioError("Add a clip to the sequence first")
            film.queue_export(studio, seq["id"], payload)
            return handler.send_json(snapshot(studio), 202)
    raise StudioError("Clip Editor route not found", 404)


def make_clip_server(studio, host, port):
    address = IPv4Address(host)
    if host != "127.0.0.1" and not any(address in network for network in PRIVATE_NETWORKS):
        raise StudioError("Use 127.0.0.1 or this computer's private IPv4 address")
    # A cut export's worker lives in this process, so an interrupted export must be requeued.
    sequence = current_sequence(studio)
    if sequence["export"]["status"] in ACTIVE_EXPORTS:
        with studio.db() as db:
            film._write(db, "film.sequence." + sequence["id"], {
                **sequence, "export": {"status": "interrupted", "error": "The editor closed during export. Export again to continue."},
            })
    return make_server(studio, port, host=host, static_root=ROOT / "frontend/clip-editor", api_router=dispatch)


@contextmanager
def claim_library(root):
    # The shared job worker must have only one owner even when separate ports are requested.
    root.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(root / "listener.sqlite3", timeout=0)) as lock:
        try:
            lock.execute("BEGIN EXCLUSIVE")
        except sqlite3.OperationalError as error:
            if error.sqlite_errorcode == sqlite3.SQLITE_BUSY:
                raise StudioError("Clip Editor is already running. Use the address in its launcher window.") from None
            raise
        yield


def serve(host="127.0.0.1", port=8772, worker_url=None):
    root = ROOT / ".local/clip-editor"
    with claim_library(root):
        serve_library(Studio(root), host, port, worker_url)


def serve_library(studio, host, port, worker_url):
    if worker_url:
        studio.set_setting("worker_url", ComfyClient(worker_url).base_url)
    with make_clip_server(studio, host, port) as server:
        worker = threading.Thread(target=studio.worker_loop, name="clip-editor-jobs", daemon=True)
        worker.start()
        print(f"Clip Editor | http://{host}:{server.server_port}/", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            studio.stop_event.set()
