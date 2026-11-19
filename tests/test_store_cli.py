import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from last_light_radio.cli import ROOT, main
from last_light_radio.store import ProjectStore, StoreError


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / "tests")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = ProjectStore(self.root / "project")
        self.source = self.root / "original.ppm"
        self.source.write_bytes(b"P3\n1 1\n255\n255 0 0\n")

    def test_master_copy_is_independent_and_tampering_is_visible(self):
        before = self.source.read_bytes()
        master = self.store.import_master(self.source)
        self.assertEqual(self.source.read_bytes(), before)
        self.source.write_bytes(b"changed source")
        self.assertEqual(self.store.resolve(master["path"]).read_bytes(), before)
        self.store.verify_master(master)
        self.store.resolve(master["path"]).write_bytes(b"tampered master")
        with self.assertRaisesRegex(StoreError, "checksum mismatch"):
            self.store.verify_master(master)

    def test_existing_immutable_files_are_not_replaced(self):
        first = self.store.import_master(self.source)
        self.assertEqual(first, self.store.import_master(self.source))
        with self.assertRaisesRegex(StoreError, "Refusing to overwrite"):
            self.store.write_once(first["path"], b"replacement")
        self.store.verify_master(first)

    def test_interrupted_write_can_retry_without_partial_final_file(self):
        with patch("last_light_radio.store.os.fsync", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.store.write_once("records/retry.json", b"complete record")
        self.assertFalse(self.store.resolve("records/retry.json").exists())
        path = self.store.write_once("records/retry.json", b"complete record")
        self.assertEqual(path.read_bytes(), b"complete record")

    def test_snapshots_are_stable_and_portable(self):
        record = {"world": "fixture", "revision": 1, "facts": []}
        reference = self.store.save_snapshot(record)
        self.assertEqual(reference, self.store.save_snapshot(dict(reversed(list(record.items())))))
        relocated = self.root / "relocated"
        shutil.copytree(self.store.root, relocated)
        reopened = ProjectStore(relocated)
        self.assertEqual(reopened.read_snapshot(reference), record)
        reopened.resolve(reference["path"]).write_bytes(b"{}")
        with self.assertRaisesRegex(StoreError, "Snapshot checksum"):
            reopened.read_snapshot(reference)

    def test_path_escape_is_rejected(self):
        for path in ("../outside.png", "C:/outside.png", "/outside.png"):
            with self.subTest(path=path), self.assertRaises(StoreError):
                self.store.write_once(path, b"no")

    def test_symlink_escape_is_rejected(self):
        outside = self.root / "outside"
        outside.mkdir()
        try:
            (self.store.root / "escape").symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("Creating symlinks requires OS permission")
        with self.assertRaises(StoreError):
            self.store.write_once("escape/outside.png", b"no")
        self.assertFalse((outside / "outside.png").exists())


class CliTests(unittest.TestCase):
    def run_cli(self, args):
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            code = main(args)
        return code, output.getvalue(), errors.getvalue()

    def test_demo_replays_without_network_and_outputs_inspectable_artifacts(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as folder:
            args = ["demo", "--seed", "17", "--output", folder]
            with patch("last_light_radio.comfy.urlopen", side_effect=AssertionError("Network forbidden")):
                code, output, logs = self.run_cli(args)
                second_code, second_output, _ = self.run_cli(args)
            self.assertEqual((code, second_code), (0, 0), logs)
            first, second = json.loads(output), json.loads(second_output)
            self.assertEqual(first["artifacts"], second["artifacts"])
            self.assertEqual(first["duration_frames"], 600 * 24)
            self.assertEqual(first["network_requests"], 0)
            self.assertEqual(len(first["variant_counts"]), 5)
            self.assertIn('"event": "render.queued"', logs)
            self.assertIn('"event": "render.completed"', logs)
            self.assertTrue(Path(first["artifacts"]["report"]).is_file())
            manifest = json.loads(Path(first["artifacts"]["manifest"]).read_text())
            self.assertTrue(manifest["fixture"])
            self.assertFalse(manifest["renderable"])

    def test_workflow_preview_preserves_recovered_template(self):
        source = ROOT / "workflows/h3/workflow_api.json"
        before = source.read_bytes()
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as folder:
            target = Path(folder) / "preview.json"
            code, output, logs = self.run_cli([
                "workflow", "--image", "test/input.png", "--prompt", "Gentle breathing.",
                "--seed", "19", "--preview-output", str(target),
            ])
            self.assertEqual(code, 0, logs)
            self.assertFalse(json.loads(output)["submitted"])
            graph = json.loads(target.read_text())
            self.assertEqual(graph["4"]["inputs"]["image"], "test/input.png")
            self.assertEqual(graph["5"]["inputs"]["prompt"], "Gentle breathing.")
            self.assertEqual(graph["8"]["inputs"]["seed"], 19)
        self.assertEqual(source.read_bytes(), before)

    def test_missing_endpoint_is_an_actionable_failure(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as folder:
            code, _, logs = self.run_cli(["probe", "--config", str(Path(folder) / "missing.json")])
        self.assertEqual(code, 1)
        self.assertIn("Supply --url", logs)

    def test_invalid_edited_graph_never_writes_preview(self):
        bindings = json.loads((ROOT / "workflows/h3/bindings.json").read_text())
        bindings["inputs"]["motion_prompt"].update(
            {"node_id": "8", "class_type": "KSampler", "input": "sampler_name"})
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as folder:
            custom = Path(folder) / "bindings.json"
            custom.write_text(json.dumps(bindings))
            target = Path(folder) / "bad-preview.json"
            code, output, logs = self.run_cli([
                "workflow", "--bindings", str(custom), "--prompt", "not-a-sampler",
                "--preview-output", str(target),
            ])
            self.assertEqual(code, 1, logs)
            self.assertFalse(json.loads(output)["inspection"]["valid"])
            self.assertFalse(target.exists())

    def test_malformed_saved_endpoint_is_reported(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as folder:
            config = Path(folder) / "worker.json"
            config.write_text("[]")
            code, _, logs = self.run_cli(["probe", "--config", str(config)])
        self.assertEqual(code, 1)
        self.assertIn("Worker config must be a JSON object", logs)


if __name__ == "__main__":
    unittest.main()
