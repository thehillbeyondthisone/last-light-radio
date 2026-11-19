"""Persistent generation intentions, reviewed placement and truthful metadata."""
from . import film, audio_tracks
from .studio import StudioError
from .generation import utc_now
from .store import canonical_bytes


def destination(studio, value, music=False, validate_revision=True):
    if value is None: return None
    if not isinstance(value, dict): raise StudioError('Choose a generation destination')
    seq = film.sequence(studio, value.get('sequence_id'))
    revision = value.get('expected_revision')
    if type(revision) is not int or revision < 0: raise StudioError('Destination revision is required')
    if validate_revision and revision != seq['revision']: raise StudioError('Destination sequence changed; reload and choose again',409)
    track = 'A2' if music else 'V1'
    if value.get('track') != track: raise StudioError('Choose '+track+' for this generator')
    field = 'start_frame' if music else 'insert_index'
    maximum = max(0,seq['duration_frames']-1) if music else len(seq['shots'])
    position = audio_tracks._integer(value.get(field), 'Destination '+field, 0, maximum if validate_revision else 14400)
    if music and validate_revision and not seq['duration_frames']: raise StudioError('Add picture before placing a music cue')
    return {'sequence_id':seq['id'],'expected_revision':revision,'track':track,field:position}


def metadata(config, done, studio):
    recipe = config['recipe']; params = config['parameters']
    models = {}
    if config.get('workflow'):
        graph = studio.store.read_snapshot(config['workflow'])
        for identity,node in graph.items():
            for key,value in node.get('inputs',{}).items():
                if key in {'unet_name','clip_name','vae_name','lora_name'}:
                    models[identity+':'+key]=value
    model = recipe.get('model') or next((v for k,v in models.items() if k.endswith(':unet_name')), 'Unknown model')
    return {'seed':params['seed'],'model':model,'models':models or {'model':model},'created':config['created'],
            'completed':done.get('created') if done else None,'completed_semantics':'result downloaded and verified locally','recipe_id':params['recipe_id'],
            'workflow_sha256':(done.get('workflow_sha256') if done else None) or config.get('workflow_sha256') or config.get('request_sha256'),
            'references':config.get('references',{}),'reference_images':params.get('reference_images',[]),'planned_shot':config.get('planned_shot'),
            'continuation':({'id':config['continuation']['id'],'source':{k:v for k,v in config['continuation']['source'].items() if k!='shot'},'destination':config['continuation']['destination'],'boundary_policy':config['continuation']['boundary_policy']} if config.get('continuation') else None),
            'settings':({**recipe,'frames':params['length_frames']} if params.get('length_frames') else recipe),'brief':params['brief'],
            **({'length_frames':params['length_frames']} if params.get('length_frames') else {})}


def bounded_provenance(studio, provenance):
    """Keep imported summaries bounded without discarding any original metadata."""
    if len(canonical_bytes(provenance)) <= 10000:
        return provenance
    full=studio.store.save_snapshot(provenance)
    meta=provenance.get('generation_metadata',{})
    compact={k:meta[k] for k in ('seed','model','models','created','completed','completed_semantics','recipe_id','workflow_sha256','requested_duration_seconds','returned_duration_seconds','decoded_duration_seconds','elapsed_seconds','elapsed_semantics','request_started_at','observed_stage','instrumental','length_frames') if k in meta}
    compact['full_metadata_receipt']=studio.store.save_snapshot(meta)
    compact['detail_storage']='Full metadata and brief are preserved in immutable checksum-verified receipts; this is a compact summary.'
    if 'brief' in meta:
        compact['brief_receipt']=studio.store.save_snapshot({'brief':meta['brief']})
        if len(meta['brief']) <= 1000:compact['brief']=meta['brief']
    if 'lyrics' in meta:compact['lyrics_receipt']=studio.store.save_snapshot({'lyrics':meta['lyrics'],'structure':meta.get('structure','')})
    refs={role:{'id':ref['id'],'label':ref.get('label'),'source_sha256':ref.get('source',{}).get('sha256'),
                'png_sha256':ref.get('png',{}).get('sha256'),'reference_receipt':studio.store.save_snapshot(ref)}
          for role,ref in meta.get('references',{}).items()}
    compact['references']=refs
    if meta.get('reference_images'):
        compact['reference_images']=[{'image_id':item['image_id'],'picture_number':i+1,
            'role_receipt':studio.store.save_snapshot({'role':item['role']})}
            for i,item in enumerate(meta['reference_images'])]
    if meta.get('planned_shot'):
        plan=meta['planned_shot'];slot=plan['slot']
        compact['planned_shot']={'plan_revision':plan['plan_revision'],'sequence_id':plan['sequence_id'],
                                 'slot':{k:slot[k] for k in ('id','label','start_frame','end_frame')}}
    if meta.get('continuation'):
        compact['continuation']={'id':meta['continuation']['id'],'full_receipt':studio.store.save_snapshot(meta['continuation'])}
    result={k:v for k,v in provenance.items() if k not in {'generation_metadata','references'}}
    result.update(generation_metadata=compact,full_provenance_receipt=full)
    if 'references' in provenance:result['references']=refs
    if len(canonical_bytes(result)) > 10000:
        # Many long/Unicode labels can exceed the import envelope even after
        # per-reference compaction. Keep ordered IDs + immutable full receipts.
        compact['references']={role:{'id':ref['id']} for role,ref in refs.items()}
        if 'references' in result: result['references']=compact['references']
        compact.pop('brief',None)
    if len(canonical_bytes(result)) > 10000:
        result={'kind':provenance.get('kind'),'local_job_id':provenance.get('local_job_id'),
                'full_provenance_receipt':full,
                'generation_metadata':{k:compact[k] for k in ('seed','model','recipe_id','workflow_sha256','full_metadata_receipt') if k in compact}}
    return result


