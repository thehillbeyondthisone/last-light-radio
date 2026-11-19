"""Immutable reviewed WAV assets and deterministic frame-aligned audio mixing."""
from __future__ import annotations
import base64
import binascii
import io
import json
import math
import re
import subprocess
import tempfile
import wave
from pathlib import Path

from .store import canonical_bytes, sha256, file_sha256
from .studio import StudioError, text
from .generation import utc_now
from .video_tools import ffmpeg_path

LIMIT = 20 * 1024 * 1024
FILE_LIMIT = 256 * 1024 * 1024

def get(studio, identity):
    if not isinstance(identity, str) or not re.fullmatch(r"audio\.[0-9a-f]{64}", identity):
        raise StudioError("Audio asset not found", 404)
    record = studio.setting(identity)
    if not record:
        raise StudioError("Audio asset not found", 404)
    return {**record, "media_url": f"/api/audio/{identity}/media"}

def listing(studio):
    with studio.db() as db:
        rows = db.execute("SELECT name FROM settings WHERE name LIKE 'audio.%' ORDER BY name").fetchall()
    return {"assets": [get(studio, row[0]) for row in rows], "upload": {"mode":"binary", "max_bytes":FILE_LIMIT, "max_duration_seconds":600, "formats":["wav"]}}

def import_asset(studio, payload):
    filename = text(payload.get("filename"), "WAV filename", 200)
    if Path(filename).suffix.lower() != ".wav":
        raise StudioError("Choose a WAV file; other audio formats are not supported yet")
    encoded = payload.get("audio_base64")
    if not isinstance(encoded, str) or len(encoded) > (LIMIT * 4 // 3 + 8):
        raise StudioError("Choose a WAV smaller than 20 MiB")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise StudioError("Invalid WAV upload") from None
    if len(data) > LIMIT or len(data) < 44 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise StudioError("Choose a valid RIFF WAV smaller than 20 MiB")
    with tempfile.TemporaryDirectory(prefix='audio-json-', dir=studio.store.root) as temporary:
        path = Path(temporary)/'original.wav'
        path.write_bytes(data)
        return import_file(studio, path, filename, payload.get('label', filename), payload.get('provenance', {}))


def import_file(studio, path, filename, label, provenance):
    """Preserve a bounded WAV from disk; never move or modify the caller's file."""
    path = Path(path)
    filename = text(filename, 'WAV filename', 200)
    label = text(label, 'Audio label', 200)
    if Path(filename).suffix.lower() != '.wav': raise StudioError('Choose a WAV file')
    if not isinstance(provenance, dict) or len(canonical_bytes(provenance)) > 12000:
        raise StudioError('Audio provenance must be a small JSON object')
    if not path.is_file() or not 44 <= path.stat().st_size <= FILE_LIMIT:
        raise StudioError('Choose a WAV up to 256 MiB')
    with path.open('rb') as source: header = source.read(12)
    if header[:4] != b'RIFF' or header[8:12] != b'WAVE': raise StudioError('Choose a valid RIFF WAV')
    digest = file_sha256(path); identity = 'audio.'+digest
    if studio.setting(identity):
        record = get(studio, identity)
        studio.store.verify_master({'id':identity, **record['source']})
        studio.store.verify_master({'id':identity, **record['pcm']})
        return record
    with tempfile.TemporaryDirectory(prefix='audio-import-', dir=studio.store.root) as temporary:
        destination = Path(temporary)/'canonical.wav'
        result = subprocess.run([ffmpeg_path(), '-v','error','-xerror','-nostdin','-protocol_whitelist','file,pipe',
            '-i',str(path),'-map','0:a:0','-vn','-t','601','-ac','2','-ar','48000','-c:a','pcm_s24le',str(destination)],
            capture_output=True, timeout=180)
        if result.returncode or not destination.is_file(): raise StudioError('WAV could not be decoded')
        with wave.open(str(destination),'rb') as source:
            samples,rate,channels = source.getnframes(),source.getframerate(),source.getnchannels()
            if not 0 < samples <= 600*rate: raise StudioError('Audio must contain between zero and ten minutes of sound')
        pcm_digest = file_sha256(destination)
        envelope = waveform_file(destination)
        source_path = f'audio/{digest}/original.wav'; pcm_path = f'audio/{digest}/canonical.wav'
        # Expensive decode and envelope calculation occur outside the global lock.
        with studio.lock:
            if studio.setting(identity): return get(studio,identity)
            studio.store.write_file_once(source_path,path,digest)
            studio.store.write_file_once(pcm_path,destination,pcm_digest)
            record = {'id':identity,'label':label,'filename':Path(filename).name,'status':'candidate','version':0,
                'created':utc_now(),'duration_seconds':samples/rate,'sample_rate':rate,'channels':channels,'sample_count':samples,
                'source':{'path':source_path,'sha256':digest},'pcm':{'path':pcm_path,'sha256':pcm_digest},'provenance':provenance}
            envelope.update(asset_id=identity, source_sha256=pcm_digest)
            record['waveform'] = studio.store.save_snapshot(envelope)
            studio.store.save_snapshot(record)
            with studio.db() as db: db.execute('INSERT INTO settings(name,value) VALUES(?,?)',(identity,json.dumps(record)))
        return get(studio,identity)


def waveform_file(path):
    # Optional acceleration already available in the media runtime; no required dependency.
    try: import numpy as np
    except ImportError: np = None
    with wave.open(str(path),'rb') as source:
        count=source.getnframes();channels=source.getnchannels();width=source.getsampwidth();rate=source.getframerate()
        bins=min(1024,max(1,count));peaks=[]
        for index in range(bins):
            start=index*count//bins;stop=(index+1)*count//bins
            raw=source.readframes(stop-start)
            if np is not None and width==3:
                parts=np.frombuffer(raw,dtype=np.uint8).reshape(-1,3).astype(np.int32)
                values=parts[:,0] | parts[:,1]<<8 | parts[:,2]<<16
                values=(values ^ 0x800000)-0x800000
                maximum=int(np.abs(values).max(initial=0))
            else:
                maximum=max((abs(int.from_bytes(raw[n:n+width],'little',signed=True)) for n in range(0,len(raw),width)),default=0)
            peaks.append(round(maximum/(2**(width*8-1)),6))
    return {'sample_count':count,'sample_rate':rate,'channels':channels,'duration_seconds':count/rate,
            'bins':bins,'peaks':peaks,'kind':'absolute_peak_envelope','clock':'canonical PCM samples'}


def review(studio, identity, payload):
    decision = payload.get("decision")
    if decision not in {"approved", "rejected"}:
        raise StudioError("Choose approved or rejected")
    notes = text(payload.get("notes", ""), "Review notes", 2000, required=decision == "rejected")
    with studio.lock, studio.db() as db:
        db.execute("BEGIN IMMEDIATE")
        record = get(studio, identity)
        if payload.get("expected_version") != record["version"]:
            raise StudioError("Audio review changed; reload before reviewing", 409)
        record.pop("media_url", None)
        record.update(status=decision, version=record["version"] + 1, review_notes=notes, reviewed=utc_now())
        studio.store.save_snapshot(record)
        db.execute("UPDATE settings SET value=? WHERE name=?", (json.dumps(record), identity))
    return get(studio, identity)

def media(studio, identity):
    record = get(studio, identity)
    studio.store.verify_master({"id": identity, **record["pcm"]})
    return studio.store.resolve(record["pcm"]["path"])

def _integer(value, name, low, high):
    if type(value) is not int or not low <= value <= high:
        raise StudioError(f"{name} must be an integer between {low} and {high}")
    return value

def validate_tracks(studio, items, duration, fps, *, require_approval=True):
    # Film (2026-11-19, Boden): no approve/reject; any imported sound can be placed. Older editor keeps the gate.
    if not isinstance(items, list) or len(items) > 64:
        raise StudioError("Use at most 64 audio clips")
    clean, ids = [], set()
    for item in items:
        if not isinstance(item, dict):
            raise StudioError("Each audio clip needs settings")
        identity = text(item.get("id"), "Audio clip ID", 100)
        if identity in ids or item.get("role") not in {"production", "music"}:
            raise StudioError("Choose distinct audio clip IDs and a production or music role")
        ids.add(identity)
        asset = get(studio, item.get("asset_id"))
        if require_approval and asset["status"] != "approved":
            raise StudioError("Approve the audio source before placing it", 409)
        start = _integer(item.get("start_frame"), "Audio start", 0, duration - 1)
        length = _integer(item.get("duration_frames"), "Audio duration", 1, duration - start)
        source_in = _integer(item.get("source_in_frame", 0), "Audio source In", 0, 600 * fps)
        if (source_in + length) * asset["sample_rate"] > asset["sample_count"] * fps:
            raise StudioError("The audio trim extends past the source")
        gain = item.get("gain_db", 0)
        if type(gain) not in (int, float) or not math.isfinite(gain) or not -60 <= gain <= 12:
            raise StudioError("Audio gain must be between -60 and +12 dB")
        fade_in = _integer(item.get("fade_in_frames", 0), "Fade In", 0, length)
        fade_out = _integer(item.get("fade_out_frames", 0), "Fade Out", 0, length)
        if fade_in + fade_out > length:
            raise StudioError("Audio fades must fit inside the clip without overlapping")
        enabled = item.get("enabled", True)
        if type(enabled) is not bool:
            raise StudioError("Audio enabled must be true or false")
        clean.append({"id": identity, "asset_id": asset["id"], "role": item["role"], "start_frame": start,
                      "source_in_frame": source_in, "duration_frames": length, "gain_db": gain,
                      "fade_in_frames": fade_in, "fade_out_frames": fade_out, "enabled": enabled})
    return sorted(clean, key=lambda v: (v["start_frame"], v["role"], v["id"]))

def pin(studio, tracks):
    result = []
    for track in tracks:
        asset = get(studio, track["asset_id"])
        result.append({**track, "approval_version": asset["version"], "source": asset["pcm"],
                       "original": asset["source"], "provenance": asset["provenance"], "label": asset["label"]})
    return result

def validate_pinned(studio, tracks, *, require_approval=True):
    for track in tracks:
        asset = get(studio, track["asset_id"])
        if asset["pcm"] != track["source"]:
            raise StudioError("Audio source changed; rebuild the sequence before export", 409)
        if require_approval and (asset["status"] != "approved" or asset["version"] != track["approval_version"]):
            raise StudioError("Audio approval changed; rebuild the sequence before export", 409)
        studio.store.verify_master({"id": asset["id"], **track["source"]})
        studio.store.verify_master({"id": asset["id"], **track["original"]})

def mix_export(store, manifest, video_path, stop_event):
    tracks = [track for track in manifest.get("audio_tracks", []) if track["enabled"]]
    if not tracks:
        return {"audio": "none"}
    fps = manifest["fps"]
    duration = manifest["duration_frames"] / fps
    with tempfile.TemporaryDirectory(prefix="audio-mix-", dir=video_path.parent) as temporary:
        mixed = Path(temporary) / "mixed.mp4"
        args = [ffmpeg_path(), "-v", "error", "-nostdin", "-i", str(video_path)]
        filters = []
        for index, track in enumerate(tracks, 1):
            store.verify_master({"id": track["asset_id"], **track["source"]})
            args += ["-i", str(store.resolve(track["source"]["path"]))]
            start_sample = round(track["source_in_frame"] * 48000 / fps)
            count = round(track["duration_frames"] * 48000 / fps)
            chain = f"[{index}:a]atrim=start_sample={start_sample}:end_sample={start_sample+count},asetpts=PTS-STARTPTS,volume={track['gain_db']}dB"
            if track["fade_in_frames"]:
                chain += f",afade=t=in:st=0:d={track['fade_in_frames']/fps:.12f}"
            if track["fade_out_frames"]:
                chain += f",afade=t=out:st={(track['duration_frames']-track['fade_out_frames'])/fps:.12f}:d={track['fade_out_frames']/fps:.12f}"
            delay = round(track["start_frame"] * 48000 / fps)
            chain += f",adelay={delay}S:all=1[a{index}]"
            filters.append(chain)
        labels = "".join(f"[a{i}]" for i in range(1, len(tracks)+1))
        filters.append(f"{labels}amix=inputs={len(tracks)}:duration=longest:normalize=0,alimiter=limit=0.95:level=0:latency=1,apad,atrim=duration={duration:.12f}[mix]")
        args += ["-filter_complex", ";".join(filters), "-map", "0:v:0", "-map", "[mix]", "-c:v", "copy",
                 "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-t", f"{duration:.12f}", "-movflags", "+faststart", str(mixed)]
        with tempfile.TemporaryFile() as errors:
            process = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=errors)
            try:
                while True:
                    if stop_event.is_set():
                        raise InterruptedError("Audio export interrupted")
                    try:
                        code = process.wait(timeout=.25)
                        break
                    except subprocess.TimeoutExpired:
                        pass
                if code:
                    errors.seek(0)
                    raise StudioError("Audio mix failed: " + errors.read(1200).decode(errors="replace"))
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
        mixed.replace(video_path)
    return {"audio": "mixed", "audio_track_count": len(tracks), "audio_sample_rate": 48000,
            "audio_duration_seconds": duration, "audio_limiter": "0.95 peak; no automatic mix normalization"}
