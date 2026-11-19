"""Replay a saved short ambience preview and audit protected pixels, read-only."""

import argparse
import json
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image, ImageChops

from last_light_radio import pilots
from last_light_radio.ambience import Compositor
from last_light_radio.pilot_media import rgb, video_rgb
from last_light_radio.store import canonical_bytes, sha256
from last_light_radio.studio import Studio


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", default=".local/studio")
    parser.add_argument("--preview-folder", type=Path, required=True)
    args = parser.parse_args()
    output = args.preview_folder / "protected-pixel-audit.json"
    if output.exists():
        parser.error("The audit already exists; preserve it or choose a new preview folder")
    manifest = json.loads((args.preview_folder / "preview_manifest.json").read_text())
    report = json.loads((args.preview_folder / "preview_report.json").read_text())
    movie = args.preview_folder / "ambience-preview.mp4"
    assert sha256(movie.read_bytes()) == report["sha256"], "Published preview hash changed"
    studio = Studio(args.store)
    pilots.validate_approvals(studio, manifest)
    size = (manifest["width"], manifest["height"])
    compositor = Compositor(studio.store, manifest["ambience"], size, manifest["fps"])
    allowed = Image.new("L", size)
    masks = {}
    for layer in manifest["ambience"]["layers"]:
        with Image.open(studio.store.resolve(layer["mask"]["path"])) as image:
            masks[layer["kind"]] = image.convert("L").point(lambda value: 255 if value else 0)
        allowed = ImageChops.lighter(allowed, masks[layer["kind"]])
    protected = ImageChops.invert(allowed).convert("RGB")
    protected_pixels = allowed.histogram()[0]
    activity = {kind: 0 for kind in masks}
    clips = {clip["id"]: clip for clip in manifest["clips"]}
    current = rgb(studio.store, manifest["master"]).tobytes()
    count, previous = 0, None
    contact = Image.new("RGB", (960, 570), "#18251f")
    sample_indices = [0, 120, 287, 288, 411, manifest["duration_frames"] - 1]
    for event in manifest["events"]:
        frames = video_rgb(studio.store, clips[event["variant_id"]]["output"], size, threading.Event()) if event["kind"] == "clip" else (current for _ in range(event["end_frame"] - event["start_frame"]))
        try:
            for base in frames:
                changed = compositor.apply(base, count)
                image = Image.frombytes("RGB", size, changed)
                delta = ImageChops.difference(Image.frombytes("RGB", size, base), image)
                assert ImageChops.multiply(delta, protected).getbbox() is None, f"Protected pixel changed at {count}"
                if event["kind"] == "hold" and previous is not None:
                    temporal = ImageChops.difference(previous, image)
                    for kind, mask in masks.items():
                        if ImageChops.multiply(temporal, mask.convert("RGB")).getbbox():
                            activity[kind] += 1
                if count in sample_indices:
                    tile = image.copy()
                    tile.thumbnail((320, 180))
                    index = sample_indices.index(count)
                    contact.paste(tile, (index % 3 * 320, index // 3 * 285))
                    crop = image.crop((780, 620, 980, 830)).resize((100, 105))
                    contact.paste(crop, (index % 3 * 320, index // 3 * 285 + 180))
                previous, current = image, base
                count += 1
        finally:
            frames.close()
    assert count == manifest["duration_frames"]
    assert all(value > 0 for value in activity.values()), "An effect froze throughout the holds"
    contact.save(args.preview_folder / "boundary-contact-sheet.png")
    result = {"source_pilot_id": manifest["source_pilot_id"], "preview_sha256": report["sha256"], "frames_replayed": count,
              "protected_pixels_per_frame": protected_pixels, "changed_protected_pixels": 0,
              "hold_frame_pairs_with_effect_motion": activity, "clock": "absolute_episode_frame",
              "note": "Exact RGB audit is before lossy H.264 encoding. The published MP4 separately passed full decoding and timestamp validation.",
              "approved_clips": len(studio.approved_library()), "pending_candidates": sum(c["status"] == "candidate" for c in studio.candidates()), "generation_jobs": len(studio.jobs())}
    output.write_bytes(canonical_bytes(result))
    print(json.dumps(result))


if __name__ == "__main__":
    main()
