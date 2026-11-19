import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from last_light_radio.motion_profiles import INT8_VAE, ORIGINAL_VAE, get_profile
from last_light_radio.motion_profiles import job_profile, public_profiles, restore_profiles
from last_light_radio.store import StoreError, canonical_bytes, sha256
from last_light_radio.studio import Studio, StudioError

ROOT = Path(__file__).resolve().parents[1]


def image_bytes(color, mode="RGB"):
    data = io.BytesIO()
    Image.new(mode, (32, 24), color).save(data, "PNG")
    return data.getvalue()


class MotionProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / "tests")
        self.addCleanup(self.temp.cleanup)
        self.studio = Studio(self.temp.name)
        self.studio.set_setting("worker_url", "http://worker.test:8188")
        self.studio.set_setting("production_available_vaes", [INT8_VAE])
        first = image_bytes("#394b35")
        last = image_bytes("#40533c")
        mask = image_bytes(255, "L")
        self.scene = self.studio.import_scene(first, "first.png", "A room")
        self.end_scene = self.studio.import_scene(last, "last.png", "Another pose")
        files = []
        assets = []
        library = "a" * 24
        for number, (data, kind, state) in enumerate(((first, "canonical", "reading"),
                                                      (last, "state", "looking_outside"),
                                                      (mask, "mask", None)), 1):
            relative = f"legacy/{library}/archive/{number}.png"
            self.studio.store.write_once(relative, data)
            files.append({"path": relative, "sha256": sha256(data)})
            assets.append({"id": number, "scene_id": 1, "kind": kind, "sha256": sha256(data), "state_name": state})
        records = {"assets": assets, "shots": [{"id": 1, "scene_id": 1, "workflow_id": "minimax_h3_flf2v_8step_v1",
                    "first_asset_id": 1, "last_asset_id": 2, "role": "look_toward_window", "start_state": "reading",
                    "end_state": "looking_outside", "frame_count": 124, "prompt": "Turn toward the window."}],
                   "candidates": [{"id": 1, "shot_id": 1, "status": "completed", "mask_asset_id": 3, "seed": 7,
                    "metadata_json": json.dumps({"frame_count": 124, "fps": 24}),
                    "crop_json": json.dumps({"x": 0, "y": 0, "width": 32, "height": 24})}]}
        self.studio.store.write_once(f"legacy/{library}/database_records.json", canonical_bytes(records))
        self.studio.set_setting("legacy_imports", [{"id": library, "database_sha256": "a" * 64, "files": files}])
        self.profile = restore_profiles(self.studio)[0]

    def test_restore_is_portable_idempotent_and_keeps_distinct_poses_and_canonical_base(self):
        self.assertEqual(restore_profiles(self.studio), [self.profile])
        self.assertEqual(self.profile["background"], self.profile["first"])
        self.assertNotEqual(self.profile["first"]["sha256"], self.profile["last"]["sha256"])
        public = public_profiles(self.studio)[0]
        self.assertEqual(public["last_scene_id"], self.end_scene["id"])
        self.assertEqual(public["mask_url"], f"/api/motion/{self.profile['id']}/mask")
        self.assertNotIn("background", public)
        self.assertEqual(get_profile(self.studio, self.profile["id"]), self.profile)

    def payload(self, **overrides):
        return {"scene_id": self.scene["id"], "label": "Recovered test", "prompt": self.profile["prompt"],
                "seed": 7, "request_id": "once", "motion_profile_id": self.profile["id"],
                "motion_vae_name": INT8_VAE, **overrides}

    def test_submit_pins_profile_and_explicit_vae_and_survives_reopen_without_submission(self):
        job = self.studio.submit(self.payload())
        self.assertEqual(self.studio.submit(self.payload())["id"], job["id"])
        pinned = job_profile(self.studio, job["id"])
        self.assertEqual(pinned["vae_name"], INT8_VAE)
        self.assertEqual(pinned["original_vae_name"], ORIGINAL_VAE)
        self.assertEqual(Studio(self.temp.name).job(job["id"])["pipeline"], "actor_motion_v1")
        self.assertEqual(self.studio.candidates(), [])

    def test_wrong_starting_scene_and_missing_vae_are_refused_before_queueing(self):
        with self.assertRaises(StudioError):
            self.studio.submit(self.payload(scene_id=self.end_scene["id"]))
        with self.assertRaises(StudioError):
            self.studio.submit(self.payload(motion_vae_name=ORIGINAL_VAE))
        with self.assertRaises(StudioError):
            self.studio.submit(self.payload(motion_vae_name="minimax_h3_audio_vae_fp32.safetensors"))
        self.assertEqual(self.studio.jobs(), [])

    def test_altered_mask_is_detected_before_generation(self):
        self.studio.store.resolve(self.profile["mask"]["path"]).write_bytes(b"changed")
        with self.assertRaises(StoreError):
            self.studio.submit(self.payload())
        self.assertEqual(self.studio.jobs(), [])

    def test_job_processing_dispatches_to_production_engine_with_pinned_inputs(self):
        job = self.studio.submit(self.payload())
        with patch("last_light_radio.motion_jobs.start_motion_generation") as start:
            self.studio.process_job(job["id"])
        start.assert_called_once()
        self.assertEqual(start.call_args.args[2]["first"], self.profile["first"])
        self.assertEqual(start.call_args.args[2]["last"], self.profile["last"])
        self.assertEqual(start.call_args.kwargs["local_job_id"], job["id"])
        self.assertEqual(self.studio.job(job["id"])["status"], "queued")


if __name__ == "__main__":
    unittest.main()
