"""Offline-safe workflow inspection and a read-only ComfyUI connection probe.

Node identifiers live in imported binding documents, never in this adapter.
The real client deliberately has no submission or cancellation methods in M1.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


class WorkflowError(ValueError):
    def __init__(self, code: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.code = code
        self.details = details

    def to_dict(self) -> dict:
        return {"code": self.code, "message": str(self), **self.details}


class ComfyError(RuntimeError):
    def __init__(self, code: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.code = code
        self.details = details

    def to_dict(self) -> dict:
        return {"code": self.code, "message": str(self), **self.details}


def workflow_sha256(graph: dict) -> str:
    """Hash the graph's content, independent of JSON formatting."""
    try:
        content = json.dumps(graph, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise WorkflowError("INVALID_JSON_VALUE", "Workflow must contain finite JSON values.") from exc
    return hashlib.sha256(content).hexdigest()


def _diagnostic(code: str, message: str, **details: Any) -> dict:
    return {"code": code, "message": message, **details}


def _is_link(value: Any) -> bool:
    return (isinstance(value, list) and len(value) == 2
            and isinstance(value[0], str) and type(value[1]) is int)


def _literal_error(value: Any, kind: Any, options: dict) -> str | None:
    if isinstance(kind, list):
        # An uploaded image can exist despite not appearing in stale dropdown choices.
        if options.get("image_upload"):
            return None if isinstance(value, str) and value else "must be a nonempty server image name"
        return None if value in kind else "must be one of the declared choices"
    if kind == "COMBO":
        return None if value in options.get("options", []) else "must be one of the declared choices"
    valid = {
        "INT": type(value) is int,
        "FLOAT": type(value) in (int, float) and math.isfinite(value),
        "STRING": isinstance(value, str),
        "BOOLEAN": type(value) is bool,
        "*": True,
    }.get(kind, False)
    if not valid:
        return f"must be {kind}; socket inputs require a [node_id, output_index] link"
    if type(value) in (int, float):
        if not math.isfinite(value):
            return "must be finite"
        if "min" in options and value < options["min"]:
            return f"must be at least {options['min']}"
        if "max" in options and value > options["max"]:
            return f"must be at most {options['max']}"
    return None


def inspect_workflow(graph: dict, definitions: dict | None = None) -> dict:
    """Inspect any API graph; optional /object_info enables socket/type checks.

    Inspection reports diagnostics and never mutates the input. A successful
    report does not establish model readiness or visual quality.
    """
    errors: list[dict] = []
    warnings: list[dict] = []
    result = {"valid": False, "node_count": 0, "node_classes": [], "nodes": [],
              "links": [], "output_nodes": [], "errors": errors, "warnings": warnings,
              "sha256": None, "model_readiness": "unverified"}
    if not isinstance(graph, dict) or not graph or isinstance(graph.get("nodes"), list):
        errors.append(_diagnostic("INVALID_WORKFLOW", "Use a nonempty API-format node graph, not an editor workflow."))
        return result
    if definitions is not None and not isinstance(definitions, dict):
        errors.append(_diagnostic("INVALID_DEFINITIONS", "Node definitions must be an /object_info JSON object."))
        return result
    try:
        result["sha256"] = workflow_sha256(graph)
    except WorkflowError as exc:
        errors.append(exc.to_dict())
        return result
    result["node_count"] = len(graph)
    nodes: dict[str, dict] = {}
    for node_id, node in graph.items():
        if not isinstance(node_id, str) or not isinstance(node, dict):
            errors.append(_diagnostic("INVALID_NODE", "Every node needs a string ID and an object body.", node_id=str(node_id)))
            continue
        if not isinstance(node.get("class_type"), str) or not node["class_type"]:
            errors.append(_diagnostic("INVALID_NODE_CLASS", "Supply the node's class_type.", node_id=node_id))
            continue
        if not isinstance(node.get("inputs"), dict):
            errors.append(_diagnostic("INVALID_NODE_INPUTS", "Supply an inputs object for the node.", node_id=node_id))
            continue
        nodes[node_id] = node
        result["nodes"].append({"node_id": node_id, "class_type": node["class_type"],
                                "input_names": sorted(node["inputs"])})
    result["node_classes"] = sorted({n["class_type"] for n in nodes.values()})
    dependencies = {node_id: set() for node_id in nodes}
    for node_id, node in nodes.items():
        definition = definitions.get(node["class_type"]) if definitions is not None else None
        specs: dict = {}
        if definitions is not None and not isinstance(definition, dict):
            errors.append(_diagnostic("MISSING_NODE_CLASS", "Install or restore this node class on the selected worker.",
                                      node_id=node_id, class_type=node["class_type"]))
        elif definition is not None:
            declared = definition.get("input", {})
            if not isinstance(declared, dict):
                errors.append(_diagnostic("INVALID_NODE_DEFINITION", "Node input declarations must be objects.", node_id=node_id))
                declared = {}
            for category in ("required", "optional"):
                category_specs = declared.get(category, {})
                if not isinstance(category_specs, dict):
                    errors.append(_diagnostic("INVALID_NODE_DEFINITION", "Node input declarations must be objects.", node_id=node_id))
                    continue
                specs.update(category_specs)
                if category == "required":
                    for name in category_specs:
                        if name not in node["inputs"]:
                            errors.append(_diagnostic("MISSING_INPUT", "Supply this required node input.", node_id=node_id, input=name))
            if definition.get("output_node"):
                result["output_nodes"].append(node_id)
        for name, value in node["inputs"].items():
            spec = specs.get(name)
            kind = spec[0] if isinstance(spec, list) and spec else None
            options = spec[1] if isinstance(spec, list) and len(spec) > 1 and isinstance(spec[1], dict) else {}
            if definition is not None and name not in specs:
                errors.append(_diagnostic("UNKNOWN_INPUT", "The worker does not declare this node input.", node_id=node_id, input=name))
            if spec is not None and (not isinstance(spec, list) or not spec
                                     or not isinstance(kind, (str, list))):
                errors.append(_diagnostic("INVALID_NODE_DEFINITION", "Input type declarations must be nonempty lists with a type name or choices.", node_id=node_id, input=name))
                kind = None
            if _is_link(value):
                source, index = value
                result["links"].append({"source_node": source, "source_output": index,
                                        "target_node": node_id, "target_input": name})
                if source not in nodes:
                    errors.append(_diagnostic("MISSING_LINK_NODE", "Link refers to a missing or invalid source node.", node_id=node_id, input=name, source_node=source))
                    continue
                dependencies[node_id].add(source)
                if index < 0:
                    errors.append(_diagnostic("INVALID_OUTPUT_INDEX", "Output indices must be nonnegative.", node_id=node_id, input=name))
                    continue
                source_definition = definitions.get(nodes[source]["class_type"]) if definitions is not None else None
                if isinstance(source_definition, dict):
                    outputs = source_definition.get("output", [])
                    if not isinstance(outputs, list) or index >= len(outputs):
                        errors.append(_diagnostic("INVALID_OUTPUT_INDEX", "Source node does not declare this output index.", node_id=node_id, input=name, source_node=source, output_index=index))
                    elif isinstance(kind, str) and kind != "*" and outputs[index] != "*":
                        actual_types = set(str(outputs[index]).split(","))
                        expected_types = set(kind.split(","))
                        if not actual_types.intersection(expected_types):
                            errors.append(_diagnostic("LINK_TYPE_MISMATCH", "Source output type does not match the destination socket.", node_id=node_id, input=name, expected=kind, actual=outputs[index]))
            elif kind is not None:
                problem = _literal_error(value, kind, options)
                if problem:
                    errors.append(_diagnostic("INVALID_INPUT_VALUE", f"Input {problem}.", node_id=node_id, input=name))
                elif options.get("image_upload") and value not in kind:
                    warnings.append(_diagnostic("IMAGE_NOT_IN_CHOICES", "Image is absent from the captured dropdown; verify or upload it before a future submission.", node_id=node_id, input=name, value=value))
            elif isinstance(value, list):
                errors.append(_diagnostic("MALFORMED_LINK", "A node link must be [string_node_id, integer_output_index].", node_id=node_id, input=name))
    # Topological reduction catches cycles without recursion or relying on node numbering.
    pending = {key: set(value) for key, value in dependencies.items()}
    while pending:
        ready = {key for key, value in pending.items() if not value}
        if not ready:
            errors.append(_diagnostic("WORKFLOW_CYCLE", "Workflow links contain a cycle; repair the listed nodes.", node_ids=sorted(pending)))
            break
        pending = {key: value - ready for key, value in pending.items() if key not in ready}
    if definitions is None:
        warnings.append(_diagnostic("DEFINITIONS_NOT_CHECKED", "Supply captured or live /object_info to validate node availability, input values and socket types."))
    result["valid"] = not errors
    return result


def load_bindings(path: str | Path) -> dict:
    try:
        with Path(path).open(encoding="utf-8-sig") as stream:
            bindings = json.load(stream)
    except (OSError, ValueError) as exc:
        raise WorkflowError("BINDINGS_UNREADABLE", "Cannot read bindings JSON; check the path and JSON syntax.", path=str(path)) from exc
    _validate_bindings(bindings)
    return bindings


def _validate_bindings(bindings: dict) -> None:
    if not isinstance(bindings, dict) or bindings.get("schema_version") != 1:
        raise WorkflowError("INVALID_BINDINGS", "Bindings must be an object with schema_version 1.")
    if type(bindings.get("confirmed")) is not bool:
        raise WorkflowError("INVALID_BINDINGS", "Bindings need an explicit boolean confirmed field.")
    if not isinstance(bindings.get("inputs"), dict) or not bindings["inputs"]:
        raise WorkflowError("INVALID_BINDINGS", "Bindings must declare named inputs.")
    for name, binding in bindings["inputs"].items():
        if (not isinstance(name, str) or not isinstance(binding, dict)
                or not all(isinstance(binding.get(key), str) and binding[key]
                           for key in ("node_id", "class_type", "input", "type"))):
            raise WorkflowError("INVALID_BINDING", "Each named input needs node_id, class_type, input and type strings.", binding=str(name))
        if binding["type"] not in ("INT", "FLOAT", "STRING", "BOOLEAN"):
            raise WorkflowError("INVALID_BINDING", "Named input bindings must use INT, FLOAT, STRING or BOOLEAN literal types.", binding=name)
        if binding.get("nonempty") and binding["type"] != "STRING":
            raise WorkflowError("INVALID_BINDING", "The nonempty constraint only applies to STRING bindings.", binding=name)


def prepare_workflow(graph: dict, bindings: dict, overrides: dict) -> dict:
    """Build a preview from explicit bindings; confirmation is not needed to preview.

    This function never submits work or edits the template. Callers must retain
    the unconfirmed flag until the creator approves the proposed mapping.
    """
    _validate_bindings(bindings)
    inspection = inspect_workflow(graph)
    if not inspection["valid"]:
        raise WorkflowError("INVALID_WORKFLOW", "Repair the workflow before preparing a candidate.", errors=inspection["errors"])
    expected_hash = bindings.get("workflow_sha256")
    if expected_hash and inspection["sha256"] != expected_hash:
        raise WorkflowError("BINDING_TEMPLATE_MISMATCH", "Bindings belong to a different workflow; inspect and remap this template.")
    if not isinstance(overrides, dict):
        raise WorkflowError("INVALID_OVERRIDES", "Overrides must be an object of named binding values.")
    unknown = sorted(set(overrides) - set(bindings["inputs"]))
    if unknown:
        raise WorkflowError("UNKNOWN_OVERRIDE", "Use only names declared in the binding map.", names=unknown)
    for name, binding in bindings["inputs"].items():
        node = graph.get(binding["node_id"])
        if (not isinstance(node, dict) or node.get("class_type") != binding["class_type"]
                or binding["input"] not in node.get("inputs", {})):
            raise WorkflowError("BINDING_TARGET_MISSING", "Binding does not match a node/input in this workflow; inspect and remap it.", binding=name)
        if _is_link(node["inputs"][binding["input"]]):
            raise WorkflowError("BINDING_TARGET_IS_LINK", "Literal parameter bindings cannot replace graph connections.", binding=name)
    prepared = copy.deepcopy(graph)
    for name, value in overrides.items():
        binding = bindings["inputs"][name]
        problem = _literal_error(value, binding["type"], binding)
        if problem or isinstance(value, (dict, list)):
            raise WorkflowError("INVALID_OVERRIDE", f"Override {problem or 'must be a literal value'}.", binding=name)
        if binding.get("nonempty") and not value.strip():
            raise WorkflowError("INVALID_OVERRIDE", "Override must be nonempty.", binding=name)
        if "choices" in binding and value not in binding["choices"]:
            raise WorkflowError("INVALID_OVERRIDE", "Override must be one of the declared choices.", binding=name, choices=binding["choices"])
        prepared[binding["node_id"]]["inputs"][binding["input"]] = copy.deepcopy(value)
    return prepared


def parse_animated_webp_outputs(outputs: dict, node_id: str) -> list[dict]:
    """Parse the recovered SaveAnimatedWEBP `images` plus `animated` convention."""
    output = outputs.get(node_id) if isinstance(outputs, dict) else None
    if not isinstance(output, dict) or not isinstance(output.get("images"), list):
        raise ComfyError("MALFORMED_OUTPUT", "Expected an images list from the mapped SaveAnimatedWEBP node.", node_id=node_id)
    images, animated = output["images"], output.get("animated")
    if not images or not isinstance(animated, list) or len(animated) != len(images):
        raise ComfyError("MALFORMED_OUTPUT", "Expected one animated flag for each returned WebP image.", node_id=node_id)
    parsed = []
    for image, is_animated in zip(images, animated):
        if (not isinstance(image, dict) or not isinstance(image.get("filename"), str)
                or not image["filename"].lower().endswith(".webp") or is_animated is not True
                or image.get("type") != "output" or not isinstance(image.get("subfolder", ""), str)):
            raise ComfyError("MALFORMED_OUTPUT", "Expected an animated .webp reference in the worker output directory.", node_id=node_id)
        # Output references are untrusted metadata; do not allow paths to escape a future download root.
        filename, subfolder = image["filename"], image.get("subfolder", "")
        if ("/" in filename or "\\" in filename or ":" in filename
                or subfolder.startswith(("/", "\\")) or ":" in subfolder
                or ".." in subfolder.replace("\\", "/").split("/")):
            raise ComfyError("UNSAFE_OUTPUT_PATH", "Worker output metadata contains an unsafe file path.", node_id=node_id)
        parsed.append({**copy.deepcopy(image), "animated": True})
    return parsed


class ComfyClient:
    """Read-only HTTP probe. Transport injection keeps tests independent of a LAN."""

    def __init__(self, base_url: str, timeout: float = 5.0,
                 transport: Callable | None = None) -> None:
        if not isinstance(base_url, str):
            raise ComfyError("INVALID_URL", "Use a full http://host:port or https://host URL.")
        parts = urlsplit(base_url)
        if (parts.scheme not in ("http", "https") or not parts.hostname
                or any(character.isspace() for character in base_url)
                or parts.username or parts.password or parts.query or parts.fragment):
            raise ComfyError("INVALID_URL", "Use an HTTP(S) worker URL without credentials, query or fragment.")
        try:
            parts.port
        except ValueError as exc:
            raise ComfyError("INVALID_URL", "The worker URL contains an invalid port.") from exc
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
            raise ComfyError("INVALID_TIMEOUT", "Connection timeout must be a positive finite number of seconds.")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._transport = transport or self._http_json

    def _http_json(self, method: str, path: str, payload: Any = None) -> Any:
        if method != "GET" or payload is not None:
            raise ComfyError("READ_ONLY_CLIENT", "This milestone only supports read-only worker requests.")
        request = Request(self.base_url + path, headers={"Accept": "application/json"}, method="GET")
        with urlopen(request, timeout=self.timeout) as response:
            return json.load(response)

    def probe(self) -> dict:
        report = {"connected": False, "base_url": self.base_url, "system_stats": None,
                  "object_info": None, "node_classes": [], "errors": [],
                  "model_readiness": "unverified"}
        for path, key in (("/system_stats", "system_stats"), ("/object_info", "object_info")):
            try:
                value = self._transport("GET", path, None)
                if not isinstance(value, dict):
                    raise ComfyError("INVALID_RESPONSE", "Worker endpoint must return a JSON object.", endpoint=path)
                report[key] = value
            except ComfyError as exc:
                report["errors"].append({"endpoint": path, **exc.to_dict()})
            except HTTPError as exc:
                report["errors"].append(_diagnostic("HTTP_ERROR", "Worker returned an HTTP error; check the endpoint and service.", endpoint=path, status=exc.code))
            except (URLError, OSError, TimeoutError) as exc:
                report["errors"].append(_diagnostic("WORKER_OFFLINE", "Worker connection failed; check the address and server, then retry.", endpoint=path, reason=str(exc)))
            except (ValueError, UnicodeError) as exc:
                report["errors"].append(_diagnostic("INVALID_JSON", "Worker returned invalid JSON; check that this is a ComfyUI API endpoint.", endpoint=path))
        if report["object_info"] is not None:
            report["node_classes"] = sorted(report["object_info"])
        report["connected"] = not report["errors"]
        return report


class MockComfyClient:
    """Deterministic, in-memory owned jobs; no GPU, files, sleeps or network."""

    def __init__(self, *, offline: bool = False, definitions: dict | None = None) -> None:
        self.offline = offline
        self.definitions = copy.deepcopy(definitions)
        self._jobs: dict[str, dict] = {}
        self._sequence = 0
        self.events: list[dict] = []

    def _require_online(self) -> None:
        if self.offline:
            raise ComfyError("WORKER_OFFLINE", "Mock worker is offline; reconnect and retry.")

    def probe(self) -> dict:
        return {"connected": not self.offline, "base_url": "mock://offline-demo",
                "system_stats": None if self.offline else {"devices": [{"name": "Mock worker (no GPU)"}]},
                "object_info": copy.deepcopy(self.definitions or {}),
                "node_classes": sorted(self.definitions or {}),
                "errors": [_diagnostic("WORKER_OFFLINE", "Mock worker is offline.")] if self.offline else [],
                "model_readiness": "mock_only"}

    def submit(self, graph: dict, *, outcome: str = "success", queued_polls: int = 1,
               output_node_id: str | None = None) -> str:
        self._require_online()
        inspection = inspect_workflow(graph, self.definitions)
        if not inspection["valid"]:
            raise ComfyError("INVALID_WORKFLOW", "Mock submission rejected the workflow; inspect the diagnostics.", errors=inspection["errors"])
        if outcome not in ("success", "failure") or type(queued_polls) is not int or queued_polls < 0:
            raise ComfyError("INVALID_MOCK_JOB", "Use success/failure and a nonnegative queued_polls integer.")
        if output_node_id is None:
            sinks = inspection["output_nodes"] or [node_id for node_id, node in graph.items()
                                                     if node["class_type"] == "SaveAnimatedWEBP"]
            output_node_id = sinks[0] if len(sinks) == 1 else None
        if output_node_id not in graph:
            raise ComfyError("OUTPUT_BINDING_REQUIRED", "Select one existing output node for this mock job.")
        self._sequence += 1
        prompt_id = f"mock-{self._sequence:06d}"
        self._jobs[prompt_id] = {"prompt_id": prompt_id, "status": "queued", "poll_count": 0,
                                 "queued_polls": queued_polls, "outcome": outcome,
                                 "output_node_id": output_node_id, "outputs": {},
                                 "workflow": copy.deepcopy(graph), "workflow_sha256": inspection["sha256"]}
        self.events.append({"prompt_id": prompt_id, "status": "queued"})
        return prompt_id

    def _owned(self, prompt_id: str) -> dict:
        if prompt_id not in self._jobs:
            raise ComfyError("JOB_NOT_OWNED", "This client does not own that job; it cannot poll or cancel it.", prompt_id=prompt_id)
        return self._jobs[prompt_id]

    def poll(self, prompt_id: str) -> dict:
        self._require_online()
        job = self._owned(prompt_id)
        if job["status"] not in ("success", "failed", "cancelled"):
            job["poll_count"] += 1
            if job["poll_count"] <= job["queued_polls"]:
                job["status"] = "queued"
            elif job["poll_count"] == job["queued_polls"] + 1:
                job["status"] = "running"
            elif job["outcome"] == "failure":
                job["status"] = "failed"
                job["error"] = _diagnostic("MOCK_EXECUTION_FAILED", "Mock render failed; no candidate was produced.")
            else:
                job["status"] = "success"
                job["outputs"] = {job["output_node_id"]: {"images": [{"filename": f"{prompt_id}.webp",
                                      "subfolder": "mock", "type": "output"}], "animated": [True]}}
            if not self.events or self.events[-1] != {"prompt_id": prompt_id, "status": job["status"]}:
                self.events.append({"prompt_id": prompt_id, "status": job["status"]})
        return copy.deepcopy({key: value for key, value in job.items() if key != "workflow"})

    def wait(self, prompt_id: str, *, max_polls: int = 10) -> dict:
        if type(max_polls) is not int or max_polls < 1:
            raise ComfyError("INVALID_POLL_LIMIT", "max_polls must be a positive integer.")
        for _ in range(max_polls):
            result = self.poll(prompt_id)
            if result["status"] in ("success", "failed", "cancelled"):
                return result
        raise ComfyError("JOB_TIMEOUT", "Mock polling limit reached; the owned job remains available for a later retry.", prompt_id=prompt_id, max_polls=max_polls)

    def cancel(self, prompt_id: str) -> dict:
        self._require_online()
        job = self._owned(prompt_id)
        if job["status"] not in ("success", "failed", "cancelled"):
            job["status"] = "cancelled"
            self.events.append({"prompt_id": prompt_id, "status": "cancelled"})
        return copy.deepcopy({key: value for key, value in job.items() if key != "workflow"})
