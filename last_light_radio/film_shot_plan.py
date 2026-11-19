"""Audio-led contiguous shot assignments, independent of GPU scheduling."""
import json
import re
from . import film,film_images
from .studio import StudioError,text
from .store import canonical_bytes
from .generation import utc_now


def _slot_id(value):
    if not isinstance(value,str) or not re.fullmatch(r'plannedshot\.[0-9a-f]{32}',value):raise StudioError('Use a stable plannedshot ID followed by 32 hexadecimal characters')
    return value

def raw(studio,sequence_id):
    seq=film.sequence(studio,sequence_id)
    return studio.setting('film.shot-plan.'+sequence_id) or {'revision':0,'sequence_id':sequence_id,'sequence_revision':seq['revision'],'slots':[]}

def find(studio,slot_id):
    _slot_id(slot_id)
    seq_id=studio.setting('film.planned-slot.'+slot_id)
    if not seq_id:raise StudioError('Planned shot not found',404)
    plan=raw(studio,seq_id)
    slot=next((s for s in plan['slots'] if s['id']==slot_id),None)
    if not slot:raise StudioError('This planned shot was removed; its history is retained',409)
    return plan,slot

def candidates(studio,slot_id):
    result=[]
    for record in film._records(studio,'film.plan.candidate.'+slot_id+'.'):
        if record['kind']=='owned_generation':
            job=studio.job(record['job_id']);record={**record,'job':job,'asset_id':job.get('video_asset_id')}
        result.append(record)
    return result

def get(studio,sequence_id):
    plan=raw(studio,sequence_id);seq=film.sequence(studio,sequence_id)
    slots=[]
    for slot in plan['slots']:
        receipt=studio.setting('film.plan.placement.'+slot['id'])
        slots.append({**slot,'candidates':candidates(studio,slot['id']),
                      'placement':{**receipt,'stale':receipt['plan_revision']!=plan['revision']} if receipt else None})
    return {**plan,'stale':seq['revision']!=plan['sequence_revision'],'slots':slots}

def save(studio,sequence_id,payload):
    with studio.lock,studio.db() as db:
        db.execute('BEGIN IMMEDIATE');plan=raw(studio,sequence_id);seq=film.sequence(studio,sequence_id)
        if type(payload.get('expected_revision')) is not int or payload['expected_revision']!=plan['revision']:
            raise StudioError('Shot plan changed; reload before saving',409)
        if type(payload.get('expected_sequence_revision')) is not int or payload['expected_sequence_revision']!=seq['revision']:
            raise StudioError('Sequence changed; review it before anchoring the plan',409)
        slots=payload.get('slots')
        if not isinstance(slots,list) or len(slots)>128:raise StudioError('Use at most 128 planned shots')
        clean=[];cursor=0;ids=set()
        for slot in slots:
            if not isinstance(slot,dict):raise StudioError('Invalid planned shot')
            identity=_slot_id(slot.get('id'))
            if identity in ids:raise StudioError('Planned shot IDs must be unique')
            owner=studio.setting('film.planned-slot.'+identity)
            if owner and owner!=sequence_id:raise StudioError('Planned shot belongs to another sequence',409)
            start=slot.get('start_frame');end=slot.get('end_frame')
            if type(start) is not int or type(end) is not int or start!=cursor or not start<end<=seq['duration_frames']:
                raise StudioError('Plan contiguous positive intervals from frame zero, within the audio-led timeline')
            item={'id':identity,'label':text(slot.get('label'),'Shot label',200),'brief':text(slot.get('brief'),'Shot brief',4000),
                  'start_frame':start,'end_frame':end}
            for key in ('first_frame_id','last_frame_id'):
                value=slot.get(key)
                if value is not None:film_images.verify(studio,value)
                item[key]=value
            if slot.get('reference_images'):
                from . import h3_joint_av_recipe as recipe
                if slot.get('recipe_id') != recipe.R2V_RECIPE_ID or item['first_frame_id'] or item['last_frame_id']:
                    raise StudioError('Multi-image shots require the reference-to-video recipe without first/last frames')
                item['reference_images'] = film_images.reference_parameters(slot['reference_images'])
                for ref in item['reference_images']: film_images.verify(studio, ref['image_id'])
                item['recipe_id'] = recipe.R2V_RECIPE_ID
            elif slot.get('recipe_id'):
                from . import h3_joint_av_recipe as recipe
                if slot['recipe_id'] != recipe.RECIPE_ID: raise StudioError('Reference-to-video requires image references')
                item['recipe_id'] = recipe.RECIPE_ID
            if 'production_reference_bindings' in slot:
                from .film_references import resolve
                bindings = slot['production_reference_bindings']
                resolved = resolve(studio, seq['project_id'], bindings)
                if item.get('reference_images') and [b['selected_image_id'] for b in resolved] != [r['image_id'] for r in item['reference_images']]:
                    raise StudioError('Ordered reference images must match the pinned production-reference views')
                item['production_reference_bindings'] = bindings
            ids.add(identity);cursor=end;clean.append(item)
        record={**plan,'revision':plan['revision']+1,'sequence_revision':seq['revision'],'slots':clean}
        studio.store.save_snapshot(record)
        film._write(db,'film.shot-plan.'+sequence_id,record)
        for slot in clean:film._write(db,'film.planned-slot.'+slot['id'],sequence_id)
    return get(studio,sequence_id)

