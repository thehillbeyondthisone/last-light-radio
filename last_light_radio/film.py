"""Named film projects and cut sequences above the preserved scene-animation editor.

Uploads and reviewed media are immutable. Shot edits only reference source frames;
rendering is CPU-only and never changes the imported source or its original sound.
"""
from __future__ import annotations
import base64
import binascii
import json
import logging
import re
import subprocess
import tempfile
import threading
import wave
from pathlib import Path
from uuid import uuid4

from .studio import StudioError, text
from .store import canonical_bytes, sha256
from .generation import utc_now
from .video_tools import ffmpeg_path
from .pilot_media import inspect_video
from . import audio_tracks

FPS = 24
LOG = logging.getLogger(__name__)
LIMIT = 20 * 1024 * 1024
VERSION = 'film-cut-v1'
GAP_VERSION = 'film-cut-gaps-v1'


def is_gap(item):
    return item.get('kind') == 'gap'


def validate_gap(item):
    if any(key in item for key in ('asset_id', 'source_in_frame', 'source', 'approval_version', 'provenance')):
        raise StudioError('A gap has no video source or source trim fields')
    return audio_tracks._integer(item.get('duration_frames'), 'Gap duration', 1, 14400)


def _id(value, kind):
    if not isinstance(value, str) or not re.fullmatch(kind + r'\.[0-9a-f]{' + ('64' if kind == 'video' else '32') + r'}', value):
        raise StudioError(f'{kind.title()} not found', 404)
    return value

def _read(studio, key):
    record = studio.setting(key)
    if record is None:
        raise StudioError('Film record not found', 404)
    return record

def _write(db, key, record):
    db.execute('INSERT INTO settings(name,value) VALUES(?,?) ON CONFLICT(name) DO UPDATE SET value=excluded.value', (key, json.dumps(record)))

def _records(studio, prefix):
    with studio.db() as db:
        return [json.loads(row[0]) for row in db.execute('SELECT value FROM settings WHERE name LIKE ? ORDER BY name', (prefix + '%',)).fetchall()]

def asset(studio, identity):
    record = _read(studio, 'film.asset.' + _id(identity, 'video'))
    return {**record, 'media_url': f'/api/film/assets/{identity}/media'}

def sequence(studio, identity):
    return _read(studio, 'film.sequence.' + _id(identity, 'sequence'))

def project(studio, identity):
    record = _read(studio, 'film.project.' + _id(identity, 'project'))
    return {**record, 'sequences': [seq for seq in _records(studio, 'film.sequence.') if seq['project_id'] == identity]}

def listing(studio):
    return {'projects': [project(studio, p['id']) for p in _records(studio, 'film.project.')],
            'assets': [asset(studio, a['id']) for a in _records(studio, 'film.asset.')]}

def create_project(studio, payload):
    record = {'id': 'project.' + uuid4().hex, 'title': text(payload.get('title'), 'Project name', 200), 'revision': 0, 'created': utc_now()}
    with studio.lock, studio.db() as db:
        studio.store.save_snapshot(record)
        _write(db, 'film.project.' + record['id'], record)
    return project(studio, record['id'])

def create_sequence(studio, project_id, payload):
    project(studio, project_id)
    record = {'id': 'sequence.' + uuid4().hex, 'project_id': project_id,
              'title': text(payload.get('title'), 'Sequence name', 200), 'revision': 0,
              'fps': FPS, 'width': 1280, 'height': 720, 'duration_frames': 0,
              'shots': [], 'audio_tracks': [], 'created': utc_now(), 'export': {'status': 'draft', 'error': None}}
    with studio.lock, studio.db() as db:
        studio.store.save_snapshot(record)
        _write(db, 'film.sequence.' + record['id'], record)
    return record

def _inspect_import(path):
    # Explicit local-file-only decoder. Tiny preview frames bound captured output.
    command = [ffmpeg_path(), '-hide_banner', '-nostdin', '-protocol_whitelist', 'file,pipe',
               '-max_pixels', '16777216', '-i', str(path), '-map', '0:v:0', '-an',
               '-vf', 'fps=24,showinfo,scale=16:16', '-t', '601', '-fps_mode', 'passthrough',
               '-f', 'rawvideo', '-pix_fmt', 'rgb24', 'pipe:1']
    result = subprocess.run(command, capture_output=True, timeout=300)
    log = result.stderr.decode(errors='replace')
    frames = re.findall(r'\bn:\s*(\d+)\s+pts:\s*(-?\d+)\s+pts_time:([\d.eE+-]+).*?\bs:(\d+)x(\d+)', log)
    count = len(result.stdout) // (16*16*3)
    # showinfo can report one lookahead frame at a duration boundary; reject all overlong inputs.
    if result.returncode or count < 1 or count > 14400 or len(frames) != count:
        raise StudioError('Choose a decodable MP4 with video lasting at most ten minutes')
    size = (int(frames[0][3]), int(frames[0][4]))
    if any(v < 2 or v > 4096 for v in size) or any((int(f[3]), int(f[4])) != size for f in frames):
        raise StudioError('Video must have fixed dimensions between 2 and 4096 pixels')
    return {'fps': FPS, 'frame_count': count, 'duration_seconds': count/FPS, 'width': size[0], 'height': size[1]}

