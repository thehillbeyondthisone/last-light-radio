import base64
import copy
import http.client
import io
import json
import tempfile
import threading
import unittest
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

from last_light_radio.comfy import ComfyError
from last_light_radio.generation import load_request
from last_light_radio.motion_jobs import (composite_actor_frame, poll_motion_generation,
                                         prepare_motion_inputs, start_motion_generation)
from last_light_radio.motion_profiles import INT8_VAE, get_profile, job_profile, profiles
from last_light_radio.recipes import prepare_recipe, preview_recipe, save_recipe
from last_light_radio.server import make_server
from last_light_radio.store import StoreError
from last_light_radio.studio import Studio, StudioError
from last_light_radio.video_tools import sample_video, verify_video
from test_motion_jobs import MotionClient

ROOT = Path(__file__).resolve().parents[1]


def picture(size=(321, 241), color=(70, 90, 60)):
    image = Image.new("RGB", size, color)
    draw = ImageDraw.Draw(image)
    draw.rectangle((75, 45, 130, 180), fill=(150, 110, 70))
    stream = io.BytesIO()
    image.save(stream, "PNG")
    return stream.getvalue()


class RecipeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / "tests")
        self.addCleanup(self.temp.cleanup)
        self.studio = Studio(self.temp.name)
        self.studio.set_setting("worker_url", "http://worker.invalid:8188")
        self.studio.set_setting("production_available_vaes", [INT8_VAE])
        self.source = picture()
        self.scene = self.studio.import_scene(self.source, "master.png", "Small odd-sized scene")
        self.payload = {"scene_id": self.scene["id"], "actor": "Actor", "name": "Quiet idle",
                        "template_id": "idle", "start_state": "resting", "end_state": "resting",
                        "polygon": [[70, 40], [135, 40], [135, 185], [70, 185]], "feather": 3,
                        "context": 0.25, "prompt": "One small breath. Locked camera.", "seed": 7,
                        "frames": 39, "vae_name": INT8_VAE}

    def profile(self, **overrides):
        return get_profile(self.studio, save_recipe(self.studio, {**self.payload, **overrides})["id"])

    def test_preview_has_real_mask_and_does_not_write_or_submit(self):
        before = sorted(p.relative_to(self.studio.store.root).as_posix() for p in self.studio.store.root.rglob("*"))
        result = preview_recipe(self.studio, self.payload)
        self.assertEqual(result["output_size"], [321, 241])
        self.assertEqual(result["conditioning_transform"]["conditioning_size"], [768, 768])
        self.assertEqual(profiles(self.studio), [])
        for name, data in result["images"].items():
            with Image.open(io.BytesIO(base64.b64decode(data.split(",")[1]))) as image:
                image.load()
                if name in {"first", "last"}:
                    self.assertEqual(image.size, (768, 768))
        after = sorted(p.relative_to(self.studio.store.root).as_posix() for p in self.studio.store.root.rglob("*"))
        self.assertEqual(before, after)
        self.assertEqual(self.studio.jobs(), [])

    def test_recipe_dedup_revision_and_job_pinning_survive_reopen(self):
        first = self.profile()
        original = copy.deepcopy(first)
        self.assertEqual(self.profile()["id"], first["id"])
        job = self.studio.submit({"scene_id": self.scene["id"], "label": "Test", "prompt": first["prompt"],
                                  "seed": 7, "request_id": "one", "motion_profile_id": first["id"]})
        self.assertEqual(job_profile(self.studio, job["id"])["vae_name"], INT8_VAE)
        revision = self.profile(parent_id=first["id"], feather=8)
        self.assertNotEqual(first["id"], revision["id"])
        self.assertEqual(revision["revision"], 2)
        self.assertEqual(revision["family_id"], first["family_id"])
        reopened = Studio(self.temp.name)
        self.assertEqual(get_profile(reopened, first["id"]), original)
        self.assertEqual(job_profile(reopened, job["id"])["mask"], first["mask"])
        self.assertEqual(reopened.store.resolve(self.scene["master"]["path"]).read_bytes(), self.source)
        self.assertEqual(reopened.candidates(), [])

    def test_letterbox_inverse_preserves_geometry_and_outside_mask_pixels(self):
        profile = self.profile()
        prepared = prepare_motion_inputs(self.studio.store, profile)
        fit = profile["conditioning_transform"]["fitted_box"]
        crop = profile["crop"]
        self.assertAlmostEqual((fit[2] - fit[0]) / (fit[3] - fit[1]), crop["width"] / crop["height"], places=2)
        frame = Image.new("RGB", (768, 768), "red")
        # Padding must not leak back into the scene.
        ImageDraw.Draw(frame).rectangle((fit[0], fit[1], fit[2] - 1, fit[3] - 1), fill="blue")
        result = composite_actor_frame(prepared["background"], prepared["last"], frame, prepared["mask"], crop, 0, 39, prepared["policy"])
        difference = ImageChops.difference(result, prepared["background"])
        protected = prepared["effective_mask"].point(lambda v: 255 if v == 0 else 0)
        self.assertIsNone(ImageChops.multiply(difference, protected.convert("RGB")).getbbox())
        self.assertEqual(result.getpixel((100, 100)), (0, 0, 255))
        self.assertEqual(prepared["first_crop"].size, (768, 768))
        self.assertEqual(prepared["policy"]["encoded_edge_padding"], {"right": 1, "bottom": 1})

    def test_transition_requires_distinct_valid_poses_and_keeps_master_identity(self):
        last = self.studio.import_scene(picture(color=(75, 95, 65)), "last.png", "Last pose")
        profile = self.profile(template_id="transition", first_scene_id=self.scene["id"], last_scene_id=last["id"], end_state="looking")
        self.assertEqual(profile["master"], self.scene["master"])
        prepared = prepare_motion_inputs(self.studio.store, profile)
        self.assertIsNotNone(ImageChops.difference(prepared["first_crop"], prepared["last_crop"]).getbbox())
        invalid = self.studio.import_scene(picture((80, 90)), "wrong.png", "Wrong geometry")
        with self.assertRaises(StudioError):
            self.profile(template_id="transition", last_scene_id=invalid["id"], end_state="looking")

    def test_invalid_outlines_and_parameters_are_rejected_before_saving(self):
        cases = [{"polygon": []}, {"polygon": [[0, 0], [0, 0], [0, 0]]}, {"polygon": [[-1, 1], [5, 3], [8, 4]]},
                 {"polygon": [[1.1, 2], [4, 3], [8, 9]]}, {"feather": -1}, {"feather": True}, {"context": float("nan")},
                 {"frames": 40}, {"seed": True}, {"vae_name": "audio-vae"}, {"template_id": "unknown"},
                 {"template_id": "transition"}, {"end_state": "different"}]
        for change in cases:
            with self.subTest(change=change), self.assertRaises(StudioError):
                save_recipe(self.studio, {**self.payload, **change})
        self.assertEqual(profiles(self.studio), [])

    def test_authored_source_corruption_blocks_job(self):
        profile = self.profile()
        self.studio.store.resolve(profile["mask"]["path"]).write_bytes(b"corrupt")
        with self.assertRaises(StoreError):
            get_profile(self.studio, profile["id"])
        self.assertEqual(self.studio.jobs(), [])

    def test_changed_workflow_is_refused_before_upload_or_submission(self):
        profile = self.profile()
        profile["workflow_template_sha256"] = "0" * 64
        client = MotionClient()
        with self.assertRaisesRegex(ComfyError, "saved workflow"):
            start_motion_generation(self.studio.store, client, profile, profile["prompt"], 7, local_job_id="e" * 32)
        self.assertEqual(client.uploads, [])
        self.assertEqual(client.submissions, 0)

    def test_oriented_jpeg_geometry_matches_browser_coordinates_preserving_bytes(self):
        image = Image.new("RGB", (120, 80), (40, 70, 90))
        exif = Image.Exif()
        exif[274] = 6
        stream = io.BytesIO()
        image.save(stream, "JPEG", exif=exif)
        data = stream.getvalue()
        scene = self.studio.import_scene(data, "oriented.jpg", "Oriented image")
        self.assertEqual((scene["width"], scene["height"]), (80, 120))
        profile, images, _ = prepare_recipe(self.studio, {**self.payload, "scene_id": scene["id"], "polygon": [[5, 5], [60, 5], [60, 100], [5, 100]]})
        self.assertEqual(images["background"].size, (80, 120))
        self.assertEqual(self.studio.store.resolve(profile["master"]["path"]).read_bytes(), data)

    def test_mock_worker_full_path_encodes_odd_size_and_registers_unapproved_candidate(self):
        profile = self.profile()
        profile["frames"] = 3  # Small offline encoder test; authored UI exposes H3-valid lengths.
        client = MotionClient()
        job_id = "d" * 32
        start_motion_generation(self.studio.store, client, profile, profile["prompt"], 7, local_job_id=job_id)
        request = load_request(self.studio.store, job_id)
        self.assertEqual(request["master"], self.scene["master"])
        self.assertEqual(client.graph["7"]["inputs"]["width"], 768)
        result = poll_motion_generation(self.studio.store, client, job_id)
        self.studio.register_candidate(self.scene["id"], "Offline authored take", result["candidate"])
        candidate = self.studio.candidate(job_id)
        self.assertEqual(candidate["status"], "candidate")
        self.assertEqual(candidate["version"], 0)
        media = self.studio.store.resolve(candidate["metadata"]["outputs"][0]["path"])
        verify_video(media)
        with Image.open(io.BytesIO(sample_video(media, 0))) as frame:
            self.assertEqual(frame.size, (322, 242))
        self.assertEqual(client.submissions, 1)
        self.assertEqual(candidate["metadata"]["motion"]["profile"]["id"], profile["id"])

    def test_local_api_preview_save_media_and_reopen_contract(self):
        server = make_server(self.studio, 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
        self.addCleanup(connection.close)
        def post(route):
            connection.request("POST", route, json.dumps(self.payload), {"Content-Type": "application/json", "X-LLR-Client": "studio"})
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        status, preview = post("/api/motion/preview")
        self.assertEqual(status, 200)
        self.assertIn("overlay", preview["images"])
        status, profile = post("/api/motion/recipes")
        self.assertEqual(status, 201)
        self.assertNotIn("master", profile)
        connection.request("GET", profile["mask_url"])
        response = connection.getresponse()
        self.assertEqual(response.status, 200)
        with Image.open(io.BytesIO(response.read())) as mask:
            self.assertEqual((mask.mode, mask.size), ("L", (321, 241)))
        self.assertEqual(len(Studio(self.temp.name).state()["motion_profiles"]), 1)
        self.assertEqual(self.studio.jobs(), [])


if __name__ == "__main__":
    unittest.main()
