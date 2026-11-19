"""Seeded rain at three depths and small, optically shaded drops on glass.

All motion is an analytic function of episode time. No accumulated simulation
state, generated footage, scene coordinates, or new dependencies are required.
The caller applies the protected scene mask after refraction and drawing.
"""

import math

from PIL import Image, ImageDraw


def populate(rng):
    particles = []
    for depth, count in enumerate((420, 260, 120)):
        for _ in range(count):
            speed = rng.uniform(0.32, 0.56) * (1 + depth * 0.65)
            # Populate the padded wrap domain at t=0 as well; otherwise the
            # bottom/right margins start dry and fill during the first second.
            particles.append({"x": rng.random() * 1.16, "y": rng.random() * 1.2, "speed": speed,
                              "length": speed * rng.uniform(0.025, 0.045),
                              "alpha": rng.uniform(0.35, 0.85) * (0.48, 0.9, 1.5)[depth],
                              "phase": rng.random() * math.tau, "depth": depth})
    glass = []
    for index in range(112):
        runner = index < 26
        glass.append({"x": rng.random(), "y": rng.random() * 1.2,
                      "radius": rng.uniform(0.0025, 0.0052) if runner else rng.uniform(0.0009, 0.0032),
                      "speed": rng.uniform(0.012, 0.038) if runner else 0,
                      "trail": rng.uniform(0.025, 0.095) if runner else 0,
                      "alpha": rng.uniform(0.55, 1), "phase": rng.random() * math.tau})
    return particles, glass


def streak(p, seconds, width, height):
    """Local-pixel coordinates; particles wrap beyond the visible pane edges."""
    depth = p["depth"]
    wind = 0.055 * seconds + 0.045 * math.sin(seconds * 0.43) + 0.018 * math.sin(seconds * 0.91)
    x = ((p["x"] + wind * p["speed"] + 0.003 * math.sin(seconds * 0.7 + p["phase"])) % 1.16 - 0.08) * width
    y = ((p["y"] + seconds * p["speed"]) % 1.2 - 0.1) * height
    length = max(2, p["length"] * height)
    slant = 0.07 + 0.05 * math.sin(seconds * 0.43) + 0.03 * math.sin(seconds * 0.91)
    pulse = 0.78 + 0.22 * math.sin(seconds * 0.8 + p["phase"])
    return x, y, length * slant, length, max(0.65, width / 1027 * (0.7, 1.05, 1.65)[depth]), p["alpha"] * pulse


def bead(p, seconds, width, height):
    progress = p["y"] + seconds * p["speed"]
    if p["speed"]:
        progress += 0.002 * math.sin(seconds * 1.3 + p["phase"])
    y = (progress % 1.2 - 0.1) * height
    x = p["x"] * width + width * 0.0008 * math.sin(y / height * 18 + p["phase"])
    radius = max(0.8, p["radius"] * width)
    return x, y, radius, radius * (1.5 if p["speed"] else 1.18)


def glint(pixel):
    # Water catches the light already present behind it, including warm neon.
    r, g, b = pixel
    return (242, 210, 162) if r > g * 1.18 and r > b * 0.95 else (167, 202, 224)


def render(base, layer, seconds):
    """Return an unmasked RGB pane. The base image never receives feedback."""
    width, height = base.size
    strength = layer["opacity"]
    if not strength:
        return base
    scale = 2
    # Supersampling gives subpixel motion without thick, jagged white lines.
    rain = Image.new("RGBA", (width * scale, height * scale))
    draw = ImageDraw.Draw(rain)
    pixels = base.load()
    for p in layer["particles"]:
        x, y, dx, dy, thickness, alpha = streak(p, seconds, width, height)
        if x < -8 or x > width + 8 or y < 0 or y - dy > height:
            continue
        color = glint(pixels[min(width - 1, max(0, int(x))), min(height - 1, max(0, int(y)))])
        for segment, fade in enumerate((0.10, 0.28, 0.58, 1.0)):
            a, b = segment / 4, (segment + 1) / 4
            draw.line(((round((x - dx * (1 - a)) * scale), round((y - dy * (1 - a)) * scale)),
                       (round((x - dx * (1 - b)) * scale), round((y - dy * (1 - b)) * scale))),
                      fill=(*color, round(255 * strength * alpha * fade)), width=max(1, round(thickness * scale)))
    rain = rain.resize(base.size, Image.Resampling.LANCZOS)
    pane = Image.alpha_composite(base.convert("RGBA"), rain).convert("RGB")
    if layer.get("glass_model") == "adhesion-release-v1":
        from .wet_glass import render_glass
        return render_glass(base, pane, layer, seconds)
    # Tiny local lenses: magnified and offset source, dark lower rim, cool/warm
    # upper glint. Only the droplets bend the view; the city stays anchored.
    shading = Image.new("RGBA", base.size)
    shade = ImageDraw.Draw(shading)
    for p in layer["glass"]:
        x, y, rx, ry = bead(p, seconds, width, height)
        if x - rx < 0 or x + rx >= width or y - ry < 0 or y + ry >= height:
            continue
        color = glint(pixels[int(x), int(y)])
        opacity = min(1, strength / 0.22) * p["alpha"]
        if p["trail"]:
            length = p["trail"] * height
            for segment in range(8):
                a, b = segment / 8, (segment + 1) / 8
                ya, yb = y - length * (1 - a), y - length * (1 - b)
                xa = x + width * 0.0008 * (math.sin(ya / height * 18 + p["phase"]) - math.sin(y / height * 18 + p["phase"]))
                xb = x + width * 0.0008 * (math.sin(yb / height * 18 + p["phase"]) - math.sin(y / height * 18 + p["phase"]))
                shade.line((xa, ya, xb, yb), fill=(*color, round(20 * opacity * b)), width=max(1, round(rx * 0.45)))
        box = (math.floor(x - rx), math.floor(y - ry), math.ceil(x + rx), math.ceil(y + ry))
        bw, bh = box[2] - box[0], box[3] - box[1]
        lens = base.crop((x - rx * 0.65 - rx * 0.5, y - ry * 0.65 + ry * 0.3,
                          x + rx * 0.65 - rx * 0.5, y + ry * 0.65 + ry * 0.3)).resize((bw, bh), Image.Resampling.BILINEAR)
        lens_mask = Image.new("L", (bw * 2, bh * 2))
        ImageDraw.Draw(lens_mask).ellipse((0, 0, bw * 2 - 1, bh * 2 - 1), fill=round(160 * opacity))
        pane.paste(lens, box, lens_mask.resize((bw, bh), Image.Resampling.LANCZOS))
        shade.arc((x - rx, y - ry, x + rx, y + ry), 20, 155, fill=(9, 25, 36, round(95 * opacity)), width=1)
        shade.arc((x - rx * 0.75, y - ry * 0.85, x + rx * 0.75, y + ry * 0.6), 205, 285,
                  fill=(*color, round(150 * opacity)), width=1)
        if rx > 2:
            shade.point((round(x - rx * 0.3), round(y - ry * 0.5)), fill=(225, 237, 237, round(190 * opacity)))
    return Image.alpha_composite(pane.convert("RGBA"), shading).convert("RGB")