def import_bytes(studio, data, filename, label, provenance):
    filename = text(filename, 'MP4 filename', 200)
    label = text(label, 'Video label', 200)
    if Path(filename).suffix.lower() != '.mp4' or not 16 <= len(data) <= LIMIT or data[4:8] != b'ftyp':
        raise StudioError('Choose an MP4 smaller than 20 MiB')
    if not isinstance(provenance, dict) or len(canonical_bytes(provenance)) > 12000:
        raise StudioError('Video provenance must be a small JSON object')
    digest = sha256(data)
    identity = 'video.' + digest
    if studio.setting('film.asset.' + identity):
        return asset(studio, identity)
    with tempfile.TemporaryDirectory(prefix='film-import-', dir=studio.store.root) as temporary:
        incoming = Path(temporary)/'source.mp4'
        incoming.write_bytes(data)
        info = _inspect_import(incoming)
    source = {'path': f'film/assets/{digest}/original.mp4', 'sha256': digest}
    record = {'id': identity, 'filename': Path(filename).name, 'label': label, 'status': 'candidate', 'version': 0,
              'created': utc_now(), 'source': source, 'provenance': provenance, **info,
              'source_audio_policy': 'Original sound preserved in source; export uses only separate audio tracks'}
    with studio.lock, studio.db() as db:
        db.execute('BEGIN IMMEDIATE')
        # A concurrent duplicate upload keeps the first immutable provenance/review record.
        existing = db.execute('SELECT value FROM settings WHERE name=?', ('film.asset.' + identity,)).fetchone()
        if existing:
            return {**json.loads(existing[0]), 'media_url': f'/api/film/assets/{identity}/media'}
        studio.store.write_once(source['path'], data)
        studio.store.save_snapshot(record)
        _write(db, 'film.asset.' + identity, record)
    return asset(studio, identity)

def import_asset(studio, payload):
    encoded = payload.get('video_base64')
    if not isinstance(encoded, str) or len(encoded) > LIMIT*4//3+8:
        raise StudioError('Choose an MP4 smaller than 20 MiB')
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise StudioError('Invalid MP4 upload') from None
    return import_bytes(studio, data, payload.get('filename'), payload.get('label', payload.get('filename')), payload.get('provenance', {}))

def import_scene_export(studio, payload):
    from .pilots import get
    pilot = get(studio, payload.get('sequence_id'))
    if pilot['status'] != 'complete':
        raise StudioError('Export the scene animation successfully before importing it as a film shot', 409)
    identity = pilot['id']
    video = studio.store.resolve(f'exports/pilots/{identity}/pilot.mp4')
    report = json.loads(studio.store.resolve(f'exports/pilots/{identity}/export_report.json').read_text())
    data = video.read_bytes()
    if sha256(data) != report['sha256']:
        raise StudioError('The scene export checksum changed', 409)
    return import_bytes(studio, data, 'scene-animation.mp4', payload.get('label', pilot['title']),
                        {'kind': 'scene_animation_export', 'sequence_id': identity, 'manifest_hash': pilot['manifest']['manifest_hash'], 'export_sha256': report['sha256']})

def review_asset(studio, identity, payload):
    decision = payload.get('decision')
    if decision not in {'approved', 'rejected'}:
        raise StudioError('Choose approved or rejected')
    notes = text(payload.get('notes', ''), 'Review notes', 2000, required=decision == 'rejected')
    with studio.lock, studio.db() as db:
        db.execute('BEGIN IMMEDIATE')
        record = asset(studio, identity)
        if payload.get('expected_version') != record['version']:
            raise StudioError('Video review changed; reload before reviewing', 409)
        record.pop('media_url', None)
        record.update(status=decision, version=record['version']+1, review_notes=notes, reviewed=utc_now())
        studio.store.save_snapshot(record)
        _write(db, 'film.asset.' + identity, record)
    return asset(studio, identity)

def asset_media(studio, identity):
    record = asset(studio, identity)
    studio.store.verify_master({'id': identity, **record['source']})
    return studio.store.resolve(record['source']['path'])

# Rows that only mention a clip (other media's provenance, stills taken from it, its own generation import,
# earlier removals) never block removal. Anything else (sequences, shot plans, story...) blocks it.
_MENTION_ONLY = ('film.asset.', 'audio.', 'film.image.', 'film.generation.import.', 'film.deleted.')

def _usage(db, digest, own):
    blocking, mentions = [], []
    for name, value in db.execute('SELECT name, value FROM settings WHERE value LIKE ?', ('%' + digest + '%',)).fetchall():
        if name in own:
            continue
        if name.startswith(_MENTION_ONLY):
            mentions.append(name)
            continue
        try:
            record = json.loads(value)
        except ValueError:
            record = None
        title = (record.get('title') or record.get('label')) if isinstance(record, dict) else None
        if not title:  # plan rows carry no title; name the kind of use instead of a raw key
            title = next((label for prefix, label in (('film.plan.candidate.', 'a shot plan slot (attached candidate)'),
                          ('film.plan.placement.', 'a shot plan placement'), ('film.shot-plan.', 'a shot plan'),
                          ('film.generation.destination.', 'a requested take')) if name.startswith(prefix)), None)
        blocking.append({'name': name, 'title': title})
    return blocking, mentions