def anchor(studio,params):
    plan,slot=find(studio,params.get('planned_shot_id'))
    seq=film.sequence(studio,plan['sequence_id'])
    if type(params.get('planned_revision')) is not int or params['planned_revision']!=plan['revision']:
        raise StudioError('Shot plan changed; reload its current assignment',409)
    if seq['revision']!=plan['sequence_revision']:raise StudioError('Sequence changed outside the plan; explicitly review and save the plan again',409)
    if params.get('continuation_id'):raise StudioError('Use either a planned shot or continuation, not both')
    if params['brief']!=slot['brief'] or any(params.get(k)!=slot[k] for k in ('first_frame_id','last_frame_id')):
        raise StudioError('Generation brief and reference roles must match this saved shot assignment',409)
    from . import h3_joint_av_recipe as recipe
    if (params.get('recipe_id',recipe.RECIPE_ID) != slot.get('recipe_id',recipe.RECIPE_ID)
            or params.get('reference_images',[]) != slot.get('reference_images',[])):
        raise StudioError('Generation recipe and ordered reference images must match the saved shot assignment',409)
    if slot['end_frame']-slot['start_frame']>124:raise StudioError('This H3 recipe yields 124 frames, shorter than the planned interval; shorten or split the assignment before generating')
    result = {'plan_revision':plan['revision'],'sequence_id':plan['sequence_id'],'slot':slot}
    if slot.get('production_reference_bindings'):
        from .film_references import resolve
        result['production_references'] = resolve(studio, seq['project_id'], slot['production_reference_bindings'])
    return result

def destination(studio,anchored):
    plan=raw(studio,anchored['sequence_id'])
    return {'sequence_id':plan['sequence_id'],'expected_revision':plan['sequence_revision'],'track':'V1',
            'insert_index':next(i for i,s in enumerate(plan['slots']) if s['id']==anchored['slot']['id'])}

def register(db,identity,anchored):
    if not anchored:return
    slot=anchored['slot']['id'];record={'id':'job.'+identity,'kind':'owned_generation','job_id':identity,'asset_id':None,
        'planned_shot_id':slot,'plan_revision':anchored['plan_revision'],'created':utc_now(),'provenance':{'kind':'owned_job','job_id':identity,'assignment':anchored}}
    film._write(db,'film.plan.candidate.'+slot+'.'+record['id'],record)

