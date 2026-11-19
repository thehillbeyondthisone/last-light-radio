"""Masked procedural ambience, evaluated at absolute episode frame numbers.

This is a new renderer using recovered masks, not recovered effect source code.
Character/prop footage remains the immutable base; ambience never feeds a hold.
"""

from __future__ import annotations

import io
import json
import math
import random

from PIL import Image, ImageChops, ImageDraw

from .store import sha256
from .studio import StudioError

VERSION = "masked-ambience-v3"
RAIN_V2 = "masked-ambience-v2"
LEGACY_VERSION = "masked-ambience-v1"


def catalog(studio):
    """Recover only masks belonging to a known canonical scene, from local copies."""
    result = []
    for library in studio.setting("legacy_imports", []):
        records = json.loads(studio.store.resolve(f"legacy/{library['id']}/database_records.json").read_text())
        assets = {a["id"]: a for a in records["assets"]}
        files = {a["sha256"]: a for a in library["files"]}
        for canonical in (a for a in assets.values() if a["kind"] == "canonical"):
            if not any(s["master_hash"] == canonical["sha256"] for s in studio.scenes()):
                continue
            layers = []
            for region in records["regions"]:
                if region["scene_id"] != canonical["scene_id"] or region["kind"] not in {"rain", "steam"}:
                    continue
                asset = assets[region["mask_asset_id"]]
                item = files.get(asset["sha256"])
                if not item:
                    raise StudioError("A recovered ambience mask is missing")
                layers.append({"kind": region["kind"], "label": "Window rain" if region["kind"] == "rain" else "Mug steam",
                               "mask": {"path": item["path"], "sha256": asset["sha256"]},
                               "opacity": 0.22 if region["kind"] == "rain" else 0.18,
                               "source_region_id": region["id"]})
            result.append({"scene_id": canonical["sha256"][:32], "layers": layers, "source_library_id": library["id"]})
    return result


def pin(studio, scene, clips, selected, seed):
    if selected is None or selected == []:
        return None
    if not isinstance(selected, list) or any(not isinstance(item, dict) for item in selected):
        raise StudioError("Choose rain or steam and an opacity between 0 and 0.4")
    recovered = next((c for c in catalog(studio) if c["scene_id"] == scene["id"]), None)
    available = {a["kind"]: a for a in recovered["layers"]} if recovered else {}
    seen, layers = set(), []
    size = (scene["width"], scene["height"])
    # Exclude every selected actor mask's nonzero support, including feathers.
    # This also protects moving poses from the full-frame actor clips.
    protected = Image.new("L", size)
    for clip in clips:
        studio.store.verify_master({"id": "actor-mask", **clip["mask"]})
        with Image.open(studio.store.resolve(clip["mask"]["path"])) as image:
            mask = image.convert("L")
        if mask.size != size:
            raise StudioError("Actor and ambience masks must use the full scene dimensions")
        protected = ImageChops.lighter(protected, mask.point(lambda value: 255 if value else 0))
    for requested in selected:
        kind, opacity = requested.get("kind"), requested.get("opacity")
        if not isinstance(kind, str) or kind not in available or kind in seen:
            raise StudioError("Choose each recovered ambience layer at most once")
        if type(opacity) not in {int, float} or not math.isfinite(opacity) or not 0 <= opacity <= 0.4:
            raise StudioError("Ambience opacity must be between 0 and 0.4")
        seen.add(kind)
        source = available[kind]
        studio.store.verify_master({"id": "ambience-mask", **source["mask"]})
        with Image.open(studio.store.resolve(source["mask"]["path"])) as image:
            mask = image.convert("L")
        if mask.size != size:
            raise StudioError("Ambience mask dimensions differ from this scene")
        if kind == "rain":
            mask = ImageChops.multiply(mask, ImageChops.invert(protected))
        bounds = mask.getbbox()
        if not bounds:
            raise StudioError(f"{source['label']} has no safe pixels after actor protection")
        data = io.BytesIO()
        mask.save(data, "PNG")
        digest = sha256(data.getvalue())
        path = f"exports/ambience-masks/{digest}.png"
        studio.store.write_once(path, data.getvalue())
        # Retain the v2 falling-rain bed and the original steam phase.
        rng = random.Random(f"{RAIN_V2 if kind == 'rain' else LEGACY_VERSION}:{seed}:{kind}")
        glass = None
        if kind == "rain":
            from .rain import populate
            particles, glass = populate(rng)
            from .wet_glass import upgrade
            glass = upgrade(glass, rng)
        else:
            particles = [{"x": rng.random(), "y": rng.random(), "speed": rng.uniform(0.10, 0.30),
                          "length": rng.uniform(0.008, 0.026), "alpha": rng.uniform(0.35, 1), "phase": rng.random() * math.tau}
                         for _ in range(3)]
        layers.append({"kind": kind, "label": source["label"], "opacity": opacity, "bounds": list(bounds),
                       "source_mask": source["mask"], "mask": {"path": path, "sha256": digest},
                       "particles": particles, "source_region_id": source["source_region_id"],
                       **({"glass": glass, "glass_model": "adhesion-release-v1"} if glass is not None else {})})
    return {"renderer_version": VERSION, "clock": "absolute_episode_frame", "seed": seed,
            "source_library_id": recovered["source_library_id"], "layers": layers,
            "character_protection": "rain excludes actor-mask support; steam uses recovered plume-only mask", "quality_status": "draft"}


