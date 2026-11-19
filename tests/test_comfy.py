"""The bridge must be useful and safe without a running ComfyUI instance."""

import copy
import json
from pathlib import Path
import tempfile
import unittest

from last_light_radio.comfy import (
    ComfyClient, ComfyError, MockComfyClient, WorkflowError, inspect_workflow,
    load_bindings, parse_animated_webp_outputs, prepare_workflow,
)


ROOT = Path(__file__).resolve().parents[1]


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.graph = json.loads((ROOT / "workflows/h3/workflow_api.json").read_text())
        self.definitions = json.loads((ROOT / "workflows/h3/node_definitions.json").read_text())
        self.bindings = load_bindings(ROOT / "workflows/h3/bindings.json")

    def codes(self, report):
        return {item["code"] for item in report["errors"]}

    def test_recovered_graph_is_compatible_with_captured_nodes(self):
        before = copy.deepcopy(self.graph)
        report = inspect_workflow(self.graph, self.definitions)
        self.assertTrue(report["valid"], report["errors"])
        self.assertEqual(report["node_count"], 11)
        self.assertEqual(report["output_nodes"], ["11"])
        self.assertEqual(report["model_readiness"], "unverified")
        self.assertEqual(report["warnings"][0]["code"], "IMAGE_NOT_IN_CHOICES")
        self.assertEqual(self.graph, before)

    def test_generic_node_ids_are_not_bound_in_inspection(self):
        graph = {"source-x": {"class_type": "Produce", "inputs": {}},
                 "destination-y": {"class_type": "Consume", "inputs": {"value": ["source-x", 0]}}}
        definitions = {"Produce": {"input": {"required": {}}, "output": ["CUSTOM"]},
                       "Consume": {"input": {"required": {"value": ["CUSTOM"]}}, "output": [], "output_node": True}}
        report = inspect_workflow(graph, definitions)
        self.assertTrue(report["valid"])
        self.assertEqual(report["output_nodes"], ["destination-y"])

    def test_missing_node_class_is_actionable(self):
        del self.definitions["MiniMaxH3ImageToVideo"]
        report = inspect_workflow(self.graph, self.definitions)
        self.assertIn("MISSING_NODE_CLASS", self.codes(report))

    def test_broken_link_index_type_and_required_input(self):
        cases = [
            ("missing", ["not-here", 0], "MISSING_LINK_NODE"),
            ("bad-index", ["4", 5], "INVALID_OUTPUT_INDEX"),
            ("wrong-type", ["3", 0], "LINK_TYPE_MISMATCH"),
            ("malformed", ["4", "0"], "INVALID_INPUT_VALUE"),
        ]
        for label, value, expected in cases:
            with self.subTest(label=label):
                graph = copy.deepcopy(self.graph)
                graph["5"]["inputs"]["first_frame"] = value
                self.assertIn(expected, self.codes(inspect_workflow(graph, self.definitions)))
        del self.graph["8"]["inputs"]["seed"]
        self.assertIn("MISSING_INPUT", self.codes(inspect_workflow(self.graph, self.definitions)))

    def test_cycles_and_invalid_literals_are_rejected(self):
        self.graph["6"]["inputs"]["model"] = ["6", 0]
        self.graph["8"]["inputs"]["steps"] = True
        codes = self.codes(inspect_workflow(self.graph, self.definitions))
        self.assertIn("WORKFLOW_CYCLE", codes)
        self.assertIn("INVALID_INPUT_VALUE", codes)
        self.assertIn("INVALID_WORKFLOW", self.codes(inspect_workflow({"nodes": []})))

    def test_preview_changes_only_named_literals_and_preserves_originals(self):
        self.bindings["confirmed"] = False
        before = copy.deepcopy(self.graph)
        binding_before = copy.deepcopy(self.bindings)
        self.assertFalse(self.bindings["confirmed"])
        prepared = prepare_workflow(self.graph, self.bindings,
                                    {"source_image": "project/master.png", "motion_prompt": "One gentle breath.", "seed": 42})
        self.assertEqual(prepared["4"]["inputs"]["image"], "project/master.png")
        self.assertEqual(prepared["8"]["inputs"]["seed"], 42)
        self.assertEqual(prepared["5"]["inputs"]["first_frame"], ["4", 0])
        self.assertEqual(prepared["5"]["inputs"]["last_frame"], ["4", 0])
        self.assertEqual(self.graph, before)
        self.assertEqual(self.bindings, binding_before)

    def test_override_unknown_type_range_and_template_mismatch(self):
        for overrides in ({"invented": 1}, {"seed": True}, {"fps": 0}, {"quality": 101},
                          {"motion_prompt": []}, {"source_image": "   "}, {"cfg": float("nan")}):
            with self.subTest(overrides=overrides):
                with self.assertRaises(WorkflowError):
                    prepare_workflow(self.graph, self.bindings, overrides)
        self.graph["8"]["inputs"]["seed"] = 1
        with self.assertRaises(WorkflowError) as error:
            prepare_workflow(self.graph, self.bindings, {})
        self.assertEqual(error.exception.code, "BINDING_TEMPLATE_MISMATCH")

    def test_binding_target_and_link_replacement_are_rejected(self):
        del self.bindings["workflow_sha256"]
        self.bindings["inputs"]["seed"]["node_id"] = "not-here"
        with self.assertRaises(WorkflowError) as error:
            prepare_workflow(self.graph, self.bindings, {})
        self.assertEqual(error.exception.code, "BINDING_TARGET_MISSING")
        self.bindings["inputs"]["seed"] = {"node_id": "5", "class_type": "MiniMaxH3ImageToVideo", "input": "first_frame", "type": "STRING"}
        with self.assertRaises(WorkflowError) as error:
            prepare_workflow(self.graph, self.bindings, {"seed": "other-image.png"})
        self.assertEqual(error.exception.code, "BINDING_TARGET_IS_LINK")

    def test_unreadable_and_malformed_bindings_are_structured_errors(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as temporary:
            path = Path(temporary) / "bindings.json"
            with self.assertRaises(WorkflowError) as error:
                load_bindings(path)
            self.assertEqual(error.exception.to_dict()["code"], "BINDINGS_UNREADABLE")
            path.write_text('{"schema_version": 1, "confirmed": "yes", "inputs": {}}')
            with self.assertRaises(WorkflowError) as error:
                load_bindings(path)
            self.assertEqual(error.exception.code, "INVALID_BINDINGS")


class ProbeTests(unittest.TestCase):
    def test_probe_is_get_only_and_reports_nodes_without_claiming_model_readiness(self):
        calls = []
        def transport(method, path, payload):
            calls.append((method, path, payload))
            return {"devices": [{"name": "Test GPU"}]} if path == "/system_stats" else {"SomeNode": {}}
        report = ComfyClient("http://worker.invalid:8188/", transport=transport).probe()
        self.assertTrue(report["connected"])
        self.assertEqual(report["node_classes"], ["SomeNode"])
        self.assertEqual(report["model_readiness"], "unverified")
        self.assertEqual(calls, [("GET", "/system_stats", None), ("GET", "/object_info", None)])
        self.assertFalse(hasattr(ComfyClient, "submit"))
        self.assertFalse(hasattr(ComfyClient, "cancel"))

    def test_offline_invalid_response_and_reconnect(self):
        offline = True
        def transport(method, path, payload):
            if offline:
                raise TimeoutError("connection timed out")
            return {}
        client = ComfyClient("http://worker.invalid:8188", transport=transport)
        report = client.probe()
        self.assertFalse(report["connected"])
        self.assertEqual({item["code"] for item in report["errors"]}, {"WORKER_OFFLINE"})
        offline = False
        self.assertTrue(client.probe()["connected"])
        report = ComfyClient("http://worker.invalid", transport=lambda *_: []).probe()
        self.assertFalse(report["connected"])
        self.assertEqual(report["errors"][0]["code"], "INVALID_RESPONSE")

    def test_url_and_timeout_are_explicit(self):
        for url in ("worker", "ftp://worker", "http://user:secret@worker", "http://worker?bad=1", "http://worker:wrong"):
            with self.subTest(url=url), self.assertRaises(ComfyError):
                ComfyClient(url)
        for timeout in (0, -1, True, float("inf")):
            with self.subTest(timeout=timeout), self.assertRaises(ComfyError):
                ComfyClient("http://worker", timeout=timeout)


class MockJobTests(unittest.TestCase):
    def setUp(self):
        self.graph = json.loads((ROOT / "workflows/h3/workflow_api.json").read_text())
        definitions = json.loads((ROOT / "workflows/h3/node_definitions.json").read_text())
        self.client = MockComfyClient(definitions=definitions)

    def test_queued_running_success_uses_observed_h3_output_convention(self):
        prompt_id = self.client.submit(self.graph)
        self.assertEqual(self.client.poll(prompt_id)["status"], "queued")
        self.assertEqual(self.client.poll(prompt_id)["status"], "running")
        result = self.client.poll(prompt_id)
        self.assertEqual(result["status"], "success")
        self.assertTrue(parse_animated_webp_outputs(result["outputs"], "11")[0]["animated"])
        self.assertEqual([item["status"] for item in self.client.events], ["queued", "running", "success"])

    def test_failure_timeout_and_resume_do_not_cancel_jobs(self):
        failed_id = self.client.submit(self.graph, outcome="failure", queued_polls=0)
        result = self.client.wait(failed_id)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error"]["code"], "MOCK_EXECUTION_FAILED")
        slow_id = self.client.submit(self.graph, queued_polls=3)
        with self.assertRaises(ComfyError) as error:
            self.client.wait(slow_id, max_polls=1)
        self.assertEqual(error.exception.code, "JOB_TIMEOUT")
        self.assertEqual(self.client.wait(slow_id)["status"], "success")
        self.assertNotIn("cancelled", [event["status"] for event in self.client.events])

    def test_job_ownership_and_cancellation_are_scoped(self):
        owned_id = self.client.submit(self.graph)
        other_id = self.client.submit(self.graph)
        for method in (self.client.poll, self.client.cancel):
            with self.assertRaises(ComfyError) as error:
                method("someone-elses-job")
            self.assertEqual(error.exception.code, "JOB_NOT_OWNED")
        self.assertEqual(self.client.cancel(owned_id)["status"], "cancelled")
        self.assertEqual(self.client.wait(other_id)["status"], "success")

    def test_offline_reconnect_keeps_owned_job(self):
        prompt_id = self.client.submit(self.graph)
        self.client.offline = True
        self.assertFalse(self.client.probe()["connected"])
        with self.assertRaises(ComfyError) as error:
            self.client.poll(prompt_id)
        self.assertEqual(error.exception.code, "WORKER_OFFLINE")
        self.client.offline = False
        self.assertEqual(self.client.wait(prompt_id)["status"], "success")

    def test_invalid_workflow_never_queues(self):
        del self.graph["4"]
        with self.assertRaises(ComfyError):
            self.client.submit(self.graph)
        self.assertEqual(self.client.events, [])

    def test_malformed_or_unsafe_output_is_visible(self):
        bad_outputs = [
            {}, {"images": [], "animated": []},
            {"images": [{"filename": "x.webp", "type": "output"}], "animated": [False]},
            {"images": [{"filename": "x.mp4", "type": "output"}], "animated": [True]},
            {"images": [{"filename": "x.webp", "type": "output", "subfolder": "../master"}], "animated": [True]},
        ]
        for output in bad_outputs:
            with self.subTest(output=output), self.assertRaises(ComfyError):
                parse_animated_webp_outputs({"11": output}, "11")


if __name__ == "__main__":
    unittest.main()
