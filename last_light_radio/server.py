"""HTTP serving for the loopback studio and the separate Clip Editor."""

from __future__ import annotations

import base64
import binascii
import json
import logging
import mimetypes
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .comfy import ComfyError
from .studio import ROOT, Studio, StudioError

LOG = logging.getLogger("last_light_radio")
BODY_LIMIT = 29 * 1024 * 1024


def make_server(studio: Studio, port: int = 8765, *, static_root: Path | None = None,
                host: str = "127.0.0.1", api_router=None):
    static_root = (static_root or ROOT / "frontend/dist").resolve()

    class Handler(BaseHTTPRequestHandler):
        server_version = "LastLightRadio/0.2"

        def log_message(self, format, *args):
            LOG.info("http.request", extra={"fields": {"message": format % args}})

        def send_bytes(self, data: bytes, content_type: str, status=200):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Cache-Control", "no-store" if content_type.startswith("application/json") else "private, max-age=60")
            self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' blob: data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(data)

        def send_json(self, value, status=200):
            self.send_bytes(json.dumps(value, ensure_ascii=False, allow_nan=False).encode(), "application/json; charset=utf-8", status)

        def send_file(self, file: Path, content_type: str):
            length = file.stat().st_size
            start, end, status = 0, length - 1, 200
            requested = self.headers.get("Range")
            if requested:
                match = re.fullmatch(r"bytes=(\d*)-(\d*)", requested)
                if not match or not any(match.groups()):
                    raise StudioError("Invalid media range", 416)
                left, right = match.groups()
                if left:
                    start = int(left)
                    end = min(int(right), end) if right else end
                else:
                    start = max(0, length - int(right))
                if start > end or start >= length:
                    raise StudioError("Media range is outside this file", 416)
                status = 206
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(end - start + 1))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "private, max-age=60")
            if status == 206:
                self.send_header("Content-Range", f"bytes {start}-{end}/{length}")
            self.end_headers()
            with file.open("rb") as stream:
                stream.seek(start)
                remaining = end - start + 1
                while remaining > 0:
                    data = stream.read(min(64 * 1024, remaining))
                    if not data:
                        break
                    self.wfile.write(data)
                    remaining -= len(data)

        def path_parts(self):
            return [unquote(part) for part in urlsplit(self.path).path.strip("/").split("/") if part]

        def guard_host(self):
            allowed = {f"{host}:{self.server.server_port}"}
            if host == "127.0.0.1":
                allowed.add(f"localhost:{self.server.server_port}")
            if self.headers.get("Host") not in allowed:
                raise StudioError("Use the studio's configured address", 403)

        def body(self):
            self.guard_host()
            origin = self.headers.get("Origin")
            if origin and origin != f"http://{self.headers.get('Host')}":
                raise StudioError("Requests must originate in this local studio", 403)
            if self.headers.get("X-LLR-Client") != "studio" or self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                raise StudioError("A JSON studio request is required", 403)
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                raise StudioError("Invalid request length") from None
            if not 0 < length <= BODY_LIMIT:
                raise StudioError("Request is empty or exceeds the image upload limit", 413)
            value = json.loads(self.rfile.read(length))
            if not isinstance(value, dict):
                raise StudioError("Expected a JSON object")
            return value

        def receive_audio_upload(self, token):
            self.guard_host()
            self.close_connection = True
            origin = self.headers.get("Origin")
            allowed = {f"http://127.0.0.1:{self.server.server_port}", f"http://localhost:{self.server.server_port}"}
            if origin and origin not in allowed:
                raise StudioError("Requests must originate in this local studio", 403)
            if self.headers.get("X-LLR-Client") != "studio" or self.headers.get("Content-Type", "").split(";")[0] != "application/octet-stream":
                raise StudioError("A binary studio upload is required", 403)
            lengths = self.headers.get_all("Content-Length", [])
            if self.headers.get("Transfer-Encoding") or len(lengths) != 1 or not re.fullmatch(r"[0-9]+", lengths[0]):
                raise StudioError("Supply one exact Content-Length without Transfer-Encoding", 400)
            length = int(lengths[0])
            if not 44 <= length <= 256*1024*1024:
                raise StudioError("Choose a WAV up to 256 MiB", 413)
            from .audio_uploads import receive
            previous = self.connection.gettimeout()
            self.connection.settimeout(60)
            try:
                return self.send_json(receive(studio, token, self.rfile, length), 201)
            finally:
                self.connection.settimeout(previous)

        def dispatch(self, mutation=False):
            try:
                self.guard_host()
                parts = self.path_parts()
                if api_router is not None and (mutation or parts[:1] == ["api"]):
                    return api_router(self, studio, parts, self.body() if mutation else None)
                if mutation:
                    if len(parts) == 5 and parts[:3] == ['api','audio','uploads'] and parts[4] == 'content':
                        return self.receive_audio_upload(parts[3])
                    payload = self.body()
                    if parts[:2] == ["api", "film"]:
                        from . import film
                        if parts[:3] == ["api", "film", "music"]:
                            from . import music_generation
                            if parts == ["api", "film", "music", "preflight"]:
                                return self.send_json(music_generation.preflight(studio, payload))
                            if parts == ["api", "film", "music", "jobs"]:
                                return self.send_json(music_generation.submit(studio, payload), 202)
                            if len(parts) == 6 and parts[3] == "jobs" and parts[5] == "resume":
                                return self.send_json(music_generation.resume(studio, parts[4]))
                            if len(parts) == 6 and parts[3] == "jobs" and parts[5] == "import":
                                return self.send_json(music_generation.import_completed(studio, parts[4]), 201)
                            raise StudioError("Music API route not found", 404)
                        if parts[:3] == ["api", "film", "generation"]:
                            from . import film_generation
                            if parts == ["api", "film", "generation", "preflight"]:
                                return self.send_json(film_generation.preflight(studio, payload))
                            if parts == ["api", "film", "generation", "jobs"]:
                                return self.send_json(film_generation.submit(studio, payload), 202)
                            if len(parts) == 6 and parts[3] == "jobs" and parts[5] == "resume":
                                return self.send_json(film_generation.resume(studio, parts[4]))
                            if len(parts) == 6 and parts[3] == "jobs" and parts[5] == "import":
                                return self.send_json(film_generation.import_completed(studio, parts[4]), 201)
                            raise StudioError("Joint-AV API route not found", 404)
                        if len(parts) >= 5 and parts[2] == "projects" and parts[4] == "story":
                            from . import film_story
                            if len(parts) == 5:
                                return self.send_json(film_story.save(studio, parts[3], payload))
                            if len(parts) == 6 and parts[5] == "export":
                                return self.send_json(film_story.export(studio, parts[3], payload))
                            raise StudioError("Story API route not found", 404)
                        if len(parts) == 5 and parts[2] == "generations" and parts[4] == "place":
                            from .generation_timeline import place
                            return self.send_json(place(studio, parts[3], payload))
                        if len(parts) in (5, 6) and parts[2] == "projects" and parts[4] == "references":
                            from . import film_references
                            if len(parts) == 5:
                                return self.send_json(film_references.save(studio, parts[3], payload), 201)
                            if parts[5] == "compile":
                                return self.send_json(film_references.compile_shot(studio, parts[3], payload))
                            raise StudioError("Production reference API route not found", 404)
                        if parts == ["api", "film", "images", "import"]:
                            from .film_images import import_image
                            return self.send_json(import_image(studio, payload), 201)
                        if parts == ["api", "film", "images", "from-frame"]:
                            from .film_images import from_frame
                            return self.send_json(from_frame(studio, payload), 201)
                        if parts == ["api", "film", "continuations"]:
                            from .film_continuations import prepare
                            return self.send_json(prepare(studio, payload), 201)
                        if len(parts) >= 5 and parts[2] == "sequences" and parts[4] == "shot-plan":
                            from . import film_shot_plan
                            if len(parts) == 5:
                                return self.send_json(film_shot_plan.save(studio, parts[3], payload))
                            if len(parts) == 7 and parts[6] == "candidates":
                                return self.send_json(film_shot_plan.attach(studio, parts[3], parts[5], payload))
                            if len(parts) == 7 and parts[6] == "place":
                                return self.send_json(film_shot_plan.place(studio, parts[3], parts[5], payload))
                            raise StudioError("Shot plan API route not found", 404)
                        if parts == ["api", "film", "projects"]:
                            return self.send_json(film.create_project(studio, payload), 201)
                        if len(parts) == 5 and parts[2] == "projects" and parts[4] == "sequences":
                            return self.send_json(film.create_sequence(studio, parts[3], payload), 201)
                        if parts == ["api", "film", "assets", "import"]:
                            return self.send_json(film.import_asset(studio, payload), 201)
                        if parts == ["api", "film", "assets", "from-take"]:
                            return self.send_json(film.import_take(studio, payload), 201)
                        if parts == ["api", "film", "assets", "from-sequence"]:
                            return self.send_json(film.import_scene_export(studio, payload), 201)
                        if len(parts) == 5 and parts[2] == "assets" and parts[4] == "review":
                            return self.send_json(film.review_asset(studio, parts[3], payload))
                        if len(parts) == 5 and parts[2] == "assets" and parts[4] == "delete":
                            return self.send_json(film.delete_asset(studio, parts[3], payload))
                        if len(parts) == 4 and parts[2] == "sequences":
                            return self.send_json(film.save_sequence(studio, parts[3], payload))
                        if len(parts) == 5 and parts[2] == "sequences" and parts[4] == "export":
                            return self.send_json(film.queue_export(studio, parts[3], payload), 202)
                        raise StudioError("Film API route not found", 404)
                    if parts == ["api", "audio", "uploads"]:
                        from .audio_uploads import begin
                        return self.send_json(begin(studio, payload), 201)
                    if parts == ["api", "audio", "import"]:
                        from .audio_tracks import import_asset
                        return self.send_json(import_asset(studio, payload), 201)
                    if len(parts) == 4 and parts[:2] == ["api", "audio"] and parts[3] == "review":
                        from .audio_tracks import review
                        return self.send_json(review(studio, parts[2], payload))
                    if parts == ["api", "scenes"]:
                        encoded = payload.get("image_base64")
                        if not isinstance(encoded, str):
                            raise StudioError("Choose an image to import")
                        data = base64.b64decode(encoded, validate=True)
                        return self.send_json(studio.import_scene(data, payload.get("filename", ""), payload.get("title"), payload.get("description", "")), 201)
                    if parts == ["api", "worker"]:
                        return self.send_json(studio.connect_worker(payload.get("url")))
                    if parts == ["api", "generate"]:
                        return self.send_json(studio.submit(payload), 202)
                    if parts == ["api", "editor", "plan"]:
                        from .editor import plan
                        return self.send_json(plan(studio, payload), 201)
                    if parts == ["api", "pilots"]:
                        from .pilots import plan
                        return self.send_json(plan(studio, payload), 201)
                    if len(parts) == 4 and parts[:2] == ["api", "pilots"] and parts[3] == "export":
                        from .pilots import queue_export
                        return self.send_json(queue_export(studio, parts[2]), 202)
                    if parts == ["api", "motion", "preview"]:
                        from .recipes import preview_recipe
                        return self.send_json(preview_recipe(studio, payload))
                    if parts == ["api", "motion", "recipes"]:
                        from .recipes import save_recipe
                        return self.send_json(save_recipe(studio, payload), 201)
                    if len(parts) == 4 and parts[:2] == ["api", "candidates"] and parts[3] == "area":
                        from .motion_masks import save_mask_revision
                        from .recompose import recompose
                        profile = save_mask_revision(studio, parts[2], payload.get("mask_base64"))
                        original = studio.candidate(parts[2])
                        if profile["id"] == original["metadata"]["motion"]["profile_id"]:
                            return self.send_json(original)
                        return self.send_json(recompose(studio, parts[2], profile["id"]), 201)
                    if parts == ["api", "library", "import"]:
                        from .legacy import import_library
                        from .motion_profiles import restore_profiles
                        report = import_library(studio, payload.get("path", ""))
                        restore_profiles(studio)
                        return self.send_json(report)
                    if len(parts) == 4 and parts[:2] == ["api", "candidates"] and parts[3] == "review":
                        return self.send_json(studio.review(parts[2], payload))
                    if len(parts) == 4 and parts[:2] == ["api", "jobs"] and parts[3] == "resume":
                        return self.send_json(studio.resume(parts[2]))
                    raise StudioError("API route not found", 404)
                if parts[:2] == ["api", "film"]:
                    from . import film
                    if parts[:3] == ["api", "film", "music"]:
                        from . import music_generation
                        if parts == ["api", "film", "music"]:
                            return self.send_json(music_generation.state(studio))
                        if len(parts) == 5 and parts[3] == "jobs":
                            return self.send_json(music_generation.get_job(studio, parts[4]))
                        raise StudioError("Music API route not found", 404)
                    if parts[:3] == ["api", "film", "generation"]:
                        from . import film_generation
                        if parts == ["api", "film", "generation"]:
                            return self.send_json(film_generation.state(studio))
                        if len(parts) == 5 and parts[3] == "jobs":
                            return self.send_json(film_generation.get_job(studio, parts[4]))
                        raise StudioError("Joint-AV API route not found", 404)
                    if len(parts) >= 5 and parts[2] == "projects" and parts[4] == "story":
                        from . import film_story
                        if len(parts) == 5:
                            return self.send_json(film_story.story(studio, parts[3]))
                        if len(parts) == 6 and parts[5] == "manifest":
                            return self.send_json(film_story.frozen(studio, parts[3]))
                        if len(parts) == 8 and parts[5] == "exports" and parts[7] == "manifest":
                            return self.send_json(film_story.frozen(studio, parts[3], parts[6]))
                        if len(parts) == 10 and parts[5] == "exports" and parts[7] == "nodes" and parts[9] == "media":
                            return self.send_file(film_story.media(studio, parts[3], parts[6], parts[8]), "video/mp4")
                        raise StudioError("Story API route not found", 404)
                    if len(parts) == 5 and parts[2] == "projects" and parts[4] == "references":
                        from .film_references import listing
                        return self.send_json(listing(studio, parts[3]))
                    if parts == ["api", "film", "images"]:
                        from .film_images import listing
                        return self.send_json(listing(studio))
                    if len(parts) == 5 and parts[2] == "images" and parts[4] == "media":
                        from .film_images import verify
                        return self.send_file(studio.store.resolve(verify(studio, parts[3])["png"]["path"]), "image/png")
                    if len(parts) == 5 and parts[2] == "audio" and parts[4] == "waveform":
                        return self.send_json(film.audio_waveform(studio, parts[3]))
                    if len(parts) == 5 and parts[2] == "sequences" and parts[4] == "shot-plan":
                        from .film_shot_plan import get
                        return self.send_json(get(studio, parts[3]))
                    if parts == ["api", "film", "takes"]:
                        return self.send_json(film.takes(studio))
                    if parts == ["api", "film"]:
                        return self.send_json(film.listing(studio))
                    if len(parts) == 5 and parts[2] == "sequences" and parts[4] == "generations":
                        from .generation_timeline import listing
                        return self.send_json(listing(studio, parts[3]))
                    if len(parts) == 4 and parts[2] == "sequences":
                        return self.send_json(film.sequence(studio, parts[3]))
                    if len(parts) == 5 and parts[2] == "assets" and parts[4] == "media":
                        return self.send_file(film.asset_media(studio, parts[3]), "video/mp4")
                    if len(parts) == 5 and parts[2] == "sequences" and parts[4] in {"media", "manifest"}:
                        path, kind = film.export_media(studio, parts[3], parts[4])
                        return self.send_file(path, kind)
                    raise StudioError("Film API route not found", 404)
                if parts == ["api", "audio"]:
                    from .audio_tracks import listing
                    return self.send_json({**listing(studio), "upload_capability": {"begin_url":"/api/audio/uploads", "max_bytes":256*1024*1024, "max_duration_seconds":600, "content_type":"application/octet-stream"}})
                if len(parts) == 4 and parts[:2] == ["api", "audio"] and parts[3] == "media":
                    from .audio_tracks import media
                    return self.send_file(media(studio, parts[2]), "audio/wav")
                if parts == ["api", "health"]:
                    return self.send_json({"application": "last-light-radio", "data_root": str(studio.store.root.resolve())})
                if parts == ["api", "state"]:
                    return self.send_json(studio.state())
                if len(parts) == 3 and parts[:2] == ["api", "editor"]:
                    from .editor import state
                    return self.send_json(state(studio, parts[2]))
                if len(parts) == 6 and parts[:3] == ["api", "editor", "plans"] and parts[4] == "masks":
                    from .editor import mask_media
                    return self.send_file(mask_media(studio, parts[3], parts[5]), "image/png")
                if len(parts) == 5 and parts[:2] == ["api", "candidates"] and parts[3] == "source":
                    from .motion_masks import source_sample
                    return self.send_bytes(source_sample(studio, parts[2], parts[4]), "image/png")
                if len(parts) == 5 and parts[:2] == ["api", "candidates"] and parts[3] == "compare":
                    from .take_review import compare_takes
                    return self.send_json(compare_takes(studio, parts[2], parts[4]))
                if (len(parts) == 5 and parts[:2] == ["api", "candidates"]
                        and parts[3] == "frames" and parts[4].isdigit()):
                    from .take_review import decoded_frame
                    return self.send_bytes(decoded_frame(studio, parts[2], int(parts[4])), "image/png")
                if parts[:2] == ["api", "pilots"]:
                    from .pilots import get, media
                    if len(parts) == 5 and parts[3] == "ambience":
                        from .pilots import ambience_media
                        return self.send_file(ambience_media(studio, parts[2], parts[4]), "image/png")
                    if len(parts) == 3:
                        return self.send_json(get(studio, parts[2]))
                    if len(parts) == 4:
                        file, kind = media(studio, parts[2], parts[3])
                        return self.send_file(file, kind)
                    if len(parts) == 6 and parts[3] == "frames" and parts[4].isdigit():
                        file, kind = media(studio, parts[2], parts[5], int(parts[4]))
                        return self.send_file(file, kind)
                    raise StudioError("Pilot route not found", 404)
                if len(parts) == 4 and parts[:2] == ["api", "motion"]:
                    from .motion_profiles import profile_media
                    return self.send_file(profile_media(studio, parts[2], parts[3]), "image/png")
                if len(parts) in (4, 5) and parts[0] == "api" and parts[1] in {"scenes", "candidates"}:
                    if len(parts) == 5 and parts[3] != "frames":
                        raise StudioError("Media not found", 404)
                    file, kind = studio.media(parts[1], parts[2], parts[-1])
                    return self.send_file(file, kind)
                if parts and parts[0] == "api":
                    raise StudioError("API route not found", 404)
                relative = "/".join(parts) or "index.html"
                file = (static_root / relative).resolve()
                if not file.is_relative_to(static_root):
                    raise StudioError("File not found", 404)
                if not file.is_file():
                    if relative != "index.html":
                        raise StudioError("File not found", 404)
                    raise StudioError("Build the React interface first: cd frontend; npm run build", 503)
                return self.send_bytes(file.read_bytes(), mimetypes.guess_type(file.name)[0] or "application/octet-stream")
            except ConnectionError:
                # Video players routinely cancel a range request when seeking.
                # The socket is closed; writing a JSON error would fail again.
                self.close_connection = True
                LOG.debug("http.client_disconnected")
            except (StudioError, ComfyError, OSError, ValueError, KeyError, binascii.Error) as error:
                status = error.status if isinstance(error, StudioError) else (502 if isinstance(error, ComfyError) else 400)
                details = error.to_dict() if isinstance(error, ComfyError) else {"message": str(error)}
                return self.send_json({"error": details}, status)

        def do_GET(self):
            from . import shot_controls_bridge
            if api_router is None and shot_controls_bridge.handles(self.path):
                return shot_controls_bridge.bridge(self)
            self.dispatch()

        def do_POST(self):
            from . import shot_controls_bridge
            if api_router is None and shot_controls_bridge.handles(self.path):
                return shot_controls_bridge.bridge(self, mutating=True)
            self.dispatch(mutation=True)

        def do_OPTIONS(self):
            self.send_json({"error": {"message": "Cross-origin requests are not enabled"}}, 403)

    return ThreadingHTTPServer((host, port), Handler)


def serve(root: str | Path = ".local/studio", port: int = 8765):
    studio = Studio(root)
    studio.bootstrap_example()
    from .motion_profiles import restore_profiles
    restore_profiles(studio)
    server = make_server(studio, port)
    worker = threading.Thread(target=studio.worker_loop, name="studio-jobs", daemon=True)
    worker.start()
    from .pilots import worker_loop
    exporter = threading.Thread(target=worker_loop, args=(studio,), name="pilot-exports", daemon=True)
    exporter.start()
    print(f"Last Light Radio studio: http://127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        studio.stop_event.set()
        exporter.join(timeout=5)
        server.server_close()
