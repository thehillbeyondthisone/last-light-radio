#!/usr/bin/env python3
"""Minimal HTTP client for ComfyUI at 192.168.1.168:8188.

Read-only preflight, validated workflow loading, queue submission,
history polling, and output download.

Usage:
    python comfyui_client.py preflight
    python comfyui_client.py run A02.workflow.json
    python comfyui_client.py poll <prompt_id>
    python comfyui_client.py download <subfolder> <filename>
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import json
import urllib.request
import urllib.parse
import urllib.error

BASE = "http://192.168.1.168:8188"

@dataclass
class PreflightResult:
    system_ok: bool
    queue_empty: bool
    model_names: list
    object_count: int

def preflight() -> PreflightResult:
    """Read-only preflight: system_stats, queue, object_info."""
    try:
        stats = _req(BASE + "/system_stats")
        queue = _req(BASE + "/queue")
        objects = _req(BASE + "/object_info")  # Returns dict of class_type -> info, not {"objects": [...]}
        # object_info returns a flat dict: {"KSampler": {...}, "CheckpointLoaderSimple": {...}, ...}
        model_names = [o["name"] for o in objects.values() if "name" in o]
        return PreflightResult(
            system_ok=True,
            queue_empty=(not queue.get("queue_running")) and (not queue.get("queue_pending")),
            model_names=model_names,
            object_count=len(objects),
        )
    except urllib.error.HTTPError as e:
        print(f"Preflight HTTP error: {e.code} {e.reason}")
        return PreflightResult(system_ok=False, queue_empty=False, model_names=[], object_count=0)

def load_workflow(path: str) -> dict:
    """Load a .workflow.json file and return the parsed JSON."""
    return json.loads(Path(path).read_text(encoding="utf-8"))

def validate_workflow(workflow: dict, objects: dict) -> list[str]:
    """Check that every node class in the workflow exists in the ComfyUI object_info."""
    missing = []
    for node in workflow.get("14", {}).get("inputs", []) + workflow.get("14", {}).get("inputs", []):
        # Nodes are stored under their index keys; extract class_type from node dict
        if isinstance(node, dict):
            cls = node.get("class_type")
            if cls and cls not in objects:
                missing.append(cls)
        elif isinstance(node, str):
            # Some nodes might be stored as strings
            cls = node
            if cls and cls not in objects:
                missing.append(cls)
    return missing

def submit(workflow: dict) -> dict:
    """POST workflow to the queue and return the receipt."""
    body = json.dumps(workflow).encode("utf-8")
    req = urllib.request.Request(
        BASE + "/prompt",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        resp = _req(req)
        # _req now returns a dict, so just return it
        return resp
    except urllib.error.HTTPError as e:
        print(f"Submit HTTP error: {e.code} {e.reason}")
        error_body = e.read().decode("utf-8")
        print(error_body)
        return {"prompt_id": None, "error": error_body}

def poll(prompt_id: str) -> dict:
    """GET /history/{prompt_id} and return the history."""
    try:
        return _req(BASE + f"/history/{prompt_id}")  # _req returns dict directly
    except urllib.error.HTTPError as e:
        print(f"Poll HTTP error: {e.code} {e.reason}")
        error_body = e.read().decode("utf-8")
        print(error_body)
        return {"prompt_id": prompt_id, "error": error_body}

def download(subfolder: str, filename: str, typ: str = "output") -> bytes:
    """GET /view?filename=...&type=... and return the binary data.
    
    Args:
        subfolder: Optional ("input" or "output"). If provided, the URL will include it.
        filename: The filename from ComfyUI's input/output directory
        typ: "input" or "output" (optional, defaults to "output")
    
    The URL format is:
        - Input: /view?filename=...&type=input
        - Output: /view?filename=...&subfolder=output&type=output
    """
    url = BASE + f"/view?filename={urllib.parse.quote(filename)}"
    if subfolder and subfolder != "input":
        url += f"&subfolder={urllib.parse.quote(subfolder)}"
    if typ:
        url += f"&type={urllib.parse.quote(typ)}"
    try:
        return urllib.request.urlopen(url, timeout=120).read()
    except urllib.error.HTTPError as e:
        print(f"Download HTTP error: {e.code} {e.reason}")
        return b""

def _req(req_or_url, method="GET") -> dict:
    """Helper to build and send a request, returning the parsed JSON response."""
    if isinstance(req_or_url, str):
        req = urllib.request.Request(req_or_url, method=method)
    elif isinstance(req_or_url, urllib.request.Request):
        req = req_or_url
    else:
        raise TypeError("req_or_url must be str or Request")
    resp = urllib.request.urlopen(req, timeout=120)
    return json.loads(resp.read().decode("utf-8"))

def main():
    import sys
    if len(sys.argv) < 2:
        print("Usage: python comfyui_client.py <command> [args]")
        print("Commands: preflight | run <workflow.json> | poll <prompt_id> | download <subfolder> <filename>")
        return

    cmd = sys.argv[1]
    if cmd == "preflight":
        r = preflight()
        print(f"System OK: {r.system_ok}")
        print(f"Queue empty: {r.queue_empty}")
        print(f"Models: {r.model_names}")
        print(f"Objects: {r.object_count}")
    elif cmd == "run":
        if len(sys.argv) < 3:
            print("Missing workflow path")
            return
        wf = load_workflow(sys.argv[2])
        objs = json.loads(_req(BASE + "/object_info").read())
        missing = validate_workflow(wf, objs)
        if missing:
            print(f"Missing node classes: {missing}")
            return
        r = submit(wf)
        print(f"Receipt: {json.dumps(r, indent=2)}")
    elif cmd == "poll":
        if len(sys.argv) < 3:
            print("Missing prompt_id")
            return
        h = poll(sys.argv[2])
        print(f"History: {json.dumps(h, indent=2)}")
    elif cmd == "download":
        if len(sys.argv) < 4:
            print("Missing subfolder and filename")
            return
        data = download(sys.argv[2], sys.argv[3])
        if data:
            path = Path.cwd() / f"{sys.argv[3]}_{sys.argv[2]}.bin"
            path.write_bytes(data)
            print(f"Downloaded to: {path}")
        else:
            print("Download failed")
    else:
        print(f"Unknown command: {cmd}")

if __name__ == "__main__":
    main()
