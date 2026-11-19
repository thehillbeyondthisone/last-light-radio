import copy
import io
import http.client
import json
import math
import random
import unittest
import threading
from unittest.mock import patch

from PIL import Image, ImageChops

import test_pilots as fixtures
from last_light_radio import ambience, pilots
from last_light_radio.store import sha256
from last_light_radio.studio import StudioError
from last_light_radio.server import make_server


class AmbienceTests(unittest.TestCase):
    def setUp(self):
        fixtures.PilotTests.setUp(self)
        layers = []
        for kind in ("rain", "steam"):
            mask = Image.new("L", (64, 48), 255 if kind == "rain" else 0)
            if kind == "steam":
                mask.paste(255, (38, 4, 58, 28))
            data = io.BytesIO()
            mask.save(data, "PNG")
            relative = f"effect-{kind}.png"
            self.studio.store.write_once(relative, data.getvalue())
            layers.append({"kind": kind, "label": kind.title(), "mask": {"path": relative, "sha256": sha256(data.getvalue())},
                           "source_region_id": len(layers) + 1, "opacity": 0.18})
        self.catalog = [{"scene_id": self.scene["id"], "layers": layers, "source_library_id": "fixture"}]
        self.selected = [{"kind": "rain", "opacity": 0.12}, {"kind": "steam", "opacity": 0.18}]
        self.catalog_patch = patch("last_light_radio.ambience.catalog", return_value=self.catalog)
        self.catalog_patch.start()
        self.addCleanup(self.catalog_patch.stop)

    def plan(self):
        return pilots.plan(self.studio, {**self.payload, "ambience": self.selected}, duration_seconds=20)

    def test_recipe_is_pinned_seeded_and_does_not_change_original_plan(self):
        plain = pilots.plan(self.studio, self.payload, duration_seconds=20)
        a, b = self.plan(), self.plan()
        self.assertEqual(a["id"], b["id"])
        self.assertNotEqual(a["id"], plain["id"])
        self.assertEqual(a["manifest"]["events"], plain["manifest"]["events"])
        self.assertEqual(a["manifest"]["ambience"]["clock"], "absolute_episode_frame")
        changed = pilots.plan(self.studio, {**self.payload, "seed": 8, "ambience": self.selected}, duration_seconds=20)
        self.assertNotEqual(a["manifest"]["ambience"], changed["manifest"]["ambience"])
        self.assertEqual(len(self.studio.approved_library()), 1)
        self.assertEqual(self.studio.jobs(), [])

    def test_effects_preserve_protected_pixels_and_are_independent_of_call_order(self):
        recipe = self.plan()["manifest"]["ambience"]
        compositor = ambience.Compositor(self.studio.store, recipe, (64, 48), 24)
        image = Image.new("RGB", (64, 48))
        image.putdata([(x * 3, y * 4, (x + y) * 2) for y in range(48) for x in range(64)])
        base = image.tobytes()
        a = compositor.apply(base, 301)
        compositor.apply(base, 0)
        self.assertEqual(a, compositor.apply(base, 301))
        self.assertNotEqual(a, compositor.apply(base, 351))
        allowed = Image.new("L", (64, 48))
        for layer in recipe["layers"]:
            mask = Image.open(self.studio.store.resolve(layer["mask"]["path"])).convert("L")
            allowed = ImageChops.lighter(allowed, mask)
        delta = ImageChops.difference(image, Image.frombytes("RGB", (64, 48), a))
        self.assertIsNone(Image.composite(Image.new("RGB", image.size), delta, allowed.point(lambda v: 255 if v else 0)).getbbox())
        self.assertIsNone(delta.crop((10, 10, 30, 35)).getbbox())
        rain = next(layer for layer in recipe["layers"] if layer["kind"] == "rain")
        self.assertEqual(Image.open(self.studio.store.resolve(rain["mask"]["path"])).getpixel((20, 20)), 0)

    def test_invalid_unsupported_or_tampered_ambience_fails_visibly(self):
        for selected in ({}, [{"kind": "unknown", "opacity": 0.1}], [{"kind": "rain", "opacity": True}],
                         [{"kind": "rain", "opacity": 0.41}], self.selected * 2):
            with self.subTest(selected=selected), self.assertRaises(StudioError):
                pilots.plan(self.studio, {**self.payload, "ambience": selected}, duration_seconds=20)
        p = self.plan()
        layer = p["manifest"]["ambience"]["layers"][0]
        self.studio.store.resolve(layer["mask"]["path"]).write_bytes(b"changed")
        with self.assertRaises(ValueError):
            pilots.queue_export(self.studio, p["id"])

    def test_zero_strength_preserves_source_and_unknown_renderer_is_rejected(self):
        recipe = copy.deepcopy(self.plan()["manifest"]["ambience"])
        for layer in recipe["layers"]:
            layer["opacity"] = 0
        base = self.master.tobytes()
        self.assertEqual(ambience.Compositor(self.studio.store, recipe, (64, 48), 24).apply(base, 180), base)
        recipe["renderer_version"] = "missing"
        with self.assertRaises(ValueError):
            ambience.Compositor(self.studio.store, recipe, (64, 48), 24)

    def test_v3_pins_depths_rolling_glass_and_the_original_steam_phase(self):
        recipe = self.plan()["manifest"]["ambience"]
        self.assertEqual(recipe["renderer_version"], "masked-ambience-v3")
        rain, steam = recipe["layers"]
        self.assertEqual({p["depth"] for p in rain["particles"]}, {0, 1, 2})
        self.assertTrue(any(p["x"] > 1 for p in rain["particles"]))
        self.assertTrue(any(p["y"] > 1 for p in rain["particles"]))
        self.assertTrue(any(p["speed"] == 0 for p in rain["glass"]))
        self.assertTrue(any(p["speed"] > 0 and p["trail"] > 0 for p in rain["glass"]))
        self.assertEqual(rain["glass_model"], "adhesion-release-v1")
        self.assertTrue(any(p["radius"] > 0.009 and "roll" in p for p in rain["glass"]))
        rng = random.Random(f"masked-ambience-v1:{recipe['seed']}:steam")
        for _ in range(5):
            rng.random()
        self.assertEqual(steam["particles"][0]["phase"], rng.random() * math.tau)

    def test_saved_v2_rain_pixels_are_unchanged(self):
        from last_light_radio.rain import populate, render
        particles, glass = populate(random.Random("legacy-v2-fixture"))
        base = Image.new("RGB", (128, 96))
        base.putdata([(x * 2, y * 2, (x * 11 + y * 7) % 256) for y in range(96) for x in range(128)])
        result = render(base, {"opacity": 0.22, "particles": particles, "glass": glass}, 12)
        self.assertEqual(sha256(result.tobytes()), "ab1edb0635f636156079d25b17d7f1131fd771d5589a22b4668363a6b994939e")

    def test_rolling_drops_pause_accelerate_stretch_and_follow_monotone_paths(self):
        from last_light_radio.wet_glass import state
        layer = self.plan()["manifest"]["ambience"]["layers"][0]
        p = next(p for p in layer["glass"] if "roll" in p)
        roll = p["roll"]
        samples = [state(p, age - roll["offset"], 1027, 933) for age in (0.1 + i * 0.04 for i in range(int((roll["duration"] - 0.2) / 0.04)))]
        self.assertTrue(all(b[1] >= a[1] for a, b in zip(samples, samples[1:])))
        self.assertGreater(max(s[4] for s in samples), min(s[4] for s in samples) * 40)
        self.assertGreater(max(s[3] / s[2] for s in samples), min(s[3] / s[2] for s in samples) * 1.3)
        self.assertGreater(max(s[0] for s in samples) - min(s[0] for s in samples), 1)
        self.assertLess(state(p, -roll["offset"], 1027, 933)[1], 0)
        self.assertGreater(state(p, roll["duration"] - roll["offset"] - 0.0001, 1027, 933)[1], 933)

    def test_v3_unknown_glass_model_fails_visibly(self):
        recipe = copy.deepcopy(self.plan()["manifest"]["ambience"])
        recipe["layers"][0]["glass_model"] = "missing"
        with self.assertRaisesRegex(ValueError, "glass-motion"):
            ambience.Compositor(self.studio.store, recipe, (64, 48), 24)

    def test_saved_v1_renders_identically_without_v2_glass(self):
        recipe = copy.deepcopy(self.plan()["manifest"]["ambience"])
        recipe["renderer_version"] = "masked-ambience-v1"
        recipe["layers"] = [recipe["layers"][0]]
        layer = recipe["layers"][0]
        layer.pop("glass")
        layer["particles"] = [{"x": 0.75, "y": 0.5, "speed": 0.2, "length": 0.2, "alpha": 1, "phase": 0}]
        compositor = ambience.Compositor(self.studio.store, recipe, (64, 48), 24)
        base = Image.new("RGB", (64, 48), (20, 30, 40))
        rendered = Image.frombytes("RGB", base.size, compositor.apply(base.tobytes(), 0))
        self.assertEqual(rendered.getpixel((48, 24)), (40, 52, 62))
        self.assertEqual(rendered.getpixel((40, 24)), (20, 30, 40))
        self.assertEqual(rendered.tobytes(), compositor.apply(base.tobytes(), 0))

    def test_glass_refracts_existing_pixels_and_replays_after_seeking(self):
        from last_light_radio.rain import render
        base = Image.new("RGB", (128, 96))
        base.putdata([(x * 2, y * 2, (x * 11 + y * 7) % 256) for y in range(96) for x in range(128)])
        layer = {"opacity": 0.22, "particles": [], "glass": [
            {"x": 0.5, "y": 0.5, "radius": 0.05, "speed": 0.02, "trail": 0.12, "alpha": 1, "phase": 0}]}
        first = render(base, layer, 12)
        self.assertNotEqual(first.tobytes(), base.tobytes())
        self.assertIsNone(ImageChops.difference(base, first).crop((0, 0, 40, 96)).getbbox())
        render(base, layer, 600)
        self.assertEqual(first.tobytes(), render(base, layer, 12).tobytes())
        self.assertNotEqual(first.tobytes(), render(base, layer, 13).tobytes())

    def test_cpu_export_keeps_unmodified_base_holds_and_continuous_effect_clock(self):
        p = self.plan()
        pilots.queue_export(self.studio, p["id"])
        pilots.process_export(self.studio, p["id"])
        complete = pilots.get(self.studio, p["id"])
        self.assertEqual(complete["status"], "complete", complete["error"])
        folder = f"exports/pilots/{p['id']}"
        report = json.loads(self.studio.store.resolve(f"{folder}/export_report.json").read_text())
        self.assertEqual(report["ambience"]["clock"], "absolute_episode_frame")
        self.assertEqual(report["ambience"]["layers"], ["rain", "steam"])
        self.assertTrue(all(c["matches_current_rgb"] for c in report["hold_checks"]))
        self.assertEqual(report["inspection"]["frame_count"], 480)
        self.assertEqual(pilots.ambience_media(self.studio, p["id"], "rain").suffix, ".png")
        with self.assertRaises(StudioError):
            pilots.ambience_media(self.studio, p["id"], "other")

    def test_loopback_serves_only_a_registered_pilot_mask(self):
        p = self.plan()
        server = make_server(self.studio, 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=15)
        self.addCleanup(connection.close)
        connection.request("GET", f"/api/pilots/{p['id']}/ambience/rain")
        response = connection.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(response.read(), pilots.ambience_media(self.studio, p["id"], "rain").read_bytes())
        connection.request("GET", f"/api/pilots/{p['id']}/ambience/unknown")
        response = connection.getresponse()
        self.assertEqual(response.status, 404)
        response.read()


if __name__ == "__main__":
    unittest.main()