def register(db, identity, dest):
    if dest:
        film._write(db,'film.generation.destination.'+identity,{'job_id':identity,'destination':dest,
                    'placed_revision':None,'error':None,'created':utc_now()})


def _provider(studio, identity):
    from . import film_generation, music_generation
    if film_generation.configuration(studio,identity): return film_generation
    if music_generation.configuration(studio,identity): return music_generation
    raise StudioError('Generation job not found',404)


def auto_import(studio, identity):
    # Every finished take imports by itself (Boden, 2026-11-19): generated clips simply exist in the Browser.
    provider=_provider(studio,identity)
    if studio.job(identity)['status']!='success':return
    if studio.setting('film.generation.import.'+identity):return
    try:
        studio.set_setting('film.generation.import_state.'+identity,{'stage':'importing','error':None})
        provider.import_completed(studio,identity)
        studio.set_setting('film.generation.import_state.'+identity,{'stage':'imported','error':None})
    except Exception as error:
        # A usable generated result remains successful even if candidate import fails.
        studio.set_setting('film.generation.import_state.'+identity,{'stage':'awaiting_import','error':str(error)})


def placement(studio, identity):
    record=studio.setting('film.generation.destination.'+identity)
    if not record:raise StudioError('This job has no timeline destination',404)
    job=studio.job(identity); seq=film.sequence(studio,record['destination']['sequence_id'])
    state=studio.setting('film.generation.import_state.'+identity,{})
    video_id=job.get('video_asset_id');audio_id=job.get('audio_asset_id')
    stage=job['status']; error=state.get('error')
    if record.get('placed_revision') is not None:stage='placed'
    elif stage=='success':
        if not audio_id or (record['destination']['track']=='V1' and not video_id):
            stage='importing' if state.get('stage')=='importing' else 'awaiting_import'
        else:
            stage='ready_to_place'
            error=None
            if seq['revision']!=record['destination']['expected_revision']:
                stage='conflict';error='Sequence changed. Review the current cut and explicitly choose a new insertion position.'
    planned=job.get('metadata',{}).get('planned_shot')
    if planned:
        from . import film_shot_plan
        try:plan,slot=film_shot_plan.find(studio,planned['slot']['id'])
        except StudioError:plan,slot=None,None
        receipt=studio.setting('film.plan.placement.'+planned['slot']['id'])
        if (receipt and receipt['candidate_id']=='job.'+identity and plan and receipt['plan_revision']==plan['revision']
                and seq['revision']==plan['sequence_revision'] and any(s['id']==planned['slot']['id'] and s.get('asset_id')==video_id for s in seq['shots'])):
            stage='placed';record={**record,'placed_revision':receipt['sequence_revision']};error=None
        elif not plan or plan['revision']!=planned['plan_revision'] or slot!=planned['slot'] or seq['revision']!=plan['sequence_revision']:
            stage='conflict';error='Shot assignment or sequence changed; review the current plan.'
        elif job['status']=='success' and video_id:
            stage='ready_to_place';error=None
    is_continuation=bool(job.get('metadata',{}).get('continuation'))
    suggested='preserve' if not is_continuation and not seq['shots'] and seq.get('timeline_duration_frames') is not None else 'ripple'
    return {**record,'suggested_audio_policy':suggested,'audio_policy_options':['ripple'] if is_continuation else ['preserve','ripple'],'job':job,'stage':stage,'video_asset_id':video_id,'audio_asset_id':audio_id,'error':error}


def listing(studio, sequence_id):
    film.sequence(studio,sequence_id)
    return {'placements':[placement(studio,r['job_id']) for r in film._records(studio,'film.generation.destination.')
                          if r['destination']['sequence_id']==sequence_id]}


