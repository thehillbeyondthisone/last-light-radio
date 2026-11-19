import base64
import http.client
import io
import json
import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing
from pathlib import Path

from PIL import Image

from last_light_radio.legacy import import_library
from last_light_radio.server import make_server
from last_light_radio.store import sha256
from last_light_radio.studio import Studio, StudioError
from test_generation import FakeLiveClient

ROOT = Path(__file__).resolve().parents[1]


def png():
    buffer = io.BytesIO()
    Image.new("RGB", (32, 24), "#394b35").save(buffer, "PNG")
    return buffer.getvalue()


class StudioClient(FakeLiveClient):
    def download_output(self, reference):
        buffer = io.BytesIO()
        Image.new("RGB", (32, 24), "#394b35").save(buffer, "WEBP", save_all=True,
              append_images=[Image.new("RGB", (32, 24), "#40533c")], duration=41, loop=0)
        return buffer.getvalue()


class StudioTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / "tests")
        self.addCleanup(self.temp.cleanup)
        self.client = StudioClient()
        self.studio = Studio(Path(self.temp.name) / "working", client_factory=lambda *args, **kwargs: self.client)
        self.studio.set_setting("worker_url", self.client.base_url)
        self.scene = self.studio.import_scene(png(), "scene.png", "A room", "Original test still")

    def generate(self):
        payload = {"scene_id": self.scene["id"], "label": "One breath", "prompt": "Gentle breathing, fixed camera.", "seed": 7, "request_id": "generate-once"}
        job = self.studio.submit(payload)
        self.assertEqual(self.studio.submit(payload)["id"], job["id"])
        self.studio.process_job(job["id"])
        self.studio.process_job(job["id"])
        return self.studio.candidate(job["id"])

    def test_import_preserves_bytes_and_reopen_deduplicates_master(self):
        self.assertEqual(self.studio.store.resolve(self.scene["master"]["path"]).read_bytes(), png())
        reopened = Studio(self.studio.store.root)
        again = reopened.import_scene(png(), "another.png", "Another title")
        self.assertEqual(again["id"], self.scene["id"])
        self.assertEqual(len(reopened.scenes()), 1)
        self.assertFalse(again["fixture"])

    def test_invalid_or_animated_master_is_rejected(self):
        with self.assertRaises(StudioError):
            self.studio.import_scene(b"not an image", "bad.png", "Bad image")
        animated = self.client.download_output({})
        with self.assertRaises(StudioError):
            self.studio.import_scene(animated, "animated.webp", "Not a still")

    def test_generation_is_idempotent_resumable_and_never_auto_approves(self):
        candidate = self.generate()
        self.assertEqual(self.client.submissions, 1)
        self.assertEqual(candidate["status"], "candidate")
        self.assertEqual(candidate["version"], 0)
        self.assertTrue(candidate["metadata"]["outputs"][0]["properties"]["pixel_decode_verified"])
        reopened = Studio(self.studio.store.root)
        self.assertEqual(reopened.candidate(candidate["id"])["status"], "candidate")
        self.assertEqual(self.studio.job(candidate["id"])["status"], "success")

    def test_approval_rejection_history_and_conflict_preserve_original_take(self):
        candidate = self.generate()
        source = self.studio.store.resolve(candidate["metadata"]["outputs"][0]["path"])
        before = source.read_bytes()
        payload = {"decision": "approved", "notes": "Reviewed start and end", "entry_anchor": "reading", "exit_anchor": "reading", "visual_checked": False, "expected_version": 0, "request_id": "approval-1"}
        with self.assertRaises(StudioError):
            self.studio.review(candidate["id"], payload)
        payload["visual_checked"] = True
        approved = self.studio.review(candidate["id"], payload)
        self.assertEqual(approved["status"], "approved")
        self.assertEqual([item["id"] for item in self.studio.approved_library()], [candidate["id"]])
        self.assertEqual(self.studio.review(candidate["id"], payload)["version"], 1)
        with self.assertRaises(StudioError) as conflict:
            self.studio.review(candidate["id"], {**payload, "request_id": "stale-review"})
        self.assertEqual(conflict.exception.status, 409)
        with self.assertRaises(StudioError):
            self.studio.review(candidate["id"], {**payload, "decision": "rejected", "expected_version": 1, "request_id": "reject-1", "notes": ""})
        rejected = self.studio.review(candidate["id"], {**payload, "decision": "rejected", "expected_version": 1, "request_id": "reject-1", "notes": "Head drifts"})
        self.assertEqual([review["decision"] for review in rejected["reviews"]], ["approved", "rejected"])
        self.assertEqual(rejected["status"], "rejected")
        self.assertEqual(self.studio.approved_library(), [])
        self.assertEqual(source.read_bytes(), before)
        self.assertEqual(len(list(self.studio.store.resolve(f"approved/{candidate['id']}").glob("*.webp"))), 1)

    def test_modified_candidate_blocks_approval(self):
        candidate = self.generate()
        self.studio.store.resolve(candidate["metadata"]["outputs"][0]["path"]).write_bytes(b"changed")
        with self.assertRaises(StudioError):
            self.studio.review(candidate["id"], {"decision": "approved", "notes": "", "entry_anchor": "a", "exit_anchor": "b", "visual_checked": True, "expected_version": 0, "request_id": "bad"})

    def test_import_old_schema_read_only_and_preserve_every_source_byte(self):
        source = Path(self.temp.name) / "old"
        source.mkdir()
        image = source / "master.png"
        image.write_bytes(png())
        database = source / "last_light_radio.db"
        with closing(sqlite3.connect(database)) as db:
            db.executescript("CREATE TABLE scenes(id,name); CREATE TABLE assets(id,scene_id,kind,role,state_name,path,sha256); CREATE TABLE shots(id); CREATE TABLE candidates(id); CREATE TABLE sequences(id);")
            db.execute("INSERT INTO scenes VALUES(1,'Earlier scene')")
            db.execute("INSERT INTO assets VALUES(1,1,'canonical','master','reading',?,?)", (str(image), sha256(png())))
            db.commit()
        original = database.read_bytes()
        report = import_library(self.studio, str(source))
        self.assertEqual(report["scene_count"], 1)
        self.assertEqual(database.read_bytes(), original)
        self.assertEqual(image.read_bytes(), png())
        self.assertEqual(import_library(self.studio, str(source))["id"], report["id"])
        self.assertFalse((source / "last_light_radio.db-wal").exists())
        self.assertEqual(len(self.studio.setting("legacy_imports")), 1)

    def test_api_import_guard_and_media_match_browser_contract(self):
        server = make_server(self.studio, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        self.addCleanup(connection.close)
        connection.request("GET", "/api/state")
        response = connection.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(json.loads(response.read())["scenes"][0]["id"], self.scene["id"])
        payload = json.dumps({"title": "Imported through API", "filename": "room.png", "image_base64": base64.b64encode(png()).decode()})
        connection.request("POST", "/api/scenes", payload, {"Content-Type": "application/json", "X-LLR-Client": "studio", "Origin": "https://outside.invalid"})
        self.assertEqual(connection.getresponse().status, 403)
        connection.close()
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        self.addCleanup(connection.close)
        connection.request("POST", "/api/scenes", payload, {"Content-Type": "application/json", "X-LLR-Client": "studio"})
        response = connection.getresponse()
        self.assertEqual(response.status, 201)
        imported = json.loads(response.read())
        connection.request("GET", imported["image_url"])
        response = connection.getresponse()
        self.assertEqual(response.read(), png())
        connection.request("GET", imported["image_url"], headers={"Range": "bytes=0-7"})
        response = connection.getresponse()
        self.assertEqual(response.status, 206)
        self.assertEqual(response.read(), png()[:8])


if __name__ == "__main__":
    unittest.main()
