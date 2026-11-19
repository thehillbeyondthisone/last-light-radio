"""Compare an authorized motion batch and build explicit static-hold diagnostics.

This is a review assembly, not a production timeline. It uses unapproved takes
only for comparison and never changes approval, original media or worker state.
"""

from __future__ import annotations

import argparse
import io
import json
import sqlite3
import subprocess
import sys
import tempfile
from contextlib import closing
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageStat

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from compare_motion import candidate, make_comparison, read_frame, verified
from last_light_radio.store import ProjectStore, canonical_bytes, sha256
from last_light_radio.video_tools import ffmpeg_path, verify_video


def mean_difference(before, after, mask):
    delta = ImageChops.difference(before, after)
    means = ImageStat.Stat(delta, mask).mean
    left = ImageStat.Stat(before, mask).mean
    right = ImageStat.Stat(after, mask).mean
    return {"mean_absolute_rgb_0_255": sum(means) / 3,
            "mean_channel_shift_rgb": [b - a for a, b in zip(left, right)]}


def load_image(store, ref, mode="RGB"):
    with Image.open(verified(store, ref)) as image:
        return image.convert(mode)


def pose_frame(store, motion, part):
    profile = motion["profile"]
    base = load_image(store, profile["background"])
    pose = load_image(store, profile[part])
    mask = load_image(store, profile["mask"], "L")
    c = profile["crop"]
    box = (c["x"], c["y"], c["x"] + c["width"], c["y"] + c["height"])
    base.paste(pose.crop(box), (c["x"], c["y"]), mask.crop(box))
    return base


def video_frames(store, record):
    output = record["metadata"]["outputs"][0]
    p = output["properties"]
    size = (p["width"], p["height"])
    args = [ffmpeg_path(), "-v", "error", "-i", str(verified(store, output)),
            "-map", "0:v:0", "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"]
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=errors)
        try:
            for _ in range(p["frame_count"]):
                yield Image.frombytes("RGB", size, read_frame(process.stdout, size[0] * size[1] * 3))
            if process.stdout.read(1):
                raise ValueError("A source clip contains more frames than its recorded timebase")
            if process.wait(timeout=30):
                errors.seek(0)
                raise ValueError("Source decode failed: " + errors.read(1200).decode(errors="replace"))
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
            process.stdout.close()


