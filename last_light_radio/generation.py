"""Explicit live requests, durable ownership, polling and candidate provenance.

Only start_generation submits. Resuming a persisted job never submits again,
including after timeouts or an ambiguous network failure during submission.
"""

from __future__ import annotations

import copy
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .comfy import ComfyError, inspect_workflow, parse_animated_webp_outputs
from .comfy import prepare_workflow, workflow_sha256
from .media import inspect_webp
from .store import ProjectStore, canonical_bytes, sha256


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def job_folder(job_id: str) -> str:
    if not isinstance(job_id, str) or not re.fullmatch(r"[a-f0-9]{32}", job_id):
        raise ComfyError("INVALID_JOB_ID", "Use the local job ID printed by render")
    return f"records/live_jobs/{job_id}"


def _read(store: ProjectStore, path: str) -> dict:
    value = json.loads(store.resolve(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ComfyError("INVALID_JOB_RECORD", "Expected a persisted job object")
    return value


def record_event(store: ProjectStore, job_id: str, status: str, **details) -> dict:
    folder = f"{job_folder(job_id)}/events"
    existing = sorted(store.resolve(folder).glob("*.json"))
    event = {"local_job_id": job_id, "status": status, "at_utc": utc_now(), **details}
    store.write_once(f"{folder}/{len(existing):06d}.json", canonical_bytes(event))
    return event


def latest_event(store: ProjectStore, job_id: str) -> dict:
    folder = store.resolve(f"{job_folder(job_id)}/events")
    events = sorted(folder.glob("*.json"))
    return json.loads(events[-1].read_text()) if events else {"status": "unknown"}


def execution_timing(history: dict) -> dict:
    timestamps = {}
    for name, details in history.get("status", {}).get("messages", []):
        value = details.get("timestamp")
        if name in ("execution_start", "execution_success") and type(value) is int:
            timestamps[name] = value
    start, end = timestamps.get("execution_start"), timestamps.get("execution_success")
    return {"start_unix_ms": start, "end_unix_ms": end,
            "runtime_seconds": (end - start) / 1000 if start is not None and end is not None and end >= start else None}


def load_request(store: ProjectStore, job_id: str) -> dict:
    pointer = _read(store, f"{job_folder(job_id)}/request.json")
    request = store.read_snapshot(pointer)
    if request.get("local_job_id") != job_id or request.get("kind") != "live_generation_request":
        raise ComfyError("INVALID_JOB_RECORD", "Job ownership record does not match local ID")
    store.verify_master(request["master"])
    return request


def start_generation(store: ProjectStore, client, graph: dict, bindings: dict,
                     image: str | Path, motion_prompt: str, seed: int = 7,
                     *, local_job_id: str | None = None) -> dict:
    """Queue exactly one creator-requested job; never retry an uncertain POST."""
    if bindings.get("confirmed") is not True:
        raise ComfyError("BINDINGS_UNCONFIRMED", "Review and confirm this imported workflow's mapping before live generation")
    output = bindings.get("output", {})
    if (output.get("parser") != "images_animated_webp"
            or graph.get(output.get("node_id"), {}).get("class_type") != "SaveAnimatedWEBP"):
        raise ComfyError("UNSUPPORTED_OUTPUT", "The live output adapter currently supports the recovered animated WebP convention")
    local_id = local_job_id or uuid4().hex
    folder = job_folder(local_id)
    if store.resolve(folder).exists():
        raise ComfyError("JOB_EXISTS", "This local job already has a durable record; resume it instead of submitting again")
    prefix = f"LastLightRadio/{local_id}/candidate"
    # Validate all known override fields before upload or GPU work.
    preview = prepare_workflow(graph, bindings, {"source_image": "pending.png",
                               "motion_prompt": motion_prompt, "seed": seed,
                               "filename_prefix": prefix})
    probe = client.probe()
    if not probe["connected"]:
        raise ComfyError("WORKER_OFFLINE", "Connection probe failed before upload/submission", errors=probe["errors"])
    inspection = inspect_workflow(preview, probe["object_info"])
    if not inspection["valid"]:
        raise ComfyError("INVALID_WORKFLOW", "Live worker rejected workflow compatibility checks", errors=inspection["errors"])
    master = store.import_master(image)
    data = store.resolve(master["path"]).read_bytes()
    record_event(store, local_id, "uploading")
    try:
        upload = client.upload_image(data, "test_still" + Path(image).suffix.lower(),
                                     f"LastLightRadio/{local_id}")
        prepared = prepare_workflow(graph, bindings, {"source_image": upload["path"],
                                   "motion_prompt": motion_prompt, "seed": seed,
                                   "filename_prefix": prefix})
        inspection = inspect_workflow(prepared, probe["object_info"])
        if not inspection["valid"]:
            raise ComfyError("INVALID_WORKFLOW", "Uploaded-image workflow failed validation", errors=inspection["errors"])
        workflow_ref = store.save_snapshot(prepared, kind="workflows")
        definitions = {name: probe["object_info"][name] for name in inspection["node_classes"]}
        definitions_ref = store.save_snapshot(definitions, kind="workflows")
        request = {"schema_version": 1, "kind": "live_generation_request", "local_job_id": local_id,
                   "created_at_utc": utc_now(), "base_url": client.base_url,
                   "client_id": str(uuid4()), "master": master, "upload": upload,
                   "workflow": workflow_ref, "workflow_sha256": workflow_sha256(prepared),
                   "template_sha256": workflow_sha256(graph), "bindings": copy.deepcopy(bindings),
                   "node_definitions": definitions_ref,
                   "parameters": {name: prepared[binding["node_id"]]["inputs"][binding["input"]]
                                  for name, binding in bindings["inputs"].items()},
                   "overrides": {"motion_prompt": motion_prompt, "seed": seed},
                   "system_stats_before": probe["system_stats"], "review_status": "candidate",
                   "canon_approved": False, "purpose": "creator_requested_generation"}
        pointer = store.save_snapshot(request, kind="jobs")
        store.write_once(f"{folder}/request.json", canonical_bytes(pointer))
        # This durable checkpoint precedes POST. A crash here must never auto-submit.
        record_event(store, local_id, "submitting", workflow_sha256=request["workflow_sha256"])
        try:
            response = client.submit(prepared, client_id=request["client_id"], local_job_id=local_id)
        except Exception as error:
            details = error.to_dict() if isinstance(error, ComfyError) else {"message": str(error)}
            record_event(store, local_id, "submission_unknown" if details.get("code") == "SUBMISSION_AMBIGUOUS" else "submission_failed", error=details)
            raise
        accepted = {"local_job_id": local_id, "prompt_id": response["prompt_id"],
                    "client_id": request["client_id"], "base_url": client.base_url,
                    "workflow_sha256": request["workflow_sha256"], "response": response}
        store.write_once(f"{folder}/accepted.json", canonical_bytes(accepted))
        record_event(store, local_id, "queued", prompt_id=response["prompt_id"])
        return {"local_job_id": local_id, "prompt_id": response["prompt_id"], "status": "queued",
                "output_root": str(store.root), "master": master}
    except Exception as error:
        if isinstance(error, ComfyError):
            error.details["local_job_id"] = local_id
            error.details["output_root"] = str(store.root)
        raise


def poll_generation(store: ProjectStore, client, job_id: str) -> dict:
    """Resume only a recorded owned job; never upload, resubmit or cancel."""
    folder = job_folder(job_id)
    request = load_request(store, job_id)
    if client.base_url != request["base_url"]:
        raise ComfyError("WORKER_MISMATCH", "Resume with the same worker URL recorded for this job")
    accepted_path = store.resolve(f"{folder}/accepted.json")
    if not accepted_path.is_file():
        raise ComfyError("SUBMISSION_UNRESOLVED", "No accepted prompt ID is recorded. Inspect the server queue/history before creating another job; resume never resubmits.", local_job_id=job_id)
    accepted = _read(store, f"{folder}/accepted.json")
    if any(accepted.get(key) != request.get(key) for key in ("local_job_id", "client_id", "base_url", "workflow_sha256")):
        raise ComfyError("INVALID_JOB_RECORD", "Accepted job does not match its ownership request")
    candidate_path = store.resolve(f"candidates/{job_id}/candidate.json")
    if candidate_path.is_file():
        candidate = _read(store, f"candidates/{job_id}/candidate.json")
        for item in candidate["outputs"]:
            if sha256(store.resolve(item["path"]).read_bytes()) != item["sha256"]:
                raise ComfyError("CANDIDATE_CHECKSUM_MISMATCH", "An existing candidate was modified externally")
        return {"local_job_id": job_id, "prompt_id": accepted["prompt_id"], "status": "success",
                "candidate": candidate, "candidate_path": str(candidate_path)}
    previous = latest_event(store, job_id)
    try:
        result = client.poll(accepted["prompt_id"])
    except ComfyError as error:
        if previous.get("status") != "connection_error":
            record_event(store, job_id, "connection_error", error=error.to_dict())
        raise
    status = result["status"]
    if status != previous.get("status"):
        record_event(store, job_id, status, prompt_id=accepted["prompt_id"], error=result.get("error"))
    response = {"local_job_id": job_id, "prompt_id": accepted["prompt_id"], "status": status}
    if status == "failed":
        failure_ref = store.save_snapshot(result, kind="jobs")
        response.update({"error": result.get("error"), "failure_record": failure_ref})
        return response
    if status != "success":
        return response
    graph = store.read_snapshot(request["workflow"])
    if workflow_sha256(graph) != request["workflow_sha256"]:
        raise ComfyError("WORKFLOW_CHECKSUM_MISMATCH", "Submitted workflow snapshot was modified")
    history_ref = store.save_snapshot(result, kind="jobs")
    historical_prompt = result.get("history", {}).get("prompt", [])
    history_graph = historical_prompt[2] if isinstance(historical_prompt, list) and len(historical_prompt) > 2 else None
    if history_graph is not None and workflow_sha256(history_graph) != request["workflow_sha256"]:
        record_event(store, job_id, "provenance_mismatch", history=history_ref)
        raise ComfyError("HISTORY_WORKFLOW_MISMATCH", "Executed history graph differs from the submitted workflow snapshot")
    output_node = request["bindings"]["output"]["node_id"]
    output_records = []
    try:
        references = parse_animated_webp_outputs(result["outputs"], output_node)
        for index, reference in enumerate(references):
            data = client.download_output(reference)
            properties = inspect_webp(data)
            digest = sha256(data)
            relative = f"candidates/{job_id}/{index:02d}-{digest}.webp"
            store.write_once(relative, data)
            output_records.append({"path": relative, "sha256": digest, "bytes": len(data),
                                   "reference": reference, "properties": properties})
    except (ComfyError, OSError, ValueError) as error:
        details = error.to_dict() if isinstance(error, ComfyError) else {"message": str(error)}
        record_event(store, job_id, "download_failed", error=details, history=history_ref)
        raise
    try:
        stats_after = client.system_stats()
    except ComfyError as error:
        stats_after = {"unavailable": error.to_dict()}
    candidate = {"schema_version": 1, "local_job_id": job_id, "prompt_id": accepted["prompt_id"],
                 "created_at_utc": utc_now(), "review_status": "candidate", "canon_approved": False,
                 "master": request["master"], "base_url": request["base_url"],
                 "workflow": request["workflow"], "workflow_sha256": request["workflow_sha256"],
                 "template_sha256": request["template_sha256"], "bindings": request["bindings"],
                 "parameters": request["parameters"],
                 "execution": execution_timing(result.get("history", {})),
                 "history_workflow_verified": history_graph is not None,
                 "history": history_ref, "system_stats_before": request["system_stats_before"],
                 "system_stats_after": stats_after, "peak_vram": None,
                 "peak_vram_note": "Before/after snapshots do not measure peak VRAM",
                 "outputs": output_records, "quality_review": "pending_creator_review"}
    store.write_once(f"candidates/{job_id}/candidate.json", canonical_bytes(candidate))
    record_event(store, job_id, "downloaded", outputs=len(output_records))
    response.update({"candidate": candidate, "candidate_path": str(candidate_path)})
    return response
