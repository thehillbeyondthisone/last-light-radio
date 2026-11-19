"""Creator-selected starting points; ordinary text templates, no AI director."""

from .studio import StudioError, text

STARTERS = [
    {"id": "custom", "name": "My own action", "template_id": "action", "frames": 124,
     "direction": "", "hint": "Describe one complete action, including how it finishes."},
    {"id": "idle", "name": "Quiet idle", "template_id": "idle", "frames": 90,
     "direction": "One small breath and a subtle blink, then settle into the same resting pose.",
     "hint": "Keep the movement small and relaxed."},
    {"id": "sip", "name": "Sip from a mug", "template_id": "action", "frames": 124,
     "direction": "Pause, reach for the existing mug, lift it to the lips, take one small sip, put it back in its original place, and resume the starting activity.",
     "hint": "Include the hand, mug, face and the entire path between them."},
    {"id": "page_turn", "name": "Turn a page", "template_id": "action", "frames": 124,
     "direction": "Turn one page of the open book, then return the hand and gaze to reading.",
     "hint": "Include the moving hand and the whole open book."},
    {"id": "glance", "name": "A brief glance", "template_id": "action", "frames": 124,
     "direction": "Pause the starting activity, glance briefly to one side, then return the head and gaze to the original pose.",
     "hint": "Include room around the head for the turn."},
]


def compile_direction(actor, value):
    if not isinstance(value, dict):
        raise StudioError("Describe the motion to make")
    starter = next((row for row in STARTERS if row["id"] == value.get("starter_id")), None)
    if starter is None:
        raise StudioError("Choose a motion starting point")
    description = text(value.get("description"), "What happens", 2000)
    result = f"Animate {actor}: {description} End in the supplied starting pose, with all handled props back in their original places. "
    if starter["id"] == "sip":
        result += "Show a continuous physical reach, lift, sip and replacement. The same mug must leave its support and reach the lips; no duplicate mug, floating props or disappearing hands. "
    result += ("Keep the camera locked. Preserve identity, anatomy, clothing, prop designs, room geometry, lighting, colors and the source image style. "
               "No new objects, scene cuts, zooms or unrelated actions. Only the selected subject and handled props may move.")
    return result, {"starter_id": starter["id"], "description": description}
