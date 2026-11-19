import copy
import json
import tempfile
import unittest
from pathlib import Path

from last_light_radio.comfy import ComfyError, load_bindings
from last_light_radio.generation import latest_event, load_request, poll_generation, start_generation
from last_light_radio.media import inspect_webp
from last_light_radio.store import ProjectStore, sha256

ROOT = Path(__file__).resolve().parents[1]


def animated_container():
    def chunk(kind, payload):
        return kind + len(payload).to_bytes(4, "little") + payload + b"\0" * (len(payload) % 2)
    contents = b"WEBP" + chunk(b"VP8X", b"\x02\0\0\0" + (383).to_bytes(3, "little") + (479).to_bytes(3, "little"))
    contents += chunk(b"ANIM", b"\0" * 6)
    for duration in (41, 42):
        contents += chunk(b"ANMF", b"\0" * 12 + duration.to_bytes(3, "little") + b"\0" + b"frame-data")
    return b"RIFF" + len(contents).to_bytes(4, "little") + contents


class FakeLiveClient:
    base_url = "http://worker.invalid:8188"

    def __init__(self):
        self.submissions = 0
        self.uploads = 0
        self.polls = 0
        self.ambiguous = False
        self.fail_download_once = False
        self.failure = False
        self.history_graph = None
        self.definitions = json.loads((ROOT / "workflows/h3/node_definitions.json").read_text())

    def probe(self):
        return {"connected": True, "object_info": copy.deepcopy(self.definitions),
                "system_stats": {"devices": [{"vram_total": 12, "vram_free": 2}]}, "errors": []}

    def system_stats(self):
        return {"devices": [{"vram_total": 12, "vram_free": 3}]}

    def upload_image(self, data, filename, subfolder):
        self.uploads += 1
        return {"name": filename, "subfolder": subfolder, "type": "input", "path": f"{subfolder}/{filename}"}

    def submit(self, graph, client_id, local_job_id):
        self.submissions += 1
        self.history_graph = copy.deepcopy(graph)
        if self.ambiguous:
            raise ComfyError("SUBMISSION_AMBIGUOUS", "Response lost")
        return {"prompt_id": "owned-prompt", "number": 1}

    def poll(self, prompt_id):
        self.polls += 1
        if self.failure:
            return {"status": "failed", "error": {"code": "EXECUTION_FAILED"}}
        return {"prompt_id": prompt_id, "status": "success", "history": {
                    "prompt": [0, prompt_id, copy.deepcopy(self.history_graph)],
                    "status": {"completed": True, "messages": [
                        ["execution_start", {"timestamp": 1000}],
                        ["execution_success", {"timestamp": 36925}]]}},
                "outputs": {"11": {"images": [{"filename": "candidate.webp", "subfolder": "ours", "type": "output"}], "animated": [True]}}}

    def download_output(self, reference):
        if self.fail_download_once:
            self.fail_download_once = False
            raise ComfyError("WORKER_OFFLINE", "Temporary disconnect")
        return animated_container()


class GenerationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / "tests")
        self.addCleanup(self.temp.cleanup)
        self.store = ProjectStore(self.temp.name)
        self.graph = json.loads((ROOT / "workflows/h3/workflow_api.json").read_text())
        self.bindings = load_bindings(ROOT / "workflows/h3/bindings.json")
        self.bindings["confirmed"] = True
        self.client = FakeLiveClient()
        self.image = ROOT / "assets/test_scene/test_still.png"

    def start(self):
        return start_generation(self.store, self.client, self.graph, self.bindings, self.image, "One gentle breath.", 7)

    def test_live_success_preserves_template_master_and_unapproved_provenance(self):
        before = self.image.read_bytes(), copy.deepcopy(self.graph)
        job = self.start()
        request = load_request(self.store, job["local_job_id"])
        self.assertEqual(request["parameters"]["frames"], 39)
        result = poll_generation(self.store, self.client, job["local_job_id"])
        candidate = result["candidate"]
        self.assertEqual(candidate["review_status"], "candidate")
        self.assertFalse(candidate["canon_approved"])
        output = candidate["outputs"][0]
        self.assertEqual(output["sha256"], sha256(self.store.resolve(output["path"]).read_bytes()))
        self.assertEqual(output["properties"]["frame_count"], 2)
        self.assertIsNone(candidate["peak_vram"])
        self.assertTrue(candidate["history_workflow_verified"])
        self.assertEqual(candidate["execution"]["runtime_seconds"], 35.925)
        self.assertEqual(self.image.read_bytes(), before[0])
        self.assertEqual(self.graph, before[1])
        # Reopen in a separate invocation: no network, upload or resubmission.
        reopened = ProjectStore(self.temp.name)
        self.assertEqual(poll_generation(reopened, self.client, job["local_job_id"])["candidate"], candidate)
        self.assertEqual((self.client.submissions, self.client.uploads, self.client.polls), (1, 1, 1))

    def test_unconfirmed_mapping_never_reaches_worker(self):
        self.bindings["confirmed"] = False
        with self.assertRaises(ComfyError) as error:
            self.start()
        self.assertEqual(error.exception.code, "BINDINGS_UNCONFIRMED")
        self.assertEqual(self.client.submissions, 0)

    def test_missing_live_nodes_never_uploads_or_submits(self):
        del self.client.definitions["MiniMaxH3ImageToVideo"]
        with self.assertRaises(ComfyError):
            self.start()
        self.assertEqual((self.client.uploads, self.client.submissions), (0, 0))

    def test_ambiguous_post_is_durable_and_resume_never_resubmits(self):
        self.client.ambiguous = True
        with self.assertRaises(ComfyError) as error:
            self.start()
        local_id = error.exception.details["local_job_id"]
        self.assertEqual(load_request(self.store, local_id)["local_job_id"], local_id)
        with self.assertRaises(ComfyError) as unresolved:
            poll_generation(self.store, self.client, local_id)
        self.assertEqual(unresolved.exception.code, "SUBMISSION_UNRESOLVED")
        self.assertEqual(self.client.submissions, 1)

    def test_download_retry_resumes_same_prompt_and_modified_output_is_detected(self):
        job = self.start()
        self.client.fail_download_once = True
        with self.assertRaises(ComfyError):
            poll_generation(self.store, self.client, job["local_job_id"])
        self.assertEqual(latest_event(self.store, job["local_job_id"])["status"], "download_failed")
        candidate = poll_generation(self.store, self.client, job["local_job_id"])["candidate"]
        self.assertEqual(self.client.submissions, 1)
        self.store.resolve(candidate["outputs"][0]["path"]).write_bytes(b"changed")
        with self.assertRaises(ComfyError) as error:
            poll_generation(self.store, self.client, job["local_job_id"])
        self.assertEqual(error.exception.code, "CANDIDATE_CHECKSUM_MISMATCH")

    def test_wrong_worker_and_foreign_job_are_rejected(self):
        job = self.start()
        self.client.base_url = "http://different-worker.invalid"
        with self.assertRaises(ComfyError) as error:
            poll_generation(self.store, self.client, job["local_job_id"])
        self.assertEqual(error.exception.code, "WORKER_MISMATCH")
        with self.assertRaises((ComfyError, OSError)):
            poll_generation(self.store, self.client, "f" * 32)
        self.assertEqual(self.client.submissions, 1)

    def test_failure_is_logged_and_does_not_produce_candidate(self):
        job = self.start()
        self.client.failure = True
        result = poll_generation(self.store, self.client, job["local_job_id"])
        self.assertEqual(result["status"], "failed")
        self.assertNotIn("candidate", result)
        self.assertEqual(self.client.submissions, 1)

    def test_executed_workflow_mismatch_blocks_candidate_provenance(self):
        job = self.start()
        self.client.history_graph["8"]["inputs"]["seed"] = 999
        with self.assertRaises(ComfyError) as error:
            poll_generation(self.store, self.client, job["local_job_id"])
        self.assertEqual(error.exception.code, "HISTORY_WORKFLOW_MISMATCH")
        self.assertEqual(latest_event(self.store, job["local_job_id"])["status"], "provenance_mismatch")
        self.assertEqual(self.client.submissions, 1)


class MediaTests(unittest.TestCase):
    def test_encoded_timing_is_distinct_from_requested_fps(self):
        properties = inspect_webp(animated_container())
        self.assertEqual((properties["width"], properties["height"]), (384, 480))
        self.assertEqual(properties["duration_ms"], 83)
        self.assertAlmostEqual(properties["effective_fps"], 2000 / 83)
        self.assertFalse(properties["pixel_decode_verified"])

    def test_truncated_or_nonanimated_outputs_fail(self):
        data = animated_container()
        for invalid in (b"not-webp", data[:-1], data[:12]):
            with self.subTest(invalid=invalid[:12]), self.assertRaises(ComfyError):
                inspect_webp(invalid)


if __name__ == "__main__":
    unittest.main()
