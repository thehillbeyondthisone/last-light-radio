"""Sparse large drops with pinned adhesion/release curves and optical lenses.

Motion is sampled directly from episode time, including its recent trail. No
per-frame simulation state is kept, so seeking and out-of-order exports agree.
"""

import math

from PIL import Image, ImageDraw

from .rain import bead, glint

MODEL = "adhesion-release-v1"


def upgrade(glass, rng):
    for index, p in enumerate(glass[:26]):
        p["radius"] = rng.uniform(0.0065, 0.0105) if index < 10 else rng.uniform(0.0035, 0.006)
        # Tiny creep while surface tension pins a drop, followed by a gravity
        # release. Smooth interpolation accelerates and catches it again.
        keys, elapsed, distance = [[0, 0]], 0, 0
        weights = [rng.uniform(0.12, 0.28) for _ in range(6)]
        total = sum(weights)
        for weight in weights:
            elapsed += rng.uniform(0.7, 2.5)
            distance += 0.002
            keys.append([elapsed, distance])
            elapsed += rng.uniform(1.0, 2.1)
            distance += weight / total * 0.988
            keys.append([elapsed, distance])
        p["roll"] = {"keys": keys, "duration": elapsed, "offset": rng.uniform(0, elapsed),
                     "wander": rng.uniform(0.002, 0.005), "trail_seconds": rng.uniform(2.0, 3.6)}
    # Occasional heavier beads remain attached among the smaller droplets.
    for _ in range(8):
        glass.append({"x": rng.random(), "y": rng.random() * 1.2, "radius": rng.uniform(0.0038, 0.006),
                      "speed": 0, "trail": 0, "alpha": rng.uniform(0.6, 0.9), "phase": rng.random() * math.tau})
    return glass


def state(p, seconds, width, height):
    roll = p.get("roll")
    if not roll:
        x, y, rx, ry = bead(p, seconds, width, height)
        return x, y, rx, ry, 0, 0
    age = (seconds + roll["offset"]) % roll["duration"]
    keys = roll["keys"]
    for (t0, y0), (t1, y1) in zip(keys, keys[1:]):
        if age <= t1:
            u = (age - t0) / (t1 - t0)
            progress = y0 + (y1 - y0) * u * u * (3 - 2 * u)
            velocity = (y1 - y0) * 6 * u * (1 - u) / (t1 - t0)
            break
    stretch = min(0.9, velocity * 4)
    radius = max(0.8, p["radius"] * width)
    x = p["x"] * width + width * roll["wander"] * (math.sin(progress * 9 + p["phase"]) + 0.35 * math.sin(progress * 23 + p["phase"] * 1.7))
    return x, (progress * 1.24 - 0.12) * height, radius / (1 + stretch * 0.22), radius * (1.12 + stretch * 0.85), velocity, age


def outline(rx, ry):
    """Rounded lower head, narrower upper shoulder; shared with the canvas."""
    points = []
    for i in range(49):
        angle = i / 48 * math.tau
        vertical = math.sin(angle)
        taper = 0.82 + 0.18 * vertical
        points.append((math.cos(angle) * rx * taper, vertical * ry))
    return points


def render_glass(base, pane, layer, seconds):
    width, height = base.size
    pixels = base.load()
    trails = Image.new("RGBA", base.size)
    trail_draw = ImageDraw.Draw(trails)
    stamps = []
    for p in layer["glass"]:
        x, y, rx, ry, velocity, age = state(p, seconds, width, height)
        if x - rx < 0 or x + rx >= width or y - ry < 0 or y + ry >= height:
            continue
        color = glint(pixels[int(x), int(y)])
        opacity = min(1, layer["opacity"] / 0.22) * p["alpha"]
        if "roll" in p:
            last = (x, y)
            for index in range(1, 25):
                lag = index / 24 * p["roll"]["trail_seconds"]
                if lag > age:
                    break  # Never join the bottom of one cycle to the next.
                px, py, *_ = state(p, seconds - lag, width, height)
                if math.hypot(last[0] - px, last[1] - py) < 0.65:
                    continue
                fade = (1 - index / 25) ** 1.5
                trail_draw.line((*last, px, py), fill=(*color, round(42 * opacity * fade)), width=max(1, round(rx * 0.24)))
                last = (px, py)
        stamps.append((p, x, y, rx, ry, velocity, color, opacity))
    pane = Image.alpha_composite(pane.convert("RGBA"), trails).convert("RGB")
    for p, x, y, rx, ry, velocity, color, opacity in stamps:
        box = (math.floor(x - rx - 1), math.floor(y - ry - 1), math.ceil(x + rx + 1), math.ceil(y + ry + 1))
        bw, bh = box[2] - box[0], box[3] - box[1]
        cx, cy = x - box[0], y - box[1]
        shape = outline(rx, ry)
        mask = Image.new("L", (bw * 2, bh * 2))
        ImageDraw.Draw(mask).polygon([((cx + px) * 2, (cy + py) * 2) for px, py in shape], fill=round(210 * opacity))
        lens = Image.new("RGB", (bw, bh))
        # The magnification varies down the curved lens; larger drops bend
        # city detail rather than acting as an opaque colored sprite.
        for row in range(0, bh, 2):
            band = min(2, bh - row)
            v = (row + band / 2 - cy) / ry
            magnify = 0.58 + 0.13 * min(1, abs(v))
            sx = x - bw * magnify / 2 - rx * 0.28 * (1 - min(1, v * v))
            sy = y + (row - cy) * 0.7 + ry * 0.24
            patch = base.crop((math.floor(sx), math.floor(sy), math.ceil(sx + bw * magnify), math.ceil(sy + band * 0.7)))
            lens.paste(patch.resize((bw, band), Image.Resampling.BILINEAR), (0, row))
        pane.paste(lens, box, mask.resize((bw, bh), Image.Resampling.LANCZOS))
        light = Image.new("RGBA", (bw * 2, bh * 2))
        draw = ImageDraw.Draw(light)
        def arc(start, end, rgba, inset=1):
            points = []
            for index in range(18):
                a = (start + (end - start) * index / 17) * math.pi / 180
                v = math.sin(a)
                points.append(((cx + math.cos(a) * rx * (0.82 + 0.18 * v) * inset) * 2,
                               (cy + v * ry * inset) * 2))
            draw.line(points, fill=rgba, width=2)
        arc(10, 160, (8, 21, 30, round(125 * opacity)))
        arc(205, 282, (*color, round(180 * opacity)), 0.88)
        arc(47, 112, (*color, round(80 * opacity)), 0.65)
        if rx > 3:
            hx, hy = (cx - rx * 0.28) * 2, (cy - ry * 0.58) * 2
            draw.ellipse((hx - 1, hy - 1, hx + 1, hy + 1), fill=(230, 241, 242, round(205 * opacity)))
        pane.paste(Image.alpha_composite(pane.crop(box).convert("RGBA"), light.resize((bw, bh), Image.Resampling.LANCZOS)).convert("RGB"), box)
    return pane
