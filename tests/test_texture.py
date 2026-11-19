"""Deterministic texture, legacy compatibility, persistence and CPU export."""

import copy
import json
from pathlib import Path
import shutil
import subprocess
import unittest

from PIL import Image

from last_light_radio import editor, pilots, texture
from last_light_radio.store import sha256
from last_light_radio.studio import Studio, StudioError
from last_light_radio.video_tools import ffmpeg_path
import test_editor as fixtures


SETTINGS = {"enabled": True, "strength": 0.65, "size": 2, "seed": 23}


class TextureTests(unittest.TestCase):
    def test_validation_rejects_ambiguous_or_nonfinite_controls(self):
        for patch in ({"enabled": 1}, {"strength": True}, {"strength": float("nan")},
                      {"strength": float("inf")}, {"strength": 1.01}, {"strength": -0.1},
                      {"size": 0}, {"size": 1.5}, {"seed": True}, {"seed": -1}, {"unknown": 2}):
            with self.subTest(patch=patch), self.assertRaises(StudioError):
                texture.settings({**SETTINGS, **patch})
        self.assertIsNone(texture.settings(None))

    def test_disabled_and_zero_strength_are_exact_passthrough(self):
        base = Image.new("RGB", (32, 24), (73, 91, 61)).tobytes()
        for value in (None, {**SETTINGS, "enabled": False}, {**SETTINGS, "strength": 0}):
            self.assertIsNone(texture.pin(value))
            self.assertEqual(texture.Compositor(texture.pin(value), (32, 24)).apply(base, 17), base)

    def test_seek_replay_seed_changes_and_strength_are_visible(self):
        base = Image.new("RGB", (64, 48), (73, 91, 61)).tobytes()
        compositor = texture.Compositor(texture.pin(SETTINGS), (64, 48))
        first = compositor.apply(base, 124)
        compositor.apply(base, 900)
        self.assertEqual(first, compositor.apply(base, 124))
        self.assertNotEqual(first, compositor.apply(base, 125))
        other = texture.Compositor(texture.pin({**SETTINGS, "seed": 24}), (64, 48))
        self.assertNotEqual(first, other.apply(base, 124))
        changes = []
        for strength in (0.1, 0.5, 1):
            output = texture.Compositor(texture.pin({**SETTINGS, "strength": strength}), (64, 48)).apply(base, 124)
            changes.append(sum(abs(a-b) for a, b in zip(base, output)))
        self.assertLess(changes[0], changes[1])
        self.assertLess(changes[1], changes[2])

    def test_unknown_recipe_fails_instead_of_silently_changing_the_look(self):
        for key, value in (("renderer_version", "missing"), ("blend", "other"), ("tile_size", 512), ("clock", "local_clip")):
            with self.subTest(key=key), self.assertRaises(ValueError):
                texture.Compositor({**texture.pin(SETTINGS), key: value}, (64, 48))

    @unittest.skipUnless(shutil.which("node"), "Cross-runtime pattern check requires the frontend Node runtime")
    def test_browser_and_export_have_identical_grain_and_frame_geometry(self):
        module = (Path(__file__).resolve().parents[1] / "frontend/src/videoTexture.ts").as_uri()
        program = """import {createHash} from 'node:crypto';
const m=await import(process.argv[1]);
const pixels=m.textureTile(23);
const gray=Uint8Array.from({length:pixels.length/4},(_,i)=>pixels[i*4]);
console.log(JSON.stringify({tile:createHash('sha256').update(gray).digest('hex'),offsets:[0,1,124,14400].map(f=>m.textureOffset(23,f))}));"""
        result = subprocess.run([shutil.which("node"), "--input-type=module", "-e", program, module],
                                capture_output=True, text=True, check=True, timeout=15)
        actual = json.loads(result.stdout)
        self.assertEqual(actual["tile"], sha256(texture.tile(23).tobytes()))
        self.assertEqual(actual["offsets"], [list(texture.offset(23, frame)) for frame in (0, 1, 124, 14400)])


class TextureEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.SubjectEditorTests.setUpClass.__func__(cls)

    def setUp(self):
        fixtures.SubjectEditorTests.setUp(self)

    def test_texture_round_trips_without_changing_motion_or_legacy_plan(self):
        plain = editor.plan(self.studio, self.payload)
        self.assertNotIn("texture", plain["sequence"]["manifest"])
        request = {**copy.deepcopy(self.payload), "expected_revision": 1, "texture": SETTINGS}
        textured = editor.plan(self.studio, request)
        self.assertNotEqual(plain["sequence_id"], textured["sequence_id"])
        self.assertEqual(plain["sequence"]["manifest"]["tracks"], textured["sequence"]["manifest"]["tracks"])
        self.assertEqual(textured["sequence"]["manifest"]["texture"], texture.pin(SETTINGS))
        reopened = editor.state(Studio(self.temp.name), self.scene["id"])
        self.assertEqual(reopened["config"]["texture"], SETTINGS)
        self.assertNotIn("texture", pilots.get(self.studio, plain["sequence_id"])["manifest"])

    def test_textured_hold_export_animates_and_retains_exact_timing(self):
        request = copy.deepcopy(self.payload)
        request["texture"] = SETTINGS
        for subject in request["subjects"]:
            subject["mode"] = "still"
        plan = editor.plan(self.studio, request)
        identity = plan["sequence_id"]
        original = self.studio.scene(self.scene["id"])["master"]
        pilots.queue_export(self.studio, identity)
        pilots.process_export(self.studio, identity)
        complete = pilots.get(self.studio, identity)
        self.assertEqual(complete["status"], "complete", complete.get("error"))
        folder = self.studio.store.resolve(f"exports/pilots/{identity}")
        report = json.loads((folder / "export_report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["texture"], texture.pin(SETTINGS))
        self.assertEqual(report["inspection"]["frame_count"], 96)
        self.assertTrue(report["inspection"]["presentation_timestamps_verified"])
        result = subprocess.run([ffmpeg_path(), "-v", "error", "-i", str(folder / "pilot.mp4"),
                                 "-frames:v", "24", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
                                capture_output=True, check=True, timeout=30)
        length = 64 * 48 * 3
        frames = [result.stdout[i:i+length] for i in range(0, len(result.stdout), length)]
        self.assertEqual(len(frames), 24)
        self.assertGreater(len({sha256(frame) for frame in frames}), 20)
        self.assertEqual(self.studio.scene(self.scene["id"])["master"], original)
        self.assertEqual(self.studio.jobs(), [])