def _removal(studio, db, identity, mode, include_sound, dry):
    """What removing a clip would touch. Read-only; the caller holds the lock for a real removal."""
    digest = identity.split('.', 1)[1]
    row = db.execute('SELECT value FROM settings WHERE name=?', ('film.asset.' + identity,)).fetchone()
    if not row:
        raise StudioError('Video not found', 404)
    record = json.loads(row[0])
    imports = []
    for name, value in db.execute("SELECT name, value FROM settings WHERE name LIKE 'film.generation.import.%'").fetchall():
        value = json.loads(value)
        if value.get('video_asset_id') == identity:
            imports.append((name, value))
    sound_id = next((v['audio_asset_id'] for _, v in imports if isinstance(v.get('audio_asset_id'), str)), None)
    sound_row = db.execute('SELECT value FROM settings WHERE name=?', (sound_id,)).fetchone() if sound_id else None
    sound = json.loads(sound_row[0]) if sound_row else None
    own = {'film.asset.' + identity, *(name for name, _ in imports)} | ({sound_id} if sound else set())
    blocking, mentions = _usage(db, digest, own)
    sound_blocking = _usage(db, sound_id.split('.', 1)[1], own)[0] if sound else []
    delete_sound = bool(sound) and include_sound and not sound_blocking
    files = [record['source']['path']]
    if delete_sound:
        files += [sound['source']['path'], sound['pcm']['path']]
    # Only the clip's own content-addressed files are ever deleted.
    sound_digest = sound_id.split('.', 1)[1] if sound else None
    allowed = {f'film/assets/{digest}/original.mp4'} | ({f'audio/{sound_digest}/original.wav', f'audio/{sound_digest}/canonical.wav'} if sound else set())
    files = [p for p in dict.fromkeys(files) if p in allowed]
    sizes = {}
    for relative in files:
        path = studio.store.resolve(relative)
        sizes[relative] = path.stat().st_size if path.is_file() else 0
    report = {'id': identity, 'label': record.get('label'), 'status': record.get('status'), 'mode': mode, 'dry_run': dry,
              'used_by': blocking, 'mentioned_by': mentions, 'generation_jobs': [name.rsplit('.', 1)[1] for name, _ in imports],
              'sound': ({'id': sound_id, 'label': sound.get('label'), 'status': sound.get('status'), 'used_by': sound_blocking,
                         'will_delete': delete_sound} if sound else None),
              'files': files if mode == 'disk' else [], 'sizes': sizes if mode == 'disk' else {},
              'bytes': sum(sizes.values()) if mode == 'disk' else 0}
    return report, record, imports, sound, sound_id, delete_sound

def delete_asset(studio, identity, payload):
    """Remove a video clip (and its linked production sound) from the library, optionally deleting its files.

    Refused while any sequence, shot plan or other record uses it. A receipt of the removed records is kept in
    records/projects; generation job outputs are left alone, so an owned take can be imported again from History."""
    identity = _id(identity, 'video')
    mode = payload.get('mode')
    if mode not in {'library', 'disk'}:
        raise StudioError('Choose library (keep the file) or disk (delete the file)')
    include_sound = payload.get('include_sound', True) is True
    if payload.get('dry_run') is True:
        with studio.db() as db:  # plain read, no lock: a real removal re-checks everything under the lock
            return _removal(studio, db, identity, mode, include_sound, True)[0]
    with studio.lock, studio.db() as db:
        db.execute('BEGIN IMMEDIATE')
        report, record, imports, sound, sound_id, delete_sound = _removal(studio, db, identity, mode, include_sound, False)
        if payload.get('expected_version') != record['version']:
            raise StudioError('This clip changed; reload before deleting it', 409)
        blocking = report['used_by']
        if blocking:
            names = ', '.join(b['title'] or b['name'] for b in blocking[:5]) + (' and more' if len(blocking) > 5 else '')
            raise StudioError(f'This clip is in use by {names}. Remove it from there first.', 409)
        removed = utc_now()
        receipt = studio.store.save_snapshot({'kind': 'film_asset_removed', 'record': record, 'sound': sound if delete_sound else None,
                                              'imports': dict(imports), 'mode': mode, 'files': report['files'], 'removed': removed})
        db.execute('DELETE FROM settings WHERE name=?', ('film.asset.' + identity,))
        if delete_sound:
            db.execute('DELETE FROM settings WHERE name=?', (sound_id,))
        for name, _ in imports:
            db.execute('DELETE FROM settings WHERE name=?', (name,))
        _write(db, 'film.deleted.' + identity, {'id': identity, 'label': record.get('label'), 'mode': mode,
                                               'sound_id': sound_id if delete_sound else None, 'removed': removed, 'receipt': receipt})
    # Files go after the records are committed: a file Windows keeps open is reported, never silently skipped.
    freed, left = 0, []
    if mode == 'disk':
        for relative in report['files']:
            path = studio.store.resolve(relative)
            try:
                size = path.stat().st_size
                path.unlink()
                freed += size
            except FileNotFoundError:
                pass
            except OSError as error:
                left.append({'path': relative, 'error': str(error)})
            try:
                path.parent.rmdir()
            except OSError:
                pass
    LOG.info('film.asset_removed id=%s mode=%s sound=%s freed=%d left=%d', identity, mode, sound_id if delete_sound else None, freed, len(left))
    return {**report, 'dry_run': False, 'bytes_freed': freed, 'files_left': left, 'receipt': receipt}

