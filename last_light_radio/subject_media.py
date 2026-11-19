"""CPU-only compositing of disjoint, already feathered subject takes.

Approved scene videos already contain their original feathered blend. Their
binary support selects those finished pixels exactly once; applying the source
alpha a second time would fade the subject back toward the canonical plate.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageChops

from .pilot_media import rgb, video_rgb
from .video_tools import ffmpeg_path

VERSION = "subject-sequence-v1"


def _prepare(store, manifest, stop_event):
    if manifest.get("kind") != "studio_subject_sequence" or manifest.get("renderer_version") != VERSION:
        raise ValueError("This subject sequence renderer is unavailable")
    size = (manifest["width"], manifest["height"])
    duration = manifest["duration_frames"]
    if (any(type(value) is not int or value < 1 for value in (*size, duration))
            or manifest["fps"] != 24):
        raise ValueError("Subject sequences require positive dimensions, frames and the pinned 24fps timebase")
    master = rgb(store, manifest["master"])
    if master.size != size:
        raise ValueError("The canonical plate differs from the subject sequence dimensions")
    clips, masks, supports = {}, {}, {}
    for clip in manifest["clips"]:
        if stop_event.is_set():
            raise InterruptedError("Studio stopped; retry this pinned export after restarting")
        identity, actor = clip["id"], clip["actor"]
        if identity in clips:
            raise ValueError("A subject sequence contains duplicate clip identities")
        output = clip["output"]
        properties = output["properties"]
        if (type(clip["frames"]) is not int or clip["frames"] < 1
                or properties["frame_count"] != clip["frames"]
                or properties["effective_fps"] != manifest["fps"]
                or (properties["width"], properties["height"]) != size):
            raise ValueError("An approved take differs from its pinned subject timing or geometry")
        store.verify_master({"id": identity, **output})
        store.verify_master({"id": "subject-mask", **clip["mask"]})
        with Image.open(store.resolve(clip["mask"]["path"])) as image:
            mask = image.convert("L")
        if mask.size != size or any(mask.histogram()[1:255]) or not mask.getbbox():
            raise ValueError("Subject support must be a nonempty binary mask at scene dimensions")
        bounds = mask.getbbox()
        masks[identity] = (mask.crop(bounds), bounds)
        supports[actor] = ImageChops.lighter(supports[actor], mask) if actor in supports else mask
        clips[identity] = clip
    actors = sorted(supports)
    for index, actor in enumerate(actors):
        for other in actors[index + 1:]:
            if ImageChops.multiply(supports[actor], supports[other]).getbbox():
                raise ValueError("Subject masks overlap; independent compositing cannot be rendered safely")
    states, seen = [], set()
    master_bytes = master.tobytes()
    for track in manifest["tracks"]:
        actor, events = track["actor"], track["events"]
        if actor in seen:
            raise ValueError("Each subject must have exactly one resolved animation schedule")
        seen.add(actor)
        cursor, last_layer = 0, None
        for event in events:
            start, end = event["start_frame"], event["end_frame"]
            if (type(start) is not int or type(end) is not int or start != cursor
                    or not start < end <= duration or event.get("actor", actor) != actor):
                raise ValueError("Subject events must be contiguous and cover the exact sequence duration")
            if event["kind"] == "clip":
                clip = clips.get(event["variant_id"])
                if (clip is None or clip["actor"] != actor or end - start != clip["frames"]
                        or event.get("layer_clip_id") != clip["id"]):
                    raise ValueError("A subject event differs from its pinned approved take")
                last_layer = clip["id"]
            elif event["kind"] != "hold" or event.get("layer_clip_id") != last_layer:
                raise ValueError("A subject hold must retain its actual preceding take and mask")
            cursor = end
        if cursor != duration:
            raise ValueError("Subject events must cover the exact sequence duration")
        states.append({"actor": actor, "events": events, "index": 0, "decoder": None,
                       "current": master_bytes, "layer": None})
    return size, master, clips, masks, states


def subject_frames(store, manifest, stop_event, *, hold_checks=None):
    """Yield exact RGB scene frames, streaming at most one decoder per subject.

    Holds keep the last decoded take under that take's mask. The immutable master
    is rebuilt underneath the independent subject patches for every frame.
    """
    size, master, clips, masks, states = _prepare(store, manifest, stop_event)
    length = size[0] * size[1] * 3
    try:
        for frame in range(manifest["duration_frames"]):
            if stop_event.is_set():
                raise InterruptedError("Studio stopped; retry this pinned export after restarting")
            scene = master.copy()
            for state in states:
                event = state["events"][state["index"]]
                if frame == event["start_frame"]:
                    if event["kind"] == "clip":
                        state["layer"] = event["variant_id"]
                        state["decoder"] = video_rgb(store, clips[state["layer"]]["output"], size, stop_event)
                    else:
                        expected = rgb(store, event["frame_image"])
                        if expected.size != size or expected.tobytes() != state["current"]:
                            raise ValueError("A subject hold does not match its actual current decoded frame")
                        if hold_checks is not None:
                            hold_checks.append({"event_index": event["index"], "actor": state["actor"],
                                                "source_sha256": event["frame_image"]["sha256"],
                                                "matches_current_rgb": True,
                                                "frames": event["end_frame"] - event["start_frame"]})
                if event["kind"] == "clip":
                    try:
                        state["current"] = next(state["decoder"])
                    except StopIteration:
                        raise ValueError("A subject take ended before its pinned event") from None
                    if len(state["current"]) != length:
                        raise ValueError("A subject decoder returned the wrong RGB frame dimensions")
                if state["layer"] is not None:
                    mask, bounds = masks[state["layer"]]
                    source = Image.frombytes("RGB", size, state["current"])
                    scene.paste(source.crop(bounds), bounds, mask)
                if frame + 1 == event["end_frame"]:
                    if state["decoder"] is not None:
                        try:
                            next(state["decoder"])
                        except StopIteration:
                            pass
                        else:
                            raise ValueError("A subject take contains more frames than its pinned event")
                        finally:
                            state["decoder"].close()
                            state["decoder"] = None
                    state["index"] += 1
            yield scene.tobytes()
    finally:
        for state in states:
            if state["decoder"] is not None:
                state["decoder"].close()


def encode_subjects(store, manifest, output_path, stop_event, progress):
    """Encode the resolved subjects and absolute-time effects in one timebase."""
    from .ambience import Compositor
    from .texture import Compositor as TextureCompositor
    size, fps = (manifest["width"], manifest["height"]), manifest["fps"]
    duration = manifest["duration_frames"]
    pauses = manifest.get("steam_pauses", [])
    for pause in pauses:
        if (not isinstance(pause, list) or len(pause) != 2
                or any(type(value) is not int for value in pause) or not 0 <= pause[0] < pause[1] <= duration):
            raise ValueError("The fixed-plume steam pause has invalid frame boundaries")
    ambience = Compositor(store, manifest.get("ambience"), size, fps)
    texture = TextureCompositor(manifest.get("texture"), size)
    args = [ffmpeg_path(), "-v", "error", "-nostdin", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s:v", f"{size[0]}x{size[1]}",
            "-r", str(fps), "-i", "pipe:0", "-an", "-vf",
            "pad=ceil(iw/2)*2:ceil(ih/2)*2:0:0,scale=in_range=full:out_range=limited:out_color_matrix=bt601,format=yuv420p",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", "-threads", "4", "-color_range", "tv", "-colorspace", "smpte170m",
            "-video_track_timescale", "24000", "-movflags", "+faststart", str(output_path)]
    written, hold_checks = 0, []
    frames = subject_frames(store, manifest, stop_event, hold_checks=hold_checks)
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=errors)
        try:
            for frame, data in enumerate(frames):
                disabled = ("steam",) if any(start <= frame < end for start, end in pauses) else ()
                process.stdin.write(texture.apply(ambience.apply(data, frame, disabled_kinds=disabled), frame))
                written += 1
                if written % fps == 0:
                    progress(written / duration * 0.9)
            process.stdin.close()
            if process.wait(timeout=180):
                errors.seek(0)
                raise ValueError("FFmpeg subject export failed: " + errors.read(1200).decode(errors="replace"))
        finally:
            frames.close()
            if process.poll() is None:
                process.kill()
                process.wait()
            if not process.stdin.closed:
                process.stdin.close()
    if written != duration:
        raise ValueError("Export did not write the exact subject sequence duration")
    report = {"frames_written": written, "hold_checks": hold_checks, "audio": "none", "renderer_version": VERSION,
            "subject_tracks": [track["actor"] for track in manifest["tracks"]],
            "compositing_policy": "disjoint binary support; already feathered approved pixels; canonical background",
            "encoder": "libx264 veryfast crf17 yuv420p BT.601 limited", "steam_pauses": pauses,
            "ambience": {"renderer_version": manifest["ambience"]["renderer_version"], "clock": "absolute_episode_frame",
                         "layers": [layer["kind"] for layer in manifest["ambience"]["layers"]]} if manifest.get("ambience") else None}
    if manifest.get("texture"):
        report["texture"] = manifest["texture"]
    if manifest.get("audio_tracks"):
        from .audio_tracks import mix_export
        report.update(mix_export(store, manifest, Path(output_path), stop_event))
    return report
