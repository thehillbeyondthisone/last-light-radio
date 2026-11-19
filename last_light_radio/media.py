"""Dependency-free metadata inspection for the recovered animated WebP output."""

from .comfy import ComfyError


def inspect_webp(data: bytes) -> dict:
    """Read container timing; pixel decoding is a separate quality check."""
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise ComfyError("INVALID_MEDIA", "Expected a RIFF WebP output")
    if int.from_bytes(data[4:8], "little") + 8 != len(data):
        raise ComfyError("INVALID_MEDIA", "WebP container size does not match downloaded bytes")
    offset, width, height = 12, None, None
    durations = []
    animation_header = False
    while offset < len(data):
        if offset + 8 > len(data):
            raise ComfyError("INVALID_MEDIA", "Truncated WebP chunk header")
        kind = data[offset:offset + 4]
        size = int.from_bytes(data[offset + 4:offset + 8], "little")
        end = offset + 8 + size
        if end + (size % 2) > len(data):
            raise ComfyError("INVALID_MEDIA", "Truncated WebP chunk")
        chunk = data[offset + 8:end]
        if kind == b"VP8X" and size == 10:
            width = int.from_bytes(chunk[4:7], "little") + 1
            height = int.from_bytes(chunk[7:10], "little") + 1
        elif kind == b"ANIM" and size == 6:
            animation_header = True
        elif kind == b"ANMF":
            if size <= 16:
                raise ComfyError("INVALID_MEDIA", "Animated WebP frame has no image data")
            duration = int.from_bytes(chunk[12:15], "little")
            if not duration:
                raise ComfyError("INVALID_MEDIA", "Animated WebP has an untimed frame")
            durations.append(duration)
        offset = end + (size % 2)
    if not animation_header or not width or not height or len(durations) < 2:
        raise ComfyError("INVALID_MEDIA", "Expected a timed animated WebP with multiple frames")
    duration_ms = sum(durations)
    return {"container": "webp", "codec": "WebP", "animated": True,
            "width": width, "height": height, "frame_count": len(durations),
            "frame_durations_ms": durations, "duration_ms": duration_ms,
            "duration_seconds": duration_ms / 1000,
            "effective_fps": len(durations) * 1000 / duration_ms,
            "pixel_decode_verified": False}
