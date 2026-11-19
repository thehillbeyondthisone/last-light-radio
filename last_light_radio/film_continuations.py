"""Explicit continuation from a saved shot's actual rendered last used frame."""
import json
import re
import subprocess
from . import film, film_images
from .studio import StudioError,text
from .store import canonical_bytes,sha256
from .video_tools import ffmpeg_path

POLICY={'drop_generated_first_frames':1,'audio_source_in_frame':1,
        'guarantee':'Conditioned reconstruction, not pixel-identical; skip one generated boundary frame without trimming the original.'}

def get(studio,identity):
    if not isinstance(identity,str) or not re.fullmatch(r'continuation\.[0-9a-f]{64}',identity):raise StudioError('Continuation not found',404)
    return studio.store.read_snapshot(film._read(studio,'film.continuation.'+identity))

def validate(studio,identity,params=None,destination=None):
    record=get(studio,identity);source=record['source'];seq=film.sequence(studio,record['destination']['sequence_id'])
    if seq['revision']!=source['sequence_revision'] or seq.get('manifest_hash')!=source['sequence_manifest_hash']:
        raise StudioError('Continuation source sequence changed; prepare a new continuation from the current cut',409)
    film.validate_manifest(studio,studio.store.read_snapshot(seq['manifest']))
    studio.store.verify_master({'id':identity,**source['rendered_media']})
    film_images.verify(studio,record['first_frame_id'])
    if params is not None and params.get('first_frame_id')!=record['first_frame_id']:
        raise StudioError('Continuation requires its exact rendered boundary image',409)
    if destination is not None and destination!=record['destination']:
        raise StudioError('Continuation must be placed immediately after its unchanged source shot',409)
    return record

def prepare(studio,payload):
    with studio.lock:
        seq=film.sequence(studio,payload.get('sequence_id'))
        if type(payload.get('expected_revision')) is not int or payload['expected_revision']!=seq['revision']:
            raise StudioError('Source sequence changed; save/reload before continuing',409)
        identity=text(payload.get('shot_id'),'Source shot',100)
        index=next((i for i,s in enumerate(seq['shots']) if s['id']==identity),None)
        if index is None:raise StudioError('Choose a source shot in this sequence',404)
        if film.is_gap(seq['shots'][index]):raise StudioError('A gap has no picture to continue; choose a video shot',409)
        manifest=studio.store.read_snapshot(seq['manifest']);film.validate_manifest(studio,manifest)
        path,mime=film.export_media(studio,seq['id'],'media')
        if mime!='video/mp4':raise StudioError('Continuation requires rendered picture, not an audio-only sequence',409)
        if seq['export']['report']['manifest_hash']!=seq['manifest_hash']:raise StudioError('Export the current source sequence first',409)
        exported,_=film.export_media(studio,seq['id'],'manifest')
        if json.loads(exported.read_text(encoding="utf-8"))!=manifest:raise StudioError('Source export manifest changed',409)
        shot=seq['shots'][index];frame=sum(s['duration_frames'] for s in seq['shots'][:index+1])-1
        media={'path':path.relative_to(studio.store.root).as_posix(),'sha256':seq['export']['report']['sha256']}
        source={'sequence_id':seq['id'],'sequence_revision':seq['revision'],'sequence_manifest':seq['manifest'],
                'sequence_manifest_hash':seq['manifest_hash'],'shot_id':identity,'shot_index':index,
                'asset_id':shot['asset_id'],'source_in_frame':shot['source_in_frame'],'duration_frames':shot['duration_frames'],
                'last_used_source_frame':shot['source_in_frame']+shot['duration_frames']-1,
                'rendered_frame':frame,'frame_rate':24,'rendered_media':media,'shot':manifest['shots'][index]}
        result=subprocess.run([ffmpeg_path(),'-v','error','-nostdin','-protocol_whitelist','file,pipe','-i',str(path),
             '-vf',f'select=eq(n\\,{frame})','-frames:v','1','-f','image2pipe','-vcodec','png','pipe:1'],capture_output=True,timeout=120)
        if result.returncode or not result.stdout:raise StudioError('Could not extract the actual rendered boundary frame')
        lineage=studio.store.save_snapshot(source)
        image=film_images.import_bytes(studio,result.stdout,'continuation-boundary.png','Continue '+seq['title']+' / '+identity,
                                       {'kind':'rendered_shot_boundary','lineage':lineage,'rendered_frame':frame,'frame_rate':24})
        record={'kind':'film_shot_continuation_v1','source':source,'first_frame_id':image['id'],'image':image,
                'destination':{'sequence_id':seq['id'],'expected_revision':seq['revision'],'track':'V1','insert_index':index+1},
                'boundary_policy':POLICY}
        identity='continuation.'+sha256(canonical_bytes(record));record['id']=identity
        ref=studio.store.save_snapshot(record)
        studio.set_setting('film.continuation.'+identity,ref)
        return record