def save_sequence(studio, identity, payload, *, allow_empty=False):
    current = sequence(studio, identity)
    expected = payload.get('expected_revision')
    if type(expected) is not int or expected != current['revision']:
        raise StudioError('This film sequence changed; reload before saving', 409)
    width = audio_tracks._integer(payload.get('width', current['width']), 'Canvas width', 2, 3840)
    height = audio_tracks._integer(payload.get('height', current['height']), 'Canvas height', 2, 2160)
    if width%2 or height%2:
        raise StudioError('Choose even canvas dimensions')
    shots = payload.get('shots')
    if not isinstance(shots, list) or len(shots) > 256:
        raise StudioError('Use at most 256 shots')
    if 'timeline_duration_frames' in payload and payload['timeline_duration_frames'] is None:
        raise StudioError('Timeline duration must be an integer; omit it to retain the current mode')
    explicit_duration = payload.get('timeline_duration_frames', current.get('timeline_duration_frames'))
    if not shots and explicit_duration is None and not allow_empty:
        raise StudioError('Add picture or choose an explicit audio-first timeline duration')
    clean, pinned, ids, cursor = [], [], set(), 0
    for shot in shots:
        if not isinstance(shot, dict):
            raise StudioError('Each shot needs source and trim settings')
        shot_id = text(shot.get('id'), 'Shot ID', 100)
        if shot_id in ids:
            raise StudioError('Each shot needs a distinct ID')
        ids.add(shot_id)
        if shot.get('kind', 'video') not in ('video', 'gap'):
            raise StudioError('Shot kind must be video or gap')
        if is_gap(shot):
            duration = validate_gap(shot)
            item = {'id': shot_id, 'kind': 'gap', 'duration_frames': duration}
            clean.append(item)
            pinned.append({**item, 'start_frame': cursor})
            cursor += duration
            continue
        # No approve/reject in Film (Boden, 2026-11-19): every imported clip can be placed.
        source = asset(studio, shot.get('asset_id'))
        start =audio_tracks._integer(shot.get('source_in_frame', 0), 'Shot source In', 0, source['frame_count']-1)
        duration = audio_tracks._integer(shot.get('duration_frames'), 'Shot duration', 1, source['frame_count']-start)
        item = {'id': shot_id, 'asset_id': source['id'], 'source_in_frame': start, 'duration_frames': duration}
        clean.append(item)
        pinned.append({**item, 'start_frame': cursor, 'source': source['source'], 'approval_version': source['version'],
                       'label': source['label'], 'provenance': source['provenance']})
        cursor += duration
    if cursor > 14400:
        raise StudioError('Film sequences currently support up to ten minutes')
    picture_duration = cursor
    if explicit_duration is not None:
        if 'timeline_duration_frames' not in payload:
            explicit_duration = max(explicit_duration, picture_duration)
        cursor = audio_tracks._integer(explicit_duration, 'Timeline duration', max(1, picture_duration), 14400)
    audio = audio_tracks.validate_tracks(studio, payload.get('audio_tracks', []), cursor, FPS, require_approval=False)
    title = text(payload.get('title'), 'Sequence name', 200)
    manifest = {'schema_version': 1, 'kind': 'film_sequence', 'renderer_version': GAP_VERSION if any(is_gap(s) for s in clean) else VERSION,
                'sequence_id': identity, 'project_id': current['project_id'], 'title': title,
                'fps': FPS, 'width': width, 'height': height, 'duration_frames': cursor,
                'shots': pinned, 'audio_tracks': audio_tracks.pin(studio, audio),
                'source_audio_policy': 'muted; separate approved audio placements only'}
    if explicit_duration is not None:
        manifest.update(timeline_duration_frames=cursor, picture_duration_frames=picture_duration,
                        media_kind='video' if clean else 'audio',
                        uncovered_picture_policy='Black after the last picture; audio timeline is not shortened')
    manifest['manifest_hash'] = sha256(canonical_bytes(manifest))
    record = {**current, 'title': title, 'revision': expected+1, 'width': width, 'height': height,
              'duration_frames': cursor, 'shots': clean, 'audio_tracks': audio,
              'manifest': studio.store.save_snapshot(manifest), 'manifest_hash': manifest['manifest_hash'],
              'export': {'status': 'draft', 'error': None}}
    if explicit_duration is not None:
        record.update(timeline_duration_frames=cursor, picture_duration_frames=picture_duration, media_kind='video' if clean else 'audio')
    if 'markers' in payload:
        record['markers'] = _markers(payload['markers'], cursor)
    elif 'markers' in record:
        _markers(record['markers'], cursor)
    if 'selection' in payload:
        record['selection'] = _selection(payload['selection'], cursor)
    elif 'selection' in record:
        _selection(record['selection'], cursor)
    with studio.lock, studio.db() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT value FROM settings WHERE name=?', ('film.sequence.'+identity,)).fetchone()
        if json.loads(row[0])['revision'] != expected:
            raise StudioError('This film sequence changed; reload before saving', 409)
        validate_manifest(studio, manifest)
        studio.store.save_snapshot(record)
        _write(db, 'film.sequence.'+identity, record)
    return record


