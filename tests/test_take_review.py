import copy
import io
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from last_light_radio.media import inspect_webp
from last_light_radio.motion_jobs import _encode_mp4
from last_light_radio.store import ProjectStore, StoreError, canonical_bytes, sha256
from last_light_radio.studio import StudioError
from last_light_radio.take_review import compare_takes, decoded_frame
from last_light_radio.video_tools import ffmpeg_path


ROOT = Path(__file__).resolve().parents[1]


def png(image):
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


class ReadOnlyStudio:
    """Minimal read surface; calling a production mutation cannot succeed."""

    def __init__(self, directory):
        self.store = ProjectStore(directory)
        self.rows = {}
        self.scenes = {}
        self.settings = {}

    def candidate(self, identity):
        return copy.deepcopy(self.rows[identity])

    def scene(self, identity):
        return copy.deepcopy(self.scenes[identity])

    def setting(self, name, default=None):
        return copy.deepcopy(self.settings.get(name, default))

    def reference(self, path, data):
        self.store.write_once(path, data)
        return {"path": path, "sha256": sha256(data)}


class TakeReviewTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=ROOT / "tests")
        self.addCleanup(temporary.cleanup)
        self.studio = ReadOnlyStudio(temporary.name)
        self.size = (8, 6)
        self.master = self.studio.reference("masters/scene.png", png(Image.new("RGB", self.size, (10, 10, 10))))
        self.scene_id = self.master["sha256"][:32]
        self.studio.scenes[self.scene_id] = {"id": self.scene_id, "master": self.master, "width": 8, "height": 6}
        mask = self.studio.reference("masters/mask.png", png(Image.new("L", self.size, 255)))
        self.profile = {"id": "profile-a", "family_id": "motion-family", "revision": 2,
                        "actor": "Button", "start_state": "off", "end_state": "off",
                        "first": self.master, "last": self.master, "mask": mask, "background": self.master,
                        "frames": 3, "fps": 25, "crop": {"x": 0, "y": 0, "width": 8, "height": 6}}
        a_end = Image.new("RGB", self.size, (10, 10, 10))
        a_end.putpixel((2, 3), (25, 10, 10))
        self.a_frames = [Image.new("RGB", self.size, (10, 10, 10)), Image.new("RGB", self.size, (60, 60, 60)), a_end]
        self.b_frames = [Image.new("RGB", self.size, (30, 30, 30)), Image.new("RGB", self.size, (80, 80, 80)), Image.new("RGB", self.size, (10, 10, 10))]
        self.add_take("a", self.a_frames, "candidate")
        self.add_take("b", self.b_frames, "rejected")

    def add_take(self, identity, frames, status):
        buffer = io.BytesIO()
        frames[0].save(buffer, "WEBP", save_all=True, append_images=frames[1:], duration=40, loop=0, lossless=True)
        data = buffer.getvalue()
        output = {**self.studio.reference(f"candidates/{identity}/assembled.webp", data), "properties": inspect_webp(data)}
        samples = {part: {**self.studio.reference(f"candidates/{identity}/{part}.png", png(frames[index])), "frame_index": index}
                   for part, index in (("start", 0), ("end", len(frames) - 1))}
        self.studio.rows[identity] = {"id": identity, "label": "Take " + identity.upper(), "scene_id": self.scene_id,
                                      "status": status, "version": int(status == "rejected"),
                                      "metadata": {"master": self.master, "outputs": [output],
                                                   "motion": {"profile": copy.deepcopy(self.profile), "lossless_samples": samples}}}

    def checks(self, result):
        return {check["id"]: check for check in result["checks"]}

    def tree(self):
        return {str(path.relative_to(self.studio.store.root)): path.read_bytes()
                for path in self.studio.store.root.rglob("*") if path.is_file()}

    def test_pending_and_rejected_take_comparison_is_advisory_and_read_only(self):
        files, records = self.tree(), canonical_bytes(self.studio.rows)
        result = compare_takes(self.studio, "a", "b")
        self.assertTrue(result["advisory_only"])
        self.assertTrue(result["same_motion"])
        self.assertEqual(result["takes"]["a"]["source"], "decoded_webp")
        self.assertEqual((result["takes"]["b"]["status"], result["takes"]["b"]["version"]), ("rejected", 1))
        self.assertIn("not make it eligible", " ".join(result["warnings"]))
        self.assertEqual(files, self.tree())
        self.assertEqual(records, canonical_bytes(self.studio.rows))
        self.assertEqual(result, compare_takes(self.studio, "a", "b"))

    def test_exact_pixel_metrics_and_explicit_region_do_not_invent_quality_thresholds(self):
        result = compare_takes(self.studio, "a", "b", {"x": 2, "y": 3, "width": 1, "height": 1})
        checks = self.checks(result)
        self.assertEqual(checks["a_loop"]["pixels"], 1)
        self.assertEqual(checks["a_loop"]["changed_pixels"], 1)
        self.assertEqual(checks["a_loop"]["mean_absolute_error"], 5)
        self.assertEqual(checks["a_loop"]["max_channel_difference"], 15)
        self.assertEqual(checks["a_exit_b_entry"]["mean_absolute_error"], 15)
        self.assertTrue(checks["a_start_encoding"]["exact_match"])
        full = self.checks(compare_takes(self.studio, "a", "b"))["a_loop"]
        self.assertEqual((full["pixels"], full["changed_pixels"]), (48, 1))
        self.assertNotIn("passed", full)
        self.assertNotIn("approved", full)

    def test_exact_frame_decodes_full_assembled_output_and_validates_range(self):
        for index, expected in enumerate(self.a_frames):
            with Image.open(io.BytesIO(decoded_frame(self.studio, "a", index))) as actual:
                self.assertEqual(actual.convert("RGB").tobytes(), expected.tobytes())
        for invalid in (-1, 3, 0.5, True, "0"):
            with self.subTest(index=invalid), self.assertRaises(StudioError):
                decoded_frame(self.studio, "a", invalid)

    def test_legacy_profile_resolution_does_not_restore_or_write_missing_samples(self):
        for identity in ("a", "b"):
            profile = {**self.profile, "reference_candidate_id": identity}
            reference = self.studio.store.save_snapshot(profile)
            self.studio.settings.setdefault("motion_profile_refs", []).append(reference)
            self.studio.rows[identity]["metadata"].pop("motion")
        before = self.tree()
        result = compare_takes(self.studio, "a", "b")
        self.assertEqual(len(result["checks"]), 7)
        self.assertEqual(self.checks(result)["a_loop"]["changed_pixels"], 1)
        self.assertIn("no pinned lossless", " ".join(result["warnings"]))
        self.assertEqual(before, self.tree())

    def test_compatible_other_motion_family_and_different_duration_are_visible(self):
        profile = self.studio.rows["b"]["metadata"]["motion"]["profile"]
        profile.update({"id": "other", "family_id": "other", "actor": "button"})
        profile["frames"] = 39  # A source recipe can have a differently timed take.
        result = compare_takes(self.studio, "a", "b")
        self.assertFalse(result["same_motion"])
        self.assertEqual(result["takes"]["b"]["frame_count"], 3)
        self.assertIn("different motion families", " ".join(result["warnings"]))

    def test_incompatible_subject_states_poses_and_scene_are_refused(self):
        original = copy.deepcopy(self.studio.rows["b"]["metadata"]["motion"]["profile"])
        other = self.studio.reference("masters/other.png", png(Image.new("RGB", self.size, (11, 11, 11))))
        for key, value in (("actor", "Knob"), ("end_state", "on"), ("last", other), ("background", other)):
            self.studio.rows["b"]["metadata"]["motion"]["profile"] = {**original, key: value}
            with self.subTest(field=key), self.assertRaises(StudioError):
                compare_takes(self.studio, "a", "b")
        with self.assertRaises(StudioError):
            compare_takes(self.studio, "a", "a")

    def test_missing_or_changed_pinned_assets_and_missing_recipes_fail_visibly(self):
        for part in ("output", "lossless"):
            with self.subTest(part=part):
                row = self.studio.rows["a"]["metadata"]
                ref = row["outputs"][0] if part == "output" else row["motion"]["lossless_samples"]["end"]
                path = self.studio.store.resolve(ref["path"])
                data = path.read_bytes()
                path.write_bytes(b"changed")
                with self.assertRaises(StoreError):
                    compare_takes(self.studio, "a", "b")
                path.write_bytes(data)
        self.studio.rows["a"]["metadata"].pop("motion")
        with self.assertRaisesRegex(StudioError, "pinned motion recipe"):
            compare_takes(self.studio, "a", "b")

    def test_wrong_saved_frame_indices_and_decoded_frame_counts_are_refused(self):
        samples = self.studio.rows["a"]["metadata"]["motion"]["lossless_samples"]
        samples["end"]["frame_index"] = 1
        with self.assertRaisesRegex(StudioError, "frame index"):
            compare_takes(self.studio, "a", "b")
        samples["end"]["frame_index"] = 2
        self.studio.rows["a"]["metadata"]["outputs"][0]["properties"]["frame_count"] = 4
        with self.assertRaisesRegex(StudioError, "frame count"):
            compare_takes(self.studio, "a", "b")

    def test_invalid_regions_are_refused_before_decoding(self):
        for region in ([], {}, {"x": -1, "y": 0, "width": 1, "height": 1}, {"x": 0, "y": 0, "width": 9, "height": 1},
                       {"x": True, "y": 0, "width": 1, "height": 1}, {"x": 0, "y": 0, "width": 0, "height": 1}):
            with self.subTest(region=region), self.assertRaises(StudioError), patch("last_light_radio.take_review._decode", side_effect=AssertionError("decoded invalid request")):
                compare_takes(self.studio, "a", "b", region)

    def test_concurrent_review_change_refuses_stale_report(self):
        original = self.studio.candidate
        calls = []

        def changed(identity):
            calls.append(identity)
            result = original(identity)
            if len(calls) > 2:
                result.update({"status": "approved", "version": 2})
            return result

        self.studio.candidate = changed
        with self.assertRaisesRegex(StudioError, "changed during comparison"):
            compare_takes(self.studio, "a", "b")

    def test_real_mp4_exact_frame_and_boundary_checks_use_decoded_media(self):
        try:
            ffmpeg_path()
        except ValueError as error:
            self.skipTest(str(error))
        for identity, frames in (("a", self.a_frames), ("b", self.b_frames)):
            output = _encode_mp4(self.studio.store, f"candidates/{identity}/fixture.mp4", iter(frames), self.size, 25)
            output["properties"] = {"container": "mp4", "frame_count": 3, "effective_fps": 25, "width": 8, "height": 6}
            self.studio.rows[identity]["metadata"]["outputs"] = [output]
        before = self.tree()
        result = compare_takes(self.studio, "a", "b")
        self.assertEqual(result["takes"]["a"]["source"], "decoded_video")
        self.assertEqual(result["takes"]["a"]["frames"]["exit"], "/api/candidates/a/frames/2")
        with Image.open(io.BytesIO(decoded_frame(self.studio, "a", 1))) as frame:
            self.assertGreater(frame.getpixel((0, 0))[0], 40)
        # Encoding deltas are explicitly separate from the saved lossless sample.
        self.assertIn("a_end_encoding", self.checks(result))
        self.assertEqual(before, self.tree())

    def test_decoder_timeouts_become_visible_studio_errors(self):
        self.studio.rows["a"]["metadata"]["outputs"][0]["properties"]["container"] = "mp4"
        error = subprocess.TimeoutExpired("ffmpeg", 90)
        with patch("last_light_radio.take_review.subprocess.run", side_effect=error):
            with self.assertRaisesRegex(StudioError, "timed out"):
                decoded_frame(self.studio, "a", 1)
        with patch("last_light_radio.take_review.inspect_video", side_effect=error):
            with self.assertRaisesRegex(StudioError, "timed out"):
                compare_takes(self.studio, "a", "b")

    def test_exact_frame_decode_slots_bound_concurrent_requests_and_report_busy(self):
        self.studio.rows["a"]["metadata"]["outputs"][0]["properties"]["container"] = "mp4"
        slots = threading.BoundedSemaphore(2)
        both_running, finish = threading.Event(), threading.Event()
        lock = threading.Lock()
        entered, results, errors = [], [], []

        def blocked_decoder(*args, **kwargs):
            with lock:
                entered.append(1)
                if len(entered) == 2:
                    both_running.set()
            if not finish.wait(3):
                raise AssertionError("Test did not release its blocked decoder")
            return SimpleNamespace(returncode=0, stderr=b"", stdout=bytes([10]) * (8 * 6 * 3))

        def request():
            try:
                results.append(decoded_frame(self.studio, "a", 1))
            except Exception as error:
                errors.append(error)

        with patch("last_light_radio.take_review._DECODE_SLOTS", slots), \
                patch("last_light_radio.take_review._DECODE_WAIT_SECONDS", 0.02), \
                patch("last_light_radio.take_review.subprocess.run", side_effect=blocked_decoder):
            threads = [threading.Thread(target=request) for _ in range(2)]
            for thread in threads:
                thread.start()
            try:
                self.assertTrue(both_running.wait(2), "Both available decode slots should be usable")
                with self.assertRaises(StudioError) as busy:
                    decoded_frame(self.studio, "a", 1)
                self.assertEqual(busy.exception.status, 503)
                self.assertEqual(len(entered), 2, "The third decoder must not start")
            finally:
                finish.set()
                for thread in threads:
                    thread.join(3)
            self.assertEqual(errors, [])
            self.assertEqual(len(results), 2)
            self.assertTrue(all(data.startswith(b"\x89PNG") for data in results))
            self.assertTrue(slots.acquire(blocking=False))
            self.assertTrue(slots.acquire(blocking=False))
            self.assertFalse(slots.acquire(blocking=False))
            slots.release()
            slots.release()

    def test_failed_exact_decoders_release_slots_for_later_requests(self):
        self.studio.rows["a"]["metadata"]["outputs"][0]["properties"]["container"] = "mp4"
        slots = threading.BoundedSemaphore(2)
        with patch("last_light_radio.take_review._DECODE_SLOTS", slots), \
                patch("last_light_radio.take_review._DECODE_WAIT_SECONDS", 0.02), \
                patch("last_light_radio.take_review.subprocess.run", side_effect=subprocess.TimeoutExpired("ffmpeg", 90)):
            for _ in range(4):
                with self.assertRaisesRegex(StudioError, "timed out") as failed:
                    decoded_frame(self.studio, "a", 1)
                self.assertEqual(failed.exception.status, 409)
            self.assertTrue(slots.acquire(blocking=False))
            self.assertTrue(slots.acquire(blocking=False))
            self.assertFalse(slots.acquire(blocking=False))
            slots.release()
            slots.release()


if __name__ == "__main__":
    unittest.main()
