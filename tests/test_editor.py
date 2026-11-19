"""Offline coverage for persisted subject plans and their public API contracts."""

import copy
from concurrent.futures import ThreadPoolExecutor
import io
import json
import shutil
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw

from last_light_radio import editor, pilots
from last_light_radio.motion_jobs import _encode_mp4
from last_light_radio.motion_profiles import INT8_VAE, get_profile
from last_light_radio.recipes import save_recipe
from last_light_radio.server import make_server
from last_light_radio.studio import Studio, StudioError


ROOT = Path(__file__).resolve().parents[1]


def png(image):
    stream = io.BytesIO()
    image.save(stream, "PNG")
    return stream.getvalue()


def fixture_candidate(studio, scene, number, actor, role, *, frames=3, polygon=None,
                      approved=True, first_scene=None, last_scene=None, start="rest", end="rest"):
    """Explicit test-only approvals of tiny CPU videos, never production assets."""
    polygon = polygon or ([[4, 8], [22, 8], [22, 36], [4, 36]] if actor == "Reader"
                          else [[40, 8], [58, 8], [58, 36], [40, 36]])
    identity = f"{number:032x}"
    payload = {"scene_id": scene["id"], "actor": actor, "name": f"{actor} {role} {number}",
               "template_id": role, "start_state": start, "end_state": end, "polygon": polygon,
               "feather": 0, "context": 0, "prompt": "Offline test motion", "seed": number,
               "frames": 39, "vae_name": INT8_VAE}
    if first_scene:
        payload["first_scene_id"] = first_scene["id"]
    if last_scene:
        payload["last_scene_id"] = last_scene["id"]
    profile = get_profile(studio, save_recipe(studio, payload)["id"])
    images = []
    for frame in range(frames):
        image = Image.new("RGB", (64, 48), (70, 90, 60))
        ImageDraw.Draw(image).polygon([tuple(point) for point in polygon],
                                     fill=(80 + number + frame, 96 + frame, 65 + frame))
        images.append(image)
    output = _encode_mp4(studio.store, f"fixture-{number}.mp4", iter(images), (64, 48), 24)
    output["properties"] = {"container": "mp4", "width": 64, "height": 48, "frame_count": frames,
                            "effective_fps": 24, "duration_seconds": frames / 24,
                            "pixel_decode_verified": False}
    metadata = {"local_job_id": identity, "master": scene["master"], "workflow_sha256": "a" * 64,
                "outputs": [output], "parameters": {"seed": number}, "motion": {"profile": profile}}
    studio.register_candidate(scene["id"], f"{actor} {role} take {number}", metadata)
    if approved:
        studio.review(identity, {"decision": "approved", "entry_anchor": start, "exit_anchor": end,
                                "visual_checked": True, "notes": "Explicit offline fixture approval",
                                "expected_version": 0, "request_id": f"fixture-approve-{number}"})
    return identity


class SubjectEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Encode the immutable fixture once; every test receives its own store copy.
        cls.template = tempfile.TemporaryDirectory(prefix="editor-fixture-", dir=ROOT / "tests")
        cls.addClassCleanup(cls.template.cleanup)
        studio = Studio(cls.template.name)
        cls.scene = studio.import_scene(png(Image.new("RGB", (64, 48), (70, 90, 60))),
                                       "master.png", "Offline subject room")
        cls.reader_idle = fixture_candidate(studio, cls.scene, 1, "Reader", "idle")
        cls.reader_idle_b = fixture_candidate(studio, cls.scene, 2, "Reader", "idle")
        cls.reader_action = fixture_candidate(studio, cls.scene, 3, "Reader", "action", frames=4)
        cls.cat_idle = fixture_candidate(studio, cls.scene, 4, "Cat", "idle")
        cls.cat_action = fixture_candidate(studio, cls.scene, 5, "Cat", "action", frames=4)
        cls.unapproved = fixture_candidate(studio, cls.scene, 6, "Reader", "action", approved=False)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="editor-test-", dir=ROOT / "tests")
        self.addCleanup(self.temp.cleanup)
        shutil.copytree(self.template.name, self.temp.name, dirs_exist_ok=True)
        self.studio = Studio(self.temp.name)
        self.payload = {"scene_id": self.scene["id"], "title": "Offline action sequence",
                        "duration_frames": 96, "seed": 7, "expected_revision": 0,
                        "subjects": [{"actor": "Reader", "mode": "continuous", "seed": 7,
                                      "pool": [self.reader_idle, self.reader_idle_b]},
                                     {"actor": "Cat", "mode": "continuous", "seed": 19,
                                      "pool": [self.cat_idle]}],
                        "placements": [], "ambience": []}

    def plan(self, payload=None):
        return editor.plan(self.studio, payload or self.payload)

    def tracks(self, result):
        return {track["actor"]: track["events"] for track in result["sequence"]["manifest"]["tracks"]}

    def assert_exact_coverage(self, events, duration=96):
        self.assertEqual(events[0]["start_frame"], 0)
        self.assertEqual(events[-1]["end_frame"], duration)
        self.assertTrue(all(event["end_frame"] > event["start_frame"] for event in events))
        self.assertTrue(all(a["end_frame"] == b["start_frame"] for a, b in zip(events, events[1:])))

    def test_defaults_put_only_approved_idles_in_subject_setup_and_no_pinned_idle(self):
        state = editor.state(self.studio, self.scene["id"])
        self.assertEqual(state["revision"], 0)
        self.assertEqual(state["config"]["duration_frames"], 14400)
        self.assertEqual(state["config"]["placements"], [])
        pools = {row["actor"]: row["pool"] for row in state["config"]["subjects"]}
        self.assertEqual(set(pools["Reader"]), {self.reader_idle, self.reader_idle_b})
        self.assertEqual(pools["Cat"], [self.cat_idle])
        self.assertNotIn(self.unapproved, {clip["id"] for clip in state["clips"]})

    def test_case_variants_share_one_subject_without_mutating_source_profiles(self):
        lowercase = fixture_candidate(self.studio, self.scene, 7, "reader", "action", frames=4,
                                      polygon=[[4, 8], [22, 8], [22, 36], [4, 36]])
        original = self.studio.candidate(lowercase)
        self.assertEqual(original["metadata"]["motion"]["profile"]["actor"], "reader")
        state = editor.state(self.studio, self.scene["id"])
        self.assertEqual(state["actors"], ["Cat", "Reader"])
        public = next(clip for clip in state["clips"] if clip["id"] == lowercase)
        self.assertEqual(public["actor"], "Reader")
        setup = {subject["actor"]: subject for subject in state["config"]["subjects"]}
        self.assertEqual(set(setup["Reader"]["pool"]), {self.reader_idle, self.reader_idle_b})

        self.payload["placements"] = [{"id": "lowercase-action", "candidate_id": lowercase, "start_frame": 20}]
        saved = self.plan()
        self.assertEqual(saved["config"]["placements"][0]["actor"], "Reader")
        manifest = saved["sequence"]["manifest"]
        pinned = next(clip for clip in manifest["clips"] if clip["id"] == lowercase)
        self.assertEqual(pinned["actor"], "Reader")
        motion = next(event for event in self.tracks(saved)["Reader"] if event["origin"] == "motion")
        self.assertEqual(motion["variant_id"], lowercase)
        self.assertEqual(motion["actor"], "Reader")
        reopened = editor.state(Studio(self.temp.name), self.scene["id"])
        self.assertEqual(reopened["actors"], ["Cat", "Reader"])
        self.assertEqual(reopened["config"], saved["config"])
        self.assertEqual(self.studio.candidate(lowercase), original)

        # An entered spelling variant resolves to the existing subject identity.
        entered = copy.deepcopy(self.payload)
        entered["expected_revision"] = saved["revision"]
        entered["subjects"][0]["actor"] = "reader"
        normalized = self.plan(entered)
        self.assertEqual(normalized["config"]["subjects"][0]["actor"], "Reader")
        self.assertEqual(normalized["sequence_id"], saved["sequence_id"])
        self.assertEqual(self.studio.candidate(lowercase), original)

        duplicate = copy.deepcopy(self.payload)
        duplicate["expected_revision"] = normalized["revision"]
        duplicate["subjects"].append({"actor": "reader", "mode": "still", "seed": 9, "pool": []})
        with self.assertRaises(StudioError):
            self.plan(duplicate)

    def test_same_inputs_remain_byte_equivalent_across_save_revisions(self):
        original_candidates = self.studio.candidates()
        first = self.plan()
        second = self.plan({**self.payload, "expected_revision": 1})
        self.assertEqual(first["sequence"]["id"], second["sequence"]["id"])
        self.assertEqual(first["sequence"]["manifest"], second["sequence"]["manifest"])
        self.assertEqual(second["revision"], 2)
        self.assertNotIn("expected_revision", second["sequence"]["manifest"]["config"])
        for events in self.tracks(first).values():
            self.assert_exact_coverage(events)
        self.assertEqual(self.studio.candidates(), original_candidates)
        self.assertEqual(self.studio.jobs(), [])
        self.assertEqual(len(pilots.listing(self.studio, all_kinds=True)), 1)
        self.assertEqual(pilots.listing(self.studio), [])

    def test_idle_seed_changes_order_without_changing_manual_motion(self):
        fixed = {"id": "reader-page", "candidate_id": self.reader_action, "start_frame": 20}
        sequences = []
        for revision, seed in enumerate(range(7, 12)):
            payload = copy.deepcopy(self.payload)
            payload.update(expected_revision=revision, placements=[fixed])
            payload["subjects"][0]["seed"] = seed
            events = self.tracks(self.plan(payload))["Reader"]
            motions = [event for event in events if event["origin"] == "motion"]
            self.assertEqual([(e["start_frame"], e["end_frame"], e["variant_id"]) for e in motions],
                             [(20, 24, self.reader_action)])
            sequences.append([event.get("variant_id") for event in events])
        self.assertGreater(len({tuple(sequence) for sequence in sequences}), 1)

    def test_motion_overrides_idle_on_its_subject_and_other_subject_remains_independent(self):
        self.payload["placements"] = [{"id": "reader-page", "candidate_id": self.reader_action, "start_frame": 20},
                                      {"id": "cat-stretch", "candidate_id": self.cat_action, "start_frame": 20}]
        result = self.plan()
        for actor, action in (("Reader", self.reader_action), ("Cat", self.cat_action)):
            events = self.tracks(result)[actor]
            self.assert_exact_coverage(events)
            motion = next(event for event in events if event["origin"] == "motion")
            self.assertEqual((motion["start_frame"], motion["end_frame"], motion["variant_id"]), (20, 24, action))
            self.assertFalse(any(event["origin"] == "idle" and event["start_frame"] < 24
                                 and event["end_frame"] > 20 for event in events))
        self.assertEqual(result["sequence"]["manifest"]["canon_changes"], [])

    def test_incomplete_idle_remainder_holds_the_actual_previous_exit(self):
        self.payload["placements"] = [{"id": "reader-page", "candidate_id": self.reader_action, "start_frame": 20}]
        events = self.tracks(self.plan())["Reader"]
        gap = next(event for event in events if event["start_frame"] == 18)
        self.assertEqual((gap["kind"], gap["end_frame"]), ("hold", 20))
        previous = next(event for event in events if event["end_frame"] == 18)
        self.assertEqual(gap["frame_image"], previous["exit_image"])
        self.assertEqual(gap["layer_clip_id"], previous["variant_id"])
        self.assertIn("No complete approved idle", gap["reason"])
        self.assertTrue(all(e["end_frame"] - e["start_frame"] in (3, 4)
                            for e in events if e["kind"] == "clip"))

    def test_blank_pool_and_still_mode_produce_explicit_holds(self):
        self.payload["subjects"][0]["pool"] = []
        self.payload["subjects"][1]["mode"] = "still"
        tracks = self.tracks(self.plan())
        self.assertEqual([(e["kind"], e["start_frame"], e["end_frame"]) for e in tracks["Reader"]],
                         [("hold", 0, 96)])
        self.assertEqual([(e["kind"], e["start_frame"], e["end_frame"]) for e in tracks["Cat"]],
                         [("hold", 0, 96)])
        self.assertIn("Hold selected", tracks["Cat"][0]["reason"])
        self.assertIsNone(tracks["Cat"][0]["layer_clip_id"])

    def test_creator_can_explicitly_assign_a_returning_action_to_their_idle_pool(self):
        # Recovered cat variations are returning motions even when the original role is action.
        self.payload["subjects"][1]["pool"] = [self.cat_action]
        events = self.tracks(self.plan())["Cat"]
        self.assertTrue(all(e["variant_id"] == self.cat_action and e["origin"] == "idle" for e in events))

    def test_same_subject_overlapping_actions_and_pinned_idles_are_rejected(self):
        for placements in ([{"id": "first", "candidate_id": self.reader_action, "start_frame": 20},
                            {"id": "second", "candidate_id": self.reader_action, "start_frame": 22}],
                           [{"id": "pinned-idle", "candidate_id": self.reader_idle, "start_frame": 20}]):
            with self.subTest(placements=placements), self.assertRaises(StudioError):
                self.plan({**self.payload, "placements": placements})
        self.assertEqual(pilots.listing(self.studio), [])

    def test_overlapping_subject_mask_support_cannot_be_combined(self):
        overlap = fixture_candidate(self.studio, self.scene, 7, "Cat", "idle",
                                    polygon=[[15, 8], [35, 8], [35, 36], [15, 36]])
        self.payload["subjects"][1]["pool"] = [overlap]
        with self.assertRaisesRegex(StudioError, "overlapping motion masks") as error:
            self.plan()
        self.assertEqual(error.exception.status, 409)
        self.assertEqual(pilots.listing(self.studio), [])

    def test_unapproved_wrong_subject_and_stale_review_anchors_are_ineligible(self):
        for bad in (self.unapproved, self.cat_idle):
            payload = copy.deepcopy(self.payload)
            payload["subjects"][0]["pool"] = [bad]
            with self.subTest(bad=bad), self.assertRaises(StudioError):
                self.plan(payload)
        self.studio.review(self.reader_action, {"decision": "approved", "entry_anchor": "wrong",
                          "exit_anchor": "rest", "visual_checked": True, "notes": "Fixture mismatched anchors",
                          "expected_version": 1, "request_id": "wrong-anchor-review"})
        payload = {**self.payload, "placements": [{"id": "bad-action", "candidate_id": self.reader_action, "start_frame": 20}]}
        with self.assertRaises(StudioError):
            self.plan(payload)
        state = editor.state(self.studio, self.scene["id"])
        self.assertIn(self.reader_action, {row["id"] for row in state["excluded"]})

    def test_pose_changes_and_noncanonical_start_poses_are_excluded(self):
        other = self.studio.import_scene(png(Image.new("RGB", (64, 48), (80, 90, 60))), "other.png", "Other pose")
        transition = fixture_candidate(self.studio, self.scene, 8, "Reader", "transition",
                                       last_scene=other, start="rest", end="looking")
        noncanonical = fixture_candidate(self.studio, self.scene, 9, "Reader", "idle",
                                        first_scene=other, last_scene=other)
        state = editor.state(self.studio, self.scene["id"])
        self.assertFalse({transition, noncanonical} & {row["id"] for row in state["clips"]})
        self.assertTrue({transition, noncanonical} <= {row["id"] for row in state["excluded"]})
        for candidate in (transition, noncanonical):
            with self.subTest(candidate=candidate), self.assertRaises(StudioError):
                self.plan({**self.payload, "placements": [{"id": "changed-location", "candidate_id": candidate,
                                                          "start_frame": 20}]})

    def test_stale_save_conflict_and_reopen_preserve_exact_config_and_sequence(self):
        saved = self.plan()
        with self.assertRaises(StudioError) as conflict:
            self.plan()
        self.assertEqual(conflict.exception.status, 409)
        reopened = Studio(self.temp.name)
        state = editor.state(reopened, self.scene["id"])
        self.assertEqual(state["revision"], 1)
        self.assertEqual(state["config"], saved["config"])
        self.assertEqual(state["sequence_id"], saved["sequence_id"])
        self.assertEqual(pilots.get(reopened, saved["sequence_id"])["manifest"], saved["sequence"]["manifest"])
        self.assertEqual(reopened.jobs(), [])

    def test_new_subject_appears_after_save_without_losing_or_mutating_saved_work(self):
        self.payload.update(title="Creator's saved episode", seed=31,
                            placements=[{"id": "saved-page", "candidate_id": self.reader_action, "start_frame": 20}])
        self.payload["subjects"][0].update(mode="spaced", seed=23, pool=[self.reader_idle_b])
        self.payload["subjects"][1].update(mode="still", seed=29)
        saved = self.plan()
        key = f"editor.{self.scene['id']}"
        original = self.studio.setting(key)
        save_recipe(self.studio, {"scene_id": self.scene["id"], "actor": "Bird", "name": "Bird breathing",
                    "template_id": "idle", "start_state": "perched", "end_state": "perched",
                    "polygon": [[28, 4], [36, 4], [36, 16], [28, 16]], "feather": 0, "context": 0,
                    "prompt": "Offline fixture subject added after sequence save", "seed": 11,
                    "frames": 39, "vae_name": INT8_VAE})

        state = editor.state(self.studio, self.scene["id"])

        self.assertEqual(set(state["actors"]), {"Bird", "Cat", "Reader"})
        returned = {subject["actor"]: subject for subject in state["config"]["subjects"]}
        self.assertIn("Bird", returned)
        self.assertEqual(returned["Bird"]["mode"], "continuous")
        self.assertEqual(returned["Bird"]["pool"], [])
        for subject in saved["config"]["subjects"]:
            self.assertEqual(returned[subject["actor"]], subject)
        for field in ("title", "seed", "duration_frames", "placements", "ambience"):
            self.assertEqual(state["config"][field], saved["config"][field])
        self.assertEqual(state["revision"], saved["revision"])
        self.assertEqual(state["sequence_id"], saved["sequence_id"])
        self.assertEqual(self.studio.setting(key), original)
        # Repeated reads keep the additive view stable without persisting or duplicating it.
        self.assertEqual(editor.state(self.studio, self.scene["id"]), state)
        self.assertEqual(self.studio.setting(key), original)

    def test_two_store_instances_cannot_both_commit_the_same_expected_revision(self):
        other = Studio(self.temp.name)
        # Keep the race focused on the SQLite head update rather than simultaneous
        # publication of cold FFmpeg caches/directories on a Windows filesystem.
        chosen = {identity for subject in self.payload["subjects"] for identity in subject["pool"]}
        for row in editor.catalog(self.studio, self.scene["id"])[1]:
            if row["candidate"]["id"] in chosen:
                editor.support_mask(self.studio, row["profile"], (64, 48))
                editor.prepare_clip(self.studio.store, row["candidate"]["metadata"]["outputs"][0], 24, (64, 48))
        barrier = threading.Barrier(2)
        validate = editor.validate_config

        def synchronized_validation(*args):
            config = validate(*args)
            # Both callers must pass the early revision preflight before either commits.
            barrier.wait(timeout=20)
            return config

        with patch("last_light_radio.editor.validate_config", side_effect=synchronized_validation):
            with ThreadPoolExecutor(max_workers=2) as workers:
                futures = [workers.submit(editor.plan, studio, self.payload) for studio in (self.studio, other)]
                successes, conflicts = [], []
                for future in futures:
                    try:
                        successes.append(future.result(timeout=30))
                    except StudioError as error:
                        conflicts.append(error)
        self.assertEqual(len(successes), 1)
        self.assertEqual([error.status for error in conflicts], [409])
        saved = editor.state(other, self.scene["id"])
        self.assertEqual(saved["revision"], 1)
        self.assertEqual(saved["sequence_id"], successes[0]["sequence_id"])
        self.assertEqual(len(pilots.listing(other, all_kinds=True)), 1)

    def test_later_review_revocation_blocks_sequence_export(self):
        result = self.plan()
        self.studio.review(self.reader_idle, {"decision": "rejected", "entry_anchor": "rest", "exit_anchor": "rest",
                          "notes": "Fixture revoked", "expected_version": 1, "request_id": "revoke-idle"})
        self.assertFalse(pilots.get(self.studio, result["sequence_id"])["approval_current"])
        with self.assertRaises(StudioError):
            pilots.queue_export(self.studio, result["sequence_id"])
        self.assertEqual(pilots.get(self.studio, result["sequence_id"])["status"], "draft")

    def test_tampered_video_or_masks_block_export_before_queueing(self):
        result = self.plan()
        clip = result["sequence"]["manifest"]["clips"][0]
        for kind in ("output", "mask", "display_mask", "source_mask"):
            path = self.studio.store.resolve(clip[kind]["path"])
            original = path.read_bytes()
            path.write_bytes(b"tampered fixture")
            try:
                with self.subTest(kind=kind), self.assertRaises(ValueError):
                    pilots.queue_export(self.studio, result["sequence_id"])
            finally:
                path.write_bytes(original)
        self.assertEqual(pilots.get(self.studio, result["sequence_id"])["status"], "draft")

    def test_invalid_settings_fail_with_visible_validation_errors(self):
        for field, value in (("seed", True), ("seed", -1), ("duration_frames", 1),
                             ("expected_revision", False), ("expected_revision", -1)):
            with self.subTest(field=field, value=value), self.assertRaises(StudioError):
                self.plan({**self.payload, field: value})
        for mode in ([], {}, "unknown"):
            payload = copy.deepcopy(self.payload)
            payload["subjects"][0]["mode"] = mode
            with self.subTest(mode=mode), self.assertRaises(StudioError):
                self.plan(payload)

    def api(self, parts, payload=None):
        # Exercise actual dispatch/status/file routing without opening a network socket.
        with patch("last_light_radio.server.ThreadingHTTPServer") as server_type:
            make_server(self.studio, 0)
            handler = object.__new__(server_type.call_args.args[1])
        handler.close_connection = False
        with patch.object(handler, "guard_host"), patch.object(handler, "path_parts", return_value=parts), \
                patch.object(handler, "body", return_value=payload), patch.object(handler, "send_json") as send_json, \
                patch.object(handler, "send_file") as send_file:
            handler.dispatch(mutation=payload is not None)
        return send_json.call_args, send_file.call_args

    def test_editor_state_plan_mask_routes_and_persisted_pilot_export_contract(self):
        sent, media = self.api(["api", "editor", self.scene["id"]])
        self.assertIsNone(media)
        self.assertEqual(sent.args[0]["revision"], 0)
        sent, media = self.api(["api", "editor", "plan"], self.payload)
        self.assertEqual(sent.args[1], 201)
        result = sent.args[0]
        sent, media = self.api(["api", "editor", "plans", result["sequence_id"], "masks", self.reader_idle])
        self.assertIsNone(sent)
        self.assertEqual(media.args[1], "image/png")
        with Image.open(media.args[0]) as image:
            self.assertEqual(image.mode, "RGBA")
            self.assertEqual(image.size, (64, 48))
            self.assertEqual(image.getpixel((0, 0))[3], 0)
        sent, media = self.api(["api", "editor", "plan"], self.payload)
        self.assertEqual(sent.args[1], 409)
        self.assertIn("another window", sent.args[0]["error"]["message"])
        sent, media = self.api(["api", "editor", "plans", result["sequence_id"], "masks", self.unapproved])
        self.assertEqual(sent.args[1], 404)
        sent, media = self.api(["api", "pilots", result["sequence_id"], "export"], {})
        self.assertEqual(sent.args[1], 202)
        self.assertEqual(sent.args[0]["status"], "queued")


if __name__ == "__main__":
    unittest.main()