def place_picture_interval(studio, identity, payload):
    """Fill one planned contiguous interval without rippling or touching audio.

    Plan ownership and candidate lineage belong to the calling plan service.
    This helper only places already-approved Film media with exact frame bounds.
    """
    current = sequence(studio, identity)
    expected = payload.get('expected_revision')
    if type(expected) is not int or expected != current['revision']:
        raise StudioError('This film sequence changed; reload before placing picture', 409)
    total = current.get('timeline_duration_frames')
    if total is None:
        raise StudioError('Planned picture placement requires an explicit audio-first timeline duration')
    start = audio_tracks._integer(payload.get('start_frame'), 'Planned In', 0, total-1)
    end = audio_tracks._integer(payload.get('end_frame'), 'Planned Out', start+1, total)
    shot_id = text(payload.get('shot_id'), 'Planned shot ID', 100)
    source = asset(studio, payload.get('asset_id'))
    source_in = audio_tracks._integer(payload.get('source_in_frame', 0), 'Shot source In', 0, source['frame_count']-1)
    available = source['frame_count']-source_in
    duration = end-start
    if available < duration:
        raise StudioError('This take is shorter than the planned interval; no stretching or looping is applied')
    if available > duration and payload.get('trim_to_fit') is not True:
        raise StudioError('This take is longer than the planned interval; explicitly confirm trim_to_fit')
    shots = [dict(item) for item in current['shots']]
    cursor = 0
    replace_index = None
    for index, item in enumerate(shots):
        next_cursor = cursor+item['duration_frames']
        if cursor == start and next_cursor == end:
            replace_index = index
        cursor = next_cursor
    if replace_index is None and start != cursor:
        raise StudioError('Place picture contiguously from frame zero, or replace exactly one existing shot; gaps and partial overlaps are not supported')
    if any(item['id'] == shot_id and index != replace_index for index, item in enumerate(shots)):
        raise StudioError('This planned shot ID already occupies another interval', 409)
    item = {'id':shot_id, 'asset_id':source['id'], 'source_in_frame':source_in, 'duration_frames':duration}
    if replace_index is None:
        shots.append(item)
    else:
        shots[replace_index] = item
    return save_sequence(studio, identity, {
        'expected_revision':expected, 'title':current['title'],
        'width':current['width'], 'height':current['height'],
        'timeline_duration_frames':total, 'shots':shots,
        'audio_tracks':current.get('audio_tracks', []),
    })


def _markers(items, duration):
    if not isinstance(items, list) or len(items) > 256:
        raise StudioError('Use at most 256 sequence markers')
    result = []; seen = set()
    for marker in items:
        if not isinstance(marker, dict): raise StudioError('Invalid sequence marker')
        identity = text(marker.get('id'), 'Marker ID', 100)
        if identity in seen: raise StudioError('Marker IDs must be unique')
        seen.add(identity)
        result.append({'id':identity, 'label':text(marker.get('label'), 'Marker label', 200),
                       'frame':audio_tracks._integer(marker.get('frame'), 'Marker frame', 0, duration-1)})
    return result


def _selection(value, duration):
    if value is None: return None
    if not isinstance(value, dict): raise StudioError('Invalid sequence selection')
    start = audio_tracks._integer(value.get('in_frame'), 'Selection In', 0, duration-1)
    end = audio_tracks._integer(value.get('out_frame'), 'Selection Out (exclusive)', start+1, duration)
    return {'in_frame':start, 'out_frame':end}


def audio_waveform(studio, identity):
    """Bounded peak envelope of the verified canonical PCM, not invented waveform art."""
    asset_record = audio_tracks.get(studio, identity)
    path = audio_tracks.media(studio, identity)
    if asset_record.get('waveform'):
        result = studio.store.read_snapshot(asset_record['waveform'])
        if result.get('source_sha256') != asset_record['pcm']['sha256']:
            raise StudioError('Audio waveform source checksum changed', 409)
        return result
    result = audio_tracks.waveform_file(path)
    result.update(asset_id=identity, source_sha256=asset_record['pcm']['sha256'])
    return result


