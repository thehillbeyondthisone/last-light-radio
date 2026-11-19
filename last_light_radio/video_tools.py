"""Optional FFmpeg support for previews of imported MP4 clips."""

import os
import shutil
import subprocess
from pathlib import Path

from .comfy import ComfyError


def ffmpeg_path() -> str:
    executable = os.environ.get("LLR_FFMPEG") or shutil.which("ffmpeg")
    if executable:
        return executable
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        folder = Path(__file__).resolve().parents[1] / ".local/vendor/imageio_ffmpeg/binaries"
        candidates = list(folder.glob("ffmpeg*.exe"))
        if candidates:
            return str(candidates[0])
    raise ComfyError("FFMPEG_REQUIRED", "Install the optional media dependencies or set LLR_FFMPEG to import MP4 clips")


def sample_video(path: Path, seconds: float) -> bytes:
    result = subprocess.run([ffmpeg_path(), "-v", "error", "-i", str(path), "-ss", str(max(0, seconds)),
                             "-frames:v", "1", "-f", "image2pipe", "-c:v", "png", "pipe:1"],
                            capture_output=True, timeout=40, check=False)
    if result.returncode or not result.stdout.startswith(b"\x89PNG"):
        raise ComfyError("VIDEO_PREVIEW_FAILED", "Could not decode an imported MP4 preview frame", reason=result.stderr.decode(errors="replace")[:700])
    return result.stdout


def verify_video(path: Path):
    result = subprocess.run([ffmpeg_path(), "-v", "error", "-i", str(path), "-map", "0:v:0", "-f", "null", "-"],
                            capture_output=True, timeout=120, check=False)
    if result.returncode or result.stderr.strip():
        raise ComfyError("VIDEO_DECODE_FAILED", "Imported MP4 could not be fully decoded", reason=result.stderr.decode(errors="replace")[:700])
