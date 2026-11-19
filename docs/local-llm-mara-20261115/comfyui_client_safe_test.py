"""Exercise comfyui_client_safe.py against an in-process mock ComfyUI. No GPU, no LAN."""
import json, shutil, sys, threading, tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

PKG = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent
sys.path.insert(0, str(PKG))
import comfyui_client_safe as c  # noqa: E402

STATE = {"posts": 0, "history": {}, "queue": [], "mode": "ok", "out_subfolder": None}
WF = json.loads((PKG / "A02.workflow.json").read_text(encoding="utf-8"))
COMBOS = {}
for n in WF.values():
    for k, v in n["inputs"].items():
        if isinstance(v, str) and k not in ("filename_prefix", "prompt"):  # STRING inputs, not combos
            COMBOS.setdefault(n["class_type"], {}).setdefault(k, []).append(v)


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def send(self, obj, code=200, raw=None):
        body = raw if raw is not None else json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Length", str(len(body))); self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path); p = u.path
        if p == "/system_stats":
            return self.send({"system": {"comfyui_version": "mock"}, "devices": [{"name": "mock", "vram_total": 12 * 2**30, "vram_free": 10 * 2**30}]})
        if p == "/queue":
            return self.send({"queue_running": STATE["queue"], "queue_pending": []})
        if p.startswith("/object_info/"):
            cls = p.split("/", 2)[2]
            if cls == "MissingNode":
                return self.send({})
            req = {k: ["COMBO", {"options": ["other.safetensors", *v]}] for k, v in COMBOS.get(cls, {}).items()}
            return self.send({cls: {"input": {"required": req}}})
        if p == "/view":
            return self.send(None, raw=b"FAKEBYTES-" + parse_qs(u.query)["filename"][0].encode())
        if p == "/history":
            return self.send(STATE["history"])
        if p.startswith("/history/"):
            pid = p.split("/")[2]
            return self.send({pid: STATE["history"][pid]} if pid in STATE["history"] else {})
        self.send({}, 404)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        STATE["posts"] += 1
        assert "prompt" in body and "client_id" in body, "missing wrapper"
        pid = f"pid-{STATE['posts']}"
        prefix = body["prompt"]["14"]["inputs"]["filename_prefix"]
        STATE["history"][pid] = {"prompt": [STATE["posts"], pid, body["prompt"], {"client_id": body["client_id"]}, ["14"]],
                                 "status": {"status_str": "success", "completed": True},
                                 "outputs": {"14": {"images": [{"filename": "A02_00001_.mp4",
                                                                 "subfolder": STATE["out_subfolder"] or prefix.rsplit("/", 1)[0],
                                                                 "type": "output"}]}}}
        if STATE["mode"] == "drop":
            self.connection.close(); return  # job queued, client never hears back
        self.send({"prompt_id": pid, "number": STATE["posts"], "node_errors": {}})


srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{srv.server_port}"
tmp = Path(tempfile.mkdtemp())
results = []


def check(name, cond):
    results.append((name, bool(cond))); print(("PASS " if cond else "FAIL ") + name)


def run(*a):
    return c.main(["--base", BASE, *a])


wf = str(PKG / "A02.workflow.json")
check("preflight ok", run("preflight", wf) == 0)
bad = tmp / "bad.json"; g = json.loads(json.dumps(WF)); g["2"]["inputs"]["unet_name"] = "nope.safetensors"
g["99"] = {"class_type": "MissingNode", "inputs": {}}; bad.write_text(json.dumps(g))
check("preflight catches bad model + missing node", run("preflight", str(bad)) == 1)

e1 = tmp / "exp-one"
check("prepare", run("prepare", wf, str(e1), "--variable", "baseline") == 0)
led = json.loads((e1 / "experiment.json").read_text())
check("prefix rewritten", led["filename_prefix"] == "exp-one/A02" and json.loads((e1 / "workflow.json").read_text())["14"]["inputs"]["filename_prefix"] == "exp-one/A02")
check("archived workflow untouched", json.loads(Path(wf).read_text())["14"]["inputs"]["filename_prefix"] == "van-action-20261115/A02")
check("prepare refuses existing dir", run("prepare", wf, str(e1)) == 1)
check("submit refuses without --confirm", run("submit", str(e1)) == 1 and STATE["posts"] == 0)
STATE["queue"] = [[0, "someone-else", {}, {}, []]]
check("submit refuses busy queue", run("submit", str(e1), "--confirm") == 1 and STATE["posts"] == 0)
STATE["queue"] = []
check("submit refused after earlier attempt left no intent? (busy-queue refusal happens before intent)", not (e1 / "submit-intent.json").exists())
check("submit ok", run("submit", str(e1), "--confirm") == 0 and STATE["posts"] == 1)
check("second submit refused", run("submit", str(e1), "--confirm") == 1 and STATE["posts"] == 1)
check("poll success", run("poll", str(e1)) == 0)
check("download", run("download", str(e1)) == 0 and list((e1 / "outputs").rglob("*.mp4")))
check("download refuses overwrite", run("download", str(e1)) == 1)

e2 = tmp / "exp-two"; run("prepare", wf, str(e2))
STATE["mode"] = "drop"
check("dropped POST -> ambiguous exit 3", run("submit", str(e2), "--confirm") == 3 and STATE["posts"] == 2)
STATE["mode"] = "ok"
check("no resubmit after ambiguous", run("submit", str(e2), "--confirm") == 1 and STATE["posts"] == 2)
check("reconcile finds job", run("reconcile", str(e2)) == 0 and json.loads((e2 / "experiment.json").read_text())["prompt_id"] == "pid-2")

e3 = tmp / "exp-three"; run("prepare", wf, str(e3))
STATE["out_subfolder"] = "../../evil"
run("submit", str(e3), "--confirm"); run("poll", str(e3))
check("traversal refused", run("download", str(e3)) == 1 and not (tmp / "evil").exists())

e4 = tmp / "exp-four"
check("--set changes literal", run("prepare", wf, str(e4), "--set", "18.image=new-ref.png") == 0 and json.loads((e4 / "workflow.json").read_text())["18"]["inputs"]["image"] == "new-ref.png")
check("--set refuses links", run("prepare", wf, str(tmp / "exp-five"), "--set", "7.model=x") == 1)

srv.shutdown(); shutil.rmtree(tmp)
print(f"\n{sum(ok for _, ok in results)}/{len(results)} passed")
sys.exit(0 if all(ok for _, ok in results) else 1)