def _render_audio(studio, manifest, destination):
    tracks = [track for track in manifest.get('audio_tracks', []) if track['enabled']]
    fps = manifest['fps']; samples = manifest['duration_frames']*48000//fps
    args = [ffmpeg_path(), '-v', 'error', '-nostdin']
    filters = []
    for index, track in enumerate(tracks):
        studio.store.verify_master({'id':track['asset_id'], **track['source']})
        args += ['-i', str(studio.store.resolve(track['source']['path']))]
        start = track['source_in_frame']*48000//fps; count = track['duration_frames']*48000//fps
        chain = f"[{index}:a]atrim=start_sample={start}:end_sample={start+count},asetpts=PTS-STARTPTS,volume={track['gain_db']}dB"
        if track['fade_in_frames']:
            chain += f",afade=t=in:st=0:d={track['fade_in_frames']/fps:.12f}"
        if track['fade_out_frames']:
            chain += f",afade=t=out:st={(track['duration_frames']-track['fade_out_frames'])/fps:.12f}:d={track['fade_out_frames']/fps:.12f}"
        delay = track['start_frame']*48000//fps
        filters.append(chain+f",adelay={delay}S:all=1[a{index}]")
    if tracks:
        labels = ''.join(f'[a{i}]' for i in range(len(tracks)))
        filters.append(f'{labels}amix=inputs={len(tracks)}:duration=longest:normalize=0,alimiter=limit=0.95:level=0:latency=1,apad,atrim=end_sample={samples}[mix]')
        args += ['-filter_complex',';'.join(filters),'-map','[mix]']
    else:
        args += ['-f','lavfi','-i','anullsrc=r=48000:cl=stereo','-af',f'atrim=end_sample={samples}']
    args += ['-vn','-ar','48000','-ac','2','-c:a','pcm_s24le',str(destination)]
    _run(args, studio.stop_event)
    with wave.open(str(destination), 'rb') as output:
        if output.getnframes()!=samples or output.getframerate()!=48000 or output.getnchannels()!=2 or output.getsampwidth()!=3:
            raise StudioError('Audio-first export clock or format mismatch')
        while output.readframes(65536): pass
    return {'renderer_version':VERSION,'media_kind':'audio','shot_count':0,'frames_written':0,
            'timeline_frames':manifest['duration_frames'],'audio':'mixed' if tracks else 'silence',
            'audio_track_count':len(tracks),'audio_sample_rate':48000,'audio_sample_count':samples,
            'audio_duration_seconds':samples/48000,'audio_limiter':'0.95 peak; no automatic mix normalization',
            'inspection':{'fully_decoded':True,'sample_count':samples,'sample_rate':48000,
                          'channels':2,'sample_width':3,'duration_seconds':samples/48000}}


def validate_manifest(studio, manifest):
    if manifest.get('renderer_version') not in (VERSION, GAP_VERSION):
        raise StudioError('This film renderer version is unavailable', 409)
    for shot in manifest['shots']:
        if is_gap(shot):
            if manifest.get('renderer_version') != GAP_VERSION:
                raise StudioError('Gap requires the gap-aware renderer version', 409)
            validate_gap(shot)
            continue
        if shot.get('kind', 'video') != 'video':
            raise StudioError('Unknown film item kind')
        current = asset(studio, shot['asset_id'])
        # Content-addressed source must match; review status/version no longer gate Film (2026-11-19).
        if current['source'] != shot['source']:
            raise StudioError('A video source changed; rebuild the film sequence', 409)
        studio.store.verify_master({'id': current['id'], **shot['source']})
    audio_tracks.validate_pinned(studio, manifest.get('audio_tracks', []), require_approval=False)

def _run(command, stop_event, timeout=600):
    import time
    started = time.monotonic()
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=errors)
        try:
            while True:
                if stop_event.is_set():
                    raise InterruptedError('Film export stopped; retry after restarting')
                if time.monotonic()-started > timeout:
                    raise StudioError('Film export timed out')
                try:
                    code = process.wait(timeout=.25)
                    break
                except subprocess.TimeoutExpired:
                    pass
            if code:
                errors.seek(0)
                raise StudioError('Film export failed: '+errors.read(1200).decode(errors='replace'))
        finally:
            if process.poll() is None:
                process.kill(); process.wait()