def validate(store, recipe):
    if not recipe:
        return
    if recipe["renderer_version"] not in {VERSION, RAIN_V2, LEGACY_VERSION}:
        raise ValueError("This ambience renderer version is unavailable; preserve the plan and use its matching runtime")
    for layer in recipe["layers"]:
        if recipe["renderer_version"] == VERSION and layer["kind"] == "rain" and layer.get("glass_model") != "adhesion-release-v1":
            raise ValueError("This saved glass-motion model is unavailable")
        for name in ("mask", "source_mask"):
            store.verify_master({"id": "ambience-mask", **layer[name]})


def strokes(layer, seconds):
    """Legacy v1 stroke geometry, retained for saved recipes."""
    left, top, right, bottom = layer["bounds"]
    width, height = right - left, bottom - top
    if layer["kind"] == "rain":
        for p in layer["particles"]:
            x = left + p["x"] * width
            y = top + ((p["y"] + seconds * p["speed"]) % 1) * height
            length = p["length"] * height
            yield ((x - length * 0.06, y - length), (x, y), max(1, width / 850), p["alpha"], (186, 207, 220))


def steam_shift(layer, seconds, row):
    left, top, right, bottom = layer["bounds"]
    u = 1 - row / (bottom - top)
    phase = layer["particles"][0]["phase"]
    wave = math.sin(seconds * 0.85 - u * 5 + phase) + 0.35 * math.sin(seconds * 0.39 + u * 8 + phase)
    return math.floor((right - left) * 0.055 * layer["opacity"] / 0.18 * math.sin(math.pi * u) ** 1.2 * wave + 0.5)


class Compositor:
    def __init__(self, store, recipe, size, fps):
        validate(store, recipe)
        self.recipe, self.size, self.fps, self.layers = recipe, size, fps, []
        for layer in recipe["layers"] if recipe else []:
            with Image.open(store.resolve(layer["mask"]["path"])) as image:
                mask = image.convert("L")
            if mask.size != size:
                raise ValueError("Pinned ambience mask has the wrong dimensions")
            bounds = tuple(layer["bounds"])
            self.layers.append((layer, mask.crop(bounds), bounds))

    def apply(self, base, frame, *, disabled_kinds=()):
        if not self.layers:
            return base
        image = Image.frombytes("RGB", self.size, base)
        for layer, mask, bounds in self.layers:
            left, top, right, bottom = bounds
            if layer["opacity"] == 0 or layer["kind"] in disabled_kinds:
                continue
            if layer["kind"] == "steam":
                # The master already contains a painted plume. Move its own
                # pixels gently instead of drawing a second plume over it.
                patch = Image.new("RGB", (right - left, bottom - top))
                for row in range(bottom - top):
                    shift = steam_shift(layer, frame / self.fps, row)
                    patch.paste(image.crop((left + shift, top + row, right + shift, top + row + 1)), (0, row))
                image.paste(Image.composite(patch, image.crop(bounds), mask), bounds)
                continue
            if self.recipe["renderer_version"] in {VERSION, RAIN_V2}:
                from .rain import render
                base = image.crop(bounds)
                image.paste(Image.composite(render(base, layer, frame / self.fps), base, mask), bounds)
                continue
            alpha = Image.new("L", (right - left, bottom - top))
            draw = ImageDraw.Draw(alpha)
            color = (186, 207, 220)
            for start, end, width, strength, _ in strokes(layer, frame / self.fps):
                draw.line([(round(start[0] - left), round(start[1] - top)), (round(end[0] - left), round(end[1] - top))],
                          fill=round(255 * layer["opacity"] * strength), width=max(1, round(width)))
            alpha = ImageChops.multiply(alpha, mask)
            patch = Image.composite(Image.new("RGB", alpha.size, color), image.crop(bounds), alpha)
            image.paste(patch, bounds)
        return image.tobytes()
