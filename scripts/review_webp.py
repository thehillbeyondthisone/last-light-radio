"""Optional Pillow QA: decode every frame and save a head/middle/tail contact sheet.

Pillow is only required for this review helper, not for scheduling or generation.
It is available in the Codex bundled Python runtime used for the live smoke test.
"""

import argparse
import io
import json
import sys
from pathlib import Path

# Make the source checkout importable when invoked as python scripts/review_webp.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from last_light_radio.media import inspect_webp
from last_light_radio.store import ProjectStore, canonical_bytes, sha256


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path)
    args = parser.parse_args()
    try:
        from PIL import Image, ImageChops, ImageDraw, ImageStat
    except ImportError:
        parser.error("This optional QA helper needs Pillow; the core app does not")
    data = args.candidate.read_bytes()
    properties = inspect_webp(data)
    selected = {}
    durations = []
    with Image.open(io.BytesIO(data)) as image:
        if image.format != "WEBP" or not image.is_animated:
            raise ValueError("Expected a decodable animated WebP")
        indices = {0, image.n_frames // 2, image.n_frames - 1}
        for index in range(image.n_frames):
            image.seek(index)
            image.load()
            durations.append(image.info.get("duration", 0))
            if index in indices:
                selected[index] = image.convert("RGB").copy()
        size = image.size
    if (len(durations) != properties["frame_count"] or sum(durations) != properties["duration_ms"]
            or size != (properties["width"], properties["height"])):
        raise ValueError("Pixel decoder and container metadata disagree")
    store = ProjectStore(args.candidate.resolve().parent, create=False)
    width, height = size
    sheet = Image.new("RGB", (3 * width, height + 32), "#101b20")
    draw = ImageDraw.Draw(sheet)
    for column, (index, frame) in enumerate(sorted(selected.items())):
        sheet.paste(frame, (column * width, 32))
        draw.text((column * width + 12, 10), f"Frame {index + 1} / {len(durations)}", fill="#f5dfb0")
        output = io.BytesIO()
        frame.save(output, format="PNG")
        store.write_once(f"review/frame-{index:04d}.png", output.getvalue())
    output = io.BytesIO()
    sheet.save(output, format="PNG")
    sheet_path = store.write_once("review/contact_sheet.png", output.getvalue())
    first, last = selected[0], selected[len(durations) - 1]
    difference = ImageStat.Stat(ImageChops.difference(first, last)).mean
    review = {"candidate_sha256": sha256(data), "pixel_decode_verified": True,
              "decoded_frame_count": len(durations), "duration_ms": sum(durations),
              "effective_fps": len(durations) * 1000 / sum(durations),
              "width": width, "height": height,
              "head_tail_mean_absolute_difference_rgb_0_255": difference,
              "creator_approval": False, "quality_review": "requires_creator_review",
              "note": "Pixel decoding and simple differences do not establish loop or identity quality"}
    store.write_once("review/validation.json", canonical_bytes(review))
    print(json.dumps({**review, "contact_sheet": str(sheet_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
