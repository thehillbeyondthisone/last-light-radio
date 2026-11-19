import argparse
import importlib.util
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from last_light_radio.server import make_server
from last_light_radio.studio import Studio

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("quickstart", ROOT / "scripts/quickstart.py")
quickstart = importlib.util.module_from_spec(spec)
spec.loader.exec_module(quickstart)


class QuickstartTests(unittest.TestCase):
    def test_missing_ffmpeg_is_a_setup_condition(self):
        from last_light_radio.comfy import ComfyError
        with patch("last_light_radio.video_tools.ffmpeg_path", side_effect=ComfyError("FFMPEG_REQUIRED", "Missing")):
            self.assertFalse(quickstart.media_ready())

    def test_build_staleness_tracks_source_changes_and_missing_output(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as directory:
            root = Path(directory)
            (root / "frontend/src").mkdir(parents=True)
            (root / "frontend/index.html").write_text("source")
            with patch.object(quickstart, "ROOT", root):
                self.assertTrue(quickstart.frontend_stale())
                output = root / "frontend/dist/index.html"
                output.parent.mkdir()
                output.write_text("built")
                self.assertFalse(quickstart.frontend_stale())
                source = root / "frontend/src/App.tsx"
                source.write_text("updated")
                import os
                stamp = output.stat().st_mtime_ns + 1_000_000_000
                os.utime(source, ns=(stamp, stamp))
                self.assertTrue(quickstart.frontend_stale())

    def test_existing_build_needs_no_node_or_install(self):
        with patch.object(quickstart, "frontend_stale", return_value=False), patch.object(quickstart, "run") as run:
            quickstart.build_frontend()
            run.assert_not_called()

    def test_check_mode_does_not_start_a_server_or_open_browser(self):
        with patch.object(quickstart, "ensure_media", return_value=None), patch.object(quickstart, "build_frontend"), patch.object(quickstart, "launch") as launch:
            self.assertEqual(quickstart.main(["--check"]), 0)
            launch.assert_not_called()

    def test_other_library_is_never_reused(self):
        self.assertFalse(quickstart.matching_studio({"application": "other"}, ROOT))
        self.assertFalse(quickstart.matching_studio({"application": "last-light-radio", "data_root": str(ROOT / "other")}, ROOT))

    def test_health_and_relaunch_reuse_same_library_without_spawning(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as directory:
            studio = Studio(directory)
            server = make_server(studio, 0)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                report = quickstart.health(f"http://127.0.0.1:{server.server_port}/")
                self.assertTrue(quickstart.matching_studio(report, Path(directory)))
                args = argparse.Namespace(port=server.server_port, data=Path(directory), no_browser=True)
                with patch.object(quickstart.subprocess, "Popen") as spawn, patch.object(quickstart.webbrowser, "open") as browser:
                    self.assertEqual(quickstart.launch(args), 0)
                    spawn.assert_not_called()
                    browser.assert_not_called()
                args.data = Path(directory) / "different-library"
                with self.assertRaisesRegex(RuntimeError, "in use"):
                    quickstart.launch(args)
            finally:
                server.shutdown()
                server.server_close()


if __name__ == "__main__":
    unittest.main()
