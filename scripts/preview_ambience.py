"""Render a short, separate preview from a pinned pilot; no AI or review writes."""

import argparse
import copy
import json
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from last_light_radio import pilots
from last_light_radio.pilot_media import encode_pilot, inspect_video
from last_light_radio.store import canonical_bytes, sha256
from last_light_radio.studio import Studio


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot-id", required=True)
    parser.add_argument("--store", default=".local/studio")
    parser.add_argument("--seconds", type=int, default=24)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 60:
        parser.error("Preview duration must be between 1 and 60 seconds")
    if args.output.exists():
        parser.error("Choose a new output folder; existing evidence is preserved")
    studio = Studio(args.store)
    source = pilots.get(studio, args.pilot_id)["manifest"]
    pilots.validate_approvals(studio, source)
    manifest = copy.deepcopy(source)
    end = args.seconds * manifest["fps"]
    if any(e["kind"] == "clip" and e["start_frame"] < end < e["end_frame"] for e in manifest["events"]):
        parser.error("Preview would truncate a motion clip; choose a duration ending in a hold")
    manifest["events"] = [e for e in manifest["events"] if e["start_frame"] < end]
    manifest["events"][-1]["end_frame"] = end
    manifest.update({"kind": "short_ambience_preview", "duration_frames": end,
                     "source_pilot_id": args.pilot_id, "source_manifest_hash": source["manifest_hash"]})
    del manifest["manifest_hash"]
    manifest["manifest_hash"] = sha256(canonical_bytes(manifest))
    args.output.mkdir(parents=True)
    movie = args.output / "ambience-preview.mp4"
    report = encode_pilot(studio.store, manifest, movie, threading.Event(), lambda value: None)
    size = (manifest["width"] + manifest["width"] % 2, manifest["height"] + manifest["height"] % 2)
    report["inspection"] = inspect_video(movie, end, manifest["fps"], size)
    pilots.validate_approvals(studio, source)
    report.update({"manifest_hash": manifest["manifest_hash"], "sha256": sha256(movie.read_bytes()), "bytes": movie.stat().st_size})
    (args.output / "preview_manifest.json").write_bytes(canonical_bytes(manifest))
    (args.output / "preview_report.json").write_bytes(canonical_bytes(report))
    print(json.dumps({"path": str(movie.resolve()), "report": report["inspection"], "bytes": report["bytes"]}))


if __name__ == "__main__":
    main()