def render(studio, manifest, destination):
    if not manifest['shots']:
        return _render_audio(studio, manifest, destination)
    with tempfile.TemporaryDirectory(prefix='film-cuts-', dir=destination.parent) as temporary:
        root = Path(temporary)
        for index, shot in enumerate(manifest['shots']):
            segment = root/f'shot-{index:04d}.mp4'
            if is_gap(shot):
                validate_gap(shot)
                _run([ffmpeg_path(),'-v','error','-nostdin','-f','lavfi','-i',
                      f"color=c=black:s={manifest['width']}x{manifest['height']}:r=24",'-an',
                      '-frames:v',str(shot['duration_frames']),'-c:v','libx264','-pix_fmt','yuv420p',
                      '-preset','veryfast','-crf','17','-threads','4','-video_track_timescale','24000',
                      str(segment)],studio.stop_event)
                continue
            source = studio.store.resolve(shot['source']['path'])
            filters = (f"fps=24,trim=start_frame={shot['source_in_frame']}:end_frame={shot['source_in_frame']+shot['duration_frames']},"
                       f"setpts=PTS-STARTPTS,scale={manifest['width']}:{manifest['height']}:force_original_aspect_ratio=decrease,"
                       f"pad={manifest['width']}:{manifest['height']}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p")
            _run([ffmpeg_path(),'-v','error','-nostdin','-protocol_whitelist','file,pipe','-i',str(source),'-map','0:v:0','-an',
                  '-vf',filters,'-frames:v',str(shot['duration_frames']),'-r','24','-fps_mode','cfr','-c:v','libx264',
                  '-preset','veryfast','-crf','17','-threads','4','-video_track_timescale','24000',str(segment)],studio.stop_event)
        segment_count = len(manifest['shots'])
        remaining = manifest['duration_frames'] - sum(shot['duration_frames'] for shot in manifest['shots'])
        if remaining > 0:
            _run([ffmpeg_path(),'-v','error','-nostdin','-f','lavfi','-i',
                  f"color=c=black:s={manifest['width']}x{manifest['height']}:r=24",'-an','-frames:v',str(remaining),
                  '-c:v','libx264','-pix_fmt','yuv420p','-preset','veryfast','-crf','17','-threads','4',
                  '-video_track_timescale','24000',str(root/f'shot-{segment_count:04d}.mp4')],studio.stop_event)
            segment_count += 1
        concat = root/'cuts.txt'
        concat.write_text(''.join(f"file 'shot-{i:04d}.mp4'\n" for i in range(segment_count)),encoding='utf-8')
        _run([ffmpeg_path(),'-v','error','-nostdin','-f','concat','-safe','1','-i',str(concat),'-map','0:v:0','-an','-c:v','copy',
              '-video_track_timescale','24000','-movflags','+faststart',str(destination)],studio.stop_event)
    report = {'renderer_version': manifest['renderer_version'], 'shot_count': len(manifest['shots']), 'frames_written': manifest['duration_frames'],
              'source_audio_policy': 'muted; separate approved audio placements only'}
    report.update(audio_tracks.mix_export(studio.store,manifest,destination,studio.stop_event))
    report['inspection'] = inspect_video(destination,manifest['duration_frames'],FPS,(manifest['width'],manifest['height']))
    return report

def _update_export(studio, identity, manifest_hash, export):
    with studio.lock, studio.db() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT value FROM settings WHERE name=?',('film.sequence.'+identity,)).fetchone()
        record = json.loads(row[0])
        if record.get('manifest_hash') == manifest_hash:
            record['export'] = export
            _write(db,'film.sequence.'+identity,record)

def process_export(studio, identity, manifest):
    digest = manifest['manifest_hash']
    folder = f'film/exports/{digest}'
    try:
        validate_manifest(studio,manifest)
        _update_export(studio,identity,digest,{'status':'exporting','error':None})
        filename = 'mix.wav' if not manifest['shots'] else 'film.mp4'
        video = studio.store.resolve(folder+'/'+filename)
        report_path = studio.store.resolve(folder+'/report.json')
        if video.is_file() and report_path.is_file():
            report = json.loads(report_path.read_text())
            if sha256(video.read_bytes()) != report['sha256'] or report['manifest_hash'] != digest:
                raise StudioError('Existing film export checksum changed; it was preserved')
        else:
            with tempfile.TemporaryDirectory(prefix='film-export-',dir=studio.store.root) as temporary:
                destination = Path(temporary)/filename
                report = render(studio,manifest,destination)
                validate_manifest(studio,manifest)
                data = destination.read_bytes()
                report.update(sha256=sha256(data),bytes=len(data),manifest_hash=digest)
                studio.store.write_once(folder+'/'+filename,data)
                studio.store.write_once(folder+'/manifest.json',canonical_bytes(manifest))
                studio.store.write_once(folder+'/report.json',canonical_bytes(report))
        validate_manifest(studio,manifest)
        _update_export(studio,identity,digest,{'status':'complete','error':None,
                       'media_url':f'/api/film/sequences/{identity}/media',
                       'manifest_url':f'/api/film/sequences/{identity}/manifest', 'report':report})
    except Exception as error:
        _update_export(studio,identity,digest,{'status':'interrupted' if isinstance(error,InterruptedError) else 'failed','error':str(error)})

def queue_export(studio, identity, payload):
    with studio.lock:
        current = sequence(studio,identity)
        if payload.get('expected_revision') != current['revision']:
            raise StudioError('Sequence changed; save/reload before exporting',409)
        if not current.get('manifest'):
            raise StudioError('Save a picture or audio-first sequence before exporting')
        manifest = studio.store.read_snapshot(current['manifest'])
        validate_manifest(studio,manifest)
        jobs = getattr(studio,'film_jobs',{})
        studio.film_jobs = jobs
        key = manifest['manifest_hash']
        if key in jobs and jobs[key].is_alive():
            return current
        _update_export(studio,identity,key,{'status':'queued','error':None})
        thread = threading.Thread(target=process_export,args=(studio,identity,manifest),name='film-export-'+key[:8],daemon=True)
        jobs[key]=thread
        thread.start()
        return sequence(studio,identity)