def boundaries(store, record):
    output = record["metadata"]["outputs"][0]
    props = output["properties"]
    path = verified(store, output)
    size = (props["width"], props["height"])
    selected = f"select=eq(n\\,0)+eq(n\\,{props['frame_count'] - 1})"
    response = subprocess.run([ffmpeg_path(), "-v", "error", "-i", str(path), "-vf", selected,
                               "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
                              capture_output=True, check=True, timeout=40)
    frame_bytes = size[0] * size[1] * 3
    if len(response.stdout) != 2 * frame_bytes:
        raise ValueError("Cannot decode both exact boundary frames")
    return [Image.frombytes("RGB", size, response.stdout[offset:offset + frame_bytes])
            for offset in (0, frame_bytes)]


def render_review(store, pairs, roles, path, mode):
    with tempfile.TemporaryDirectory(prefix="hold-review-", dir=path.parent) as temporary:
        staged = Path(temporary) / "review.mp4"
        info = _render_review_unpublished(store, pairs, roles, staged, mode)
        ProjectStore(path.parent, create=False).write_once(path.name, staged.read_bytes())
        return {**info, "path": path.name}


def validate_frame_count(path, expected):
    result = subprocess.run([ffmpeg_path(), "-v", "error", "-i", str(path), "-map", "0:v:0", "-vf", "scale=16:16",
                             "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
                            capture_output=True, check=True, timeout=90)
    frame_bytes = 16 * 16 * 3
    if len(result.stdout) != expected * frame_bytes:
        raise ValueError(f"Diagnostic frame count differs from the planned holds: expected {expected}")


def _render_review_unpublished(store, pairs, roles, path, mode):
    """Pair new/old frames without fades, frame interpolation or retiming."""
    fps = 24
    font = ImageFont.load_default(size=24)
    small = ImageFont.load_default(size=17)
    count = 0
    last_frames = None

    def segment_frames():
        nonlocal last_frames
        first_motion = pairs[roles[0]][0]["metadata"]["motion"]
        if mode == "held_frames":
            firsts = [boundaries(store, row)[0] for row in pairs[roles[0]]]
        else:
            pose = pose_frame(store, first_motion, "first")
            firsts = [pose, pose]
        for _ in range(fps):
            yield firsts, "START HOLD", roles[0]
        for role in roles:
            rows = pairs[role]
            generators = [video_frames(store, row) for row in rows]
            try:
                frames = rows[0]["metadata"]["outputs"][0]["properties"]["frame_count"]
                for index in range(frames):
                    last_frames = [next(generator) for generator in generators]
                    yield last_frames, f"MOTION {index + 1}/{frames}", role
                for generator in generators:
                    try:
                        next(generator)
                    except StopIteration:
                        pass
                    else:
                        raise ValueError("Review source has extra frames")
            finally:
                for generator in generators:
                    generator.close()
            if mode == "direct" and role != roles[-1]:
                continue
            if mode == "held_frames":
                hold = last_frames
            else:
                pose = pose_frame(store, rows[0]["metadata"]["motion"], "last")
                hold = [pose, pose]
            for _ in range(fps):
                yield hold, "ACTUAL LAST-FRAME HOLD" if mode == "held_frames" else "SUPPLIED POSE HOLD", role

    args = [ffmpeg_path(), "-v", "error", "-nostdin", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s:v", "1920x612",
            "-r", str(fps), "-i", "pipe:0", "-an", "-vf", "scale=in_range=full:out_range=limited:out_color_matrix=bt601,format=yuv420p",
            "-c:v", "libx264", "-preset", "fast", "-crf", "17", "-threads", "2", "-movflags", "+faststart", str(path)]
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=errors)
        try:
            for frames, phase, role in segment_frames():
                canvas = Image.new("RGB", (1920, 612), "#17201e")
                draw = ImageDraw.Draw(canvas)
                for side, (image, label) in enumerate(zip(frames, ("RESTORED / INT8", "EARLIER / FP16"))):
                    x = side * 960
                    canvas.paste(image.resize((960, 540), Image.Resampling.LANCZOS), (x, 72))
                    draw.text((x + 14, 7), f"{label} | {role.replace('_', ' ')}", fill="#f0dfb7", font=font)
                    draw.text((x + 14, 39), f"{phase} | {count / fps:.3f}s | cuts only", fill="white", font=small)
                process.stdin.write(canvas.tobytes())
                count += 1
            process.stdin.close()
            if process.wait(timeout=90):
                errors.seek(0)
                raise ValueError("Hold diagnostic encode failed: " + errors.read(1200).decode(errors="replace"))
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
            if not process.stdin.closed:
                process.stdin.close()
    verify_video(path)
    validate_frame_count(path, count)
    return {"path": path.name, "sha256": sha256(path.read_bytes()), "frames": count, "fps": fps,
            "duration_seconds": count / fps, "mode": mode, "full_decode": True}


def suite(batch_file, store_root, output):
    batch = json.loads(batch_file.read_text())
    store = ProjectStore(store_root, create=False)
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    pairs = {}
    statuses = {}
    with closing(sqlite3.connect(store.resolve("studio.sqlite3").as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        for request in batch["requests"]:
            job = db.execute("SELECT status,error FROM jobs WHERE id=?", (request["job_id"],)).fetchone()
            statuses[request["role"]] = dict(job) if job else {"status": "missing"}
            if not job or job["status"] != "success":
                continue
            new = candidate(db, request["job_id"])
            old = candidate(db, request["reference_candidate_id"])
            pairs[request["role"]] = (new, old)
    results = {}
    for role, rows in pairs.items():
        directory = output / role
        if not directory.exists():
            make_comparison(rows[0]["id"], store_root, directory)
        report = json.loads((directory / "comparison.json").read_text())
        if report["job_id"] != rows[0]["id"]:
            raise ValueError("Existing comparison belongs to another take")
        motion = rows[0]["metadata"]["motion"]
        crop = motion["crop"]
        box = (crop["x"], crop["y"], crop["x"] + crop["width"], crop["y"] + crop["height"])
        mask = load_image(store, motion["mask"], "L").crop(box).point(lambda value: 255 if value > 0 else 0)
        poses = [pose_frame(store, motion, part) for part in ("first", "last")]
        endpoints = [boundaries(store, row) for row in rows]
        measurements = {}
        for side, label in enumerate(("restored", "earlier")):
            first, last = [frame.crop(box) for frame in endpoints[side]]
            measurements[label] = {"pose_hold_to_clip": mean_difference(poses[0].crop(box), first, mask),
                                   "clip_to_pose_hold": mean_difference(last, poses[1].crop(box), mask),
                                   "actual_first_frame_hold_to_clip": 0.0, "clip_to_actual_last_frame_hold": 0.0}
        results[role] = {"job_id": rows[0]["id"], "status": rows[0]["status"], "comparison": f"{role}/comparison.mp4",
                         "pose_hold_joins": measurements, "lossless_background": report["lossless_protected_background_samples"],
                         "execution": rows[0]["metadata"].get("execution"),
                         "visible_motion": report["visible_adjacent_frame_actor_difference"]}
        preview = output / f"{role}-pose-holds.mp4"
        if not preview.exists():
            info = render_review(store, pairs, [role], preview, "pose_holds")
            store_result = ProjectStore(output, create=False)
            store_result.write_once(f"{role}-pose-holds.json", canonical_bytes(info))
        # The two rows show new/old, with pose and clip frames around each cut.
        sheet = Image.new("RGB", (1280, 744), "#17201e")
        draw = ImageDraw.Draw(sheet)
        font = ImageFont.load_default(size=19)
        for side, label in enumerate(("RESTORED / INT8", "EARLIER / FP16")):
            top = side * 372
            frames = [poses[0], endpoints[side][0], endpoints[side][1], poses[1]]
            labels = ["Start pose hold", "First clip frame", "Last clip frame", "End pose hold"]
            for col, (frame, caption) in enumerate(zip(frames, labels)):
                draw.text((col * 320 + 8, top + 7), f"{label}: {caption}", fill="#f0dfb7", font=font)
                sheet.paste(frame.crop(box).resize((320, 320), Image.Resampling.LANCZOS), (col * 320, top + 44))
        buffer = io.BytesIO()
        sheet.save(buffer, "PNG")
        ProjectStore(output, create=False).write_once(f"{role}-hold-joins.png", buffer.getvalue())
    cycle = ["look_toward_window", "window_watching_idle", "resume_reading"]
    cycle_results = {}
    cycle_timing = []
    if all(role in pairs for role in cycle):
        elapsed = 24
        for role in cycle:
            frames = pairs[role][0]["metadata"]["outputs"][0]["properties"]["frame_count"]
            cycle_timing.append({"role": role, "direct_start_frame": elapsed, "direct_start_seconds": elapsed / 24,
                                 "direct_end_frame_exclusive": elapsed + frames})
            elapsed += frames
        for left, right in zip(cycle, cycle[1:]):
            before = pairs[left][0]["metadata"]["motion"]
            after = pairs[right][0]["metadata"]["motion"]
            if before["end_state"] != after["start_state"] or before["profile"]["last"]["sha256"] != after["profile"]["first"]["sha256"]:
                raise ValueError("Cycle clips do not meet at the same named state and conditioning pose")
        for left, right in zip(cycle, cycle[1:]):
            motion = pairs[left][0]["metadata"]["motion"]
            c = motion["crop"]
            box = (c["x"], c["y"], c["x"] + c["width"], c["y"] + c["height"])
            mask = load_image(store, motion["mask"], "L").crop(box).point(lambda v: 255 if v > 0 else 0)
            cycle_results[left + "_to_" + right] = {}
            for side, label in enumerate(("restored", "earlier")):
                before = boundaries(store, pairs[left][side])[1].crop(box)
                after = boundaries(store, pairs[right][side])[0].crop(box)
                cycle_results[left + "_to_" + right][label] = mean_difference(before, after, mask)
        for mode in ("direct", "pose_holds", "held_frames"):
            preview = output / f"window-cycle-{mode}.mp4"
            if not preview.exists():
                info = render_review(store, pairs, cycle, preview, mode)
                ProjectStore(output, create=False).write_once(f"window-cycle-{mode}.json", canonical_bytes(info))
    summary = {"schema_version": 1, "purpose": "unapproved_review_diagnostics", "statuses": statuses,
               "complete": len(pairs) == len(batch["requests"]), "results": results, "cycle_direct_joins": cycle_results,
               "cycle_timing": cycle_timing,
               "hold_policy": "One-second holds. Pose holds use exact conditioning crops assembled through the recovered mask over the canonical plate. Actual-frame holds retain the decoded first/last clip frame. No fades or endpoint replacements.",
               "measurement_note": "Mean absolute RGB differences on 0..255 within nonzero actor mask. Diagnostic comparisons to the old clips, not pass thresholds or quality scores. Actual-frame hold zeros are by construction before the review video's additional lossy encode."}
    data = canonical_bytes(summary)
    digest = sha256(data)
    ProjectStore(output, create=False).write_once(f"suite-{digest[:16]}.json", data)
    return {"complete": summary["complete"], "statuses": {k: v["status"] for k, v in statuses.items()},
            "available_comparisons": list(pairs), "report": str(output / f"suite-{digest[:16]}.json")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=Path, default=Path("artifacts/motion-suite-20261021/batch.json"))
    parser.add_argument("--store", type=Path, default=Path(".local/studio"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/motion-suite-20261021/review"))
    args = parser.parse_args()
    print(json.dumps(suite(args.batch, args.store, args.output), indent=2))


if __name__ == "__main__":
    main()
