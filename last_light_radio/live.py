"""Small, auditable ComfyUI HTTP bridge for explicitly requested renders.

There are deliberately no queue-clearing, interrupt, or cancellation methods.
Requests are never retried here: in particular, retrying POST /prompt after a
lost response can silently create a second GPU job. Persist the local job ID
before calling submit and retain ambiguous failures for reconciliation.
"""

from __future__ import annotations

import copy
from http.client import HTTPException
import json
import math
import re
import uuid
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .comfy import ComfyClient, ComfyError, inspect_workflow


JSON_LIMIT = 32 * 1024 * 1024
UPLOAD_LIMIT = 64 * 1024 * 1024
OUTPUT_LIMIT = 256 * 1024 * 1024
_PROMPT_ID = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
_RESERVED = re.compile(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?\Z", re.I)


def _segment(value: Any, field: str) -> str:
    """Require a portable file/directory segment, never an absolute path."""
    if (not isinstance(value, str) or not value or value in (".", "..")
            or value[-1:] in (".", " ") or value[:1] == " "
            or any(ord(char) < 32 or ord(char) == 127 or char in '<>:"/\\|?*'
                   for char in value) or _RESERVED.fullmatch(value)):
        raise ComfyError("UNSAFE_FILE_REFERENCE", "Worker references must use portable relative filenames.", field=field)
    return value


def _subfolder(value: Any) -> str:
    if not isinstance(value, str):
        raise ComfyError("UNSAFE_FILE_REFERENCE", "Worker subfolder must be a relative string.", field="subfolder")
    # ComfyUI uses native os.path separators in returned metadata. Normalize
    # Windows relative folders before validating, without permitting absolute
    # drive/UNC paths or traversal segments in either separator convention.
    value = value.replace("\\", "/")
    if value:
        for part in value.split("/"):
            _segment(part, "subfolder")
    return value


def _prompt_id(value: Any) -> str:
    if not isinstance(value, str) or not _PROMPT_ID.fullmatch(value):
        raise ComfyError("INVALID_PROMPT_ID", "Worker prompt ID must be a nonempty portable identifier.")
    return value


def _identity(value: Any, name: str) -> str:
    if (not isinstance(value, str) or not value.strip() or len(value) > 200
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise ComfyError("INVALID_JOB_IDENTITY", "Supply a nonempty client and local job identity.", field=name)
    return value


class _RefuseRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ComfyError("REDIRECT_REFUSED", "Worker redirects are refused; use its explicit API URL.", status=code)


class LiveComfyClient:
    """HTTP client with a byte-level injectable transport and no hidden retries.

    The transport receives (method, path, body_or_none, headers), returning
    (HTTP_status, response_headers, response_bytes). Polling is read-only and
    can inspect persisted prompt IDs after a process restart.
    """

    def __init__(self, base_url: str, timeout: float = 30,
                 transport: Callable | None = None) -> None:
        validated = ComfyClient(base_url, timeout=timeout)
        self.base_url = validated.base_url
        self.timeout = validated.timeout
        self._transport = transport or self._http

    @staticmethod
    def _read_response(response, limit: int) -> bytes:
        declared = response.headers.get("Content-Length")
        if declared is not None:
            try:
                length = int(declared)
            except (TypeError, ValueError) as exc:
                raise ComfyError("INVALID_RESPONSE", "Worker returned an invalid Content-Length.") from exc
            if length < 0 or length > limit:
                raise ComfyError("RESPONSE_TOO_LARGE", "Worker response exceeds the configured byte limit.", limit=limit)
        body = response.read(limit + 1)
        if len(body) > limit:
            raise ComfyError("RESPONSE_TOO_LARGE", "Worker response exceeds the configured byte limit.", limit=limit)
        return body

    def _http(self, method: str, path: str, body: bytes | None,
              headers: dict) -> tuple[int, dict, bytes]:
        limit = OUTPUT_LIMIT if path.startswith("/view?") else JSON_LIMIT
        request = Request(self.base_url + path, data=body, headers=headers, method=method)
        opener = build_opener(_RefuseRedirects())
        try:
            response = opener.open(request, timeout=self.timeout)
        except HTTPError as exc:
            response = exc
        with response:
            return response.code, dict(response.headers.items()), self._read_response(response, limit)

    def _request(self, method: str, path: str, body: bytes | None = None,
                 headers: dict | None = None, *, limit: int = JSON_LIMIT,
                 ambiguity_code: str | None = None) -> tuple[int, dict, bytes]:
        try:
            result = self._transport(method, path, body, headers or {"Accept": "application/json"})
        except (ComfyError, HTTPException, URLError, OSError, TimeoutError) as exc:
            if ambiguity_code:
                raise ComfyError(ambiguity_code,
                                "Worker response was lost; do not automatically repeat this POST.",
                                endpoint=path, reason=str(exc), may_have_been_accepted=True) from exc
            if isinstance(exc, ComfyError):
                raise
            raise ComfyError("WORKER_OFFLINE", "Worker request failed; retry this read after reconnecting.",
                            endpoint=path, reason=str(exc)) from exc
        if (not isinstance(result, tuple) or len(result) != 3
                or type(result[0]) is not int or not isinstance(result[1], dict)
                or not isinstance(result[2], bytes)):
            raise ComfyError(ambiguity_code or "INVALID_RESPONSE", "Worker transport returned malformed response metadata.",
                            endpoint=path, may_have_been_accepted=bool(ambiguity_code))
        status, response_headers, data = result
        if len(data) > limit:
            raise ComfyError(ambiguity_code or "RESPONSE_TOO_LARGE", "Worker response exceeds the configured byte limit.",
                            endpoint=path, limit=limit, may_have_been_accepted=bool(ambiguity_code))
        normalized = {str(key).lower(): str(value) for key, value in response_headers.items()}
        return status, normalized, data

    @staticmethod
    def _decode(data: bytes, path: str, *, ambiguity_code: str | None = None) -> dict:
        try:
            value = json.loads(data.decode("utf-8"), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
        except (ValueError, UnicodeError) as exc:
            raise ComfyError(ambiguity_code or "INVALID_JSON", "Worker returned invalid JSON.",
                            endpoint=path, may_have_been_accepted=bool(ambiguity_code)) from exc
        if not isinstance(value, dict):
            raise ComfyError(ambiguity_code or "INVALID_RESPONSE", "Worker endpoint must return a JSON object.",
                            endpoint=path, may_have_been_accepted=bool(ambiguity_code))
        return value

    def _get_json(self, path: str) -> dict:
        status, _, data = self._request("GET", path)
        if not 200 <= status < 300:
            raise ComfyError("HTTP_ERROR", "Worker returned an HTTP error.", endpoint=path, status=status)
        return self._decode(data, path)

    def probe(self) -> dict:
        # Reuse the established report contract without expanding the read-only
        # ComfyClient itself to acquire any mutation methods.
        return ComfyClient(self.base_url, timeout=self.timeout,
                           transport=lambda _method, path, _body: self._get_json(path)).probe()

    def system_stats(self) -> dict:
        """Read current device statistics without reloading node definitions."""
        return self._get_json("/system_stats")

    def upload_image(self, data: bytes, filename: str, subfolder: str) -> dict:
        _segment(filename, "filename")
        subfolder = _subfolder(subfolder)
        if not isinstance(data, bytes) or not data or len(data) > UPLOAD_LIMIT:
            raise ComfyError("INVALID_UPLOAD", "Supply image bytes within the upload byte limit.", limit=UPLOAD_LIMIT)
        formats = {".png": ("image/png", data.startswith(b"\x89PNG\r\n\x1a\n")),
                   ".jpg": ("image/jpeg", data.startswith(b"\xff\xd8\xff")),
                   ".jpeg": ("image/jpeg", data.startswith(b"\xff\xd8\xff")),
                   ".webp": ("image/webp", len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP")}
        extension = "." + filename.rsplit(".", 1)[-1].lower()
        if extension not in formats or not formats[extension][1]:
            raise ComfyError("INVALID_UPLOAD", "Image extension and PNG, JPEG, or WebP signature must agree.")
        boundary = "last-light-radio-" + uuid.uuid4().hex
        chunks = []
        for name, value in (("type", "input"), ("subfolder", subfolder), ("overwrite", "false")):
            chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode("utf-8"))
        chunks.extend([
            f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{filename}"\r\nContent-Type: {formats[extension][0]}\r\n\r\n'.encode("utf-8"),
            data, f"\r\n--{boundary}--\r\n".encode("ascii")])
        body = b"".join(chunks)
        status, _, response = self._request("POST", "/upload/image", body,
                                            {"Accept": "application/json", "Content-Type": "multipart/form-data; boundary=" + boundary},
                                            ambiguity_code="UPLOAD_AMBIGUOUS")
        if not 200 <= status < 300:
            raise ComfyError("UPLOAD_REJECTED", "Worker rejected the image upload.", status=status)
        result = self._decode(response, "/upload/image", ambiguity_code="UPLOAD_AMBIGUOUS")
        name = _segment(result.get("name"), "name")
        folder = _subfolder(result.get("subfolder"))
        if result.get("type") != "input" or folder != subfolder:
            raise ComfyError("INVALID_UPLOAD_RESPONSE", "Worker upload destination does not match the requested input subfolder.")
        return {"name": name, "subfolder": folder, "type": "input", "path": f"{folder}/{name}" if folder else name}

    def submit(self, graph: dict, client_id: str, local_job_id: str) -> dict:
        report = inspect_workflow(graph)
        if not report["valid"]:
            raise ComfyError("INVALID_WORKFLOW", "Repair workflow diagnostics before submitting.", errors=report["errors"])
        payload = {"prompt": graph, "client_id": _identity(client_id, "client_id"),
                   "extra_data": {"last_light_radio": {"local_job_id": _identity(local_job_id, "local_job_id")}}}
        body = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
        status, _, response = self._request("POST", "/prompt", body,
                                            {"Accept": "application/json", "Content-Type": "application/json"},
                                            ambiguity_code="SUBMISSION_AMBIGUOUS")
        if not 200 <= status < 300:
            details = {"status": status}
            try:
                details["worker_response"] = self._decode(response, "/prompt")
            except ComfyError:
                pass
            if status in (400, 422):
                raise ComfyError("PROMPT_REJECTED", "Worker rejected the workflow; inspect its validation errors.", **details)
            raise ComfyError("SUBMISSION_AMBIGUOUS", "Worker submission failed without a definitive rejection; reconcile before resubmitting.",
                            may_have_been_accepted=True, **details)
        result = self._decode(response, "/prompt", ambiguity_code="SUBMISSION_AMBIGUOUS")
        # ComfyUI can accept the valid outputs of a partially valid graph and
        # return node_errors for other outputs alongside its queued prompt ID.
        # Retain that accepted identity and its diagnostics; rejecting it here
        # would lose ownership and could lead the caller to queue a duplicate.
        if "prompt_id" not in result and (result.get("error") or result.get("node_errors")):
            raise ComfyError("PROMPT_REJECTED", "Worker reported workflow validation errors.", worker_response=result)
        try:
            _prompt_id(result.get("prompt_id"))
            number = result.get("number")
            if type(number) not in (int, float) or not math.isfinite(number) or number < 0:
                raise ValueError("invalid queue number")
        except (ComfyError, ValueError, OverflowError) as exc:
            raise ComfyError("SUBMISSION_AMBIGUOUS", "Worker submission returned malformed job metadata; reconcile before resubmitting.",
                            may_have_been_accepted=True, worker_response=result) from exc
        return copy.deepcopy(result)

    def poll(self, prompt_id: str) -> dict:
        _prompt_id(prompt_id)
        history = self._get_json("/history/" + quote(prompt_id, safe=""))
        result = {"prompt_id": prompt_id, "status": "unknown", "outputs": {}}
        record = history.get(prompt_id)
        if prompt_id in history:
            if not isinstance(record, dict) or not isinstance(record.get("outputs", {}), dict):
                raise ComfyError("MALFORMED_HISTORY", "Worker history must contain an object with output metadata.", prompt_id=prompt_id)
            state = record.get("status", {})
            if not isinstance(state, dict) or ("completed" in state and type(state["completed"]) is not bool):
                raise ComfyError("MALFORMED_HISTORY", "Worker history status is malformed.", prompt_id=prompt_id)
            if "status_str" in state and not isinstance(state["status_str"], str):
                raise ComfyError("MALFORMED_HISTORY", "Worker history status name is malformed.", prompt_id=prompt_id)
            messages = state.get("messages", [])
            if (not isinstance(messages, list) or any(not isinstance(item, list) or len(item) != 2
                                                     or not isinstance(item[0], str) or not isinstance(item[1], dict)
                                                     for item in messages)):
                raise ComfyError("MALFORMED_HISTORY", "Worker history status messages are malformed.", prompt_id=prompt_id)
            recorded_prompt = record.get("prompt")
            if recorded_prompt is not None and (not isinstance(recorded_prompt, list) or len(recorded_prompt) < 2
                                                 or recorded_prompt[1] != prompt_id):
                raise ComfyError("HISTORY_ID_MISMATCH", "Worker history contains a different prompt identity.", prompt_id=prompt_id)
            if (("prompt_id" in record and record["prompt_id"] != prompt_id)
                    or any("prompt_id" in item[1] and item[1]["prompt_id"] != prompt_id for item in messages)):
                raise ComfyError("HISTORY_ID_MISMATCH", "Worker history contains a different prompt identity.", prompt_id=prompt_id)
            result.update({"history": copy.deepcopy(record), "outputs": copy.deepcopy(record.get("outputs", {}))})
            failures = [item for item in messages if item[0] in ("execution_error", "execution_interrupted")]
            if failures or state.get("status_str") in ("error", "failed", "interrupted"):
                result.update({"status": "failed", "error": {"code": "WORKER_EXECUTION_FAILED",
                               "message": "Worker render failed or was interrupted.", "messages": copy.deepcopy(failures or messages)}})
                return result
            if state.get("completed") is True and state.get("status_str") == "success":
                result["status"] = "success"
                return result
        queue = self._get_json("/queue")
        for key, status in (("queue_running", "running"), ("queue_pending", "queued")):
            entries = queue.get(key)
            if (not isinstance(entries, list) or any(not isinstance(item, list) or len(item) < 2
                                                     or not isinstance(item[1], str) for item in entries)):
                raise ComfyError("MALFORMED_QUEUE", "Worker queue metadata is malformed.", field=key)
            for item in entries:
                if item[1] == prompt_id:
                    result.update({"status": status, "number": item[0]})
                    return result
        result["reason"] = "Prompt is absent from current queue and retained history; completion is unconfirmed."
        return result

    def download_output(self, reference: dict) -> bytes:
        if not isinstance(reference, dict) or reference.get("type") != "output":
            raise ComfyError("UNSAFE_FILE_REFERENCE", "Only output-directory references can be downloaded.")
        filename = _segment(reference.get("filename"), "filename")
        folder = _subfolder(reference.get("subfolder", ""))
        if not filename.lower().endswith(".webp"):
            raise ComfyError("INVALID_OUTPUT_MEDIA", "The recovered H3 adapter expects a WebP output.")
        path = "/view?" + urlencode({"filename": filename, "subfolder": folder, "type": "output"})
        status, headers, data = self._request("GET", path, headers={"Accept": "image/webp"}, limit=OUTPUT_LIMIT)
        if not 200 <= status < 300:
            raise ComfyError("HTTP_ERROR", "Worker output download returned an HTTP error.", status=status)
        if (headers.get("content-type", "").split(";", 1)[0].strip().lower() != "image/webp"
                or len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WEBP"):
            raise ComfyError("INVALID_OUTPUT_MEDIA", "Downloaded output must have image/webp content type and RIFF/WEBP signature.")
        declared_size = int.from_bytes(data[4:8], "little") + 8
        if declared_size != len(data):
            raise ComfyError("INVALID_OUTPUT_MEDIA", "Downloaded WebP container size does not match its bytes.")
        return data

    def download_png_output(self, reference: dict) -> bytes:
        """Download a production SaveImage frame, retaining the WebP contract."""
        if not isinstance(reference, dict) or reference.get("type") != "output":
            raise ComfyError("UNSAFE_FILE_REFERENCE", "Only output-directory references can be downloaded.")
        filename = _segment(reference.get("filename"), "filename")
        folder = _subfolder(reference.get("subfolder", ""))
        if not filename.lower().endswith(".png"):
            raise ComfyError("INVALID_OUTPUT_MEDIA", "The production H3 adapter expects PNG frame outputs.")
        path = "/view?" + urlencode({"filename": filename, "subfolder": folder, "type": "output"})
        status, headers, data = self._request("GET", path, headers={"Accept": "image/png"}, limit=OUTPUT_LIMIT)
        if not 200 <= status < 300:
            raise ComfyError("HTTP_ERROR", "Worker frame download returned an HTTP error.", status=status)
        if (headers.get("content-type", "").split(";", 1)[0].strip().lower() != "image/png"
                or not data.startswith(b"\x89PNG\r\n\x1a\n")):
            raise ComfyError("INVALID_OUTPUT_MEDIA", "Downloaded frame must have image/png content type and PNG signature.")
        return data


    def download_mp4_output(self, reference: dict) -> bytes:
        """Download a declared joint-AV SaveVideo result; keep old parsers strict."""
        if not isinstance(reference, dict) or reference.get("type") != "output":
            raise ComfyError("UNSAFE_FILE_REFERENCE", "Only output-directory references can be downloaded.")
        filename = _segment(reference.get("filename"), "filename")
        folder = _subfolder(reference.get("subfolder", ""))
        if not filename.lower().endswith(".mp4"):
            raise ComfyError("INVALID_OUTPUT_MEDIA", "The joint-AV recipe requires an MP4 result.")
        path = "/view?" + urlencode({"filename": filename, "subfolder": folder, "type": "output"})
        status, headers, data = self._request("GET", path, headers={"Accept": "video/mp4"}, limit=20 * 1024 * 1024)
        mime = headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if not 200 <= status < 300:
            raise ComfyError("HTTP_ERROR", "Worker MP4 download returned an HTTP error.", status=status)
        if mime not in {"video/mp4", "application/octet-stream"} or len(data) < 16 or data[4:8] != b"ftyp":
            raise ComfyError("INVALID_OUTPUT_MEDIA", "The declared result is not an MP4 container.")
        return data
