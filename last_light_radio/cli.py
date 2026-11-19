"""Offline demo, workflow inspection, and an explicitly requested LAN probe."""

from __future__ import annotations

import argparse
import copy
import json
import logging
import sys
import time
from collections import Counter
from pathlib import Path

from .comfy import ComfyClient, ComfyError, MockComfyClient, WorkflowError
from .comfy import inspect_workflow, load_bindings, prepare_workflow
from .domain import load_project, validate_project
from .generation import load_request, poll_generation, start_generation
from .live import LiveComfyClient
from .report import schedule_report
from .scheduler import format_event_log, schedule
from .store import ProjectStore, canonical_bytes

ROOT = Path(__file__).resolve().parents[1]
LOG = logging.getLogger("last_light_radio")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({"level": record.levelname.lower(), "event": record.getMessage(),
                           **getattr(record, "fields", {})}, sort_keys=True)


def read_json(path: str | Path) -> dict:
    def unique_pairs(pairs):
        value = {}
        for name, item in pairs:
            if name in value:
                raise ValueError(f"Duplicate JSON property: {name}")
            value[name] = item
        return value

    with Path(path).open(encoding="utf-8-sig") as stream:
        return json.load(stream, object_pairs_hook=unique_pairs)


def emit(value: dict) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False))


def _demo(args: argparse.Namespace) -> int:
    original = load_project(args.project)
    project = copy.deepcopy(original)
    store = ProjectStore(args.output)
    project_folder = Path(args.project).resolve().parent
    for scene in project["scenes"]:
        source = (project_folder / scene["master"]["path"]).resolve()
        # Verify the supplied record before importing, then pin the immutable copy.
        source_store = ProjectStore(project_folder, create=False)
        source_store.verify_master(scene["master"])
        scene["master"] = {**store.import_master(source), "id": scene["master"]["id"]}
        store.verify_master(scene["master"])
    project = validate_project(project)
    snapshot = store.save_snapshot(project)
    manifest = schedule(project, seed=args.seed, duration_seconds=args.seconds, fps=args.fps)
    artifacts = store.save_manifest(manifest, format_event_log(manifest), schedule_report(manifest))
    LOG.info("schedule.completed", extra={"fields": {"seed": args.seed,
             "frames": manifest["duration_frames"], "manifest_hash": manifest["manifest_hash"]}})
    graph = read_json(ROOT / "workflows/h3/workflow_api.json")
    mock = MockComfyClient()
    job_id = mock.submit(graph)
    LOG.info("render.queued", extra={"fields": {"mock": True, "prompt_id": job_id}})
    job = mock.wait(job_id)
    store.save_snapshot({"mock": True, "workflow": graph, "result": job}, kind="jobs")
    LOG.info("render.completed", extra={"fields": {"mock": True, "prompt_id": job_id}})
    counts = Counter(event["variant_id"] for event in manifest["events"] if event["kind"] == "clip")
    emit({"mode": "offline_mock", "fixture": project["fixture"], "seed": args.seed,
          "duration_frames": manifest["duration_frames"], "fps": args.fps,
          "variant_counts": dict(sorted(counts.items())), "project_snapshot": snapshot,
          "artifacts": artifacts, "mock_job_status": job["status"], "network_requests": 0})
    return 0


def _workflow(args: argparse.Namespace) -> int:
    graph = read_json(args.workflow)
    definitions = read_json(args.definitions) if args.definitions else None
    report = inspect_workflow(graph, definitions)
    bindings = load_bindings(args.bindings)
    result = {"template_inspection": report, "bindings": bindings, "submitted": False}
    overrides = {name: value for name, value in {
        "source_image": args.image, "motion_prompt": args.prompt, "seed": args.seed,
    }.items() if value is not None}
    prepared = prepare_workflow(graph, bindings, overrides)
    report = inspect_workflow(prepared, definitions)
    result["inspection"] = report
    if not report["valid"]:
        emit(result)
        return 1
    if args.preview_output:
        path = Path(args.preview_output)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = canonical_bytes(prepared)
        try:
            with path.open("xb") as stream:
                stream.write(data)
        except FileExistsError:
            if path.read_bytes() != data:
                raise ValueError("Preview file exists with different content; choose a new filename") from None
        result["preview_output"] = str(path.resolve())
    emit(result)
    return 0 if report["valid"] else 1


def _probe(args: argparse.Namespace) -> int:
    config = Path(args.config)
    saved = read_json(config) if not args.url and config.is_file() else {}
    if not isinstance(saved, dict):
        raise ValueError("Worker config must be a JSON object containing base_url")
    url = args.url or saved.get("base_url")
    if not url:
        raise ValueError("Supply --url http://HOST:PORT or save a successful endpoint with --save")
    result = ComfyClient(url, timeout=args.timeout).probe()
    definitions = result.pop("object_info", None)
    if definitions:
        result["workflow_compatibility"] = inspect_workflow(read_json(args.workflow), definitions)
    if args.save and result["connected"]:
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_bytes(canonical_bytes({"base_url": result["base_url"]}))
        result["saved_config"] = str(config.resolve())
    emit(result)
    return 0 if result["connected"] else 1


def _worker_url(args: argparse.Namespace) -> str:
    if args.url:
        return args.url
    config = Path(args.config)
    saved = read_json(config) if config.is_file() else {}
    if not isinstance(saved, dict) or not saved.get("base_url"):
        raise ValueError("Supply --url http://HOST:PORT or first use probe --save")
    return saved["base_url"]


