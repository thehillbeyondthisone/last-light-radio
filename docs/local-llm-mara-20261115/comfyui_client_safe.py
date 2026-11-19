#!/usr/bin/env python3
"""Safer ComfyUI client for the local Mara experiment (stdlib only).

Written 2026-11-16 to replace the broken draft `comfyui_client.py` (kept
unchanged next to this file). Follows the START_HERE.md protocol:

  preflight <workflow.json>             read-only: stats, queue, node classes,
                                        every loader/LoadImage choice, reference hash
  prepare <workflow.json> <exp_dir>     copy graph into a NEW experiment dir with a
                                        unique output prefix; write experiment.json
  submit <exp_dir> --confirm            exactly one POST per experiment dir
  reconcile <exp_dir>                   find this experiment's job in queue/history
                                        by its unique prefix (after an ambiguous POST)
  poll <exp_dir> [--wait]               GET /history/<id>, save history.json
  download <exp_dir>                    fetch outputs named in history, sha256 them

Never cancels, interrupts, clears or frees anything on the server.
Base URL: --base or env COMFY_BASE (default http://192.168.1.168:8188).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

DEFAULT_BASE = os.environ.get("COMFY_BASE", "http://192.168.1.168:8188")
SAVE_CLASSES = {"SaveVideo", "SaveImage", "SaveAnimatedWEBP", "SaveAudio"}
EXIT_OK, EXIT_FAIL, EXIT_AMBIGUOUS = 0, 1, 3


class ClientError(Exception):
    pass


# ---------------------------------------------------------------- HTTP

def http_get_json(base: str, path: str, timeout: float = 30):
    with urllib.request.urlopen(base + path, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_get_bytes(base: str, path: str, timeout: float = 300) -> bytes:
    with urllib.request.urlopen(base + path, timeout=timeout) as resp:
        return resp.read()


def view_path(filename: str, subfolder: str, typ: str) -> str:
    q = {"filename": filename, "type": typ}
    if subfolder:
        q["subfolder"] = subfolder
    return "/view?" + urllib.parse.urlencode(q)


# ---------------------------------------------------------------- helpers

def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, data, exclusive: bool = False) -> None:
    text = json.dumps(data, indent=2, ensure_ascii=False)
    mode = "x" if exclusive else "w"
    with path.open(mode, encoding="utf-8") as f:
        f.write(text + "\n")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_graph(path: Path) -> dict:
    g = read_json(path)
    if not isinstance(g, dict) or not g:
        raise ClientError(f"{path}: not an API-format graph (expected a dict of nodes)")
    for nid, node in g.items():
        if not isinstance(node, dict) or "class_type" not in node or "inputs" not in node:
            raise ClientError(f"{path}: node {nid} lacks class_type/inputs (UI-format export?)")
    return g


def save_nodes(graph: dict) -> list[str]:
    return [nid for nid, n in graph.items() if n["class_type"] in SAVE_CLASSES]


def graph_prefixes(graph) -> set[str]:
    out = set()
    if isinstance(graph, dict):
        for n in graph.values():
            if isinstance(n, dict) and n.get("class_type") in SAVE_CLASSES:
                p = n.get("inputs", {}).get("filename_prefix")
                if isinstance(p, str):
                    out.add(p)
    return out


def combo_choices(spec):
    """Return the list of allowed values for a combo input, or None if not a combo."""
    if not isinstance(spec, list) or not spec:
        return None
    if isinstance(spec[0], list):  # legacy: [[choices...], {...}]
        return spec[0]
    if spec[0] == "COMBO" and len(spec) > 1 and isinstance(spec[1], dict):
        opts = spec[1].get("options")
        return opts if isinstance(opts, list) else None
    return None


def summarize_graph(graph: dict) -> dict:
    """Pull out the recipe facts worth recording. Generic, but tuned to the A0x graphs."""
    s: dict = {"models": {}, "reference_images": {}}
    for nid, n in graph.items():
        ct, inp = n["class_type"], n["inputs"]
        for key in ("unet_name", "clip_name", "vae_name", "lora_name", "ckpt_name"):
            if isinstance(inp.get(key), str):
                s["models"][f"{nid}:{ct}.{key}"] = inp[key]
        if ct == "LoadImage" and isinstance(inp.get("image"), str):
            s["reference_images"][nid] = inp["image"]
        if "noise_seed" in inp:
            s["seed"] = inp["noise_seed"]
        if ct == "MiniMaxH3ImageToVideo":
            s.update(prompt=inp.get("prompt"), width=inp.get("width"),
                     height=inp.get("height"), frames=inp.get("length"))
        if ct == "CreateVideo":
            s["fps"] = inp.get("fps")
        if ct == "BasicScheduler":
            s.update(steps=inp.get("steps"), scheduler=inp.get("scheduler"), denoise=inp.get("denoise"))
        if ct == "KSamplerSelect":
            s["sampler"] = inp.get("sampler_name")
    return s


# ---------------------------------------------------------------- preflight

def run_preflight(base: str, graph: dict, hash_references: bool = True) -> dict:
    """Read-only checks. Returns a report; report['problems'] empty means OK."""
    rep: dict = {"base": base, "checked_at": now(), "problems": [], "warnings": []}

    stats = http_get_json(base, "/system_stats")
    rep["comfyui_version"] = stats.get("system", {}).get("comfyui_version")
    rep["devices"] = [
        {"name": d.get("name"),
         "vram_total_gb": round(d.get("vram_total", 0) / 2**30, 1),
         "vram_free_gb": round(d.get("vram_free", 0) / 2**30, 1)}
        for d in stats.get("devices", [])
    ]

    q = http_get_json(base, "/queue")
    rep["queue_running"] = len(q.get("queue_running", []))
    rep["queue_pending"] = len(q.get("queue_pending", []))
    if rep["queue_running"] or rep["queue_pending"]:
        rep["warnings"].append("GPU queue occupied; coordinate with its owner, do not clear it")

    info_cache: dict = {}
    for nid, n in graph.items():
        ct = n["class_type"]
        if ct not in info_cache:
            try:
                info_cache[ct] = http_get_json(base, "/object_info/" + urllib.parse.quote(ct)).get(ct)
            except urllib.error.HTTPError:
                info_cache[ct] = None
        info = info_cache[ct]
        if not info:
            rep["problems"].append(f"node {nid}: class {ct} not installed")
            continue
        spec_all = {**info.get("input", {}).get("required", {}), **info.get("input", {}).get("optional", {})}
        for key, val in n["inputs"].items():
            if isinstance(val, list):  # link to another node
                continue
            choices = combo_choices(spec_all.get(key))
            if choices is not None and val not in choices:
                rep["problems"].append(f"node {nid} {ct}.{key}: '{val}' not among server choices ({len(choices)} offered)")

    rep["reference_hashes"] = {}
    if hash_references:
        for nid, n in graph.items():
            if n["class_type"] == "LoadImage" and isinstance(n["inputs"].get("image"), str):
                name = n["inputs"]["image"]
                try:
                    data = http_get_bytes(base, view_path(name, "", "input"))
                    rep["reference_hashes"][name] = {"sha256": sha256_bytes(data), "bytes": len(data)}
                except urllib.error.HTTPError as e:
                    rep["problems"].append(f"reference {name}: /view returned {e.code}")
    return rep


# ---------------------------------------------------------------- experiment dir

def safe_component(text: str, what: str) -> str:
    if not text or any(c in text for c in '\\:*?"<>|') or text in (".", "..") or "/" in text:
        raise ClientError(f"unsafe {what}: {text!r}")
    return text


def cmd_prepare(args) -> int:
    src = Path(args.workflow)
    graph = load_graph(src)
    exp = Path(args.exp_dir)
    exp_id = safe_component(exp.name, "experiment directory name")
    if exp.exists():
        raise ClientError(f"{exp} already exists; every experiment needs a NEW directory")
    exp.mkdir(parents=True)

    savers = save_nodes(graph)
    if len(savers) != 1:
        raise ClientError(f"expected exactly one save node, found {savers}")
    shot = safe_component(args.shot or src.name.split(".")[0], "shot name")
    prefix = f"{exp_id}/{shot}"
    old_prefix = graph[savers[0]]["inputs"].get("filename_prefix")
    graph[savers[0]]["inputs"]["filename_prefix"] = prefix

    for setting in args.set or []:  # node.input=value, JSON value if it parses
        target, _, raw = setting.partition("=")
        nid, _, key = target.partition(".")
        if nid not in graph or not key or key not in graph[nid]["inputs"]:
            raise ClientError(f"--set {setting}: no such node/input")
        if isinstance(graph[nid]["inputs"][key], list):
            raise ClientError(f"--set {setting}: input is a graph link; refusing to rewire")
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            value = raw
        graph[nid]["inputs"][key] = value

    wf_path = exp / "workflow.json"
    write_json(wf_path, graph, exclusive=True)
    ledger = {
        "experiment_id": exp_id,
        "created_at": now(),
        "source_workflow": str(src.resolve()),
        "source_workflow_sha256": sha256_file(src),
        "submitted_workflow_sha256": sha256_file(wf_path),
        "original_filename_prefix": old_prefix,
        "filename_prefix": prefix,
        "changed_inputs": args.set or [],
        "intended_variable": args.variable,
        "recipe": summarize_graph(graph),
        "planned_start_state": args.planned_start,
        "planned_end_state": args.planned_end,
        "observed_start_state": None,
        "observed_end_state": None,
        "status": "prepared",
        "approval": "candidate",
    }
    write_json(exp / "experiment.json", ledger, exclusive=True)
    print(f"Prepared {exp} (prefix {prefix}). Nothing was sent to the server.")
    return EXIT_OK


def update_ledger(exp: Path, **fields) -> None:
    p = exp / "experiment.json"
    ledger = read_json(p)
    ledger.update(fields)
    write_json(p, ledger)


# ---------------------------------------------------------------- submit / reconcile

def find_by_prefix(base: str, prefix: str) -> list[dict]:
    """Search queue and history for jobs whose save prefix equals `prefix`."""
    hits = []
    q = http_get_json(base, "/queue")
    for state in ("queue_running", "queue_pending"):
        for item in q.get(state, []):
            if len(item) > 2 and prefix in graph_prefixes(item[2]):
                hits.append({"prompt_id": item[1], "where": state})
    hist = http_get_json(base, "/history", timeout=120)
    for pid, entry in hist.items():
        p = entry.get("prompt", [])
        if len(p) > 2 and prefix in graph_prefixes(p[2]):
            hits.append({"prompt_id": pid, "where": "history",
                         "status": entry.get("status", {}).get("status_str")})
    return hits


def cmd_submit(args) -> int:
    exp = Path(args.exp_dir)
    ledger = read_json(exp / "experiment.json")
    intent = exp / "submit-intent.json"
    if intent.exists() or (exp / "receipt.json").exists():
        raise ClientError("this experiment was already submitted (or attempted). "
                          "Use reconcile/poll, or prepare a NEW experiment dir.")
    if not args.confirm:
        raise ClientError("submit changes the shared GPU queue; re-run with --confirm "
                          "once the GPU owner has agreed")
    graph = load_graph(exp / "workflow.json")
    if sha256_file(exp / "workflow.json") != ledger["submitted_workflow_sha256"]:
        raise ClientError("workflow.json changed after prepare; prepare a new experiment")

    rep = run_preflight(args.base, graph)
    write_json(exp / "preflight.json", rep)
    if rep["problems"]:
        print("\n".join(rep["problems"]))
        raise ClientError("preflight failed; not submitting")
    if rep["queue_running"] or rep["queue_pending"]:
        raise ClientError("GPU queue occupied; coordinate, do not clear it")
    if find_by_prefix(args.base, ledger["filename_prefix"]):
        raise ClientError("server already has a job with this prefix; reconcile instead")

    client_id = str(uuid.uuid4())
    write_json(intent, {"at": now(), "client_id": client_id, "base": args.base,
                        "filename_prefix": ledger["filename_prefix"],
                        "reference_hashes": rep["reference_hashes"]}, exclusive=True)
    update_ledger(exp, status="submitting", reference_hashes=rep["reference_hashes"])

    body = json.dumps({"prompt": graph, "client_id": client_id}).encode("utf-8")
    req = urllib.request.Request(args.base + "/prompt", data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        write_json(exp / "rejection.json", {"at": now(), "code": e.code, "body": detail})
        update_ledger(exp, status="rejected")
        print(detail)
        raise ClientError(f"server rejected the job (HTTP {e.code}); see rejection.json")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        update_ledger(exp, status="ambiguous")
        print(f"POST outcome unknown ({e}). Do NOT resubmit. Run: reconcile {exp}")
        return EXIT_AMBIGUOUS

    (exp / "receipt.raw.json").write_text(raw, encoding="utf-8")
    receipt = json.loads(raw)
    write_json(exp / "receipt.json", receipt)
    pid = receipt.get("prompt_id")
    if not pid or receipt.get("node_errors"):
        update_ledger(exp, status="rejected")
        raise ClientError("no prompt_id or node errors; see receipt.json")
    update_ledger(exp, status="queued", prompt_id=pid, submitted_at=now())
    print(f"Queued prompt_id {pid}")
    return EXIT_OK


def cmd_reconcile(args) -> int:
    exp = Path(args.exp_dir)
    ledger = read_json(exp / "experiment.json")
    hits = find_by_prefix(args.base, ledger["filename_prefix"])
    write_json(exp / "reconcile.json", {"at": now(), "hits": hits})
    if not hits:
        print("No job with this prefix in queue or history. The POST did not land, or history "
              "was cleared. Do not resubmit from this dir; prepare a new one if you retry.")
        return EXIT_FAIL
    if len(hits) > 1:
        print(json.dumps(hits, indent=2))
        raise ClientError("more than one job carries this prefix; resolve by hand")
    pid = hits[0]["prompt_id"]
    if not (exp / "receipt.json").exists():
        write_json(exp / "receipt.json", {"prompt_id": pid, "recovered_by": "reconcile"})
    update_ledger(exp, prompt_id=pid, status="queued" if hits[0]["where"] != "history" else ledger["status"])
    print(f"Found {pid} in {hits[0]['where']}")
    return EXIT_OK


# ---------------------------------------------------------------- poll / download

def prompt_id_of(exp: Path) -> str:
    pid = read_json(exp / "experiment.json").get("prompt_id")
    if not pid:
        raise ClientError("no prompt_id recorded; submit or reconcile first")
    return pid


def cmd_poll(args) -> int:
    exp = Path(args.exp_dir)
    pid = prompt_id_of(exp)
    deadline = time.monotonic() + args.timeout
    while True:
        try:
            hist = http_get_json(args.base, "/history/" + urllib.parse.quote(pid))
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            print(f"{now()} poll failed ({e}); will retry the GET, never the submit")
            hist = {}
        entry = hist.get(pid)
        if entry:
            write_json(exp / "history.json", hist)
            st = entry.get("status", {})
            status = st.get("status_str")
            update_ledger(exp, status="succeeded" if status == "success" and st.get("completed") else f"failed:{status}",
                          finished_at=now())
            print(f"{pid}: {status} completed={st.get('completed')}")
            return EXIT_OK if status == "success" else EXIT_FAIL
        print(f"{now()} {pid}: not in history yet (running or pending)")
        if not args.wait or time.monotonic() > deadline:
            return EXIT_AMBIGUOUS if not args.wait else EXIT_FAIL
        time.sleep(args.interval)


def safe_rel(subfolder: str, filename: str) -> PurePosixPath:
    parts = [p for p in subfolder.replace("\\", "/").split("/") if p] + [filename]
    for p in parts:
        if p in (".", "..") or any(c in p for c in ':*?"<>|') or "\\" in p or "/" in p:
            raise ClientError(f"unsafe output path component: {p!r}")
    return PurePosixPath(*parts)


def cmd_download(args) -> int:
    exp = Path(args.exp_dir)
    pid = prompt_id_of(exp)
    hist = read_json(exp / "history.json")
    entry = hist.get(pid) or {}
    if entry.get("status", {}).get("status_str") != "success":
        raise ClientError("history does not show success; not downloading")
    files = []
    for node_id, out in entry.get("outputs", {}).items():
        for kind, items in out.items():
            if not isinstance(items, list):
                continue
            for it in items:
                if isinstance(it, dict) and "filename" in it:
                    files.append((node_id, kind, it))
    if not files:
        raise ClientError("history lists no output files")
    out_root = (exp / "outputs").resolve()
    records = []
    for node_id, kind, it in files:
        rel = safe_rel(it.get("subfolder", ""), it["filename"])
        dest = out_root.joinpath(*rel.parts)
        if out_root not in dest.resolve().parents:
            raise ClientError(f"refusing path outside outputs/: {rel}")
        if dest.exists():
            raise ClientError(f"{dest} already exists; not overwriting")
        data = http_get_bytes(args.base, view_path(it["filename"], it.get("subfolder", ""), it.get("type", "output")))
        if not data:
            raise ClientError(f"{rel}: empty download")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        records.append({"node": node_id, "kind": kind, "server_file": it, "local": str(dest),
                        "bytes": len(data), "sha256": sha256_bytes(data)})
        print(f"{dest}  {len(data)} bytes  sha256 {records[-1]['sha256']}")
    update_ledger(exp, outputs=records, downloaded_at=now())
    print("Downloaded. Still required: full decode, probe, and human/local visual+audio review.")
    return EXIT_OK


# ---------------------------------------------------------------- CLI

def cmd_preflight(args) -> int:
    graph = load_graph(Path(args.workflow))
    rep = run_preflight(args.base, graph, hash_references=not args.no_hash)
    print(json.dumps(rep, indent=2))
    if args.out:
        write_json(Path(args.out), rep)
    return EXIT_FAIL if rep["problems"] else EXIT_OK


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default=DEFAULT_BASE, help="ComfyUI base URL")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("preflight", help="read-only checks")
    p.add_argument("workflow")
    p.add_argument("--no-hash", action="store_true", help="skip downloading references to hash them")
    p.add_argument("--out", help="also write the report to this JSON file")
    p.set_defaults(fn=cmd_preflight)

    p = sub.add_parser("prepare", help="create a new experiment dir (local only)")
    p.add_argument("workflow")
    p.add_argument("exp_dir", help="NEW directory; its name becomes the output prefix folder")
    p.add_argument("--shot", help="shot name in the prefix (default: workflow stem, e.g. A02)")
    p.add_argument("--set", action="append", metavar="NODE.INPUT=VALUE",
                   help="change one literal input, e.g. 18.image=new-ref.png (repeatable)")
    p.add_argument("--variable", help="the one variable this experiment tests")
    p.add_argument("--planned-start")
    p.add_argument("--planned-end")
    p.set_defaults(fn=cmd_prepare)

    p = sub.add_parser("submit", help="POST once (changes the shared GPU queue)")
    p.add_argument("exp_dir")
    p.add_argument("--confirm", action="store_true")
    p.set_defaults(fn=cmd_submit)

    p = sub.add_parser("reconcile", help="find this experiment's job by prefix")
    p.add_argument("exp_dir")
    p.set_defaults(fn=cmd_reconcile)

    p = sub.add_parser("poll", help="GET /history/<prompt_id>")
    p.add_argument("exp_dir")
    p.add_argument("--wait", action="store_true")
    p.add_argument("--interval", type=float, default=20)
    p.add_argument("--timeout", type=float, default=1800)
    p.set_defaults(fn=cmd_poll)

    p = sub.add_parser("download", help="fetch outputs listed in history.json")
    p.add_argument("exp_dir")
    p.set_defaults(fn=cmd_download)

    args = ap.parse_args(argv)
    args.base = args.base.rstrip("/")
    try:
        return args.fn(args)
    except ClientError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return EXIT_FAIL
    except urllib.error.URLError as e:
        print(f"ERROR: cannot reach {args.base}: {e}", file=sys.stderr)
        return EXIT_FAIL


if __name__ == "__main__":
    sys.exit(main())
