"""Byte transport fixtures exercise the live bridge without a GPU or network."""

import copy
from http.client import IncompleteRead
import io
import json
from pathlib import Path
import unittest
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from last_light_radio.comfy import ComfyError, parse_animated_webp_outputs
from last_light_radio.live import LiveComfyClient, _RefuseRedirects


ROOT = Path(__file__).resolve().parents[1]
PNG = b"\x89PNG\r\n\x1a\nfixture"
WEBP = b"RIFF" + (16).to_bytes(4, "little") + b"WEBPVP8 " + (4).to_bytes(4, "little") + b"test"


def response(value, status=200):
    return status, {"Content-Type": "application/json"}, json.dumps(value).encode("utf-8")


class FakeTransport:
    def __init__(self, responses=None):
        self.responses = responses or {}
        self.calls = []

    def __call__(self, method, path, body, headers):
        self.calls.append((method, path, body, headers))
        value = self.responses[(method, path)]
        if isinstance(value, BaseException):
            raise value
        return value


class LiveClientTests(unittest.TestCase):
    def setUp(self):
        self.transport = FakeTransport()
        self.client = LiveComfyClient("http://worker.invalid:8188/", transport=self.transport)
        self.graph = json.loads((ROOT / "workflows/h3/workflow_api.json").read_text())

    def assert_code(self, code, method, *args):
        with self.assertRaises(ComfyError) as raised:
            method(*args)
        self.assertEqual(raised.exception.code, code)
        return raised.exception

    def test_probe_reuses_existing_report_and_stats_has_separate_read(self):
        self.transport.responses = {("GET", "/system_stats"): response({"devices": [{"name": "fixture GPU"}]}),
                                    ("GET", "/object_info"): response({"Example": {}})}
        report = self.client.probe()
        self.assertTrue(report["connected"])
        self.assertEqual(report["node_classes"], ["Example"])
        self.assertEqual(report["model_readiness"], "unverified")
        self.assertEqual(self.client.system_stats(), report["system_stats"])
        self.assertEqual([call[1] for call in self.transport.calls], ["/system_stats", "/object_info", "/system_stats"])
        self.assertTrue(all(call[0] == "GET" and call[2] is None for call in self.transport.calls))

    def test_probe_exposes_offline_and_invalid_response_without_claiming_connection(self):
        self.transport.responses = {("GET", "/system_stats"): TimeoutError("offline"),
                                    ("GET", "/object_info"): response([])}
        report = self.client.probe()
        self.assertFalse(report["connected"])
        self.assertEqual([error["code"] for error in report["errors"]], ["WORKER_OFFLINE", "INVALID_RESPONSE"])

    def test_upload_multipart_never_overwrites_and_uses_server_renamed_image(self):
        self.transport.responses[("POST", "/upload/image")] = response({"name": "still (1).png", "subfolder": "LastLightRadio/job-1", "type": "input"})
        result = self.client.upload_image(PNG, "still.png", "LastLightRadio/job-1")
        self.assertEqual(result, {"name": "still (1).png", "subfolder": "LastLightRadio/job-1", "type": "input", "path": "LastLightRadio/job-1/still (1).png"})
        method, path, body, headers = self.transport.calls[0]
        self.assertEqual((method, path), ("POST", "/upload/image"))
        self.assertIn(b'name="overwrite"\r\n\r\nfalse\r\n', body)
        self.assertIn(b'name="subfolder"\r\n\r\nLastLightRadio/job-1\r\n', body)
        self.assertIn(b'name="image"; filename="still.png"', body)
        self.assertIn(PNG, body)
        self.assertTrue(headers["Content-Type"].startswith("multipart/form-data; boundary="))

    def test_unsafe_upload_names_and_subfolders_fail_before_network(self):
        for filename, folder in (("../master.png", "test"), ("C:master.png", "test"),
                                 ("master.png", "../canon"), ("master.png", "/absolute"),
                                 ("master.png", "one\\..\\canon"), ("master.png", "one//two"),
                                 ("con.png", "test"), ("x.png", "NUL"), ("x.png", "bad\r\npart")):
            with self.subTest(filename=filename, folder=folder):
                self.assert_code("UNSAFE_FILE_REFERENCE", self.client.upload_image, PNG, filename, folder)
        self.assertEqual(self.transport.calls, [])

    def test_windows_relative_upload_folder_is_normalized_before_comparison(self):
        self.transport.responses[("POST", "/upload/image")] = response({"name": "still.png", "subfolder": "LastLightRadio\\job-1", "type": "input"})
        result = self.client.upload_image(PNG, "still.png", "LastLightRadio/job-1")
        self.assertEqual(result["subfolder"], "LastLightRadio/job-1")
        self.assertEqual(result["path"], "LastLightRadio/job-1/still.png")

    def test_upload_signature_and_response_destination_validation(self):
        self.assert_code("INVALID_UPLOAD", self.client.upload_image, b"not png", "still.png", "job")
        for result in ({"name": "still.png", "subfolder": "elsewhere", "type": "input"},
                       {"name": "still.png", "subfolder": "job", "type": "output"}):
            self.transport.responses[("POST", "/upload/image")] = response(result)
            self.assert_code("INVALID_UPLOAD_RESPONSE", self.client.upload_image, PNG, "still.png", "job")

    def test_upload_timeout_is_visible_and_never_automatically_retried(self):
        self.transport.responses[("POST", "/upload/image")] = TimeoutError("lost response")
        error = self.assert_code("UPLOAD_AMBIGUOUS", self.client.upload_image, PNG, "still.png", "job")
        self.assertTrue(error.details["may_have_been_accepted"])
        self.assertEqual(len(self.transport.calls), 1)

    def test_submit_preserves_graph_and_includes_ownership_before_one_post(self):
        self.transport.responses[("POST", "/prompt")] = response({"prompt_id": "owned-1", "number": 3.0, "node_errors": {}})
        original = copy.deepcopy(self.graph)
        result = self.client.submit(self.graph, "client-1", "local-1")
        self.assertEqual(result["prompt_id"], "owned-1")
        self.assertEqual(self.graph, original)
        method, path, data, headers = self.transport.calls[0]
        payload = json.loads(data)
        self.assertEqual((method, path), ("POST", "/prompt"))
        self.assertEqual(payload["prompt"], original)
        self.assertEqual(payload["client_id"], "client-1")
        self.assertEqual(payload["extra_data"]["last_light_radio"], {"local_job_id": "local-1"})
        self.assertEqual(headers["Content-Type"], "application/json")

    def test_invalid_workflow_or_job_identity_never_posts(self):
        self.assert_code("INVALID_WORKFLOW", self.client.submit, {}, "client", "job")
        self.assert_code("INVALID_JOB_IDENTITY", self.client.submit, self.graph, "", "job")
        self.assert_code("INVALID_JOB_IDENTITY", self.client.submit, self.graph, "client", "bad\njob")
        self.assertEqual(self.transport.calls, [])

    def test_validation_rejection_preserves_worker_errors(self):
        validation = {"error": {"type": "prompt_outputs_failed_validation"},
                      "node_errors": {"1": {"errors": [{"message": "Missing model"}]}}}
        self.transport.responses[("POST", "/prompt")] = response(validation, 400)
        error = self.assert_code("PROMPT_REJECTED", self.client.submit, self.graph, "client", "job")
        self.assertEqual(error.details["worker_response"], validation)
        self.assertEqual(len(self.transport.calls), 1)

    def test_accepted_partial_graph_keeps_owned_identity_and_node_errors(self):
        accepted = {"prompt_id": "owned-1", "number": 3,
                    "node_errors": {"unused-output": {"errors": [{"message": "Missing optional output model"}]}}}
        self.transport.responses[("POST", "/prompt")] = response(accepted)
        result = self.client.submit(self.graph, "client", "job")
        self.assertEqual(result, accepted)
        self.assertEqual(len(self.transport.calls), 1)

    def test_present_malformed_id_with_errors_remains_ambiguous(self):
        for prompt_id in ("", None, "../other"):
            result = {"prompt_id": prompt_id, "number": 3,
                      "node_errors": {"unused-output": {"errors": [{"message": "Invalid model"}]}}}
            self.transport.responses[("POST", "/prompt")] = response(result)
            self.assert_code("SUBMISSION_AMBIGUOUS", self.client.submit, self.graph, "client", "job")

    def test_json_validation_error_without_job_id_is_definitive_rejection(self):
        rejected = {"error": {"type": "prompt_outputs_failed_validation"}, "node_errors": {"1": {"errors": []}}}
        self.transport.responses[("POST", "/prompt")] = response(rejected)
        error = self.assert_code("PROMPT_REJECTED", self.client.submit, self.graph, "client", "job")
        self.assertEqual(error.details["worker_response"], rejected)

    def test_network_error_server_error_or_lost_metadata_is_ambiguous(self):
        for result in (TimeoutError("timed out after write"), IncompleteRead(b"partial"), response({"message": "server error"}, 500),
                       response({"prompt_id": "", "number": 1}), response({"prompt_id": "id", "number": True}),
                       (200, {}, b"not-json"), response(["wrong shape"])):
            with self.subTest(result=result):
                self.transport.calls.clear()
                self.transport.responses[("POST", "/prompt")] = result
                error = self.assert_code("SUBMISSION_AMBIGUOUS", self.client.submit, self.graph, "client", "job")
                self.assertTrue(error.details["may_have_been_accepted"])
                self.assertEqual(len(self.transport.calls), 1)

    def test_poll_queue_running_pending_and_absent_remains_unknown(self):
        self.transport.responses[("GET", "/history/owned-1")] = response({})
        for entries, expected in (({"queue_running": [], "queue_pending": [[1, "owned-1", {}, {}, []]]}, "queued"),
                                  ({"queue_running": [[1, "owned-1", {}, {}, []]], "queue_pending": []}, "running"),
                                  ({"queue_running": [], "queue_pending": []}, "unknown")):
            with self.subTest(expected=expected):
                self.transport.responses[("GET", "/queue")] = response(entries)
                result = self.client.poll("owned-1")
                self.assertEqual(result["status"], expected)
                self.assertEqual(result["outputs"], {})
        self.assertTrue(all(call[0] == "GET" for call in self.transport.calls))

    def test_captured_success_preserves_history_outputs_and_execution_timestamps(self):
        history = json.loads((ROOT / "workflows/h3/source_history.json").read_text())
        prompt_id = next(iter(history))
        self.transport.responses[("GET", "/history/" + prompt_id)] = response(history)
        result = self.client.poll(prompt_id)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["history"], history[prompt_id])
        self.assertEqual(result["outputs"], history[prompt_id]["outputs"])
        self.assertTrue(parse_animated_webp_outputs(result["outputs"], "11")[0]["animated"])
        self.assertEqual(len(self.transport.calls), 1)

    def test_failed_and_interrupted_history_are_terminal_and_keep_diagnostics(self):
        for event in ("execution_error", "execution_interrupted"):
            record = {"outputs": {}, "status": {"completed": False, "status_str": "error",
                      "messages": [[event, {"prompt_id": "owned-1", "exception_message": "fixture error"}]]}}
            self.transport.responses[("GET", "/history/owned-1")] = response({"owned-1": record})
            result = self.client.poll("owned-1")
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["error"]["messages"], record["status"]["messages"])

    def test_poll_rejects_malformed_history_and_foreign_prompt_ids(self):
        malformed = [None, [], {"outputs": []}, {"status": {"completed": "true"}}, {"status": {"status_str": []}},
                     {"status": {"messages": [["execution_success", "bad"]]}}]
        for record in malformed:
            self.transport.responses[("GET", "/history/owned-1")] = response({"owned-1": record})
            self.assert_code("MALFORMED_HISTORY", self.client.poll, "owned-1")
        mismatched = [{"prompt_id": "someone-else"}, {"prompt": [0, "someone-else"]},
                      {"status": {"messages": [["execution_success", {"prompt_id": "someone-else"}]]}}]
        for record in mismatched:
            self.transport.responses[("GET", "/history/owned-1")] = response({"owned-1": record})
            self.assert_code("HISTORY_ID_MISMATCH", self.client.poll, "owned-1")

    def test_poll_offline_does_not_resubmit_and_reconnect_can_read_same_id(self):
        self.transport.responses[("GET", "/history/owned-1")] = TimeoutError("offline")
        self.assert_code("WORKER_OFFLINE", self.client.poll, "owned-1")
        self.transport.responses[("GET", "/history/owned-1")] = response({})
        self.transport.responses[("GET", "/queue")] = response({"queue_running": [], "queue_pending": []})
        self.assertEqual(self.client.poll("owned-1")["status"], "unknown")
        self.assertTrue(all(call[0] == "GET" for call in self.transport.calls))

    def test_poll_rejects_bad_id_before_network_and_malformed_queue(self):
        self.assert_code("INVALID_PROMPT_ID", self.client.poll, "../other")
        self.assertEqual(self.transport.calls, [])
        self.transport.responses[("GET", "/history/owned-1")] = response({})
        self.transport.responses[("GET", "/queue")] = response({"queue_running": "bad", "queue_pending": []})
        self.assert_code("MALFORMED_QUEUE", self.client.poll, "owned-1")

    def test_output_download_encodes_reference_and_checks_content_type_and_magic(self):
        reference = {"filename": "small clip.webp", "subfolder": "LastLightRadio/job-1", "type": "output", "animated": True}
        calls = []
        def transport(method, path, body, headers):
            calls.append((method, path, body, headers))
            return 200, {"Content-Type": "image/webp; charset=binary"}, WEBP
        client = LiveComfyClient("http://worker.invalid", transport=transport)
        self.assertEqual(client.download_output(reference), WEBP)
        self.assertEqual(parse_qs(urlsplit(calls[0][1]).query),
                         {"filename": ["small clip.webp"], "subfolder": ["LastLightRadio/job-1"], "type": ["output"]})
        self.assertEqual(calls[0][0], "GET")

    def test_output_download_normalizes_windows_relative_subfolder(self):
        reference = {"filename": "clip.webp", "subfolder": "LastLightRadio\\job-1", "type": "output"}
        calls = []
        def transport(method, path, body, headers):
            calls.append(path)
            return 200, {"Content-Type": "image/webp"}, WEBP
        client = LiveComfyClient("http://worker.invalid", transport=transport)
        self.assertEqual(client.download_output(reference), WEBP)
        self.assertEqual(parse_qs(urlsplit(calls[0]).query)["subfolder"], ["LastLightRadio/job-1"])

    def test_output_download_rejects_windows_traversal_absolute_and_drive_folders(self):
        for folder in ("LastLightRadio\\..\\canon", "..\\canon", "\\absolute", "\\\\server\\share", "C:\\output"):
            reference = {"filename": "clip.webp", "subfolder": folder, "type": "output"}
            self.assert_code("UNSAFE_FILE_REFERENCE", self.client.download_output, reference)
        self.assertEqual(self.transport.calls, [])

    def test_download_rejects_traversal_wrong_folder_wrong_media_and_corruption(self):
        for reference in ({"filename": "../master.webp", "type": "output"},
                          {"filename": "clip.webp", "subfolder": "../master", "type": "output"},
                          {"filename": "clip.webp", "type": "input"},
                          {"filename": "AUX.webp", "type": "output"}):
            self.assert_code("UNSAFE_FILE_REFERENCE", self.client.download_output, reference)
        self.assertEqual(self.transport.calls, [])
        reference = {"filename": "clip.webp", "type": "output"}
        for headers, data in (({"Content-Type": "text/html"}, WEBP),
                              ({"Content-Type": "image/webp"}, b"not webp"),
                              ({"Content-Type": "image/webp"}, WEBP[:-1])):
            client = LiveComfyClient("http://worker.invalid", transport=lambda *_: (200, headers, data))
            self.assert_code("INVALID_OUTPUT_MEDIA", client.download_output, reference)

    def test_transport_and_default_reader_enforce_response_size(self):
        client = LiveComfyClient("http://worker.invalid", transport=lambda *_: (200, {}, b"x" * 9))
        with patch("last_light_radio.live.JSON_LIMIT", 8):
            # Explicit override exercises the transport seam independently of urllib.
            self.assert_code("RESPONSE_TOO_LARGE", lambda: client._request("GET", "/system_stats", limit=8))
        stream = io.BytesIO(b"x" * 9)
        stream.headers = {}
        self.assert_code("RESPONSE_TOO_LARGE", client._read_response, stream, 8)
        stream = io.BytesIO(b"x")
        stream.headers = {"Content-Length": "9"}
        self.assert_code("RESPONSE_TOO_LARGE", client._read_response, stream, 8)

    def test_default_transport_refuses_redirects_and_has_no_destructive_apis(self):
        handler = _RefuseRedirects()
        self.assert_code("REDIRECT_REFUSED", handler.redirect_request, None, None, 302, "Found", {}, "http://elsewhere")
        self.assertFalse(hasattr(self.client, "cancel"))
        self.assertFalse(hasattr(self.client, "interrupt"))
        self.assertFalse(hasattr(self.client, "clear_queue"))


if __name__ == "__main__":
    unittest.main()
