"""Same-origin bridge from the editor to the local Astrid shot-control service.

Ported from artifacts/production-reference-multi-20261117/native_viewer_server.py (Codex, 2026-11-18)
so the one editor (:8769) can show original generation receipts and queue SD rerolls.
Only reads (state, original/reference/take media) and POST /api/reroll pass through. The service's
/api/use (which writes timeline copies) is deliberately not exposed.
"""

from __future__ import annotations

import os
import re
import urllib.error
import urllib.request

PREFIX = "/astrid-shot-controls"
TARGET = os.environ.get("LLR_SHOT_CONTROLS", "http://127.0.0.1:8773")
GET = re.compile(r"/api/state|/media/(?:original|reference)/(?:master|insert|reverse)|/media/take/[0-9]{8}-[0-9]{6}-[a-f0-9]{8}")
POST = ("/api/reroll",)


def handles(path: str) -> bool:
    return path.startswith(PREFIX + "/")


def bridge(handler, mutating: bool = False) -> None:
    port = handler.server.server_port
    suffix = handler.path[len(PREFIX):].split("?", 1)[0]
    if handler.headers.get("Host") not in {f"127.0.0.1:{port}", f"localhost:{port}"}:
        return handler.send_json({"error": "Invalid host."}, 403)
    data, headers = None, {}
    if mutating:
        origin_ok = handler.headers.get("Origin") in {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}
        if (suffix not in POST or not origin_ok or handler.headers.get("X-Astrid-Control") != "1"
                or handler.headers.get("Content-Type", "").split(";")[0] != "application/json"):
            return handler.send_json({"error": "Same-origin verified shot-control request required."}, 403)
        try:
            length = int(handler.headers.get("Content-Length", 0))
        except ValueError:
            return handler.send_json({"error": "Invalid length."}, 400)
        if not 0 < length < 32000:
            return handler.send_json({"error": "Invalid length."}, 400)
        data = handler.rfile.read(length)
        target_port = TARGET.rsplit(":", 1)[-1]
        headers = {"Origin": f"http://127.0.0.1:{target_port}", "X-Astrid-Control": "1", "Content-Type": "application/json"}
    elif not GET.fullmatch(suffix):
        return handler.send_json({"error": "Unknown shot-control path."}, 404)
    try:
        request = urllib.request.Request(TARGET + suffix, data=data, headers=headers)
        try:
            reply = urllib.request.urlopen(request, timeout=90)
        except urllib.error.HTTPError as error:
            reply = error
        with reply:
            payload = reply.read()
            status = reply.code
            content_type = reply.headers.get("Content-Type", "application/octet-stream")
    except Exception:
        return handler.send_json({"error": "The shot-control service (port 8773) is not running. Nothing was retried."}, 502)
    media = not mutating and suffix.startswith("/media/") and status == 200
    content_range = None
    requested = handler.headers.get("Range") if media else None
    if requested:  # partial media for seeking (Safari/iOS probe requests too)
        size = len(payload)
        match = re.fullmatch(r"bytes=(\d*)-(\d*)", requested)
        start = end = None
        if match:
            left, right = match.groups()
            if left:
                start, end = int(left), min(int(right) if right else size - 1, size - 1)
            elif right and int(right) > 0:
                start, end = max(0, size - int(right)), size - 1
        if start is None or not 0 <= start <= end < size:
            status, payload, content_range = 416, b"", f"bytes */{size}"
        else:
            status, payload, content_range = 206, payload[start:end + 1], f"bytes {start}-{end}/{size}"
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(payload)))
    if media:
        handler.send_header("Accept-Ranges", "bytes")
    if content_range:
        handler.send_header("Content-Range", content_range)
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.end_headers()
    handler.wfile.write(payload)
