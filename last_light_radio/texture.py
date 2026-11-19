"""Seeded full-picture video grain, applied after scene motion and ambience."""

import math

from PIL import Image, ImageChops

from .studio import StudioError

VERSION = "video-texture-v1"
TILE = 256
MASK = 0xFFFFFFFF


def settings(value):
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {"enabled", "strength", "size", "seed"}:
        raise StudioError("Choose texture on/off, strength, grain size and pattern seed")
    enabled, strength, size, seed = (value[k] for k in ("enabled", "strength", "size", "seed"))
    if type(enabled) is not bool:
        raise StudioError("Texture on/off must be a boolean")
    if type(strength) not in {int, float} or not math.isfinite(strength) or not 0 <= strength <= 1:
        raise StudioError("Texture strength must be between 0 and 100 percent")
    if type(size) is not int or not 1 <= size <= 8:
        raise StudioError("Grain size must be a whole number from 1 to 8 pixels")
    if type(seed) is not int or not 0 <= seed <= 2147483647:
        raise StudioError("Texture pattern seed must be a whole number from 0 to 2147483647")
    return {"enabled": enabled, "strength": strength, "size": size, "seed": seed}


def pin(value):
    value = settings(value)
    if not value or not value["enabled"] or value["strength"] == 0:
        return None
    return {"renderer_version": VERSION, "clock": "absolute_episode_frame", "blend": "overlay",
            "tile_size": TILE, **value}


def mix(value):
    value &= MASK
    value = ((value ^ (value >> 16)) * 0x7FEB352D) & MASK
    value = ((value ^ (value >> 15)) * 0x846CA68B) & MASK
    return (value ^ (value >> 16)) & MASK


def offset(seed, frame):
    value = seed ^ (((frame + 1) * 0x9E3779B9) & MASK)
    return mix(value) % TILE, mix(value ^ 0xA5A5A5A5) % TILE


def tile(seed):
    state = (seed ^ 0x9E3779B9) & MASK
    values = bytearray(TILE * TILE)
    for index in range(len(values)):
        state ^= (state << 13) & MASK
        state ^= state >> 17
        state ^= (state << 5) & MASK
        state &= MASK
        values[index] = ((state & 255) + ((state >> 8) & 255) + ((state >> 16) & 255)) // 3
    return Image.frombytes("L", (TILE, TILE), bytes(values))


class Compositor:
    def __init__(self, recipe, size):
        self.recipe, self.size = recipe, size
        if not recipe:
            return
        value = settings({key: recipe.get(key) for key in ("enabled", "strength", "size", "seed")})
        if recipe != pin(value):
            raise ValueError("The pinned video texture renderer or parameters are unavailable")
        self.tile = tile(value["seed"])
        self.period = TILE * value["size"]
        self.tiled = Image.new("L", (size[0] + self.period, size[1] + self.period))
        grain = self.tile.resize((self.period, self.period), Image.Resampling.NEAREST)
        for y in range(0, self.tiled.height, self.period):
            for x in range(0, self.tiled.width, self.period):
                self.tiled.paste(grain, (x, y))

    def apply(self, base, frame):
        if not self.recipe:
            return base
        if type(frame) is not int or frame < 0:
            raise ValueError("Texture requires a nonnegative episode frame")
        x, y = offset(self.recipe["seed"], frame)
        x *= self.recipe["size"]
        y *= self.recipe["size"]
        grain = self.tiled.crop((x, y, x + self.size[0], y + self.size[1])).convert("RGB")
        image = Image.frombytes("RGB", self.size, base)
        return Image.blend(image, ImageChops.overlay(image, grain), self.recipe["strength"]).tobytes()
