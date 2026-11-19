"""Make a synchronized, read-only comparison of a completed actor-motion take.

Example: python scripts/compare_motion.py --job-id ID --store .local/studio
Requires Pillow and the app's optional FFmpeg. Never submits or approves media.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sqlite3
import subprocess
import sys
import tempfile
from contextlib import closing
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageStat

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from last_light_radio.store import ProjectStore, canonical_bytes, sha256
from last_light_radio.video_tools import ffmpeg_path


def verified(store: ProjectStore, reference: dict) -> Path:
    path = store.resolve(reference["path"])
    if sha256(path.read_bytes()) != reference["sha256"]:
        raise ValueError(f"Checksum mismatch: {reference['path']}")
    return path


def image(store: ProjectStore, reference: dict, mode="RGB") -> Image.Image:
    with Image.open(verified(store, reference)) as source:
        source.load()
        return source.convert(mode)


def difference(a: Image.Image, b: Image.Image, mask: Image.Image | None = None) -> dict:
    if a.size != b.size:
        raise ValueError("Comparison images have different dimensions")
    delta = ImageChops.difference(a, b)
    statistics = ImageStat.Stat(delta, mask)
    values = statistics.mean
    return {"mean_absolute_rgb_0_255": values,
            "mean_absolute_channel_0_255": sum(values) / len(values)}


def candidate(db, identity):
    row = db.execute("SELECT * FROM candidates WHERE id=?", (identity,)).fetchone()
    if row is None:
        raise ValueError(f"Completed registered candidate not found: {identity}")
    result = dict(row)
    result["metadata"] = json.loads(result["metadata"])
    return result


def read_frame(stream, byte_count):
    chunks = bytearray()
    while len(chunks) < byte_count:
        part = stream.read(byte_count - len(chunks))
        if not part:
            raise ValueError("Video ended before its recorded frame count")
        chunks.extend(part)
    return bytes(chunks)


def summary(values):
    return {"minimum": min(values), "mean": sum(values) / len(values), "maximum": max(values), "count": len(values)}


def workflow_changes(old, new):
    changes = {}
    for node in sorted(set(old) | set(new)):
        a, b = old.get(node, {}), new.get(node, {})
        if a.get("class_type") != b.get("class_type"):
            changes[f"{node}.class_type"] = {"earlier": a.get("class_type"), "restored": b.get("class_type")}
        for name in sorted(set(a.get("inputs", {})) | set(b.get("inputs", {}))):
            x, y = a.get("inputs", {}).get(name), b.get("inputs", {}).get(name)
            if x != y:
                changes[f"{node}.inputs.{name}"] = {"earlier": x, "restored": y}
    return changes


def make_comparison(job_id: str, store_root: Path, output: Path) -> dict:
    if not re.fullmatch(r"[0-9a-f]{32}", job_id):
        raise ValueError("Job ID must be 32 lowercase hexadecimal characters")
    output = output.resolve()
    if output.exists():
        raise ValueError("Output already exists; choose a new directory to preserve earlier evidence")
    store = ProjectStore(store_root, create=False)
    # mode=ro reads the running studio's WAL without opening a writable connection.
    with closing(sqlite3.connect(store.resolve("studio.sqlite3").as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        job = db.execute("SELECT status FROM jobs WHERE id=?", (job_id,)).fetchone()
        if job is None or job[0] != "success":
            raise ValueError("This job is not complete; run this command after studio registration succeeds")
        restored = candidate(db, job_id)
        motion = restored["metadata"].get("motion")
        if not motion or not motion.get("reference_candidate_id"):
            raise ValueError("Candidate has no recovered actor-motion comparison reference")
        earlier = candidate(db, motion["reference_candidate_id"])
    new, old = restored["metadata"], earlier["metadata"]
    matching = {name: old["parameters"].get(name) == new["parameters"].get(name)
                for name in ("seed", "frames", "fps", "motion_prompt")}
    if not all(matching.values()):
        raise ValueError("A synchronized controlled comparison requires the same seed, timing and prompt")
    count, fps = int(new["parameters"]["frames"]), float(new["parameters"]["fps"])
    if count < 2 or not 1 <= fps <= 120:
        raise ValueError("Invalid recorded comparison timing")
    crop = motion["crop"]
    x, y, width, height = [crop[k] for k in ("x", "y", "width", "height")]
    box = (x, y, x + width, y + height)
    videos = [verified(store, metadata["outputs"][0]) for metadata in (new, old)]
    full_size = tuple(new["outputs"][0]["properties"][name] for name in ("width", "height"))
    if full_size != tuple(old["outputs"][0]["properties"][name] for name in ("width", "height")):
        raise ValueError("Full-scene geometry differs between the takes")
    new_graph = store.read_snapshot(new["workflow"])
    old_graph = store.read_snapshot(old["workflow"])
    new_vae = new_graph["3"]["inputs"]["vae_name"]
    old_vae = old_graph["3"]["inputs"]["vae_name"]
    new_label = "RESTORED / " + ("INT8 VAE" if "int8" in new_vae.lower() else "FP16 VAE" if "fp16" in new_vae.lower() else new_vae)
    old_label = "EARLIER / " + ("FP16 VAE" if "fp16" in old_vae.lower() else old_vae)
    background_ref = motion["profile"].get("background", motion["first"])
    background = image(store, background_ref)
    alpha = image(store, motion["mask"], "L")
    effective = Image.new("L", background.size, 0)
    effective.paste(alpha.crop(box), (x, y))
    protected = effective.point(lambda value: 255 if value == 0 else 0)
    actor = effective.crop(box).point(lambda value: 255 if value > 0 else 0)
    protected_count = protected.histogram()[255]
    protected_checks = {}
    for name, reference in motion["lossless_samples"].items():
        sample = image(store, reference)
        delta = ImageChops.difference(sample, background)
        maximum = ImageChops.lighter(ImageChops.lighter(*delta.split()[:2]), delta.split()[2])
        protected_delta = ImageChops.multiply(maximum, protected)
        histogram = protected_delta.histogram()
        protected_checks[name] = {"frame_index": reference["frame_index"], "checked_pixel_count": protected_count,
                                 "changed_pixel_count": sum(histogram[1:]), "maximum_channel_difference": protected_delta.getextrema()[1],
                                 "exact_background_match": protected_delta.getbbox() is None}
    if not all(item["exact_background_match"] for item in protected_checks.values()):
        raise ValueError("Lossless samples contain changed pixels outside the effective actor mask")
    prepared = motion["prepared_inputs"]
    endpoints = {}
    records = motion["raw_frames"]
    if len(records) != count:
        raise ValueError("Raw-frame count disagrees with the completed candidate")
    raw_changes = []
    previous_raw = None
    raw_first = raw_last = None
    for index, record in enumerate(records):
        raw = image(store, record)
        if raw.size != (width, height):
            raise ValueError("Raw crop geometry changed")
        if previous_raw is not None:
            raw_changes.append(difference(raw, previous_raw, actor)["mean_absolute_channel_0_255"])
        if index == 0:
            raw_first = raw.copy()
            endpoints["first"] = difference(raw, image(store, prepared["first"]))
        if index == count - 1:
            raw_last = raw.copy()
            endpoints["last"] = difference(raw, image(store, prepared["last"]))
        previous_raw = raw
    output.mkdir(parents=True)
    destination = ProjectStore(output, create=False)
    font = ImageFont.load_default(size=25)
    small = ImageFont.load_default(size=18)
    selected = {round((count - 1) * fraction) for fraction in (0, .25, .5, .75, 1)}
    samples = {}
    visible_changes = [[], []]
    pair_changes = []
    previous = [None, None]
    ffmpeg = ffmpeg_path()
    display_size = (960, round(960 * full_size[1] / full_size[0]))
    canvas_size = (display_size[0] * 2, display_size[1] + 64)
    comparison_file = output / "comparison.mp4"
    processes = []
    with tempfile.TemporaryFile() as errors:
        try:
            for video in videos:
                args = [ffmpeg, "-v", "error", "-nostdin", "-threads", "1", "-i", str(video), "-an",
                        "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"]
                processes.append(subprocess.Popen(args, stdout=subprocess.PIPE, stderr=errors))
            encoder = subprocess.Popen([ffmpeg, "-v", "error", "-nostdin", "-n", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s:v", f"{canvas_size[0]}x{canvas_size[1]}",
                                        "-r", str(fps), "-i", "pipe:0", "-an", "-vf", "scale=in_range=full:out_range=limited:out_color_matrix=bt601,format=yuv420p",
                                        "-c:v", "libx264", "-crf", "15", "-preset", "medium", "-threads", "2", "-movflags", "+faststart", str(comparison_file)],
                                       stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=errors)
            processes.append(encoder)
            for index in range(count):
                full_frames = [Image.frombytes("RGB", full_size, read_frame(process.stdout, full_size[0] * full_size[1] * 3)) for process in processes[:2]]
                frames = [frame.crop(box) for frame in full_frames]
                for side, frame in enumerate(frames):
                    if previous[side] is not None:
                        visible_changes[side].append(difference(frame, previous[side], actor)["mean_absolute_channel_0_255"])
                    previous[side] = frame
                pair_changes.append(difference(frames[0], frames[1], actor)["mean_absolute_channel_0_255"])
                if index in selected:
                    samples[index] = [frame.copy() for frame in frames]
                canvas = Image.new("RGB", canvas_size, "#17201e")
                draw = ImageDraw.Draw(canvas)
                for side, (frame, label) in enumerate(zip(full_frames, (new_label, old_label))):
                    left = side * display_size[0]
                    canvas.paste(frame.resize(display_size, Image.Resampling.LANCZOS), (left, 64))
                    draw.text((left + 14, 8), label, fill="#f0dfb7", font=font)
                    draw.text((left + 14, 38), f"Seed {new['parameters']['seed']}  |  {index + 1}/{count}  |  {index / fps:.3f}s", fill="white", font=small)
                encoder.stdin.write(canvas.tobytes())
            encoder.stdin.close()
            for decoder in processes[:2]:
                if decoder.stdout.read(1):
                    raise ValueError("A source video has more frames than its recorded metadata")
                decoder.stdout.close()
            if any(process.wait(timeout=90) for process in processes):
                errors.seek(0)
                raise ValueError("Comparison encoding failed: " + errors.read(2000).decode(errors="replace"))
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                process.wait()
                for stream in (process.stdin, process.stdout):
                    if stream is not None and not stream.closed:
                        stream.close()
    tile = 384
    sheet = Image.new("RGB", (tile * len(samples), 64 + 2 * (tile + 44)), "#17201e")
    draw = ImageDraw.Draw(sheet)
    draw.text((14, 10), "Actor crops from synchronized full-scene MP4s", fill="white", font=font)
    for row, label in enumerate((new_label, old_label)):
        top = 64 + row * (tile + 44)
        draw.text((14, top + 7), label, fill="#f0dfb7", font=font)
        for column, (index, frames) in enumerate(sorted(samples.items())):
            sheet.paste(frames[row].resize((tile, tile), Image.Resampling.LANCZOS), (column * tile, top + 44))
            draw.text((column * tile + 10, top + 44 + tile - 28), f"Frame {index + 1} / {index / fps:.3f}s", fill="white", stroke_fill="black", stroke_width=2, font=small)
    buffer = io.BytesIO()
    sheet.save(buffer, "PNG")
    destination.write_once("actor-contact-sheet.png", buffer.getvalue())
    report = {"schema_version": 1, "job_id": job_id, "reference_candidate_id": earlier["id"], "comparison_scope": "Synchronized full-scene MP4s resized to 960 pixels per side; contact sheet and metrics use decoded actor crops. No source dependence outside the working store",
              "new_status_at_comparison": restored["status"], "earlier_status_at_comparison": earlier["status"], "creator_approval": False,
              "seed": new["parameters"]["seed"], "frame_count": count, "fps": fps, "duration_seconds": count / fps,
              "matching_inputs": matching, "crop": crop, "labels": {"left": new_label, "right": old_label},
              "vae": {"restored": new_vae, "earlier": old_vae}, "workflow_input_changes": workflow_changes(old_graph, new_graph),
              "sources": {"restored": {"video": new["outputs"][0], "workflow": new["workflow"], "prompt_id": new.get("prompt_id"), "execution": new.get("execution"), "metadata": new},
                          "earlier": {"video": old["outputs"][0], "workflow": old["workflow"], "prompt_id": old.get("prompt_id"), "execution": old.get("execution")}},
              "lossless_protected_background_samples": protected_checks, "raw_generated_vs_conditioning_endpoints": endpoints,
              "raw_generated_head_tail_difference": difference(raw_first, raw_last),
              "raw_generated_adjacent_frame_actor_difference": summary(raw_changes),
              "visible_adjacent_frame_actor_difference": {"restored": summary(visible_changes[0]), "earlier": summary(visible_changes[1])},
              "visible_restored_vs_earlier_actor_difference": summary(pair_changes),
              "metric_note": "All differences are mean absolute 8-bit RGB channel values, not motion, identity or loop quality scores. Visible metrics include lossy encoding and compositing. Lossless protection checks cover saved start/middle/end samples only. VAE, compositor reconstruction and changed runtime confound attribution; matching seed is not proof of identical output.",
              "artifacts": {"comparison_video": {"path": "comparison.mp4", "sha256": sha256(comparison_file.read_bytes())},
                            "contact_sheet": {"path": "actor-contact-sheet.png", "sha256": sha256(buffer.getvalue())}}}
    destination.write_once("comparison.json", canonical_bytes(report))
    destination.write_once("README.txt", (f"LEFT: {new_label}\nRIGHT: {old_label}\nSeed {report['seed']}; {count} frames at {fps:g} fps ({count / fps:.3f}s).\n"
                                         "Video shows synchronized full scenes at 960 pixels per side. Contact sheet and metrics use the same actor crop from each full-scene MP4, sampled first, quarter, middle, three-quarter and final.\n"
                                         "The restored take remains a candidate. No approvals or source data were changed.\n"
                                         f"Selected video VAE: {new_vae}; earlier video VAE: {old_vae}. Reconstructed compositing also differs from the earlier code.\n"
                                         "Visual review is required; numeric differences are not quality scores.\n"
                                         "comparison.json records verified sources, workflow changes, lossless-background checks and RGB differences.\n").encode())
    return {"output": str(output), "comparison_video": str(comparison_file), "contact_sheet": str(output / "actor-contact-sheet.png"),
            "lossless_protected_samples_pass": True, "frame_count": count, "fps": fps, "new_status": restored["status"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--store", type=Path, default=Path(".local/studio"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/restored-motion-comparison"))
    args = parser.parse_args()
    try:
        print(json.dumps(make_comparison(args.job_id, args.store, args.output), indent=2))
    except (ValueError, OSError, sqlite3.Error, subprocess.SubprocessError) as error:
        print(f"Comparison failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