def export_media(studio, identity, kind):
    record = sequence(studio,identity)
    if record['export']['status'] != 'complete':
        raise StudioError('Export this sequence successfully first',409)
    audio_only = record.get('media_kind') == 'audio'
    filename = 'mix.wav' if audio_only else 'film.mp4'
    relative = f"film/exports/{record['manifest_hash']}/" + (filename if kind == 'media' else 'manifest.json')
    path = studio.store.resolve(relative)
    if kind == 'media' and sha256(path.read_bytes()) != record['export']['report']['sha256']:
        raise StudioError('Film export checksum changed',409)
    return path, ('audio/wav' if audio_only else 'video/mp4') if kind == 'media' else 'application/json'

def takes(studio):
    """List only already materialized same-library video takes. Never contact a worker."""
    items = []
    for candidate in studio.candidates():
        metadata = candidate['metadata']
        outputs = []
        for index, output in enumerate(metadata.get('outputs', [])):
            if Path(output.get('path', '')).suffix.lower() != '.mp4':
                continue
            properties = output.get('properties', {})
            outputs.append({'output_index': index, 'frame_count': properties.get('frame_count'),
                            'fps': properties.get('effective_fps'), 'width': properties.get('width'),
                            'height': properties.get('height'), 'sha256': output.get('sha256')})
        if outputs:
            items.append({'candidate_id': candidate['id'], 'label': candidate['label'], 'scene_id': candidate['scene_id'],
                          'status': candidate['status'], 'version': candidate['version'],
                          'pipeline': metadata.get('pipeline'), 'workflow_sha256': metadata.get('workflow_sha256'), 'outputs': outputs})
    return {'takes': items}

def import_take(studio, payload):
    """Copy an existing take and its exact receipt into Film; never submit or approve."""
    candidate_id = text(payload.get('candidate_id'), 'Completed take', 100)
    candidate = studio.candidate(candidate_id)
    metadata = candidate['metadata']
    outputs = metadata.get('outputs', [])
    index = audio_tracks._integer(payload.get('output_index', 0), 'Take output index', 0, max(0, len(outputs)-1))
    if not outputs or Path(outputs[index].get('path', '')).suffix.lower() != '.mp4':
        raise StudioError('Choose an existing MP4 take; animated WebP requires a scene export first')
    output = outputs[index]
    studio.store.verify_master({'id': candidate_id, **output})
    scene = studio.scene(candidate['scene_id'])
    studio.store.verify_master(scene['master'])
    # A registered candidate is materialized output, including recovered legacy takes.
    # Save the whole metadata, not only the UI subset; references retain their hashes.
    bundle = {'schema_version': 1, 'kind': 'film_take_ingestion_receipt',
              'candidate': candidate, 'scene_master': scene['master'], 'selected_output_index': index,
              'selected_output': output, 'generation_request': None, 'accepted_receipt': None}
    local_job_id = metadata.get('local_job_id')
    if isinstance(local_job_id, str) and re.fullmatch(r'[0-9a-f]{32}', local_job_id):
        folder = f'records/live_jobs/{local_job_id}'
        request_file = studio.store.resolve(folder+'/request.json')
        if request_file.is_file():
            from .generation import load_request
            bundle['generation_request'] = load_request(studio.store, local_job_id)
        accepted = studio.store.resolve(folder+'/accepted.json')
        if accepted.is_file():
            bundle['accepted_receipt'] = json.loads(accepted.read_text())
    for key in ('workflow', 'history'):
        if isinstance(metadata.get(key), dict) and {'path','sha256'} <= metadata[key].keys():
            bundle[key] = studio.store.read_snapshot(metadata[key])
    receipt = studio.store.save_snapshot(bundle)
    provenance = {'kind': 'generated_take', 'candidate_id': candidate_id, 'scene_id': candidate['scene_id'],
                  'source_review_status': candidate['status'], 'source_review_version': candidate['version'],
                  'source_sha256': output['sha256'], 'generation_receipt': receipt,
                  'local_job_id': local_job_id, 'prompt_id': metadata.get('prompt_id'),
                  'pipeline': metadata.get('pipeline'), 'workflow_sha256': metadata.get('workflow_sha256'),
                  'film_approval_policy': 'Separate explicit Film review; no source review is automatically promoted'}
    imported = import_bytes(studio, studio.store.resolve(output['path']).read_bytes(),
                            'completed-take.mp4', payload.get('label', candidate['label']), provenance)
    # Hash deduplication must not discard a newly discovered generation receipt.
    # Append the receipt without changing the existing asset's review or initial provenance.
    with studio.lock, studio.db() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT value FROM settings WHERE name=?', ('film.asset.'+imported['id'],)).fetchone()
        record = json.loads(row[0])
        receipts = list(record.get('generation_receipts', []))
        if receipt not in receipts:
            record['generation_receipts'] = receipts+[receipt]
            studio.store.save_snapshot(record)
            _write(db,'film.asset.'+imported['id'],record)
    return asset(studio, imported['id'])
