import copy
import http.client
import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from last_light_radio import pilots
from last_light_radio.motion_jobs import _encode_mp4
from last_light_radio.motion_profiles import INT8_VAE
from last_light_radio.pilot_media import inspect_video
from last_light_radio.recipes import save_recipe
from last_light_radio.studio import Studio, StudioError
from last_light_radio.server import make_server
from last_light_radio.scheduler import schedule

ROOT = Path(__file__).resolve().parents[1]


def png(image):
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


class PilotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / "tests")
        self.addCleanup(self.temp.cleanup)
        self.studio = Studio(self.temp.name)
        self.master = Image.new("RGB", (64, 48), (70, 90, 60))
        self.scene = self.studio.import_scene(png(self.master), "master.png", "Test room")
        self.profile = save_recipe(self.studio, {"scene_id": self.scene["id"], "actor": "Reader", "name": "Idle",
             "template_id": "idle", "start_state": "reading", "end_state": "reading", "polygon": [[10, 10], [30, 10], [30, 35], [10, 35]],
             "feather": 2, "context": 0.25, "prompt": "A small breath", "seed": 7, "frames": 39, "vae_name": INT8_VAE})
        from last_light_radio.motion_profiles import get_profile
        self.profile = get_profile(self.studio, self.profile["id"])
        # Independent decoded colors make an exit-frame hold distinguishable
        # from an incorrect reset to the master/entry image.
        images = [Image.new("RGB", self.master.size, color) for color in ((74, 94, 64), (80, 100, 70), (85, 105, 75))]
        self.identity = "1" * 32
        output = _encode_mp4(self.studio.store, "fixture.mp4", iter(images), self.master.size, 24)
        output["properties"] = {"container": "mp4", "width": 64, "height": 48, "frame_count": 3, "effective_fps": 24,
                                "duration_seconds": 3 / 24, "pixel_decode_verified": False}
        metadata = {"local_job_id": self.identity, "master": self.scene["master"], "workflow_sha256": "a" * 64,
                    "outputs": [output], "parameters": {"seed": 7}, "motion": {"profile": self.profile}}
        self.studio.register_candidate(self.scene["id"], "Approved tiny idle", metadata)
        self.studio.review(self.identity, {"decision": "approved", "entry_anchor": "reading", "exit_anchor": "reading",
                     "visual_checked": True, "notes": "Fixture approval", "expected_version": 0, "request_id": "approve"})
        self.payload = {"scene_id": self.scene["id"], "title": "Ten-minute test", "seed": 7, "density": "quiet"}

    def test_seeded_ten_minute_plan_is_exact_and_preserves_review_and_sources(self):
        original = self.studio.candidate(self.identity)
        a = pilots.plan(self.studio, self.payload)
        b = pilots.plan(self.studio, self.payload)
        self.assertEqual(a["id"], b["id"])
        self.assertEqual(a["manifest"], b["manifest"])
        m = a["manifest"]
        self.assertEqual(m["duration_frames"], 14400)
        self.assertEqual(m["events"][0]["start_frame"], 0)
        self.assertEqual(m["events"][-1]["end_frame"], 14400)
        for before, after in zip(m["events"], m["events"][1:]):
            self.assertEqual(before["end_frame"], after["start_frame"])
            if before["kind"] == "clip":
                self.assertEqual(after["kind"], "hold")
                self.assertEqual(after["frame_image"], before["exit_image"])
        self.assertEqual(self.studio.candidate(self.identity), original)
        self.assertEqual(self.studio.jobs(), [])
        self.assertEqual(len(self.studio.approved_library()), 1)

    def test_rejected_and_unapproved_or_wrong_review_anchors_cannot_enter_plan(self):
        self.studio.review(self.identity, {"decision": "rejected", "entry_anchor": "reading", "exit_anchor": "reading",
                     "visual_checked": False, "notes": "Not suitable", "expected_version": 1, "request_id": "reject"})
        with self.assertRaises(StudioError):
            pilots.plan(self.studio, {**self.payload, "candidate_ids": [self.identity]})
        self.assertEqual(pilots.listing(self.studio), [])

    def test_invalid_seed_or_density_returns_a_visible_validation_error(self):
        for field, value in (("density", []), ("density", {}), ("density", "unknown"),
                             ("seed", True), ("seed", -1), ("seed", 2_147_483_648)):
            with self.subTest(field=field, value=value), self.assertRaises(StudioError):
                pilots.plan(self.studio, {**self.payload, field: value})
        self.assertEqual(pilots.listing(self.studio), [])

    def test_later_approval_changes_block_existing_plan_export(self):
        pilot = pilots.plan(self.studio, self.payload)
        self.studio.review(self.identity, {"decision": "rejected", "entry_anchor": "reading", "exit_anchor": "reading",
                     "notes": "Changed review", "expected_version": 1, "request_id": "reject"})
        self.assertFalse(pilots.get(self.studio, pilot["id"])["approval_current"])
        with self.assertRaises(StudioError):
            pilots.queue_export(self.studio, pilot["id"])
        self.assertEqual(pilots.get(self.studio, pilot["id"])["status"], "draft")

    def test_modified_video_is_rejected_before_export(self):
        pilot = pilots.plan(self.studio, self.payload)
        clip = pilot["manifest"]["clips"][0]
        self.studio.store.resolve(clip["output"]["path"]).write_bytes(b"changed")
        with self.assertRaises(ValueError):
            pilots.queue_export(self.studio, pilot["id"])

    def test_real_cpu_export_has_exact_frames_actual_exit_holds_and_no_audio(self):
        pilot = pilots.plan(self.studio, self.payload, duration_seconds=20)
        pilots.queue_export(self.studio, pilot["id"])
        pilots.queue_export(self.studio, pilot["id"])
        pilots.process_export(self.studio, pilot["id"])
        complete = pilots.get(self.studio, pilot["id"])
        self.assertEqual(complete["status"], "complete", complete["error"])
        path, kind = pilots.media(self.studio, pilot["id"], "media")
        self.assertEqual(kind, "video/mp4")
        inspect_video(path, 480, 24, (64, 48))
        report = json.loads(path.with_name("export_report.json").read_text())
        self.assertEqual(report["frames_written"], 480)
        self.assertTrue(all(item["matches_current_rgb"] for item in report["hold_checks"]))
        self.assertEqual(report["audio"], "none")
        self.assertEqual(pilots.queue_export(self.studio, pilot["id"])["status"], "complete")
        self.assertEqual(Studio(self.temp.name).candidates()[0]["status"], "approved")
        self.assertEqual(pilots.get(Studio(self.temp.name), pilot["id"])["status"], "complete")

    def test_pose_graph_excludes_incompatible_action_and_does_not_retime(self):
        pilot = pilots.plan(self.studio, self.payload)
        project = self.studio.store.read_snapshot(pilot["manifest"]["project"])
        other = copy.deepcopy(project["variants"][0])
        other.update(id="different-pose", start_anchor="unreachable")
        project["scenes"][0]["anchors"].append({"id": "unreachable", "hold_safe": True})
        project["variants"].append(other)
        manifest = schedule(project, 19, 600, 24)
        self.assertFalse(any(event.get("variant_id") == "different-pose" for event in manifest["events"]))
        self.assertTrue(all(event["end_frame"] - event["start_frame"] == 3 for event in manifest["events"] if event["kind"] == "clip"))
        clip_events = [event for event in manifest["events"] if event["kind"] == "clip"]
        self.assertTrue(all(b["start_frame"] - a["end_frame"] >= 18 * 24 for a, b in zip(clip_events, clip_events[1:])))

    def test_revocation_during_encoding_blocks_publication(self):
        pilot = pilots.plan(self.studio, self.payload, duration_seconds=20)
        pilots.queue_export(self.studio, pilot["id"])
        encode = pilots.encode_pilot
        def revoke(*args):
            report = encode(*args)
            self.studio.review(self.identity, {"decision": "rejected", "entry_anchor": "reading", "exit_anchor": "reading",
                         "notes": "Revoked during export", "expected_version": 1, "request_id": "reject-during-export"})
            return report
        with patch("last_light_radio.pilots.encode_pilot", side_effect=revoke):
            pilots.process_export(self.studio, pilot["id"])
        result = pilots.get(self.studio, pilot["id"])
        self.assertEqual(result["status"], "failed")
        self.assertIsNone(result["media_url"])
        self.assertFalse(self.studio.store.resolve(f"exports/pilots/{pilot['id']}/pilot.mp4").exists())

    def test_loopback_plan_frame_and_manifest_routes(self):
        server = make_server(self.studio, 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=15)
        self.addCleanup(connection.close)
        connection.request("POST", "/api/pilots", json.dumps(self.payload), {"Content-Type": "application/json", "X-LLR-Client": "studio"})
        response = connection.getresponse()
        self.assertEqual(response.status, 201)
        pilot = json.loads(response.read())
        connection.request("GET", f"/api/pilots/{pilot['id']}/frames/0/hold")
        response = connection.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(response.read(), png(self.master))
        connection.request("GET", pilot["manifest_url"])
        response = connection.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(json.loads(response.read())["manifest_hash"], pilot["manifest"]["manifest_hash"])
        self.assertEqual(self.studio.jobs(), [])
        handler = object.__new__(server.RequestHandlerClass)
        handler.close_connection = False
        with patch.object(handler, "guard_host"), patch.object(handler, "path_parts", return_value=["api", "pilots", pilot["id"], "manifest"]), \
                patch.object(handler, "send_file", side_effect=ConnectionResetError), patch.object(handler, "send_json") as send_error:
            handler.dispatch()
        self.assertTrue(handler.close_connection)
        send_error.assert_not_called()


if __name__ == "__main__":
    unittest.main()