def place(studio, identity, payload):
    with studio.lock:
        current=placement(studio,identity);dest=current['destination'];seq=film.sequence(studio,dest['sequence_id'])
        if current['job']['status']!='success':raise StudioError('Wait for generation to complete',409)
        provider=_provider(studio,identity);config=provider.configuration(studio,identity)
        if config.get('planned_shot'):
            from .film_shot_plan import place_job
            result=place_job(studio,current['job'],config,payload)
            return {**result,'placement':placement(studio,identity)}
        marker='gen-'+identity
        existing=next((x for x in (seq['shots'] if dest['track']=='V1' else seq['audio_tracks']) if x['id']==marker),None)
        if existing:
            # Recover an interrupted receipt write without inserting a second copy.
            if existing.get('asset_id')!=(current['video_asset_id'] if dest['track']=='V1' else current['audio_asset_id']):
                raise StudioError('Generated clip identity conflicts with this timeline',409)
            film.validate_manifest(studio,studio.store.read_snapshot(seq['manifest']))
            record={k:v for k,v in current.items() if k not in {'job','stage','video_asset_id','audio_asset_id'}}
            record.update(placed_revision=current.get('placed_revision') or seq['revision'],error=None)
            studio.set_setting('film.generation.destination.'+identity,record)
            return {'sequence':seq,'placement':placement(studio,identity)}
        if current.get('placed_revision') is not None:raise StudioError('This generated clip was already placed and subsequently removed; add it again from the Browser',409)
        if type(payload.get('expected_revision')) is not int or payload['expected_revision']!=seq['revision']:
            raise StudioError('Sequence changed; review the current cut before placing',409)
        provider=_provider(studio,identity);config=provider.configuration(studio,identity)
        continuation=config.get('continuation')
        if continuation:
            from .film_continuations import validate
            validate(studio,continuation['id'],config['parameters'],dest)
            if payload.get('insert_index')!=dest['insert_index']:raise StudioError('Continuation must follow its original source shot',409)
        audio_policy=payload.get('audio_policy',current['suggested_audio_policy'])
        if audio_policy not in {'preserve','ripple'}:raise StudioError('Choose keep audio timing or ripple later audio')
        if continuation and audio_policy!='ripple':raise StudioError('This continuation uses the frozen ripple audio policy',409)
        source_in=1 if continuation else 0
        audio=audio_tracks.get(studio,current['audio_asset_id'])
        shots=[dict(s) for s in seq['shots']];tracks=[dict(a) for a in seq['audio_tracks']]
        available=int(audio['sample_count']*24//audio['sample_rate'])
        if dest['track']=='V1':
            video=film.asset(studio,current['video_asset_id'])
            index=audio_tracks._integer(payload.get('insert_index'),'Insertion boundary',0,len(shots))
            start=sum(s['duration_frames'] for s in shots[:index]);duration=video['frame_count']-source_in
            if duration<1:raise StudioError('Continuation needs at least two generated frames before skipping its boundary frame',409)
            if available<duration+source_in:raise StudioError('Generated production sound is shorter than the picture',409)
            shots.insert(index,{'id':marker,'asset_id':video['id'],'source_in_frame':source_in,'duration_frames':duration})
            for track in tracks:
                if audio_policy=='ripple' and track['start_frame']>=start:track['start_frame']+=duration
            audio_marker=marker+'-production';role='production'
            chosen={'insert_index':index}
        else:
            start=audio_tracks._integer(payload.get('start_frame'),'Music start',0,seq['duration_frames']-1)
            duration=min(available,seq['duration_frames']-start)
            if duration<available and payload.get('accept_trim') is not True:
                raise StudioError(f'Music will be trimmed from {available} to {duration} frames to fit the sequence. Confirm accept_trim.',409)
            audio_marker=marker;role='music';chosen={'start_frame':start}
        tracks.append({'id':audio_marker,'asset_id':audio['id'],'role':role,'start_frame':start,'source_in_frame':source_in,
                       'duration_frames':duration,'gain_db':0,'fade_in_frames':0,'fade_out_frames':0,'enabled':True})
        edit={'expected_revision':seq['revision'],'title':seq['title'],
              'width':seq['width'],'height':seq['height'],'shots':shots,'audio_tracks':tracks}
        if seq.get('timeline_duration_frames') is not None:
            edit['timeline_duration_frames']=(seq['timeline_duration_frames']+duration if dest['track']=='V1' and audio_policy=='ripple'
                                              else max(seq['timeline_duration_frames'],sum(s['duration_frames'] for s in shots)))
        saved=film.save_sequence(studio,seq['id'],edit)
        record={k:v for k,v in current.items() if k not in {'job','stage','video_asset_id','audio_asset_id'}}
        record.update(placed_revision=saved['revision'],error=None,placed_at=utc_now(),
                      placement={'start_frame':start,'duration_frames':duration,'requested_duration_frames':available,'source_in_frame':source_in,'continuation_id':continuation['id'] if continuation else None,
                                 'audio_policy':audio_policy,'ripple_policy':('Shift audio starting at/after insertion; spanning audio unchanged' if audio_policy=='ripple' else 'Keep all existing audio start times unchanged'),**chosen})
        studio.set_setting('film.generation.destination.'+identity,record)
        return {'sequence':saved,'placement':placement(studio,identity)}
