import base64
import copy
import http.client
import io
import json
import tempfile
import threading
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from last_light_radio.motion_jobs import poll_motion_generation, prepare_motion_inputs, start_motion_generation
from last_light_radio.motion_masks import decode_mask, save_mask_revision
from last_light_radio.motion_profiles import INT8_VAE, get_profile
from last_light_radio.recipes import prepare_recipe, save_recipe
from last_light_radio.recompose import recompose
from last_light_radio.server import make_server
from last_light_radio.store import StoreError, canonical_bytes
from last_light_radio.studio import Studio, StudioError
from test_motion_jobs import MotionClient
from test_recipes import picture

ROOT = Path(__file__).resolve().parents[1]


def encoded(image):
    stream = io.BytesIO()
    image.save(stream, "PNG")
    return base64.b64encode(stream.getvalue()).decode()


class MotionAuthoringTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / "tests")
        self.addCleanup(self.temp.cleanup)
        self.studio = Studio(self.temp.name, client_factory=lambda *args, **kwargs: self.fail("Unexpected worker access"))
        self.scene = self.studio.import_scene(picture((160, 160)), "scene.png", "Test scene")
        self.mask = Image.new("RGBA", (160, 160))
        ImageDraw.Draw(self.mask).rectangle((40, 40, 100, 110), fill=(255, 255, 255, 255))
        self.payload = {"scene_id": self.scene["id"], "name": "Sip", "actor": "Reader", "template_id": "action",
                        "start_state": "reading", "end_state": "reading", "frames": 39, "seed": 7,
                        "vae_name": INT8_VAE, "feather": 0, "context": 0.3, "mask_base64": encoded(self.mask),
                        "creative_direction": {"starter_id": "sip", "description": "Take one sip and resume reading."}}

    def original(self):
        profile = get_profile(self.studio, save_recipe(self.studio, self.payload)["id"])
        client = MotionClient()
        identity = "b" * 32
        start_motion_generation(self.studio.store, client, profile, profile["prompt"], 7, local_job_id=identity)
        result = poll_motion_generation(self.studio.store, client, identity)
        self.studio.register_candidate(self.scene["id"], "Original", result["candidate"])
        return profile, self.studio.candidate(identity), client

    def test_plain_language_is_compiled_and_preserved_without_model_calls(self):
        original = copy.deepcopy(self.payload)
        profile, images, _ = prepare_recipe(self.studio, self.payload)
        self.assertIn("Take one sip and resume reading.", profile["prompt"])
        self.assertIn("no duplicate mug", profile["prompt"])
        self.assertEqual(profile["creative_direction"], self.payload["creative_direction"])
        self.assertEqual(profile["start_state"], profile["end_state"])
        self.assertEqual(images["mask"].getpixel((10, 10)), 0)
        self.assertEqual(images["mask"].getpixel((60, 60)), 255)
        self.assertEqual(self.payload, original)
        self.assertEqual(self.studio.jobs(), [])
        self.assertEqual(self.studio.candidates(), [])
        self.studio.store.verify_master(self.scene["master"])
        stored = get_profile(self.studio, save_recipe(self.studio, self.payload)["id"])
        self.assertEqual(prepare_motion_inputs(self.studio.store, stored)["policy"]["mask_policy"], "authored_painted_mask")

    def test_mask_validation_handles_alpha_and_rejects_empty_bad_geometry_or_data(self):
        mask = Image.new("RGBA", (160, 160), (255, 255, 255, 0))
        ImageDraw.Draw(mask).rectangle((40, 40, 80, 80), fill=(255, 255, 255, 128))
        result = decode_mask(encoded(mask), (160, 160))
        self.assertEqual(result.getpixel((50, 50)), 128)
        self.assertEqual(result.getpixel((5, 5)), 0)
        for value in ("invalid-base64", encoded(Image.new("L", (160, 160))), encoded(Image.new("L", (10, 10), 255))):
            with self.subTest(value=value[:20]), self.assertRaises(StudioError):
                decode_mask(value, (160, 160))
        for creative in ({"starter_id": "unknown", "description": "Move"}, {"starter_id": "sip", "description": ""}):
            with self.assertRaises(StudioError):
                prepare_recipe(self.studio, {**self.payload, "creative_direction": creative})

    def test_api_adjustment_source_previews_repeat_edits_and_recovery_need_no_gpu(self):
        profile, original, client = self.original()
        before = canonical_bytes(original)
        server = make_server(self.studio, 0)
        worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=20)
        self.addCleanup(connection.close)
        connection.request("GET", original["source_frames"]["middle"])
        response = connection.getresponse()
        self.assertEqual(response.status, 200)
        with Image.open(io.BytesIO(response.read())) as image:
            self.assertEqual(image.size, (160, 160))
        def post(mask):
            connection.request("POST", f"/api/candidates/{original['id']}/area", json.dumps({"mask_base64": encoded(mask)}), {"Content-Type": "application/json", "X-LLR-Client": "studio"})
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        status, unchanged = post(self.mask)
        self.assertEqual((status, unchanged["id"]), (200, original["id"]))
        outside = Image.new("L", (160, 160), 255)
        status, failure = post(outside)
        self.assertEqual(status, 400)
        self.assertIn("beyond", failure["error"]["message"])
        revised_mask = self.mask.copy()
        ImageDraw.Draw(revised_mask).rectangle((100, 50, 112, 100), fill=(255, 255, 255, 255))
        status, derivative = post(revised_mask)
        self.assertEqual(status, 201)
        self.assertEqual((derivative["status"], derivative["version"]), ("candidate", 0))
        self.assertTrue(derivative["can_adjust_area"])
        status, repeated = post(revised_mask)
        self.assertEqual(repeated["id"], derivative["id"])
        # Subsequent correction may start from a corrected take as well.
        second_mask = revised_mask.copy()
        ImageDraw.Draw(second_mask).rectangle((50, 100, 90, 118), fill=(255, 255, 255, 255))
        next_profile = save_mask_revision(self.studio, derivative["id"], encoded(second_mask))
        second = recompose(self.studio, derivative["id"], next_profile["id"])
        self.assertNotEqual(second["id"], derivative["id"])
        self.assertFalse(second["metadata"]["recomposition"]["gpu_submitted"])
        # Recover a finished CPU assembly whose registry transaction was interrupted.
        with self.studio.db() as db:
            db.execute("DELETE FROM candidates WHERE id=?", (second["id"],))
        recovered = recompose(self.studio, derivative["id"], next_profile["id"])
        self.assertEqual(recovered["id"], second["id"])
        self.assertEqual(canonical_bytes(self.studio.candidate(original["id"])), before)
        self.assertEqual(client.submissions, 1)
        self.assertEqual(self.studio.approved_library(), [])
        self.assertEqual(self.studio.jobs(), [])
        # Cached media must still pass its hash on an idempotent request.
        output = recovered["metadata"]["outputs"][0]
        self.studio.store.resolve(output["path"]).write_bytes(b"corrupt")
        with self.assertRaises(StoreError):
            recompose(self.studio, derivative["id"], next_profile["id"])


if __name__ == "__main__":
    unittest.main()
