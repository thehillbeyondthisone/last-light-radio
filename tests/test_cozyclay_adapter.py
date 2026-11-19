"""Offline ZIP/import acceptance; no browser, Comfy installation or GPU needed."""

import copy
import contextlib
import io
import json
import stat
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from last_light_radio.cozyclay_adapter import (CozyClayError, import_keyframe_pack,
                                               inspect_keyframe_pack, main, verify_source_package)
from last_light_radio.motion_jobs import prepare_motion_inputs
from last_light_radio.motion_profiles import INT8_VAE, get_profile, profiles
from last_light_radio.store import StoreError, canonical_bytes, sha256
from last_light_radio.studio import Studio

ROOT = Path(__file__).resolve().parents[1]


def plate(color="navy", size=(160, 120), mode="RGB"):
    stream = io.BytesIO()
    Image.new(mode, size, color).save(stream, "PNG")
    return stream.getvalue()


def camera(frames=124):
    framing = {"pos": {"x": 0, "y": 1.5, "z": 3}, "yaw": 0, "pitch": -0.1, "fovDeg": 45}
    return {"startFrame": 0, "endFrame": frames - 1, "fps": 24,
            "size": {"width": 160, "height": 120}, "cameraMove": {"dolly": False, "crane": False, "rail": False},
            "framing": {"start": framing, "end": copy.deepcopy(framing)}}


def pack(*, metadata=None, first=None, last=None, extra=None, omit=(), compression=zipfile.ZIP_STORED):
    stream = io.BytesIO()
    members = {"first.png": plate() if first is None else first,
               "last.png": plate() if last is None else last,
               "camera.json": json.dumps(camera() if metadata is None else metadata).encode(),
               "prompt.txt": b"A rigid slider moves right, touches its stop, and returns. Locked camera.\n"}
    members.update(extra or {})
    with zipfile.ZipFile(stream, "w", compression=compression) as archive:
        for name, value in members.items():
            if name not in omit:
                archive.writestr("1-slider/" + name, value)
    return stream.getvalue()


class CozyClayAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / "tests")
        self.addCleanup(self.temp.cleanup)
        self.studio = Studio(self.temp.name, client_factory=lambda *_a, **_k: self.fail("No network client may be created"))
        self.options = {"name": "Cozy slider", "actor": "Slider", "start_state": "rest", "end_state": "rest",
                        "seed": 883700, "polygon": [[35, 35], [125, 35], [125, 95], [35, 95]],
                        "feather": 0, "context": 0.25, "vae_name": INT8_VAE}

    def load(self, data=None, **kwargs):
        return import_keyframe_pack(self.studio, pack() if data is None else data, self.options,
                                    fixed_camera_acknowledged=True, **kwargs)

    def test_inspection_has_exact_timing_without_writes_or_jobs(self):
        before = list(self.studio.store.root.rglob("*"))
        report = inspect_keyframe_pack(pack())
        self.assertEqual((report["frames"], report["fps"]), (124, 24))
        self.assertEqual(report["duration_seconds"], 124 / 24)
        self.assertTrue(report["requires_fixed_camera_acknowledgement"])
        self.assertFalse(report["submitted"])
        self.assertEqual(self.studio.scenes(), [])
        self.assertEqual(self.studio.jobs(), [])
        self.assertEqual(before, list(self.studio.store.root.rglob("*")))

    def test_native_save_reopen_and_content_id_include_source_before_hash(self):
        data = pack(extra={"clip.mp4": b"review-only-reference"})
        result = self.load(data, expected_sha256=sha256(data), producer={"version": "3.1.2", "commit": "a" * 40})
        profile = get_profile(self.studio, result["profile"]["id"])
        self.assertEqual(profile["source_package"]["package"]["sha256"], sha256(data))
        self.assertIn("unsupported_H3_input", profile["source_package"]["reference_clip_usage"])
        unhashed = {k: v for k, v in profile.items() if k not in {"id", "family_id"}}
        self.assertEqual(profile["id"], sha256(canonical_bytes(unhashed))[:32])
        self.assertEqual(prepare_motion_inputs(self.studio.store, profile)["first_crop"].size, (768, 768))
        reopened = Studio(self.temp.name)
        self.assertEqual(get_profile(reopened, profile["id"]), profile)
        self.assertEqual(verify_source_package(reopened, profile)["frames"], 124)
        self.assertEqual(self.load(data, producer={"version": "3.1.2", "commit": "a" * 40})["profile"]["id"], profile["id"])
        self.assertEqual(len(profiles(reopened)), 1)
        self.assertEqual(reopened.jobs(), [])
        self.assertEqual(reopened.candidates(), [])

    def test_transition_preserves_different_endpoints_and_states(self):
        self.options["end_state"] = "right"
        result = self.load(pack(last=plate("orange")))
        profile = get_profile(self.studio, result["profile"]["id"])
        self.assertEqual(profile["role"], "transition")
        self.assertNotEqual(profile["first_scene_id"], profile["last_scene_id"])
        self.assertEqual(profile["start_state"], "rest")
        self.assertEqual(profile["end_state"], "right")

    def test_unsupported_or_inconsistent_timing_refuses_without_import(self):
        changes = [{"fps": 30}, {"fps": True}, {"startFrame": -1}, {"endFrame": 119},
                   {"frameRange": {"start": 0, "end": 122}}, {"endFrame": 123.0}, {"kind": "still"}]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(CozyClayError):
                self.load(pack(metadata={**camera(), **change}))
        for count in (39, 90, 124):
            self.assertEqual(inspect_keyframe_pack(pack(metadata=camera(count)))["frames"], count)
        self.assertEqual(self.studio.scenes(), [])

    def test_camera_moves_nonfinite_values_and_missing_framing_refuse(self):
        samples = [camera(), camera(), camera(), camera(), camera()]
        samples[0]["framing"]["end"]["pos"]["x"] = 0.1
        samples[1]["cameraMove"]["rail"] = True
        samples[2]["framing"]["start"]["yaw"] = float("nan")
        del samples[3]["framing"]
        samples[4]["framing"]["start"]["pos"]["x"] = -(10 ** 400)
        for sample in samples:
            with self.subTest(sample=sample), self.assertRaises(CozyClayError):
                self.load(pack(metadata=sample))
        self.assertEqual(self.studio.scenes(), [])

    def test_camera_endpoint_tolerance_only_accepts_numerical_roundoff(self):
        metadata = camera()
        metadata["framing"]["end"]["pos"]["x"] = 8.881784197001252e-16
        report = inspect_keyframe_pack(pack(metadata=metadata))
        self.assertEqual(report["camera_endpoint_component_epsilon"], 1e-12)
        metadata["framing"]["end"]["pos"]["x"] = 1e-10
        with self.assertRaisesRegex(CozyClayError, "Moving-camera"):
            inspect_keyframe_pack(pack(metadata=metadata))

    def test_opaque_equal_geometry_and_required_members(self):
        cases = [pack(last=plate(size=(161, 120))), pack(first=b"broken"), pack(omit={"last.png"}),
                 pack(first=plate((1, 2, 3, 0), mode="RGBA")), pack(extra={"rig.fbx": b"not allowed"}),
                 pack(extra={"clip.mp4": b"one", "clip.webm": b"two"})]
        for value in cases:
            with self.subTest(size=len(value)), self.assertRaises(CozyClayError):
                self.load(value)
        self.assertEqual(self.studio.scenes(), [])

    def test_traversal_duplicate_symlink_and_multiple_shots_are_refused(self):
        for name in ("../escape.png", "/absolute.png", "C:/drive.png", "1-slider\\escape.png", "2-other/extra.txt", "1-slider/first.png"):
            stream = io.BytesIO(pack())
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                with zipfile.ZipFile(stream, "a") as archive:
                    archive.writestr(name, b"bad")
            with self.subTest(name=name), self.assertRaises(CozyClayError):
                self.load(stream.getvalue())
        stream = io.BytesIO(pack())
        with zipfile.ZipFile(stream, "a") as archive:
            link = zipfile.ZipInfo("1-slider/README.txt")
            link.create_system = 3
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(link, "elsewhere")
        with self.assertRaises(CozyClayError):
            self.load(stream.getvalue())
        self.assertEqual(self.studio.scenes(), [])

    def test_archive_size_and_compression_bombs_are_refused(self):
        with patch("last_light_radio.cozyclay_adapter.MAX_ZIP_BYTES", 20), self.assertRaises(CozyClayError):
            self.load()
        with self.assertRaisesRegex(CozyClayError, "expansion|compression"):
            self.load(pack(extra={"clip.mp4": bytes(2 * 1024 * 1024)}, compression=zipfile.ZIP_DEFLATED))
        self.assertEqual(self.studio.scenes(), [])

    def test_fixed_camera_ack_and_source_checksum_required_before_writes(self):
        with self.assertRaisesRegex(CozyClayError, "Acknowledge"):
            import_keyframe_pack(self.studio, pack(), self.options)
        with self.assertRaisesRegex(CozyClayError, "checksum changed"):
            self.load(expected_sha256="0" * 64)
        self.assertEqual(self.studio.scenes(), [])

    def test_invalid_recipe_options_leave_no_partial_imports(self):
        for change in ({"seed": True}, {"vae_name": "guessed"}, {"end_state": "different"}, {"polygon": []},
                       {"feather": -1}, {"context": float("nan")}, {"frames": 120}, {"name": ""}):
            original = self.options
            self.options = {**original, **change}
            with self.subTest(change=change), self.assertRaises(Exception):
                self.load()
            self.options = original
        self.assertEqual(self.studio.scenes(), [])
        self.assertEqual(profiles(self.studio), [])

    def test_tampered_source_member_and_source_archive_are_visible(self):
        result = self.load()
        profile = get_profile(self.studio, result["profile"]["id"])
        reference = profile["source_package"]["members"]["prompt.txt"]
        self.studio.store.resolve(reference["path"]).write_bytes(b"changed")
        with self.assertRaises(StoreError):
            verify_source_package(self.studio, profile)
        source = profile["source_package"]["package"]
        self.studio.store.resolve(source["path"]).write_bytes(b"changed archive")
        with self.assertRaises(StoreError):
            verify_source_package(self.studio, profile)

    def test_reference_video_prompt_requires_explicit_text_adaptation(self):
        data = pack(extra={"prompt.txt": b"SHOT: slider\nCAMERA: follow reference clip\nMOTION: motion and blocking come from the reference; keep timing\n"})
        with self.assertRaisesRegex(CozyClayError, "motion_direction"):
            self.load(data)
        self.options["motion_direction"] = "Move the slider right, pause against its stop, then return left."
        result = self.load(data)
        profile = get_profile(self.studio, result["profile"]["id"])
        self.assertIn("come from the reference", profile["source_package"]["source_prompt"])
        self.assertNotIn("come from the reference", profile["prompt"])
        self.assertIn(self.options["motion_direction"], profile["prompt"])
        self.assertEqual(self.studio.jobs(), [])

    def test_cli_inspection_is_read_only_and_import_saves_without_submission(self):
        source = Path(self.temp.name) / "source.zip"
        source.write_bytes(pack())
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main([str(source), "--inspect-only"]), 0)
        self.assertFalse(json.loads(output.getvalue())["submitted"])
        self.assertEqual(self.studio.scenes(), [])
        target = Path(self.temp.name) / "cli-store"
        output = io.StringIO()
        args = [str(source), "--store", str(target), "--name", "CLI slider", "--actor", "Slider",
                "--start-state", "rest", "--end-state", "rest", "--seed", "7", "--vae", "int8",
                "--polygon", json.dumps(self.options["polygon"]), "--fixed-camera"]
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(args), 0)
        result = json.loads(output.getvalue())
        self.assertFalse(result["submitted"])
        reopened = Studio(target)
        self.assertEqual(len(profiles(reopened)), 1)
        self.assertEqual(reopened.jobs(), [])
        self.assertEqual(reopened.candidates(), [])

    def test_cli_missing_camera_ack_does_not_create_target_store(self):
        source = Path(self.temp.name) / "source.zip"
        source.write_bytes(pack())
        target = Path(self.temp.name) / "must-not-exist"
        args = [str(source), "--store", str(target), "--name", "CLI slider", "--actor", "Slider",
                "--start-state", "rest", "--end-state", "rest", "--seed", "7", "--vae", "int8",
                "--polygon", json.dumps(self.options["polygon"])]
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(args), 2)
        self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
