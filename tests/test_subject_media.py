import copy
import io
import json
import threading
import unittest
from unittest.mock import patch

from PIL import Image, ImageChops

import test_pilots as fixtures
from last_light_radio import ambience, editor, pilots, subject_media
from last_light_radio.motion_jobs import _encode_mp4
from last_light_radio.motion_profiles import INT8_VAE, get_profile
from last_light_radio.pilot_media import inspect_video, video_rgb
from last_light_radio.recipes import save_recipe
from last_light_radio.store import sha256


class SubjectMediaTests(unittest.TestCase):
    def setUp(self):
        fixtures.PilotTests.setUp(self)
        self.cat_id = "2" * 32
        saved = save_recipe(self.studio, {"scene_id": self.scene["id"], "actor": "Cat", "name": "Cat idle",
                "template_id": "idle", "start_state": "resting", "end_state": "resting",
                "polygon": [[42, 10], [57, 10], [57, 30], [42, 30]], "feather": 2, "context": 0.25,
                "prompt": "A subtle breath", "seed": 8, "frames": 39, "vae_name": INT8_VAE})
        profile = get_profile(self.studio, saved["id"])
        images = [Image.new("RGB", self.master.size, color) for color in ((110, 70, 40), (130, 80, 50), (150, 90, 60))]
        output = _encode_mp4(self.studio.store, "cat-fixture.mp4", iter(images), self.master.size, 24)
        output["properties"] = {"container": "mp4", "width": 64, "height": 48, "frame_count": 3,
                                "effective_fps": 24, "duration_seconds": 3 / 24}
        metadata = {"local_job_id": self.cat_id, "master": self.scene["master"], "workflow_sha256": "b" * 64,
                    "outputs": [output], "parameters": {"seed": 8}, "motion": {"profile": profile}}
        self.studio.register_candidate(self.scene["id"], "Approved cat idle", metadata)
        self.studio.review(self.cat_id, {"decision": "approved", "entry_anchor": "resting", "exit_anchor": "resting",
                    "visual_checked": True, "notes": "Synthetic fixture", "expected_version": 0, "request_id": "cat-approve"})
        payload = {"scene_id": self.scene["id"], "title": "Independent subjects", "duration_frames": 25,
                   "seed": 7, "expected_revision": 0, "placements": [], "ambience": [],
                   "subjects": [{"actor": "Reader", "mode": "spaced", "seed": 7, "pool": [self.identity]},
                                {"actor": "Cat", "mode": "spaced", "seed": 8, "pool": [self.cat_id]}]}
        self.sequence = editor.plan(self.studio, payload)["sequence"]
        self.manifest = self.sequence["manifest"]

    def save_image(self, image, path):
        data = io.BytesIO()
        image.save(data, "PNG")
        self.studio.store.write_once(path, data.getvalue())
        return {"path": path, "sha256": sha256(data.getvalue())}

    def test_independent_takes_preserve_every_protected_pixel_and_actual_exit_holds(self):
        checks = []
        rendered = list(subject_media.subject_frames(self.studio.store, self.manifest, self.studio.stop_event, hold_checks=checks))
        self.assertEqual(len(rendered), 25)
        self.assertEqual(len(checks), 2)
        self.assertTrue(all(c["matches_current_rgb"] and c["frames"] == 22 for c in checks))
        union = Image.new("L", self.master.size)
        expected = [self.master.copy() for _ in range(3)]
        for clip in self.manifest["clips"]:
            with Image.open(self.studio.store.resolve(clip["mask"]["path"])) as image:
                mask = image.convert("L")
            self.assertEqual(set(mask.tobytes()), {0, 255})
            union = ImageChops.lighter(union, mask)
            decoded = list(video_rgb(self.studio.store, clip["output"], self.master.size, self.studio.stop_event))
            for frame, data in enumerate(decoded):
                expected[frame].paste(Image.frombytes("RGB", self.master.size, data), (0, 0), mask)
        self.assertEqual(rendered[:3], [image.tobytes() for image in expected])
        self.assertTrue(all(data == rendered[2] for data in rendered[3:]))
        protected = ImageChops.invert(union)
        for data in rendered:
            delta = ImageChops.difference(self.master, Image.frombytes("RGB", self.master.size, data))
            self.assertIsNone(Image.composite(delta, Image.new("RGB", self.master.size), protected).getbbox())
        # Track order cannot change occlusion when supports are truly disjoint.
        reversed_manifest = copy.deepcopy(self.manifest)
        reversed_manifest["tracks"].reverse()
        self.assertEqual(rendered, list(subject_media.subject_frames(self.studio.store, reversed_manifest, self.studio.stop_event)))
        self.assertEqual(self.studio.jobs(), [])

    def test_overlapping_or_nonbinary_masks_fail_instead_of_blending_twice(self):
        overlapping = copy.deepcopy(self.manifest)
        overlapping["clips"][1]["mask"] = overlapping["clips"][0]["mask"]
        with self.assertRaisesRegex(ValueError, "overlap"):
            list(subject_media.subject_frames(self.studio.store, overlapping, self.studio.stop_event))
        feathered = copy.deepcopy(self.manifest)
        feathered["clips"][0]["mask"] = self.save_image(Image.new("L", self.master.size, 128), "invalid-soft-support.png")
        with self.assertRaisesRegex(ValueError, "binary"):
            list(subject_media.subject_frames(self.studio.store, feathered, self.studio.stop_event))

    def test_invalid_holds_and_retimed_takes_fail_visibly(self):
        wrong_hold = copy.deepcopy(self.manifest)
        wrong_hold["tracks"][0]["events"][1]["frame_image"] = self.scene["master"]
        with self.assertRaisesRegex(ValueError, "actual current decoded frame"):
            list(subject_media.subject_frames(self.studio.store, wrong_hold, self.studio.stop_event))
        retimed = copy.deepcopy(self.manifest)
        events = retimed["tracks"][0]["events"]
        events[0]["end_frame"] += 1
        events[1]["start_frame"] += 1
        with self.assertRaisesRegex(ValueError, "pinned approved take"):
            list(subject_media.subject_frames(self.studio.store, retimed, self.studio.stop_event))
        missing = copy.deepcopy(self.manifest)
        missing["tracks"][0]["events"] = missing["tracks"][0]["events"][:1]
        with self.assertRaisesRegex(ValueError, "exact sequence duration"):
            list(subject_media.subject_frames(self.studio.store, missing, self.studio.stop_event))

    def test_stopped_render_and_closed_preview_release_all_decoders(self):
        cancelled = threading.Event()
        cancelled.set()
        with self.assertRaises(InterruptedError):
            list(subject_media.subject_frames(self.studio.store, self.manifest, cancelled))
        closed = []
        def decoder(store, output, size, stop_event):
            try:
                for _ in range(3):
                    yield self.master.tobytes()
            finally:
                closed.append(output["path"])
        with patch("last_light_radio.subject_media.video_rgb", side_effect=decoder):
            frames = subject_media.subject_frames(self.studio.store, self.manifest, self.studio.stop_event)
            next(frames)
            frames.close()
        self.assertEqual(len(closed), 2)

    def test_export_routes_to_subject_renderer_and_does_not_mix_legacy_pilot_list(self):
        self.assertEqual(pilots.listing(self.studio), [])
        self.assertEqual(pilots.listing(self.studio, all_kinds=True)[0]["kind"], "studio_subject_sequence")
        before = self.studio.candidates()
        pilots.queue_export(self.studio, self.sequence["id"])
        pilots.process_export(self.studio, self.sequence["id"])
        complete = pilots.get(self.studio, self.sequence["id"])
        self.assertEqual(complete["status"], "complete", complete["error"])
        path, _ = pilots.media(self.studio, complete["id"], "media")
        report = json.loads(path.with_name("export_report.json").read_text())
        self.assertEqual(report["renderer_version"], subject_media.VERSION)
        self.assertEqual(report["inspection"]["frame_count"], 25)
        self.assertEqual(report["subject_tracks"], ["Reader", "Cat"])
        self.assertEqual(len(report["hold_checks"]), 2)
        self.assertEqual(self.studio.candidates(), before)
        self.assertEqual(self.studio.jobs(), [])

    def test_steam_pauses_keep_absolute_clock_and_resume_at_exact_boundary(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["steam_pauses"] = [[1, 4]]
        seen = []
        original = ambience.Compositor.apply
        def apply(compositor, data, frame, *, disabled_kinds=()):
            seen.append((frame, disabled_kinds))
            return original(compositor, data, frame, disabled_kinds=disabled_kinds)
        path = self.studio.store.resolve("steam-pause-export.mp4")
        with patch("last_light_radio.ambience.Compositor.apply", new=apply):
            report = subject_media.encode_subjects(self.studio.store, manifest, path, self.studio.stop_event, lambda _: None)
        self.assertEqual(seen, [(frame, ("steam",) if 1 <= frame < 4 else ()) for frame in range(25)])
        self.assertEqual(report["steam_pauses"], [[1, 4]])
        inspect_video(path, 25, 24, (64, 48))

    def test_suppressing_fixed_steam_preserves_rain_and_does_not_reset_phase(self):
        rain_mask = Image.new("L", self.master.size)
        rain_mask.paste(255, (0, 0, 32, 48))
        steam_mask = Image.new("L", self.master.size)
        steam_mask.paste(255, (36, 4, 62, 40))
        rain_ref = self.save_image(rain_mask, "rain-mask.png")
        steam_ref = self.save_image(steam_mask, "steam-mask.png")
        recipe = {"renderer_version": ambience.LEGACY_VERSION, "layers": [
            {"kind": "rain", "opacity": 0.3, "bounds": [0, 0, 32, 48], "mask": rain_ref, "source_mask": rain_ref,
             "particles": [{"x": 0.5, "y": 0.5, "speed": 0.2, "length": 0.2, "alpha": 1}]},
            {"kind": "steam", "opacity": 0.3, "bounds": [36, 4, 62, 40], "mask": steam_ref, "source_mask": steam_ref,
             "particles": [{"phase": 0.5}]}]}
        source = Image.new("RGB", self.master.size)
        source.putdata([(x * 3, y * 4, (x + y) * 2) for y in range(48) for x in range(64)])
        base = source.tobytes()
        compositor = ambience.Compositor(self.studio.store, recipe, self.master.size, 24)
        only_rain = ambience.Compositor(self.studio.store, {**recipe, "layers": recipe["layers"][:1]}, self.master.size, 24)
        self.assertEqual(compositor.apply(base, 213, disabled_kinds=("steam", "rain")), base)
        self.assertEqual(compositor.apply(base, 213, disabled_kinds=("steam",)), only_rain.apply(base, 213))
        self.assertNotEqual(compositor.apply(base, 213), compositor.apply(base, 213, disabled_kinds=("steam",)))
        before = compositor.apply(base, 214)
        compositor.apply(base, 100, disabled_kinds=("steam",))
        self.assertEqual(compositor.apply(base, 214), before)


if __name__ == "__main__":
    unittest.main()
