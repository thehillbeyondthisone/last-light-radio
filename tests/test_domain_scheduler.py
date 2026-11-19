"""Offline acceptance tests: safety contracts matter more than media generation."""

import copy
import hashlib
from io import StringIO
from pathlib import Path
import unittest
from unittest.mock import patch

from last_light_radio.domain import ValidationError, canonical_json, load_project, validate_project
from last_light_radio.scheduler import SchedulingError, format_event_log, schedule


FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "demo_project.json"


class DomainTests(unittest.TestCase):
    def setUp(self):
        self.project = load_project(FIXTURE)

    def test_fixture_is_explicit_with_exact_required_pools_and_master_hash(self):
        project = self.project
        self.assertTrue(project["fixture"])
        self.assertEqual(project["world"]["facts"], {})
        self.assertEqual(len([v for v in project["variants"] if v["behavior_id"] == "READ_IDLE"]), 3)
        self.assertEqual(len([v for v in project["variants"] if v["behavior_id"] == "SIP_TEA"]), 2)
        master = project["scenes"][0]["master"]
        actual = hashlib.sha256((FIXTURE.parent / master["path"]).read_bytes()).hexdigest()
        self.assertEqual(master["sha256"], actual)

    def test_validation_copies_and_does_not_mutate_input(self):
        validated = validate_project(self.project)
        validated["world"]["facts"]["new"] = True
        self.assertEqual(self.project["world"]["facts"], {})

    def test_rejects_broken_ids_hashes_paths_contracts_and_weights(self):
        mutations = [
            lambda p: p["entities"][0].update(world_id="OTHER_WORLD"),
            lambda p: p["scenes"][0].update(location_id="MISSING"),
            lambda p: p["variants"][0].update(behavior_id="MISSING"),
            lambda p: p["variants"][0].update(master_sha256="0" * 64),
            lambda p: p["scenes"][0]["master"].update(path="../MASTER.png"),
            lambda p: p["scenes"][0]["master"].update(path="C:/MASTER.png"),
            lambda p: p["scenes"][0]["master"].update(path="\\\\server\\share\\MASTER.png"),
            lambda p: p["behaviors"][0].update(weight=0),
            lambda p: p["behaviors"][0].update(weight=float("inf")),
            lambda p: p["behaviors"][0].update(weight=True),
            lambda p: p["behaviors"][0].update(weight=10 ** 1000),
            lambda p: p["variants"][0].update(duration_frames=True),
            lambda p: p["episodes"][0].update(world_revision=True),
            lambda p: p["behaviors"][0].update(cooldown_frames=-1),
            lambda p: p["behaviors"][0].update(resources=["actor.READER"]),
            lambda p: p["variants"][0].update(start_state={}),
            lambda p: p["variants"][0].update(end_state={}),
            lambda p: p["variants"].append(copy.deepcopy(p["variants"][0])),
            lambda p: p["world"]["facts"].update(unrelated=float("nan")),
            lambda p: p.update(fixture=False),
            lambda p: p["canon_patches"][0].update(status="approved"),
            lambda p: p["episodes"][0].update(world_revision=1),
        ]
        for mutation in mutations:
            project = copy.deepcopy(self.project)
            mutation(project)
            with self.subTest(mutation=mutation):
                with self.assertRaises(ValidationError):
                    validate_project(project)

    def test_duplicate_json_properties_are_not_silently_overwritten(self):
        with patch.object(Path, "open", return_value=StringIO('{"schema_version":1,"schema_version":1}')):
            with self.assertRaisesRegex(ValidationError, "duplicate JSON"):
                load_project("duplicate.json")

    def test_video_metadata_validation_does_not_require_existing_motion_media(self):
        project = self.project
        project["fixture"] = False
        for variant in project["variants"]:
            variant["media"] = {"kind": "video", "path": "approved/not-yet-mounted.webm", "sha256": "a" * 64}
            variant["provenance"] = {"workflow_sha256": "b" * 64, "review_note": "external fixture"}
        self.assertFalse(validate_project(project)["fixture"])
        project["variants"][0]["provenance"] = {}
        with self.assertRaisesRegex(ValidationError, "workflow_sha256"):
            validate_project(project)


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.project = load_project(FIXTURE)

    def test_ten_minutes_is_byte_identical_and_does_not_change_canon_or_input(self):
        before = canonical_json(self.project)
        one = schedule(self.project, seed=42)
        two = schedule(self.project, seed=42)
        self.assertEqual(canonical_json(one), canonical_json(two))
        self.assertEqual(format_event_log(one), format_event_log(two))
        self.assertEqual(canonical_json(self.project), before)
        self.assertEqual(one["duration_frames"], 14400)
        self.assertEqual(one["events"][-1]["end_frame"], 14400)
        self.assertEqual(one["world_revision"], 0)
        self.assertFalse(one["renderable"])
        saved_hash = one.pop("manifest_hash")
        self.assertEqual(saved_hash, hashlib.sha256(canonical_json(one).encode("utf-8")).hexdigest())

    def test_different_seeds_change_variant_choices_and_all_pools_are_used(self):
        one, two = schedule(self.project, seed=1), schedule(self.project, seed=2)
        sequence_one = [e["variant_id"] for e in one["events"] if e["kind"] == "clip"]
        sequence_two = [e["variant_id"] for e in two["events"] if e["kind"] == "clip"]
        self.assertNotEqual(sequence_one, sequence_two)
        self.assertEqual(set(sequence_one), {v["id"] for v in self.project["variants"]})

    def test_full_frame_is_exclusive_contiguous_and_cooldowns_and_anti_repeat_hold(self):
        manifest = schedule(self.project, seed=5)
        previous_end, behavior_end, previous_variant = 0, {}, {}
        behaviors = {b["id"]: b for b in self.project["behaviors"]}
        for event in manifest["events"]:
            self.assertEqual(event["start_frame"], previous_end)
            self.assertGreater(event["end_frame"], event["start_frame"])
            self.assertIn("frame.full_scene", event["resources"])
            previous_end = event["end_frame"]
            if event["kind"] != "clip":
                self.assertEqual(event["state_before"], event["state_after"])
                continue
            identity = event["behavior_id"]
            behavior = behaviors[identity]
            if identity in behavior_end:
                self.assertGreaterEqual(event["start_frame"] - behavior_end[identity],
                                        max(behavior["cooldown_frames"], behavior["min_gap_frames"]))
                self.assertNotEqual(event["variant_id"], previous_variant[identity])
            self.assertGreaterEqual(event["start_frame"], behavior["initial_delay_frames"])
            behavior_end[identity] = event["end_frame"]
            previous_variant[identity] = event["variant_id"]

    def test_unapproved_semantically_invalid_and_visually_incompatible_never_run(self):
        project = self.project
        project["variants"][0]["status"] = "candidate"
        project["variants"][1]["status"] = "rejected"
        project["scenes"][0]["anchors"].append({"id": "OTHER_POSE", "hold_safe": True})
        project["variants"][2]["start_anchor"] = "OTHER_POSE"
        project["scenes"][0]["initial_state"]["CUP"]["position"] = "gone"
        manifest = schedule(project)
        self.assertTrue(all(event["kind"] == "hold" for event in manifest["events"]))
        codes = {reason["code"] for event in manifest["events"] for reason in event["skipped"]}
        self.assertIn("precondition_mismatch", codes)
        project["scenes"][0]["initial_state"]["CUP"]["position"] = "on_table"
        manifest = schedule(project)
        clips = {e["variant_id"] for e in manifest["events"] if e["kind"] == "clip"}
        self.assertTrue(clips <= {"SIP_TEA_01", "SIP_TEA_02"})
        codes = {reason["code"] for event in manifest["events"] for reason in event["skipped"]}
        self.assertTrue({"variant_not_approved", "visual_anchor_mismatch"} <= codes)

    def test_absent_actor_or_empty_library_uses_logged_safe_holds(self):
        for mutate in (lambda p: p["scenes"][0].update(present_entities=["CUP"]),
                       lambda p: p["scenes"][0].update(present_entities=["READER"]),
                       lambda p: p.update(variants=[])):
            project = copy.deepcopy(self.project)
            mutate(project)
            manifest = schedule(project, duration_seconds=19)
            self.assertTrue(all(e["kind"] == "hold" for e in manifest["events"]))
            self.assertEqual(manifest["events"][-1]["end_frame"], 456)
            self.assertTrue(manifest["events"][0]["skipped"])
            self.assertEqual(manifest["events"][0]["source"]["kind"], "master")

    def test_time_window_contains_entire_clip_and_final_hold_is_exact(self):
        project = self.project
        project["behaviors"] = [project["behaviors"][0]]
        project["variants"] = [v for v in project["variants"] if v["behavior_id"] == "READ_IDLE"]
        project["behaviors"][0].update(initial_delay_frames=0, cooldown_frames=0, min_gap_frames=0,
                                         time_windows=[{"start_frame": 48, "end_frame": 160}])
        manifest = schedule(project, duration_seconds=7)
        clips = [e for e in manifest["events"] if e["kind"] == "clip"]
        self.assertEqual(len(clips), 1)
        self.assertEqual((clips[0]["start_frame"], clips[0]["end_frame"]), (48, 144))
        self.assertEqual(manifest["events"][-1]["end_frame"], 168)

    def test_hold_uses_actual_exit_frame_and_state_never_teleports_to_master(self):
        project = self.project
        behavior = project["behaviors"][0]
        behavior.update(kind="transition", initial_delay_frames=0,
                        state_effects={"READER": {"pose": "standing"}, "CUP": {"position": "on_table"}})
        project["behaviors"] = [behavior]
        variant = project["variants"][0]
        variant.update(end_anchor="STANDING", end_state=copy.deepcopy(behavior["state_effects"]))
        project["variants"] = [variant]
        project["scenes"][0]["anchors"].append({"id": "STANDING", "hold_safe": True})
        manifest = schedule(project, duration_seconds=10)
        self.assertEqual(manifest["events"][0]["kind"], "clip")
        for event in manifest["events"][1:]:
            self.assertEqual(event["kind"], "hold")
            self.assertEqual(event["source"]["kind"], "variant_frame")
            self.assertEqual(event["source"]["frame"], 95)
            self.assertEqual(event["entry_anchor"], "STANDING")
            self.assertEqual(event["state_after"]["READER"]["pose"], "standing")
        project["scenes"][0]["anchors"][-1]["hold_safe"] = False
        with self.assertRaisesRegex(SchedulingError, "unsafe anchor.*STANDING"):
            schedule(project, duration_seconds=10)

    def test_recovery_can_leave_unsafe_anchor_without_inventing_a_hold(self):
        project = self.project
        project["scenes"][0]["anchors"][0]["hold_safe"] = False
        project["scenes"][0]["anchors"].append({"id": "RECOVERED", "hold_safe": True})
        project["behaviors"] = [project["behaviors"][0]]
        project["behaviors"][0].update(kind="recovery", initial_delay_frames=0)
        project["variants"] = [project["variants"][0]]
        project["variants"][0]["end_anchor"] = "RECOVERED"
        manifest = schedule(project, duration_seconds=10)
        self.assertEqual(manifest["events"][0]["kind"], "clip")
        self.assertEqual(manifest["events"][-1]["exit_anchor"], "RECOVERED")

    def test_invalid_timebase_duration_and_seed_fail_explicitly(self):
        for kwargs in ({"seed": True}, {"seed": -1}, {"fps": True}, {"fps": 30},
                       {"duration_seconds": 0}, {"duration_seconds": float("nan")},
                       {"duration_seconds": True}, {"duration_seconds": 0.01}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(SchedulingError):
                    schedule(self.project, **kwargs)


if __name__ == "__main__":
    unittest.main()