def _render(args: argparse.Namespace) -> int:
    client = LiveComfyClient(_worker_url(args), timeout=args.timeout)
    result = start_generation(ProjectStore(args.output), client, read_json(args.workflow),
                              load_bindings(args.bindings), args.image, args.prompt, args.seed)
    LOG.info("render.queued", extra={"fields": {"mock": False, **result}})
    emit(result)
    return 0


def _job(args: argparse.Namespace) -> int:
    if not 0 <= args.wait_seconds <= 45:
        raise ValueError("--wait-seconds must be between 0 and 45; call job again to continue")
    store = ProjectStore(args.output, create=False)
    request = load_request(store, args.job_id)
    client = LiveComfyClient(args.url or request["base_url"], timeout=args.timeout)
    deadline = time.monotonic() + args.wait_seconds
    previous = None
    while True:
        result = poll_generation(store, client, args.job_id)
        if result["status"] != previous:
            LOG.info("render." + result["status"], extra={"fields": {
                "mock": False, "local_job_id": args.job_id, "prompt_id": result["prompt_id"]}})
            previous = result["status"]
        if "candidate" in result:
            result["downloaded_files"] = [str(store.resolve(item["path"])) for item in result["candidate"]["outputs"]]
            emit(result)
            return 0
        if result["status"] == "failed":
            emit(result)
            return 1
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            result["wait_expired"] = bool(args.wait_seconds)
            result["resume_without_resubmission"] = True
            emit(result)
            return 0
        time.sleep(min(5, remaining))


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Last Light Radio — offline authoring foundations")
    commands = result.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo", help="Simulate a draft episode; no GPU or network")
    demo.add_argument("--project", type=Path, default=ROOT / "fixtures/demo_project.json")
    demo.add_argument("--seed", type=int, default=7)
    demo.add_argument("--seconds", type=int, default=600)
    demo.add_argument("--fps", type=int, default=24)
    demo.add_argument("--output", type=Path, default=Path("runs/demo"))
    demo.set_defaults(run=_demo)
    workflow = commands.add_parser("workflow", help="Inspect the recovered workflow; optionally save a preview")
    workflow.add_argument("--workflow", type=Path, default=ROOT / "workflows/h3/workflow_api.json")
    workflow.add_argument("--definitions", type=Path, default=ROOT / "workflows/h3/node_definitions.json")
    workflow.add_argument("--bindings", type=Path, default=ROOT / "workflows/h3/bindings.json")
    workflow.add_argument("--image", help="Server-side image name; preview only, no upload")
    workflow.add_argument("--prompt")
    workflow.add_argument("--seed", type=int)
    workflow.add_argument("--preview-output", type=Path)
    workflow.set_defaults(run=_workflow)
    probe = commands.add_parser("probe", help="Read server stats and node catalog; never submit work")
    probe.add_argument("--url")
    probe.add_argument("--config", type=Path, default=Path(".local/worker.json"))
    probe.add_argument("--save", action="store_true")
    probe.add_argument("--timeout", type=float, default=5)
    probe.add_argument("--workflow", type=Path, default=ROOT / "workflows/h3/workflow_api.json")
    probe.set_defaults(run=_probe)
    render = commands.add_parser("render", help="Upload an image and submit one confirmed workflow")
    render.add_argument("--image", type=Path, required=True)
    render.add_argument("--prompt", required=True)
    render.add_argument("--seed", type=int, default=7)
    render.add_argument("--url")
    render.add_argument("--config", type=Path, default=Path(".local/worker.json"))
    render.add_argument("--output", type=Path, default=Path("runs/live"))
    render.add_argument("--timeout", type=float, default=30)
    render.add_argument("--workflow", type=Path, default=ROOT / "workflows/h3/workflow_api.json")
    render.add_argument("--bindings", type=Path, default=ROOT / "workflows/h3/bindings.json")
    render.set_defaults(run=_render)
    job = commands.add_parser("job", help="Poll/download an owned job; never submit again")
    job.add_argument("--job-id", required=True)
    job.add_argument("--output", type=Path, default=Path("runs/live"))
    job.add_argument("--url")
    job.add_argument("--timeout", type=float, default=15)
    job.add_argument("--wait-seconds", type=int, default=0)
    job.set_defaults(run=_job)
    studio = commands.add_parser("studio", help="Open the local React creator application")
    studio.add_argument("--port", type=int, default=8765)
    studio.add_argument("--data", type=Path, default=Path(".local/studio"))
    def run_studio(args):
        from .server import serve
        serve(args.data, args.port)
        return 0
    studio.set_defaults(run=run_studio)
    clips = commands.add_parser("clip-editor", help="Open the separate mobile clip and sequence editor")
    clips.add_argument("--port", type=int, default=8772)
    clips.add_argument("--host", default="127.0.0.1", help="This computer's private IPv4 address for LAN access")
    clips.add_argument("--worker", help="Override the configured ComfyUI worker URL from this computer")
    def run_clips(args):
        from .clip_editor import serve
        serve(args.host, args.port, args.worker)
        return 0
    clips.set_defaults(run=run_clips)
    return result


def main(argv: list[str] | None = None) -> int:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    LOG.handlers[:] = [handler]
    LOG.setLevel(logging.INFO)
    LOG.propagate = False
    args = parser().parse_args(argv)
    try:
        return args.run(args)
    except (ComfyError, WorkflowError) as error:
        LOG.error("command.failed", extra={"fields": error.to_dict()})
    except (OSError, ValueError, KeyError) as error:
        LOG.error("command.failed", extra={"fields": {"code": type(error).__name__, "message": str(error)}})
    return 1
