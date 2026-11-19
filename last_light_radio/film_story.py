"""Bounded sequence-level FMV authoring; no runtime story invention or generation."""
import json
import re
from . import film, audio_tracks
from .studio import StudioError, text
from .store import canonical_bytes, sha256


def story(studio, project_id):
    film.project(studio, project_id)
    return studio.setting('film.story.'+project_id) or {
        'schema_version': 1, 'project_id': project_id, 'revision': 0,
        'title': '', 'start_node_id': None, 'nodes': [], 'export': None}


def _stable(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', value):
        raise StudioError('Use a stable node/choice ID of 1-80 letters, numbers, underscores or hyphens')
    return value


def _graph(studio, project_id, payload):
    nodes = payload.get('nodes')
    if not isinstance(nodes, list) or len(nodes) > 128:
        raise StudioError('A story supports at most 128 nodes')
    clean = []
    ids = set()
    for node in nodes:
        if not isinstance(node, dict): raise StudioError('Invalid story node')
        identity = _stable(node.get('id'))
        if identity in ids: raise StudioError('Duplicate story node ID')
        ids.add(identity)
        seq = film.sequence(studio, node.get('sequence_id'))
        if seq['project_id'] != project_id or not seq.get('manifest'):
            raise StudioError('Each node must reference a saved sequence in this project')
        terminal = node.get('terminal')
        choices = node.get('choices')
        if type(terminal) is not bool or not isinstance(choices, list) or len(choices) > 8:
            raise StudioError('Specify terminal and at most eight end-of-clip choices')
        if (terminal and choices) or (not terminal and not choices):
            raise StudioError('Terminal nodes have no choices; other nodes require an explicit choice')
        seen = set(); edges = []
        for choice in choices:
            if not isinstance(choice, dict): raise StudioError('Invalid choice')
            cid = _stable(choice.get('id'))
            if cid in seen: raise StudioError('Duplicate choice ID in node')
            seen.add(cid)
            edges.append({'id': cid, 'label': text(choice.get('label'), 'Choice label', 200),
                          'target_node_id': _stable(choice.get('target_node_id'))})
        clean.append({'id': identity, 'title': text(node.get('title'), 'Node title', 200),
                      'sequence_id': seq['id'], 'terminal': terminal, 'choices': edges})
    start = payload.get('start_node_id')
    if (clean and start not in ids) or (not clean and start is not None):
        raise StudioError('Choose a start node in this story')
    for node in clean:
        if any(c['target_node_id'] not in ids for c in node['choices']):
            raise StudioError('A choice refers to a missing node')
    return clean, start


def save(studio, project_id, payload):
    with studio.lock, studio.db() as db:
        db.execute('BEGIN IMMEDIATE')
        current = story(studio, project_id)
        expected = payload.get('expected_revision')
        if type(expected) is not int or expected != current['revision']:
            raise StudioError('Story changed; reload before saving', 409)
        nodes, start = _graph(studio, project_id, payload)
        record = {**current, 'title': text(payload.get('title'), 'Story title', 200),
                  'revision': expected+1, 'nodes': nodes, 'start_node_id': start, 'export': None}
        snapshot = studio.store.save_snapshot(record)
        # Immutable snapshot chain is an audit history, not a claim of command-level undo.
        studio.store.write_once(f"film/stories/{project_id}/revisions/{expected+1}.json", canonical_bytes(snapshot))
        film._write(db, 'film.story.'+project_id, record)
    return record


def _validate_node(studio, node):
    manifest = studio.store.read_snapshot(node['sequence_manifest'])
    if manifest['manifest_hash'] != node['sequence_manifest_hash']:
        raise StudioError('Frozen sequence manifest mismatch', 409)
    film.validate_manifest(studio, manifest)
    studio.store.verify_master({'id': node['id'], **node['media']})


def export(studio, project_id, payload):
    with studio.lock, studio.db() as db:
        db.execute('BEGIN IMMEDIATE')
        current = story(studio, project_id)
        if type(payload.get('expected_revision')) is not int or payload['expected_revision'] != current['revision']:
            raise StudioError('Story changed; reload before exporting', 409)
        nodes, start = _graph(studio, project_id, current)
        if not nodes: raise StudioError('Add a story node before exporting')
        # Unreachable work may be saved, but is not silently bundled into a playable release.
        reachable = set(); todo = [start]; by_id = {n['id']: n for n in nodes}
        while todo:
            identity = todo.pop()
            if identity in reachable: continue
            reachable.add(identity)
            todo.extend(c['target_node_id'] for c in by_id[identity]['choices'])
        if len(reachable) != len(nodes): raise StudioError('Every exported node must be reachable from the start')
        frozen = []
        for node in nodes:
            seq = film.sequence(studio, node['sequence_id'])
            manifest = studio.store.read_snapshot(seq['manifest'])
            film.validate_manifest(studio, manifest)
            path, mime = film.export_media(studio, seq['id'], 'media')
            if mime != 'video/mp4':raise StudioError('FMV nodes require picture exports, not audio-only sequences',409)
            if seq['export']['report']['manifest_hash'] != seq['manifest_hash']:
                raise StudioError('Sequence export is stale', 409)
            source_manifest, _ = film.export_media(studio, seq['id'], 'manifest')
            if json.loads(source_manifest.read_text(encoding="utf-8")) != manifest:
                raise StudioError('Exported sequence manifest changed', 409)
            data = path.read_bytes(); digest = sha256(data)
            relative = f'film/story-media/{digest}.mp4'
            studio.store.write_once(relative, data)
            provenance = {'video': [film.asset(studio, s['asset_id']) for s in manifest['shots'] if not film.is_gap(s)],
                          'audio': [audio_tracks.get(studio, a['asset_id']) for a in manifest.get('audio_tracks', [])]}
            frozen.append({**node, 'sequence_revision': seq['revision'], 'sequence_manifest': seq['manifest'],
                           'sequence_manifest_hash': seq['manifest_hash'], 'media': {'path': relative, 'sha256': digest},
                           'export_report': seq['export']['report'], 'review_provenance': provenance})
        manifest = {'schema_version': 1, 'kind': 'film_fmv_playable_v1', 'project_id': project_id,
                    'story_revision': current['revision'], 'title': current['title'], 'start_node_id': start,
                    'max_transitions': 256, 'nodes': frozen}
        reference = studio.store.save_snapshot(manifest)
        digest = reference['sha256']
        film._write(db, 'film.story.export.'+project_id+'.'+digest, reference)
        record = {**current, 'export': {'manifest_hash': digest, 'revision': current['revision'],
                  'manifest_url': f'/api/film/projects/{project_id}/story/exports/{digest}/manifest'}}
        film._write(db, 'film.story.'+project_id, record)
    return record


def frozen(studio, project_id, digest=None):
    current = story(studio, project_id)
    if digest is None:
        if not current['export']: raise StudioError('Freeze/export this story first', 409)
        digest = current['export']['manifest_hash']
    if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest):
        raise StudioError('Story export not found', 404)
    reference = film._read(studio, 'film.story.export.'+project_id+'.'+digest)
    result = studio.store.read_snapshot(reference)
    if result['project_id'] != project_id: raise StudioError('Story project mismatch', 409)
    for node in result['nodes']:
        _validate_node(studio, node)
        node['media_url'] = f"/api/film/projects/{project_id}/story/exports/{digest}/nodes/{node['id']}/media"
    return {**result, 'manifest_hash': digest}


def media(studio, project_id, digest, node_id):
    manifest = frozen(studio, project_id, digest)
    for node in manifest['nodes']:
        if node['id'] == node_id: return studio.store.resolve(node['media']['path'])
    raise StudioError('Story node not found', 404)
