"""Windows studio bootstrap: local tools, reproducible build, readiness and logs."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import tomllib
import urllib.error
import urllib.request
import webbrowser
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def run(arguments, **kwargs):
    subprocess.run([str(item) for item in arguments], cwd=ROOT, check=True, **kwargs)


def media_ready():
    try:
        from PIL import Image, features
        from last_light_radio.video_tools import ffmpeg_path
        Image.new("RGB", (2, 2)).close()
        if not features.check("webp"):
            return False
        result = subprocess.run([ffmpeg_path(), "-version"], capture_output=True, timeout=15)
        return result.returncode == 0
    except (ImportError, OSError, ValueError, RuntimeError):
        return False


def ensure_media(arguments):
    if media_ready():
        return
    target = ROOT / ".local/venv"
    python = target / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if Path(sys.prefix).resolve() != target.resolve():
        print("Preparing isolated Python environment for image/video support...", flush=True)
        if not python.is_file():
            run([sys.executable, "-m", "venv", target])
        # Return the nested launcher's exit code; installation never touches a global Python.
        return subprocess.call([str(python), str(Path(__file__).resolve()), *arguments], cwd=ROOT)
    print("Installing the project's declared image/video dependencies...", flush=True)
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    run([sys.executable, "-m", "pip", "install", *project["dependencies"], *project["optional-dependencies"]["media"]])
    if not media_ready():
        raise RuntimeError("Image/WebP/FFmpeg checks failed after setup. Check LLR_FFMPEG if configured.")


def frontend_stale():
    output = ROOT / "frontend/dist/index.html"
    if not output.is_file():
        return True
    frontend = ROOT / "frontend"
    inputs = [*frontend.glob("*.json"), *frontend.glob("*.ts"), frontend / "index.html"]
    for directory in ("src", "public"):
        inputs.extend(path for path in (frontend / directory).rglob("*") if path.is_file())
    return any(path.stat().st_mtime_ns > output.stat().st_mtime_ns for path in inputs)


def build_frontend(force=False):
    if not force and not frontend_stale():
        print("React interface: built and current.", flush=True)
        return
    node = shutil.which("node")
    if not node:
        bundled = Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe"
        if bundled.is_file():
            node = str(bundled)
    if not node:
        raise RuntimeError("Building the interface needs Node.js 20.19+ or 22.12+, or a prebuilt frontend/dist.")
    node_dir = Path(node).resolve().parent
    npm = next((candidate for candidate in (node_dir / "node_modules/npm/bin/npm-cli.js",
                                           node_dir.parent / "node_modules/npm/bin/npm-cli.js") if candidate.is_file()), None)
    if npm is None:
        raise RuntimeError(f"npm-cli.js is missing beside {node}. Install Node.js with npm.")
    environment = {**os.environ, "PATH": str(node_dir) + os.pathsep + os.environ.get("PATH", "")}
    if not (ROOT / "frontend/node_modules/.bin/vite.cmd").is_file():
        print("Installing locked frontend dependencies...", flush=True)
        run([node, npm, "ci", "--prefix", "frontend"], env=environment)
    print("Building and type-checking the React interface...", flush=True)
    run([node, npm, "run", "build", "--prefix", "frontend"], env=environment)


def health(url):
    try:
        # Local readiness must not go through a configured HTTP proxy.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(url + "api/health", timeout=1) as response:
            return json.load(response)
    except (OSError, ValueError, urllib.error.URLError):
        return None


def matching_studio(report, data):
    return bool(isinstance(report, dict) and report.get("application") == "last-light-radio"
                and Path(report.get("data_root", "")).resolve() == data.resolve())


def launch(args):
    url = f"http://127.0.0.1:{args.port}/"
    report = health(url)
    if matching_studio(report, args.data):
        print(f"Studio already running with this library: {url}", flush=True)
        if not args.no_browser:
            webbrowser.open(url)
        return 0
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", args.port)) == 0:
            raise RuntimeError(f"Port {args.port} is in use by another service/library. Close it or use --port 8766.")
    logs = ROOT / ".local/logs"
    logs.mkdir(parents=True, exist_ok=True)
    log = logs / f"studio-{datetime.now():%Y%m%d-%H%M%S}-{os.getpid()}.log"
    print(f"Library: {args.data}\nServer log: {log}", flush=True)
    with log.open("w", encoding="utf-8") as stream:
        process = subprocess.Popen([sys.executable, "-u", "-m", "last_light_radio", "studio",
                                    "--port", str(args.port), "--data", str(args.data)],
                                   cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        try:
            deadline = time.monotonic() + 45
            while process.poll() is None and time.monotonic() < deadline:
                if matching_studio(health(url), args.data):
                    print(f"Studio ready: {url}\nKeep this window open. Press Ctrl+C to stop.", flush=True)
                    if not args.no_browser:
                        webbrowser.open(url)
                    return process.wait()
                time.sleep(0.3)
            raise RuntimeError(f"Studio did not become ready. See {log}\n{log.read_text(encoding='utf-8')[-3000:]}")
        except KeyboardInterrupt:
            print("\nStopping the studio. Saved scenes and job IDs remain in the library.", flush=True)
            return 0
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Start Last Light Radio with its existing scene library")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data", type=Path, default=ROOT / ".local/studio")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--check", action="store_true", help="Check/setup dependencies and build without starting the server")
    parser.add_argument("--rebuild", action="store_true", help="Force a frontend build")
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    os.chdir(ROOT)
    args.data = args.data.resolve()
    try:
        if sys.version_info < (3, 11):
            raise RuntimeError("Python 3.11+ is required. Set LLR_PYTHON to a supported python.exe.")
        print(f"Last Light Radio\nPython: {sys.executable}", flush=True)
        nested_result = ensure_media(sys.argv[1:] if argv is None else argv)
        if nested_result is not None:
            return nested_result
        print("Image, WebP and FFmpeg checks passed.", flush=True)
        build_frontend(args.rebuild)
        if args.check:
            print("Quickstart checks passed. No server or GPU render started.", flush=True)
            return 0
        return launch(args)
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"Quickstart failed: {error}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
