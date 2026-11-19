"""CPU-only, frame-counted media helpers for deterministic pilot exports."""

from __future__ import annotations

import io
import re
import subprocess
import tempfile

from PIL import Image, ImageOps

from .store import canonical_bytes, sha256
from .video_tools import ffmpeg_path


def rgb(store, ref):
    store.verify_master({"id": "pilot-frame", **ref})
    with Image.open(store.resolve(ref["path"])) as image:
        return ImageOps.exif_transpose(image).convert("RGB")


def inspect_video(path, count, fps, size, *, timeout=600):
    """Fully decode and verify native frame count, dimensions, rate and PTS."""
    result = subprocess.run([ffmpeg_path(), "-hide_banner", "-nostdin", "-i", str(path), "-map", "0:v:0",
                             "-vf", "showinfo,scale=16:16", "-fps_mode", "passthrough",
                             "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"], capture_output=True, timeout=timeout)
    log = result.stderr.decode(errors="replace")
    frames = re.findall(r"\bn:\s*(\d+)\s+pts:\s*(-?\d+)\s+pts_time:([\d.eE+-]+).*?\bs:(\d+)x(\d+)", log)
    rates = re.findall(r"config in time_base:.*?frame_rate:\s*(\d+)/(\d+)", log)
    if result.returncode or len(result.stdout) != count * 16 * 16 * 3 or len(frames) != count:
        raise ValueError(f"Video decode/frame-count check failed: expected {count}, decoded {len(frames)}")
    if not rates or any(int(den) == 0 or int(num) / int(den) != fps for num, den in rates):
        raise ValueError("Video frame rate differs from the pinned pilot timebase")
    for index, (number, _, seconds, width, height) in enumerate(frames):
        if int(number) != index or (int(width), int(height)) != size or abs(float(seconds) - index / fps) > 0.001:
            raise ValueError("Video geometry or presentation timestamps differ from the pilot contract")
    return {"frame_count": count, "fps": fps, "width": size[0], "height": size[1],
            "duration_seconds": count / fps, "fully_decoded": True, "presentation_timestamps_verified": True}


def boundary_frames(path, count, size):
    result = subprocess.run([ffmpeg_path(), "-v", "error", "-nostdin", "-i", str(path),
                             "-vf", f"select=eq(n\\,0)+eq(n\\,{count - 1})", "-fps_mode", "passthrough",
                             "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"], capture_output=True, timeout=90, check=True)
    length = size[0] * size[1] * 3
    if len(result.stdout) != length * 2:
        raise ValueError("Could not retrieve both exact decoded boundary frames")
    return [Image.frombytes("RGB", size, result.stdout[offset:offset + length]) for offset in (0, length)]


def prepare_clip(store, output, fps, size):
    store.verify_master({"id": "approved-video", **output})
    cache = f"exports/pilot-cache/{output['sha256']}"
    record = store.resolve(f"{cache}/inspection.json")
    count = output["properties"]["frame_count"]
    if record.is_file():
        import json
        info = json.loads(record.read_text())
        if (info["frame_count"], info["fps"], info["width"], info["height"]) != (count, fps, *size):
            raise ValueError("Cached video inspection does not match this pilot")
        for ref in info["boundaries"].values():
            store.verify_master({"id": "cached-boundary", **ref})
        return info
    path = store.resolve(output["path"])
    info = inspect_video(path, count, fps, size)
    info["boundaries"] = {}
    for name, image in zip(("entry", "exit"), boundary_frames(path, count, size)):
        buffer = io.BytesIO()
        image.save(buffer, "PNG")
        data = buffer.getvalue()
        relative = f"{cache}/{name}.png"
        store.write_once(relative, data)
        info["boundaries"][name] = {"path": relative, "sha256": sha256(data)}
    store.write_once(f"{cache}/inspection.json", canonical_bytes(info))
    return info


def video_rgb(store, output, size, stop_event):
    length = size[0] * size[1] * 3
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen([ffmpeg_path(), "-v", "error", "-nostdin", "-i", str(store.resolve(output["path"])),
                                    "-map", "0:v:0", "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
                                   stdout=subprocess.PIPE, stderr=errors)
        try:
            for _ in range(output["properties"]["frame_count"]):
                if stop_event.is_set():
                    raise InterruptedError("Studio stopped; retry this pinned export after restarting")
                data = process.stdout.read(length)
                if len(data) != length:
                    raise ValueError("Approved clip ended before its recorded final frame")
                yield data
            if process.stdout.read(1) or process.wait(timeout=40):
                raise ValueError("Approved clip has unexpected extra frames or a decode error")
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            process.stdout.close()


def encode_pilot(store, manifest, output_path, stop_event, progress):
    """One encoder/timebase; holds repeat the actual last decoded RGB frame."""
    size = (manifest["width"], manifest["height"])
    fps = manifest["fps"]
    from .ambience import Compositor
    ambience = Compositor(store, manifest.get("ambience"), size, fps)
    clips = {clip["id"]: clip for clip in manifest["clips"]}
    args = [ffmpeg_path(), "-v", "error", "-nostdin", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s:v", f"{size[0]}x{size[1]}",
            "-r", str(fps), "-i", "pipe:0", "-an", "-vf",
            "pad=ceil(iw/2)*2:ceil(ih/2)*2:0:0,scale=in_range=full:out_range=limited:out_color_matrix=bt601,format=yuv420p",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", "-threads", "4", "-color_range", "tv", "-colorspace", "smpte170m",
            "-video_track_timescale", "24000", "-movflags", "+faststart", str(output_path)]
    current = rgb(store, manifest["master"]).tobytes()
    written = 0
    hold_checks = []
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=errors)
        try:
            for event in manifest["events"]:
                if written != event["start_frame"]:
                    raise ValueError("Pilot events are not contiguous")
                if event["kind"] == "clip":
                    frames = video_rgb(store, clips[event["variant_id"]]["output"], size, stop_event)
                else:
                    expected = rgb(store, event["frame_image"]).tobytes()
                    if current != expected:
                        raise ValueError("A hold does not match the actual current decoded frame")
                    hold_checks.append({"event_index": event["index"], "source_sha256": event["frame_image"]["sha256"],
                                        "matches_current_rgb": True, "frames": event["end_frame"] - event["start_frame"]})
                    frames = (current for _ in range(event["end_frame"] - event["start_frame"]))
                try:
                    for data in frames:
                        if stop_event.is_set():
                            raise InterruptedError("Studio stopped; retry this pinned export after restarting")
                        process.stdin.write(ambience.apply(data, written))
                        current = data
                        written += 1
                        if written % fps == 0:
                            progress(written / manifest["duration_frames"] * 0.9)
                finally:
                    frames.close()
                if written != event["end_frame"]:
                    raise ValueError("A pilot segment has the wrong frame count")
            process.stdin.close()
            if process.wait(timeout=180):
                errors.seek(0)
                raise ValueError("FFmpeg export failed: " + errors.read(1200).decode(errors="replace"))
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            if not process.stdin.closed:
                process.stdin.close()
    if written != manifest["duration_frames"]:
        raise ValueError("Export did not write the exact pilot duration")
    return {"frames_written": written, "hold_checks": hold_checks, "audio": "none", "encoder": "libx264 veryfast crf17 yuv420p BT.601 limited",
            "ambience": {"renderer_version": manifest["ambience"]["renderer_version"], "clock": "absolute_episode_frame",
                         "layers": [layer["kind"] for layer in manifest["ambience"]["layers"]]} if manifest.get("ambience") else None}
