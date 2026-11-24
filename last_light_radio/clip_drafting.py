"""Draft editable Clip Editor inputs with a loopback chat completions server."""

import http.client
import json
from urllib.parse import urlsplit

from . import h3_joint_av_recipe as recipe
from .studio import StudioError, text


CONFIG_NAME = "local-ai.json"
MAX_PROMPT = 4000
SYSTEM_PROMPT = (
    "Write a concise motion prompt for a single image-to-video shot. The renderer has "
    "the starting image. You have only the creator's written direction. Preserve the "
    "starting composition, people, props and style unless asked to change them. Describe "
    "the requested visible action, pace and camera behavior in plain language. Use a "
    "locked camera by default. Use only details grounded in the creator's direction. "
    "Keep the selected frame count unless the direction calls for a different duration. "
    "Return a brief and an allowed length_frames value."
)


def draft(config_path, direction, selected_frames):
    direction = text(direction, "Motion direction", MAX_PROMPT)
    try:
        config = json.loads(config_path.read_text(encoding="utf-8-sig"))
        base = urlsplit(config["base_url"])
        port = base.port
        model = text(config["model"], "Local AI model", 256)
        if (base.scheme != "http" or base.hostname not in {"127.0.0.1", "localhost", "::1"}
                or base.path.rstrip("/") != "/v1" or base.username is not None or base.query or base.fragment):
            raise ValueError("Expected a loopback /v1 URL")
    except FileNotFoundError:
        raise StudioError(f"Set up {CONFIG_NAME} in the Clip Editor library to use Local AI.", 503) from None
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        raise StudioError(f"Check the loopback base_url and model in {CONFIG_NAME}.", 503) from None

    schema = {
        "type": "object",
        "properties": {
            "brief": {"type": "string"},
            "length_frames": {"type": "integer", "enum": list(range(recipe.MIN_FRAMES, recipe.MAX_FRAMES + 1, recipe.FRAME_STEP))},
        },
        "required": ["brief", "length_frames"],
        "additionalProperties": False,
    }
    request = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Selected length: {selected_frames} frames at 24 fps.\n\n{direction}"},
        ],
        "response_format": {"type": "json_schema", "json_schema": {"name": "clip_draft", "strict": True, "schema": schema}},
        "temperature": 0.2,
        "max_tokens": 512,
        "stream": False,
    }
    # Connect directly to the configured loopback listener, without proxies or redirects.
    connection = http.client.HTTPConnection(base.hostname, port, timeout=90)
    try:
        connection.request("POST", "/v1/chat/completions", json.dumps(request), {"Content-Type": "application/json"})
        response = connection.getresponse()
        if response.status != 200:
            raise StudioError(f"Local AI returned HTTP {response.status}. Check that the server can run {model}.", 502)
        body = response.read(65537)
    except TimeoutError:
        raise StudioError("Local AI took too long to draft. Check the model server and try again.", 504) from None
    except (OSError, http.client.HTTPException):
        raise StudioError("Could not reach Local AI. Check that its local API server is running.", 503) from None
    finally:
        connection.close()

    try:
        if len(body) > 65536:
            raise ValueError("Oversized response")
        choice = json.loads(body)["choices"][0]
        if choice.get("finish_reason") not in {None, "stop"}:
            raise ValueError("Incomplete response")
        result = json.loads(choice["message"]["content"])
        if not isinstance(result, dict) or result.keys() != {"brief", "length_frames"} or result["length_frames"] is None:
            raise ValueError("Unexpected draft fields")
        brief = text(result["brief"], "Drafted motion prompt", MAX_PROMPT)
        length_frames = recipe.frames(result["length_frames"])
    except (ValueError, TypeError, KeyError, IndexError, AttributeError):
        raise StudioError("Local AI returned an invalid clip draft. Try again or keep editing the prompt.", 502) from None
    return {"brief": brief, "length_frames": length_frames, "model": model}
