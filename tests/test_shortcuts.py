"""Editor keyboard layout: FCP7 defaults, remapping, saved files and timecode entry."""

import json
from pathlib import Path
import shutil
import subprocess
import unittest

MODULE = (Path(__file__).resolve().parents[1] / "frontend/src/shortcuts.ts").as_uri()


def run(program: str):
    result = subprocess.run([shutil.which("node"), "--input-type=module", "-e",
                             f"const m=await import(process.argv[1]);const out=(()=>{{{program}}})();console.log(JSON.stringify(out));", MODULE],
                            capture_output=True, text=True, check=True, timeout=15)
    return json.loads(result.stdout)


@unittest.skipUnless(shutil.which("node"), "Keyboard layout checks require Node")
class ShortcutTests(unittest.TestCase):
    def test_fcp7_defaults_are_unique_valid_and_cover_core_commands(self):
        actual = run("""const d=m.defaultKeymap();const all=Object.values(d).flat();
            return {all, unique:new Set(all).size, valid:all.every(k=>m.normalizeChord(k)===k), ids:m.COMMANDS.map(c=>c.id),
                    unassignable:all.filter(k=>m.UNASSIGNABLE.has(k)||m.BROWSER_RESERVED.has(k)), d}""")
        self.assertEqual(len(actual["all"]), actual["unique"])
        self.assertTrue(actual["valid"])
        self.assertEqual(actual["unassignable"], [])
        self.assertEqual(len(actual["ids"]), len(set(actual["ids"])))
        d = actual["d"]
        expected = {"play.toggle": ["Space"], "play.reverse": ["J"], "play.stop": ["K"], "play.forward": ["L"],
                    "mark.in": ["I"], "mark.out": ["O"], "mark.add": ["M"], "mark.clip": ["X"],
                    "nav.prevEdit": ["Up"], "nav.nextEdit": ["Down"], "nav.matchFrame": ["F"],
                    "edit.overwrite": ["F10"], "edit.undo": ["Ctrl+Z"], "timeline.fit": ["Shift+Z"],
                    "window.viewer": ["Ctrl+1"], "window.canvas": ["Ctrl+2"], "window.timeline": ["Ctrl+3"], "window.browser": ["Ctrl+4"]}
        for command, keys in expected.items():
            self.assertEqual(d[command], keys, command)

    def test_events_map_to_physical_keys_with_modifiers(self):
        actual = run("""const e=(code,key,mods={})=>m.chordFromEvent({code,key,ctrlKey:false,altKey:false,shiftKey:false,metaKey:false,...mods});
            return [e('KeyJ','j'), e('KeyZ','Z',{ctrlKey:true,shiftKey:true}), e('KeyZ','z',{metaKey:true}), e('Comma','<',{shiftKey:true}),
                    e('Space',' '), e('ArrowLeft','ArrowLeft',{shiftKey:true}), e('ShiftLeft','Shift',{shiftKey:true}), e('Numpad4','4'),
                    e('KeyQ','a'), e('Backquote','`',{ctrlKey:true}), e('F10','F10')]""")
        self.assertEqual(actual, ["J", "Ctrl+Shift+Z", "Ctrl+Z", "Shift+,", "Space", "Shift+Left", None, "Num4", "Q", "Ctrl+`", "F10"])

    def test_assigning_moves_a_key_and_reset_restores_the_default(self):
        actual = run("""let k=m.defaultKeymap();k=m.assignChord(k,'play.toggle','L');const moved={toggle:k['play.toggle'],forward:k['play.forward']};
            k=m.resetCommand(k,'play.forward');const reset={toggle:k['play.toggle'],forward:k['play.forward']};
            let refused=false;try{m.assignChord(k,'play.toggle','Esc')}catch{refused=true}
            return {moved,reset,refused,changed:m.changedCommands(k)}""")
        self.assertEqual(actual["moved"], {"toggle": ["Space", "L"], "forward": []})
        self.assertEqual(actual["reset"], {"toggle": ["Space"], "forward": ["L"]})
        self.assertTrue(actual["refused"])
        self.assertEqual(actual["changed"], [])

    def test_saved_layout_round_trips_and_overrides_take_their_keys_from_defaults(self):
        actual = run("""let k=m.assignChord(m.defaultKeymap(),'edit.export','Ctrl+E');k=m.assignChord(k,'mark.add','Space');
            const back=m.parseKeymapFile(m.serializeKeymap(k));
            const partial=m.resolveKeymap({'play.forward':['space'],'mystery':['A'],'mark.in':['Ctrl++']});
            let bad='';try{m.parseKeymapFile('{"format":"other"}')}catch(e){bad=e.message}
            const stored=m.loadStoredKeymap({getItem:()=>{throw new Error('blocked')}},'x');
            return {same:JSON.stringify(back.keymap)===JSON.stringify(k), warnings:back.warnings, export:back.keymap['edit.export'],
                    toggle:partial.keymap['play.toggle'], forward:partial.keymap['play.forward'], markIn:partial.keymap['mark.in'],
                    partialWarnings:partial.warnings.length, bad, storedDefault:stored.keymap['play.toggle'], storedWarnings:stored.warnings.length}""")
        self.assertTrue(actual["same"])
        self.assertEqual(actual["warnings"], [])
        self.assertEqual(actual["export"], ["Ctrl+E"])
        self.assertEqual(actual["toggle"], [])
        self.assertEqual(actual["forward"], ["Space"])
        self.assertEqual(actual["markIn"], [])
        self.assertEqual(actual["partialWarnings"], 2)
        self.assertIn("not a Last Light Radio", actual["bad"])
        self.assertEqual(actual["storedDefault"], ["Space"])
        self.assertEqual(actual["storedWarnings"], 1)

    def test_typed_timecode_follows_fcp7_rules(self):
        actual = run("""return [m.parseTimecodeEntry('1419',0), m.parseTimecodeEntry('+1.',10), m.parseTimecodeEntry('-48',100),
            m.parseTimecodeEntry('1:00:00',0), m.parseTimecodeEntry('5',99), m.parseTimecodeEntry('01:02:03:04',0),
            m.parseTimecodeEntry('abc',0), m.parseTimecodeEntry('+',0), m.parseTimecodeEntry('123456789',0)]""")
        self.assertEqual(actual, [14 * 24 + 19, 34, 52, 60 * 24, 5, ((1 * 60 + 2) * 60 + 3) * 24 + 4, None, None, None])

    def test_shuttle_edit_points_markers_and_zoom(self):
        actual = run("""const events=[{start_frame:0,end_frame:124},{start_frame:124,end_frame:140},{start_frame:140,end_frame:264},{start_frame:200,end_frame:400}];
            const points=m.editPoints(events,0,400);
            const nested=m.editPoints(events,124,264);
            return {rates:[m.shuttleRate(0,1),m.shuttleRate(1,1),m.shuttleRate(2,1),m.shuttleRate(4,1),m.shuttleRate(8,1),m.shuttleRate(4,-1),m.shuttleRate(-1,-1)],
                    points, nested, next:m.stepPoint(points,124,1), prev:m.stepPoint(points,124,-1), none:m.stepPoint(points,399,1) ?? null,
                    zoom:[m.zoomStep(8,1),m.zoomStep(8,-1),m.zoomStep(3.3,1),m.zoomStep(64,1),m.zoomStep(0.25,-1)]}""")
        self.assertEqual(actual["rates"], [1, 2, 4, 8, 8, -1, -2])
        self.assertEqual(actual["points"], [0, 124, 140, 200, 264, 399])
        self.assertEqual(actual["nested"], [124, 140, 200, 263])
        self.assertEqual((actual["next"], actual["prev"], actual["none"]), (140, 0, None))
        self.assertEqual(actual["zoom"], [16, 4, 4, 64, 0.25])


if __name__ == "__main__":
    unittest.main()
