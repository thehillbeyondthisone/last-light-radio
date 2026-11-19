import copy, json, pathlib, unittest
from prototype import validate, compile_book, writer_packet
BOOK = json.loads(pathlib.Path(__file__).with_name("example-shotbook.json").read_text(encoding="utf-8-sig"))
class Tests(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(validate(BOOK), [])
    def test_repeatable(self):
        self.assertEqual(compile_book(BOOK), compile_book(copy.deepcopy(BOOK)))
    def test_no_submission(self):
        self.assertFalse(compile_book(BOOK)["can_submit"])
        self.assertTrue(all(not j["submitted"] for j in compile_book(BOOK)["jobs"]))
    def test_duplicate(self):
        b=copy.deepcopy(BOOK); b["shots"][1]["id"]=b["shots"][0]["id"]
        self.assertTrue(validate(b))
    def test_gap(self):
        b=copy.deepcopy(BOOK); b["shots"][1]["start"]+=1
        self.assertTrue(validate(b))
    def test_state(self):
        b=copy.deepcopy(BOOK); b["shots"][1]["state_in"]["lamp"]="on"
        self.assertTrue(validate(b))
    def test_capability(self):
        self.assertTrue(all("Interval exceeds" in x["reasons"][0] for x in compile_book(BOOK,100)["blockers"][:-1]))
    def test_ref_and_approval(self):
        r=compile_book(BOOK)
        self.assertEqual(len(r["blockers"]),7)
        self.assertIn("Shot plan remains unapproved", r["blockers"][0]["reasons"])
    def test_unknown_scene(self):
        b=copy.deepcopy(BOOK); b["shots"][0]["scene_id"]="elsewhere"
        self.assertTrue(validate(b))
    def test_bad_fps(self):
        b=copy.deepcopy(BOOK); b["fps"]["num"]=True
        self.assertTrue(validate(b))
    def test_bad_duration(self):
        b=copy.deepcopy(BOOK); b["duration_frames"]=721
        self.assertTrue(validate(b))
    def test_brief_honest(self):
        self.assertIn("No LLM",writer_packet("lamp")["backend"])
        with self.assertRaises(ValueError): writer_packet(" ")
if __name__=="__main__": unittest.main()

