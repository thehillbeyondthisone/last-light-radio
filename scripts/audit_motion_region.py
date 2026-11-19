"""Audit an existing actor take without submitting jobs or changing approval.

Replay every lossless composite, check the actual saved samples, and measure
decoded MP4 changes separately. A codec may change protected RGB values even
when the compositing input is exact; those measurements are not quality scores.
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from last_light_radio.generation import load_request
from last_light_radio.motion_jobs import composite_actor_frame, prepare_motion_inputs
from last_light_radio.store import ProjectStore, canonical_bytes, sha256
from last_light_radio.video_tools import ffmpeg_path, verify_video


def verified(store, record):
    store.verify_master({"id": "audit-input", **record})
    return store.resolve(record["path"])


def load_image(store, record):
    with Image.open(verified(store, record)) as image:
        image.load()
        return image.convert("RGB")


def metrics(before, after, mask):
    difference = ImageChops.difference(before, after)
    channels = difference.split()
    maximum = ImageChops.lighter(ImageChops.lighter(channels[0], channels[1]), channels[2])
    histogram = maximum.histogram(mask)
    means = ImageStat.Stat(difference, mask).mean
    return {"mean_absolute_rgb_0_255": sum(means) / 3,
            "changed_pixels": sum(histogram[1:]), "pixels_above_8": sum(histogram[9:]),
            "maximum_channel_difference": max((i for i, value in enumerate(histogram) if value), default=0)}


def decoded_frames(path, size, count):
    frame_bytes = size[0] * size[1] * 3
    args = [ffmpeg_path(), "-v", "error", "-nostdin", "-i", str(path), "-map", "0:v:0",
            "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"]
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=errors)
        try:
            for _ in range(count):
                data = process.stdout.read(frame_bytes)
                if len(data) != frame_bytes:
                    raise ValueError("MP4 has missing or truncated decoded frames")
                yield Image.frombytes("RGB", size, data)
            if process.stdout.read(1):
                raise ValueError("MP4 has more frames than its recorded count")
            if process.wait(timeout=40):
                errors.seek(0)
                raise ValueError(errors.read(1000).decode(errors="replace"))
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            process.stdout.close()


def png(image):
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def audit(store_root, identity, output):
    store = ProjectStore(store_root, create=False)
    with closing(sqlite3.connect(store.resolve("studio.sqlite3").as_uri() + "?mode=ro", uri=True)) as db:
        db.execute("PRAGMA query_only=ON")
        row = db.execute("SELECT scene_id,label,metadata,status,version FROM candidates WHERE id=?", (identity,)).fetchone()
        if row is None:
            raise ValueError("Wait for this candidate to complete before auditing")
    scene_id, label, metadata, status, version = row
    candidate = json.loads(metadata)
    derivative = candidate.get("recomposition")
    request = store.read_snapshot(derivative["source_generation_request"]) if derivative else load_request(store, identity)
    if request.get("pipeline") != "actor_motion_v1":
        raise ValueError("Choose an actor-motion take")
    profile = candidate["motion"]["profile"] if derivative else request["motion_profile"]
    if derivative:
        from last_light_radio.recompose import validate_mask_revision
        validate_mask_revision(request["motion_profile"], profile)
    elif candidate["motion"]["profile"] != profile:
        raise ValueError("Candidate and request refer to different recipes")
    inputs = prepare_motion_inputs(store, profile)
    raw = candidate["motion"]["raw_frames"]
    count = request["parameters"]["frames"]
    if len(raw) != count or [r["index"] for r in raw] != list(range(count)):
        raise ValueError("The raw frame sequence is incomplete or out of order")
    for reference in request["prepared_inputs"].values():
        verified(store, reference)
    effective = inputs["effective_mask"]
    inside = effective.point(lambda value: 255 if value else 0)
    outside = ImageChops.invert(inside)
    crop = profile["crop"]
    box = (crop["x"], crop["y"], crop["x"] + crop["width"], crop["y"] + crop["height"])
    background = inputs["background"]
    samples = candidate["motion"]["lossless_samples"]
    sample_by_index = {record["frame_index"]: (key, record) for key, record in samples.items()}
    first_composite = previous = None
    replayed = {}
    per_frame = []
    sample_checks = {}
    # Every generated PNG and replayed full-scene frame is decoded/checked.
    for index, reference in enumerate(raw):
        frame = load_image(store, reference)
        composite = composite_actor_frame(background, inputs["last"], frame, inputs["mask"], crop,
                                          index, count, inputs["policy"])
        protected = metrics(background, composite, outside)
        if protected["changed_pixels"]:
            raise ValueError(f"Protected pixels changed in lossless frame {index}")
        if first_composite is None:
            first_composite = composite.copy()
        record = {"index": index, "lossless_protected_vs_master": protected,
                  "lossless_inside_vs_first": metrics(first_composite, composite, inside)}
        if previous is not None:
            record["lossless_inside_vs_previous"] = metrics(previous, composite, inside)
        per_frame.append(record)
        previous = composite
        if index in sample_by_index:
            key, sample_record = sample_by_index[index]
            saved = load_image(store, sample_record)
            if ImageChops.difference(composite, saved).getbbox():
                raise ValueError("The actual saved lossless sample differs from the replay")
            sample_checks[key] = {"frame_index": index, "actual_sample_matches_replay": True,
                                  "protected_pixels_changed": metrics(background, saved, outside)["changed_pixels"]}
            replayed[index] = composite

    output_record = candidate["outputs"][0]
    media_path = verified(store, output_record)
    properties = output_record["properties"]
    size = (properties["width"], properties["height"])
    verify_video(media_path)
    first_encoded = previous_encoded = None
    frames = decoded_frames(media_path, size, count)
    try:
        for index, decoded in enumerate(frames):
            # Encoder edge padding is outside original image coordinates.
            encoded = decoded.crop((0, 0, background.width, background.height))
            if first_encoded is None:
                first_encoded = encoded.copy()
            per_frame[index]["mp4_protected_vs_first_decoded"] = metrics(first_encoded, encoded, outside)
            per_frame[index]["mp4_inside_vs_first_decoded"] = metrics(first_encoded, encoded, inside)
            if previous_encoded is not None:
                per_frame[index]["mp4_protected_vs_previous"] = metrics(previous_encoded, encoded, outside)
            previous_encoded = encoded
    finally:
        frames.close()

    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    target = ProjectStore(output, create=False)
    # Full-scene diagnostic: the difference remains black outside the mask.
    middle = replayed[count // 2]
    delta = ImageChops.difference(background, middle).point(lambda value: min(255, value * 8))
    views = [background.copy(), middle.copy(), delta]
    labels = ["PRESERVED MASTER", "MIDDLE LOSSLESS FRAME", "ABSOLUTE DIFFERENCE x8"]
    panel_width, panel_height = 336, 420
    canvas = Image.new("RGB", (panel_width * 3, panel_height + 78), "#17221c")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default(size=16)
    for column, (image, title) in enumerate(zip(views, labels)):
        image.thumbnail((panel_width, panel_height))
        canvas.paste(image, (column * panel_width + (panel_width - image.width) // 2, 52))
        draw.text((column * panel_width + 12, 18), title, font=font, fill="#e6eddb")
    draw.text((12, panel_height + 59), "Difference is from decoded generated PNGs before lossy MP4 encoding.", font=ImageFont.load_default(size=13), fill="#b8c8a6")
    target.write_once("containment-overview.png", png(canvas))
    panel_width = 390
    panel_height = round(panel_width * crop["height"] / crop["width"])
    contact = Image.new("RGB", (panel_width * 4, panel_height * 2 + 110), "#17221c")
    draw = ImageDraw.Draw(contact)
    ordered = [(background, "MASTER"), *[(replayed[i], f"FRAME {i + 1}/{count}") for i in sorted(replayed)]]
    if len(ordered) != 4:
        raise ValueError("Expected three saved start/middle/end samples")
    for column, (image, title) in enumerate(ordered):
        selected = image.crop(box).resize((panel_width, panel_height), Image.Resampling.LANCZOS)
        contact.paste(selected, (column * panel_width, 45))
        draw.text((column * panel_width + 12, 15), title, font=font, fill="#e6eddb")
        if column == 0:
            diagnostic = effective.crop(box).convert("RGB")
            diagnostic_title = "FEATHERED MASK"
        else:
            diagnostic = ImageChops.difference(background, image).crop(box).point(lambda value: min(255, value * 8))
            diagnostic_title = "DIFFERENCE x8"
        diagnostic = diagnostic.resize((panel_width, panel_height), Image.Resampling.NEAREST)
        contact.paste(diagnostic, (column * panel_width, panel_height + 100))
        draw.text((column * panel_width + 12, panel_height + 70), diagnostic_title, font=font, fill="#b8c8a6")
    target.write_once("cat-boundaries-and-differences.png", png(contact))
    target.write_once("effective-mask.png", png(effective))
    report = {"schema_version": 1, "local_job_id": identity, "prompt_id": candidate["prompt_id"], "label": label,
              "scene_id": scene_id, "review_status": status, "review_version": version,
              "master": request["master"], "recipe_id": profile["id"], "crop": crop,
              "conditioning_transform": profile.get("conditioning_transform"),
              "parameters": request["parameters"], "execution": candidate.get("execution"),
              "output": output_record, "full_mp4_decode_passed": True, "decoded_mp4_frame_count": count,
              "raw_pngs_decoded": count, "lossless_composites_replayed": count,
              "actual_saved_samples": sample_checks, "effective_mask_bbox": effective.getbbox(),
              "moving_support_pixels": sum(inside.histogram()[1:]),
              "protected_pixels": sum(outside.histogram()[1:]),
              "max_lossless_protected_pixels_changed": max(r["lossless_protected_vs_master"]["changed_pixels"] for r in per_frame),
              "max_inside_temporal_mae_0_255": max(r["lossless_inside_vs_first"]["mean_absolute_rgb_0_255"] for r in per_frame),
              "max_mp4_protected_temporal_mae_0_255": max(r["mp4_protected_vs_first_decoded"]["mean_absolute_rgb_0_255"] for r in per_frame),
              "current_compositor_sha256": sha256((ROOT / "last_light_radio/motion_jobs.py").read_bytes()),
              "frames": per_frame,
              "notes": ["Replay uses every verified original generated PNG through the current compositor; three actual saved lossless samples must match exactly.",
                        "Protected means effective feathered mask equals zero; the soft mask edge extends beyond the drawn polygon.",
                        "MP4 measurements are separate codec diagnostics, not a requirement for RGB equality or a visual quality score.",
                        "This audit never submits a render, approves a take, or modifies the source store."]}
    target.write_once("region-audit.json", canonical_bytes(report))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--store", default=".local/studio")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report = audit(args.store, args.job_id, args.output)
    print(json.dumps({key: report[key] for key in ("local_job_id", "raw_pngs_decoded", "lossless_composites_replayed",
          "max_lossless_protected_pixels_changed", "max_inside_temporal_mae_0_255", "max_mp4_protected_temporal_mae_0_255")}))


if __name__ == "__main__":
    main()
