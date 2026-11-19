"""Nested display groups preserve source events and explicit action gaps."""

import json
from pathlib import Path
import shutil
import subprocess
import unittest


class NestedSequenceTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Nested frontend checks require Node")
    def test_beds_preserve_every_source_event_and_split_at_actions(self):
        module = (Path(__file__).resolve().parents[1] / "frontend/src/nestedSequences.ts").as_uri()
        events = [{"index": 0, "origin": "idle", "start_frame": 0, "end_frame": 124, "label": "Reading Idle A"},
                  {"index": 1, "origin": "hold", "start_frame": 124, "end_frame": 140, "label": "Hold"},
                  {"index": 2, "origin": "motion", "start_frame": 140, "end_frame": 264, "label": "Page turn"},
                  {"index": 3, "origin": "idle", "start_frame": 264, "end_frame": 388, "label": "Reading Idle B"},
                  {"index": 4, "origin": "hold", "start_frame": 388, "end_frame": 400, "label": "Hold"}]
        program = """const m=await import(process.argv[1]);const events=JSON.parse(process.argv[2]);
const before=JSON.stringify(events);const beds=m.idleBeds('Reader',events);
console.log(JSON.stringify({beds,unchanged:before===JSON.stringify(events)}));"""
        result = subprocess.run([shutil.which("node"), "--input-type=module", "-e", program, module, json.dumps(events)],
                                capture_output=True, text=True, check=True, timeout=15)
        actual = json.loads(result.stdout)
        self.assertTrue(actual["unchanged"])
        self.assertEqual([(b["start_frame"], b["end_frame"]) for b in actual["beds"]], [(0, 140), (264, 400)])
        self.assertEqual([e for bed in actual["beds"] for e in bed["events"]], [e for e in events if e["origin"] != "motion"])
