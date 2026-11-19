import copy
import tempfile
import unittest
from pathlib import Path

from last_light_radio.motion_jobs import poll_motion_generation, start_motion_generation
from last_light_radio.motion_profiles import INT8_VAE, get_profile
from last_light_radio.recipes import save_recipe
from last_light_radio.recompose import recompose, validate_mask_revision
from last_light_radio.store import StoreError, canonical_bytes
from last_light_radio.studio import Studio, StudioError
from test_motion_jobs import MotionClient
from test_recipes import picture

ROOT = Path(__file__).resolve().parents[1]


class RecomposeTests(unittest.TestCase):
    def test_mask_only_mapping_rejects_changed_generation_contract(self):
        profile = {"first": {"sha256": "a"}, "last": {"sha256": "b"}, "background": {"sha256": "c"},
                   "crop": {"x": 2}, "frames": 39, "prompt": "Sip", "actor": "reader"}
        revised = copy.deepcopy(profile)
        revised["mask"] = {"sha256": "different"}
        validate_mask_revision(profile, revised)
        for key, value in (("crop", {"x": 3}), ("frames", 90), ("prompt", "Different"), ("actor", "cat")):
            with self.subTest(key=key), self.assertRaises(StudioError):
                validate_mask_revision(profile, {**revised, key: value})
        with self.assertRaises(StudioError):
            validate_mask_revision(profile, {**revised, "first": {"sha256": "new-pose"}})

    def test_recompose_appends_unapproved_derivative_without_worker_or_source_changes(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as temporary:
            studio = Studio(temporary, client_factory=lambda *args, **kwargs: self.fail("Recomposition called the worker"))
            scene = studio.import_scene(picture((160, 160)), "master.png", "Offline sip")
            payload = {"scene_id": scene["id"], "name": "Sip", "actor": "reader", "template_id": "action",
                       "start_state": "reading", "end_state": "reading", "frames": 39, "seed": 7,
                       "prompt": "One sip, then return.", "vae_name": INT8_VAE, "context": 0.1, "feather": 2,
                       "polygon": [[20, 20], [130, 20], [130, 130], [20, 130]]}
            original = get_profile(studio, save_recipe(studio, payload)["id"])
            revised = save_recipe(studio, {**payload, "parent_id": original["id"],
                                          "polygon": [[20, 20], [130, 20], [130, 130], [80, 130], [80, 70], [50, 70], [50, 130], [20, 130]]})
            client = MotionClient()
            identity = "a" * 32
            start_motion_generation(studio.store, client, original, original["prompt"], 7, local_job_id=identity)
            result = poll_motion_generation(studio.store, client, identity)
            studio.register_candidate(scene["id"], "Source", result["candidate"])
            studio.review(identity, {"decision": "approved", "visual_checked": True, "expected_version": 0,
                                     "entry_anchor": "reading", "exit_anchor": "reading", "notes": "Offline fixture", "request_id": "fixture-review"})
            before = canonical_bytes(studio.candidate(identity))
            source_bytes = {ref["path"]: studio.store.resolve(ref["path"]).read_bytes()
                            for ref in [*result["candidate"]["outputs"], *result["candidate"]["motion"]["raw_frames"]]}
            derivative = recompose(studio, identity, revised["id"])
            self.assertNotEqual(derivative["id"], identity)
            self.assertEqual((derivative["status"], derivative["version"]), ("candidate", 0))
            self.assertFalse(derivative["metadata"]["recomposition"]["gpu_submitted"])
            self.assertTrue(derivative["metadata"]["outputs"][0]["properties"]["pixel_decode_verified"])
            self.assertEqual(canonical_bytes(studio.candidate(identity)), before)
            for path, data in source_bytes.items():
                self.assertEqual(studio.store.resolve(path).read_bytes(), data)
            self.assertEqual(recompose(studio, identity, revised["id"])["id"], derivative["id"])
            self.assertEqual([c["id"] for c in studio.approved_library()], [identity])
            self.assertEqual(client.submissions, 1)
            raw = result["candidate"]["motion"]["raw_frames"][0]
            studio.store.resolve(raw["path"]).write_bytes(b"corrupt")
            with self.assertRaises(StoreError):
                recompose(studio, identity, revised["id"])
            self.assertEqual(len(studio.candidates()), 2)


if __name__ == "__main__":
    unittest.main()