def attach(studio,sequence_id,slot_id,payload):
    plan,slot=find(studio,slot_id)
    if plan['sequence_id']!=sequence_id:raise StudioError('Planned shot belongs to another sequence',409)
    asset=film.asset(studio,payload.get('asset_id'));film.asset_media(studio,asset['id'])
    identity='existing.'+asset['source']['sha256']
    record={'id':identity,'kind':'existing_asset','asset_id':asset['id'],'job_id':None,'planned_shot_id':slot_id,
            'plan_revision':plan['revision'],'created':utc_now(),'provenance':{'kind':'explicit_existing_asset_reuse','asset_receipt':studio.store.save_snapshot(asset)}}
    key='film.plan.candidate.'+slot_id+'.'+identity
    with studio.lock,studio.db() as db:
        if not studio.setting(key):film._write(db,key,record)
    return get(studio,sequence_id)

def place(studio,sequence_id,slot_id,payload):
    with studio.lock:
        plan,slot=find(studio,slot_id);seq=film.sequence(studio,sequence_id)
        if plan['sequence_id']!=sequence_id:raise StudioError('Planned shot belongs to another sequence',409)
        if payload.get('expected_revision')!=plan['revision']:raise StudioError('Shot plan changed; reload before fitting',409)
        candidate=next((c for c in candidates(studio,slot_id) if c['id']==payload.get('candidate_id')),None)
        if not candidate or not candidate.get('asset_id'):raise StudioError('Choose a completed candidate for this planned shot',409)
        if candidate['kind']=='owned_generation':
            job=candidate['job']
            if job['status']!='success':raise StudioError('Wait for generation to complete',409)
            anchored=job['metadata']['planned_shot']
            if anchored['plan_revision']!=plan['revision'] or anchored['slot']!=slot:
                raise StudioError('This take belongs to an earlier assignment; explicitly attach its source as reused media if desired',409)
        source_in=payload.get('source_in_frame',0)
        receipt=studio.setting('film.plan.placement.'+slot_id)
        existing=next((s for s in seq['shots'] if s['id']==slot_id),None)
        if (receipt and receipt['candidate_id']==candidate['id'] and receipt['plan_revision']==plan['revision']
                and existing and existing.get('asset_id')==candidate['asset_id'] and existing['source_in_frame']==source_in
                and existing['duration_frames']==slot['end_frame']-slot['start_frame'] and seq['revision']==plan['sequence_revision']):
            film.validate_manifest(studio,studio.store.read_snapshot(seq['manifest']))
            return {'sequence':seq,'plan':get(studio,sequence_id)}
        if seq['revision']!=plan['sequence_revision'] or payload.get('expected_sequence_revision')!=seq['revision']:
            raise StudioError('Sequence changed; review and re-anchor the shot plan before fitting',409)
        saved=film.place_picture_interval(studio,sequence_id,{'expected_revision':seq['revision'],'shot_id':slot_id,
            'asset_id':candidate['asset_id'],'start_frame':slot['start_frame'],'end_frame':slot['end_frame'],
            'source_in_frame':source_in,'trim_to_fit':payload.get('trim_to_fit',False)})
        receipt={'candidate_id':candidate['id'],'sequence_revision':saved['revision'],'plan_revision':plan['revision'],
                 'source_in_frame':source_in,'interval':{'start_frame':slot['start_frame'],'end_frame':slot['end_frame']},'created':utc_now()}
        with studio.db() as db:
            studio.store.save_snapshot(receipt)
            film._write(db,'film.plan.placement.'+slot_id,receipt)
            film._write(db,'film.shot-plan.'+sequence_id,{**plan,'sequence_revision':saved['revision']})
        return {'sequence':saved,'plan':get(studio,sequence_id)}

def place_job(studio,job,config,payload):
    anchored=config['planned_shot'];plan,slot=find(studio,anchored['slot']['id'])
    return place(studio,plan['sequence_id'],slot['id'],{'candidate_id':'job.'+job['id'],
        'expected_revision':anchored['plan_revision'],'expected_sequence_revision':payload.get('expected_revision'),
        'source_in_frame':payload.get('source_in_frame',0),'trim_to_fit':payload.get('trim_to_fit',False)})
