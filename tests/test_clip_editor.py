"""Exercise the separate editor with synthetic media and the existing fake worker."""

import base64
import http.client
import io
import json
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from PIL import Image

from last_light_radio.clip_editor import claim_library, make_clip_server
from last_light_radio.film_images import verify
from last_light_radio.studio import Studio, StudioError
from last_light_radio.video_tools import ffmpeg_path
from tests.test_film_generation import FakeWorker
from tests import test_film_images


class ClipEditorTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="clip-editor-test-")
        self.addCleanup(temp.cleanup)
        self.library = Path(temp.name) / "library"
        self.worker = FakeWorker(b"")
        self.studio = Studio(self.library, client_factory=lambda *args, **kwargs: self.worker)
        self.studio.set_setting("worker_url", self.worker.base_url)
        test_film_images.ImageReferencesTests.nodes(self)
        server = make_clip_server(self.studio, "127.0.0.1", 0)
        self.port = server.server_port
        self.addCleanup(server.server_close)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.shutdown)

    def http(self, path, payload=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=20)
        try:
            options = {}
            if payload is not None:
                options = {"Content-Type": "application/json", "X-LLR-Client": "studio",
                           "Origin": f"http://127.0.0.1:{self.port}"}
            connection.request("GET" if payload is None else "POST", path,
                               None if payload is None else json.dumps(payload),
                               {**options, **(headers or {})})
            response = connection.getresponse()
            data = response.read()
            return response.status, json.loads(data) if response.getheader("Content-Type").startswith("application/json") else data
        finally:
            connection.close()

    def call(self, path, payload=None, status=200):
        actual, data = self.http(path, payload)
        self.assertEqual(actual, status, data if isinstance(data, dict) else path)
        return data

    def generate(self, image, frames, title, color):
        movie = self.library.parent / (color + ".mp4")
        subprocess.run([ffmpeg_path(), "-v", "error", "-f", "lavfi", "-i", f"color=c={color}:s=672x384:r=24",
                        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=32000",
                        "-t", str(frames / 24), "-frames:v", str(frames), "-c:v", "libx264",
                        "-pix_fmt", "yuv420p", "-c:a", "aac", "-ac", "2", str(movie)], check=True, capture_output=True)
        self.worker.video = movie.read_bytes()
        inputs = {"first_frame_id": image["id"], "brief": title, "length_frames": frames,
                  "seed": 123, "worker_url": "http://different-worker:8188"}
        checked = self.call("/api/clips/preflight", inputs)
        self.assertTrue(checked["ready"], checked)
        payload = {**inputs, "preflight_id": checked["id"], "request_id": title}
        job = self.call("/api/clips/generate", payload, 202)
        self.assertEqual(self.call("/api/clips/generate", payload, 202)["id"], job["id"])
        self.studio.process_job(job["id"])
        self.studio.process_job(job["id"])
        completed = self.studio.job(job["id"])
        self.assertEqual(completed["status"], "success", completed)
        self.assertEqual(self.worker.graph["6"]["inputs"]["length"], frames)
        return completed["video_asset_id"]

    def test_upload_duration_frame_chaining_and_saved_sequence_with_sound(self):
        png = io.BytesIO()
        Image.new("RGB", (32, 24), "green").save(png, format="PNG")
        source = self.call("/api/clips/images", {"filename": "green.png", "label": "Green",
                           "image_base64": base64.b64encode(png.getvalue()).decode()}, 201)
        first = self.generate(source, 96, "First clip", "red")
        partial = self.call(f"/api/film/assets/{first}/media", status=200)
        self.assertEqual(partial, self.worker.video)
        status, head = self.http(f"/api/film/assets/{first}/media", headers={"Range": "bytes=0-31"})
        self.assertEqual((status, head), (206, partial[:32]))
        frame = self.call("/api/clips/frames", {"video_asset_id": first, "frame": 17}, 201)
        self.assertEqual(frame["provenance"]["frame"], 17)
        self.assertEqual(frame["provenance"]["video_asset_id"], first)
        second = self.generate(frame, 48, "Second clip", "blue")
        selected = verify(self.studio, frame["id"])
        self.assertEqual(self.uploads[-1][0], self.studio.store.resolve(selected["png"]["path"]).read_bytes())
        self.assertEqual(self.worker.submits, 2)

        shots = [{"id": "first", "asset_id": first}, {"id": "second", "asset_id": second}]
        saved = self.call("/api/clips/sequence", {"shots": shots, "expected_revision": 0})
        self.assertEqual(saved["sequence"]["duration_frames"], 144)
        self.call("/api/clips/sequence", {"shots": shots, "expected_revision": 0}, 409)
        self.call("/api/clips/sequence", {"shots": shots[::-1], "expected_revision": 1})
        self.assertEqual([shot["id"] for shot in self.call("/api/clips")["sequence"]["shots"]], ["second", "first"])
        self.call("/api/clips/sequence/export", {"expected_revision": 2}, 202)
        for thread in self.studio.film_jobs.values():
            thread.join(30)
            self.assertFalse(thread.is_alive())
        exported = self.call("/api/clips")["sequence"]["export"]
        self.assertEqual(exported["status"], "complete", exported)
        self.assertEqual(exported["report"]["inspection"]["frame_count"], 144)
        self.assertEqual(exported["report"]["audio"], "mixed")
        self.assertIn(b"ftyp", self.call(urlsplit(exported["media_url"]).path)[:12])
        emptied = self.call("/api/clips/sequence", {"shots": [], "expected_revision": 2})
        self.assertEqual(emptied["sequence"]["duration_frames"], 0)
        self.call("/api/clips/sequence/export", {"expected_revision": 3}, 400)
        self.assertEqual(self.call("/api/clips")["sequence"]["shots"], [])

    def test_only_editor_routes_and_matching_origins_are_allowed(self):
        self.assertIn(b"Clip Editor", self.call("/"))
        self.call("/api/state", status=404)
        self.call("/api/film", status=404)
        self.assertEqual(self.http("/api/clips", headers={"Host": "elsewhere.test"})[0], 403)
        self.assertEqual(self.http("/api/clips/images", {}, {"Origin": "http://elsewhere.test"})[0], 403)
        self.assertEqual(self.http("/api/clips/images", {}, {"X-LLR-Client": "other"})[0], 403)

    def test_local_ai_drafts_editor_fields_without_queuing_a_job(self):
        source = self.call("/api/clips/images", {"filename": "draft.png", "label": "Draft reference",
                           "image_base64": base64.b64encode(Path("assets/test_scene/test_still.png").read_bytes()).decode()}, 201)
        inputs = {"first_frame_id": source["id"], "direction": "Blink once with a fixed camera.", "length_frames": 124}
        self.assertFalse(self.call("/api/clips")["local_ai_configured"])
        self.call("/api/clips/draft", inputs, 503)

        requests = []
        draft = {"brief": "Hold the original framing as the reader blinks once.", "length_frames": 96}

        class LocalAI(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                requests.append((self.path, json.loads(body)))
                output = {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(draft)}}]}
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps(output).encode())

            def log_message(self, *_):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), LocalAI)
        self.addCleanup(server.server_close)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        config = self.library / "local-ai.json"
        config.write_text(json.dumps({
            "base_url": f"http://127.0.0.1:{server.server_port}/v1", "model": "test-qwen",
        }), encoding="utf-8")

        self.assertTrue(self.call("/api/clips")["local_ai_configured"])
        self.assertEqual(self.call("/api/clips/draft", inputs), {**draft, "model": "test-qwen"})
        path, request = requests[0]
        self.assertEqual(path, "/v1/chat/completions")
        self.assertEqual(request["model"], "test-qwen")
        self.assertIn(inputs["direction"], request["messages"][1]["content"])
        self.assertEqual(request["response_format"]["type"], "json_schema")
        self.call("/api/clips/draft", {**inputs, "direction": " "}, 400)
        self.assertEqual(len(requests), 1)
        draft["length_frames"] = 95
        self.call("/api/clips/draft", inputs, 502)
        config.write_text('{"base_url":"http://192.0.2.1/v1","model":"test-qwen"}', encoding="utf-8")
        self.call("/api/clips/draft", inputs, 503)
        snapshot = self.call("/api/clips")
        self.assertEqual(snapshot["jobs"], [])
        self.assertEqual(snapshot["clips"], [])
        self.assertEqual(snapshot["sequence"]["shots"], [])

    def test_large_phone_photo_keeps_original_and_creates_upright_reference(self):
        photo = io.BytesIO()
        exif = Image.Exif()
        exif[274] = 6
        Image.new("RGB", (8000, 6000), "green").save(photo, format="JPEG", exif=exif)
        original = photo.getvalue()
        image = self.call("/api/clips/images", {
            "filename": "phone.jpg", "label": "Phone photo",
            "image_base64": base64.b64encode(original).decode(),
        }, 201)
        self.assertEqual((image["width"], image["height"]), (1536, 2048))
        self.assertEqual(self.studio.store.resolve(image["source"]["path"]).read_bytes(), original)
        with Image.open(io.BytesIO(self.call(image["media_url"]))) as derivative:
            self.assertEqual(derivative.size, (1536, 2048))
            self.assertIsNone(derivative.getexif().get(274))

    def test_library_has_one_worker_owner_and_releases_on_exit(self):
        with claim_library(self.library):
            with self.assertRaisesRegex(StudioError, "already running"), claim_library(self.library):
                self.fail("A second listener acquired the active library")
        with claim_library(self.library):
            self.assertEqual(self.call("/api/clips")["sequence"]["shots"], [])
