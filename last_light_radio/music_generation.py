"""Explicit ACE-Step music jobs, with isolated provider execution and immutable receipts."""
import base64
import io
import json
import re
import subprocess
import tempfile
import threading
import time
import wave
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from . import ace_step_recipe as recipe
from .ace_step_client import AceClient, normalize_url, task_id
from .comfy import ComfyError
from .generation import utc_now, job_folder, record_event
from .store import canonical_bytes, sha256
from .studio import StudioError, text
from .video_tools import ffmpeg_path

ACTIVE={'pending','submitting','queued','running','unknown'}

def _stamp(value):return datetime.fromtimestamp(value,timezone.utc).isoformat()
def _client(studio,url):return getattr(studio,'music_client_factory',AceClient)(url,timeout=10)

def _params(payload,submission=False):
    allowed={'recipe_id','worker_url','brief','seed','duration_seconds','instrumental','lyrics','structure'}|({'label','preflight_id','request_id','destination'} if submission else set())
    if set(payload)-allowed:raise StudioError('This tested instrumental recipe permits only cue brief and seed changes')
    if payload.get('recipe_id') not in {recipe.RECIPE_ID,recipe.FULL_RECIPE_ID}:raise StudioError('Choose an installed ACE-Step recipe',409)
    full=payload['recipe_id']==recipe.FULL_RECIPE_ID
    duration=payload.get('duration_seconds',180 if full else 30)
    if type(duration) is not int or duration not in (recipe.FULL_DURATIONS if full else (30,)):
        raise StudioError('Choose 180, 210 or 240 seconds for the full-song recipe, or 30 for the proven cue')
    seed=payload.get('seed')
    if type(seed) is not int or not 0<=seed<=2147483647:raise StudioError('Seed must be an integer from 0 to 2147483647')
    instrumental=payload.get('instrumental',True)
    if type(instrumental) is not bool:raise StudioError('Choose instrumental or vocals explicitly')
    lyrics=payload.get('lyrics','[Instrumental]' if instrumental else '')
    structure=payload.get('structure','')
    if not full and (not instrumental or lyrics!='[Instrumental]' or structure):raise StudioError('Use the versioned full-song recipe for custom lyrics or structure')
    if instrumental and lyrics not in ('','[Instrumental]'):raise StudioError('Instrumental mode cannot silently ignore supplied lyrics')
    if instrumental:lyrics='[Instrumental]'
    if not isinstance(lyrics,str) or not lyrics.strip() or len(lyrics)>20000:raise StudioError('Provide complete lyrics up to 20000 characters')
    if not isinstance(structure,str) or len(structure)>4000:raise StudioError('Song structure must be text up to 4000 characters')
    params={'recipe_id':payload['recipe_id'],'worker_url':normalize_url(payload.get('worker_url')),
            'brief':text(payload.get('brief'),'Music cue brief',8000 if full else 4000),'seed':seed}
    if full:params.update(duration_seconds=duration,instrumental=instrumental,lyrics=lyrics,structure=structure)
    return params

def _check(client):
    errors=[];evidence={}
    try:
        evidence=client.probe()
        health=evidence.get('health',{}).get('data',{})
        inventory=evidence.get('models',{}).get('data',{})
        if health.get('status')!='ok' or health.get('service')!='ACE-Step Gradio API':
            errors.append({'code':'WRONG_SERVICE','message':'Expected the verified ACE-Step Gradio API at this loopback endpoint'})
        models=inventory.get('models',[])
        if (not isinstance(models,list) or not any(isinstance(m,dict) and m.get('name')=='acestep-v15-turbo' for m in models)
                or inventory.get('default_model')!='acestep-v15-turbo'):
            errors.append({'code':'MODEL_NOT_READY','message':'The tested acestep-v15-turbo model is not the loaded default; no model will be loaded or switched automatically'})
    except ComfyError as error:errors.append(error.to_dict())
    return {'ready':not errors,'errors':errors,'evidence':evidence,
            'warnings':[{'code':'SYNCHRONOUS_TASK_ID','message':'ACE-Step returns its task ID after generation. A lost response cannot be retried safely.'}]}

def preflight(studio,payload):
    params=_params(payload);check=_check(_client(studio,params['worker_url']));now=time.time()
    if params['recipe_id']==recipe.FULL_RECIPE_ID:
        check['warnings'].append({'code':'FULL_SONG_NOT_CALIBRATED','message':'This bounded full-song recipe is API-compatible but has not been rendered in this integration. Runtime LM state is unknown; no model settings will be changed.'})
    record={'kind':'music_preflight','parameters':params,'recipe':recipe.public_recipe(params['recipe_id'],params.get('duration_seconds'),params.get('instrumental',True)),'ready':check['ready'],
            'errors':check['errors'],'warnings':check['warnings'],'checked_at':_stamp(now),'expires_at':_stamp(now+600),'expires_epoch':now+600,
            'evidence':studio.store.save_snapshot(check['evidence'],kind='jobs')}
    ref=studio.store.save_snapshot(record,kind='jobs');studio.set_setting('music.preflight.'+ref['sha256'],ref)
    return {**{k:record[k] for k in ('ready','errors','warnings','checked_at','expires_at')},'id':ref['sha256'],
            'recipe_id':params['recipe_id'],'worker_url':params['worker_url']}

def configuration(studio,identity):
    if not isinstance(identity,str) or not re.fullmatch(r'[0-9a-f]{32}',identity):return None
    path=studio.store.resolve(f'records/music_generation/{identity}.json')
    return studio.store.read_snapshot(json.loads(path.read_text())) if path.is_file() else None

def _completion(studio,identity):
    path=studio.store.resolve(f'candidates/{identity}/music_completion.json')
    return studio.store.read_snapshot(json.loads(path.read_text())) if path.is_file() else None

def _metadata(studio,config,done):
    from .generation_timeline import metadata
    elapsed=None;started=None;identity=config['local_job_id']
    accepted=studio.store.resolve(job_folder(identity)+'/accepted.json').is_file()
    if studio.store.resolve(job_folder(identity)+'/request.json').is_file():
        request=_load_request(studio,identity);started=request['created']
        end=datetime.fromisoformat(done['created']).timestamp() if done else time.time()
        elapsed=max(0,end-datetime.fromisoformat(started).timestamp())
    return {**metadata(config,done,studio),'requested_duration_seconds':config['parameters'].get('duration_seconds',30),
            'returned_duration_seconds':done.get('returned_duration_seconds') if done else None,
            'decoded_duration_seconds':done['audio']['inspection']['duration_seconds'] if done else None,
            'elapsed_seconds':elapsed,'elapsed_semantics':'Time since the generation request began, not progress or GPU execution time',
            'request_started_at':started,'observed_stage':'result_verified' if done else ('accepted_result_available' if accepted else ('awaiting_service_response' if started else 'not_submitted')),
            'instrumental':config['parameters'].get('instrumental',True),
            'lyrics':config['parameters'].get('lyrics','[Instrumental]'),'structure':config['parameters'].get('structure','')}


def job_details(studio,identity):
    config=configuration(studio,identity)
    if not config:return {}
    imported=studio.setting('music.import.'+identity,{})
    from .generation_timeline import metadata
    done=_completion(studio,identity);elapsed=None
    if studio.store.resolve(job_folder(identity)+'/request.json').is_file():
        request=_load_request(studio,identity)
        end=datetime.fromisoformat(done['created']).timestamp() if done else time.time()
        elapsed=max(0,end-datetime.fromisoformat(request['created']).timestamp())
    return {'requested_duration_seconds':config['parameters'].get('duration_seconds',30),
            'returned_duration_seconds':done.get('returned_duration_seconds') if done else None,
            'decoded_duration_seconds':done['audio']['inspection']['duration_seconds'] if done else None,
            'elapsed_seconds':elapsed,'elapsed_semantics':'Time since the generation request began, not progress or GPU execution time',
            'pipeline':recipe.PIPELINE,'recipe_id':config['parameters']['recipe_id'],
            'ready_to_import':bool(_completion(studio,identity)),'audio_asset_id':imported.get('audio_asset_id'),
            'import_error':None if imported else studio.setting('film.generation.import_state.'+identity,{}).get('error'),
            'import_stage':None if imported else studio.setting('film.generation.import_state.'+identity,{}).get('stage'),
            'provider':'ACE-Step','submission_is_synchronous':True,
            'instrumental':config['parameters'].get('instrumental',True),'lyrics':config['parameters'].get('lyrics','[Instrumental]'),
            'structure':config['parameters'].get('structure',''),
            'destination':config.get('destination'),'metadata':_metadata(studio,config,_completion(studio,identity))}

def state(studio):
    return {'recipe':recipe.public_recipe(),'recipes':[recipe.public_recipe(),recipe.public_recipe(recipe.FULL_RECIPE_ID)],'worker_url':studio.setting('music.worker_url',recipe.DEFAULT_URL),
            'upload_capability':{'begin_url':'/api/audio/uploads','max_bytes':256*1024*1024,'max_duration_seconds':600,'content_type':'application/octet-stream'},
            'jobs':[j for j in studio.jobs() if j.get('pipeline')==recipe.PIPELINE]}

def get_job(studio,identity):
    if not configuration(studio,identity):raise StudioError('Music job not found',404)
    return studio.job(identity)

def submit(studio,payload):
    from . import generation_timeline as timeline
    params=_params(payload,True);label=text(payload.get('label'),'Cue name',100)
    request_id=text(payload.get('request_id'),'Generation request ID',100)
    with studio.lock,studio.db() as db:
        row=db.execute('SELECT id FROM jobs WHERE request_id=?',(request_id,)).fetchone()
        if row:
            prior=configuration(studio,row[0])
            if not prior or prior['parameters']!=params or prior['label']!=label or prior.get('destination')!=timeline.destination(studio,payload.get('destination'),music=True,validate_revision=False):raise StudioError('Request ID belongs to different generation settings',409)
            return studio.job(row[0])
        token=payload.get('preflight_id')
        if not isinstance(token,str) or not re.fullmatch(r'[0-9a-f]{64}',token):raise StudioError('Run preflight before generating',409)
        ref=studio.setting('music.preflight.'+token)
        if not ref:raise StudioError('Preflight token not found',409)
        checked=studio.store.read_snapshot(ref)
        if (not checked['ready'] or checked['expires_epoch']<time.time() or checked['parameters']!=params or checked['recipe']!=recipe.public_recipe(params['recipe_id'],params.get('duration_seconds'),params.get('instrumental',True))):
            raise StudioError('Preflight is stale or does not match this cue, seed, endpoint and recipe',409)
        dest=timeline.destination(studio,payload.get('destination'),music=True)
        identity=uuid4().hex;request=recipe.prepared(params['brief'],params['seed'],params.get('duration_seconds',30),params.get('lyrics','[Instrumental]'),params.get('structure',''))
        config={'kind':'owned_music_job','pipeline':recipe.PIPELINE,'local_job_id':identity,'label':label,
                'request_id':request_id,'parameters':params,'destination':dest,'recipe':recipe.public_recipe(params['recipe_id'],params.get('duration_seconds'),params.get('instrumental',True)),'preflight':ref,
                'request':studio.store.save_snapshot(request,kind='jobs'),'request_sha256':sha256(canonical_bytes(request)),'created':utc_now()}
        studio.store.write_once(f'records/music_generation/{identity}.json',canonical_bytes(studio.store.save_snapshot(config,kind='jobs')))
        db.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?)',(identity,'',label,params['brief'],params['seed'],'pending',None,utc_now(),request_id))
        timeline.register(db,identity,dest)
    return studio.job(identity)

def _status(studio,identity,status,error=None):
    with studio.db() as db:db.execute('UPDATE jobs SET status=?,error=? WHERE id=?',(status,json.dumps(error) if error else None,identity))

def _load_request(studio,identity):
    pointer=json.loads(studio.store.resolve(job_folder(identity)+'/request.json').read_text())
    request=studio.store.read_snapshot(pointer)
    if request.get('kind')!='music_generation_request' or request.get('local_job_id')!=identity:raise ComfyError('INVALID_JOB_RECORD','Music request ownership mismatch')
    payload=studio.store.read_snapshot(request['payload'])
    if sha256(canonical_bytes(payload))!=request['request_sha256']:raise ComfyError('REQUEST_CHECKSUM_MISMATCH','Frozen music request changed')
    return request

def _start(studio,config):
    identity=config['local_job_id'];folder=job_folder(identity)
    if studio.store.resolve(folder).exists():raise ComfyError('SUBMISSION_UNRESOLVED','Music request already exists; never submit it again')
    ffmpeg_path();client=_client(studio,config['parameters']['worker_url']);check=_check(client)
    if not check['ready']:raise ComfyError('PREFLIGHT_CHANGED','ACE-Step is no longer ready; nothing was submitted',errors=check['errors'])
    payload=studio.store.read_snapshot(config['request'])
    if sha256(canonical_bytes(payload))!=config['request_sha256']:raise ComfyError('REQUEST_CHECKSUM_MISMATCH','Frozen music payload changed')
    request={'kind':'music_generation_request','pipeline':recipe.PIPELINE,'local_job_id':identity,
             'base_url':client.base_url,'payload':config['request'],'request_sha256':config['request_sha256'],
             'recipe':config['recipe'],'parameters':config['parameters'],'preflight':config['preflight'],
             'service_evidence':studio.store.save_snapshot(check['evidence'],kind='jobs'),'created':utc_now()}
    studio.store.write_once(folder+'/request.json',canonical_bytes(studio.store.save_snapshot(request,kind='jobs')))
    record_event(studio.store,identity,'submitting',provider='ACE-Step',synchronous_task_id=True)
    response=client.submit(payload)  # One bounded long request on this provider's thread only.
    remote_id=task_id(response['data']['task_id'])
    accepted={'local_job_id':identity,'base_url':client.base_url,'request_sha256':config['request_sha256'],
              'task_id':remote_id,'response':response,'received_epoch':time.time(),'received':utc_now()}
    studio.store.write_once(folder+'/accepted.json',canonical_bytes(accepted))
    record_event(studio.store,identity,'queued',task_id=remote_id)
    _status(studio,identity,'queued')

def _inspect_wav(studio,path,requested_duration=30):
    # The proven WAV is IEEE float32; Python wave cannot read it directly.
    with tempfile.TemporaryDirectory(prefix='music-inspect-',dir=studio.store.root) as temporary:
        pcm=Path(temporary)/'decoded.wav'
        result=subprocess.run([ffmpeg_path(),'-v','error','-nostdin','-protocol_whitelist','file,pipe','-i',str(path),
                               '-map','0:a:0','-t',str(requested_duration+1),'-ac','2','-ar','48000','-c:a','pcm_s24le',str(pcm)],capture_output=True,timeout=300)
        if result.returncode or not pcm.is_file():raise ComfyError('INVALID_MUSIC_AUDIO','Generated WAV could not be fully decoded')
        with wave.open(str(pcm),'rb') as source:count,rate,channels=source.getnframes(),source.getframerate(),source.getnchannels()
    duration=count/rate
    if abs(duration-requested_duration)>.1:raise ComfyError('MUSIC_DURATION_MISMATCH','Decoded music duration differs from the frozen request; no truncated result is accepted',requested_duration_seconds=requested_duration,decoded_duration_seconds=duration)
    return {'duration_seconds':duration,'sample_rate':rate,'channels':channels,'sample_count':count,'fully_decoded':True}

def _poll(studio,config):
    identity=config['local_job_id'];done=_completion(studio,identity)
    if done:
        studio.store.verify_master({'id':identity,**done['audio']});_status(studio,identity,'success');return
    request=_load_request(studio,identity)
    path=studio.store.resolve(job_folder(identity)+'/accepted.json')
    if not path.is_file():raise ComfyError('SUBMISSION_UNRESOLVED','ACE-Step task ID was not received; never repeat release_task automatically')
    accepted=json.loads(path.read_text())
    if any(accepted.get(k)!=request.get(k) for k in ('local_job_id','base_url','request_sha256')):
        raise ComfyError('INVALID_JOB_RECORD','ACE-Step accepted receipt does not match the request')
    client=_client(studio,request['base_url']);response=client.poll(task_id(accepted['task_id']))
    rows=response.get('data')
    if not isinstance(rows,list) or len(rows)!=1 or rows[0].get('task_id')!=accepted['task_id']:
        raise ComfyError('TASK_ID_MISMATCH','Music result belongs to another task')
    row=rows[0]
    if type(row.get('status')) is not int:raise ComfyError('INVALID_RESPONSE','Music task status must be an integer')
    if row.get('status')==0:
        deadline=studio.setting('music.poll_deadline.'+identity,accepted['received_epoch']+300)
        if time.time()>deadline:
            _status(studio,identity,'result_unconfirmed',{'code':'RESULT_UNCONFIRMED','message':'ACE-Step reports no completed result. Its API cannot distinguish missing, still-running or failed tasks. Automatic polling stopped; Resume only checks the same task.'})
        else:_status(studio,identity,'running')
        return
    if type(row.get('status')) is not int or row['status']!=1:raise ComfyError('INVALID_RESPONSE','Unsupported music result status')
    try:outputs=json.loads(row.get('result',''))
    except (TypeError,ValueError):raise ComfyError('INVALID_RESPONSE','Music result was not valid JSON') from None
    if not isinstance(outputs,list) or len(outputs)!=1 or not isinstance(outputs[0],dict):raise ComfyError('INVALID_RESPONSE','Expected one owned instrumental cue')
    result=outputs[0];payload=studio.store.read_snapshot(request['payload'])
    expected={'seed':payload['seed'],'caption':payload['prompt'],'lyrics':payload['lyrics'],'bpm':80,'duration':payload['audio_duration'],'keyscale':'D minor','timesignature':'4'}
    if result.get('duration')!=payload['audio_duration']:
        raise ComfyError('MUSIC_DURATION_MISMATCH','Returned duration differs from the frozen request',requested_duration_seconds=payload['audio_duration'],returned_duration_seconds=result.get('duration'))
    for key,value in expected.items():
        if key not in result or result[key]!=value:raise ComfyError('MUSIC_PROVENANCE_MISMATCH','Music result metadata differs from the frozen request',field=key)
    relative=f'candidates/{identity}/music-original.wav'
    if hasattr(client,'download_to'):
        with tempfile.TemporaryDirectory(prefix='music-download-',dir=studio.store.root) as temporary:
            downloaded=Path(temporary)/'native.wav'
            transfer=client.download_to(result,downloaded)
            studio.store.write_file_once(relative,downloaded,expected_sha256=transfer['sha256'])
    else:
        # Compatibility for deterministic in-memory test clients, never the production client.
        data=client.download(result)
        if len(data)>256*1024*1024:raise ComfyError('RESPONSE_TOO_LARGE','Generated WAV exceeds 256 MiB')
        transfer={'sha256':sha256(data),'bytes':len(data)}
        studio.store.write_once(relative,data)
    inspection=_inspect_wav(studio,studio.store.resolve(relative),payload['audio_duration'])
    done={'kind':'music_completion','pipeline':recipe.PIPELINE,'local_job_id':identity,'task_id':accepted['task_id'],
          'request':request,'accepted_receipt':accepted,'result_receipt':studio.store.save_snapshot(response,kind='jobs'),
          'recipe':config['recipe'],'requested_duration_seconds':payload['audio_duration'],'returned_duration_seconds':result['duration'],
          'decoded_duration_seconds':inspection['duration_seconds'],'audio':{'path':relative,**transfer,'inspection':inspection},
          'created':utc_now(),'review_status':'candidate'}
    studio.store.write_once(f'candidates/{identity}/music_completion.json',canonical_bytes(studio.store.save_snapshot(done,kind='jobs')))
    record_event(studio.store,identity,'downloaded',audio_sha256=done['audio']['sha256']);_status(studio,identity,'success')

def process_owned_job(studio,identity):
    """One owned state transition; caller supplies a separate provider lock."""
    try:
        config=configuration(studio,identity);job=studio.job(identity)
        if not config:raise StudioError('Music job configuration is missing',409)
        if job['status']=='pending':_status(studio,identity,'submitting');_start(studio,config)
        else:_poll(studio,config)
        from .generation_timeline import auto_import
        auto_import(studio,identity)
    except Exception as error:
        details=error.to_dict() if isinstance(error,ComfyError) else {'code':type(error).__name__,'message':str(error)}
        status='submission_unknown' if details['code'] in {'SUBMISSION_AMBIGUOUS','SUBMISSION_UNRESOLVED'} else 'failed'
        _status(studio,identity,status,details)

def dispatch(studio,identity):
    """Never hold H3's job lock during synchronous ACE-Step generation."""
    with studio.lock:
        if studio.job(identity)['status'] not in ACTIVE:return
        lock=getattr(studio,'music_provider_lock',None)
        if lock is None:lock=threading.Lock();studio.music_provider_lock=lock
        if not lock.acquire(blocking=False):return
        def run():
            try:process_owned_job(studio,identity)
            finally:lock.release()
        thread=threading.Thread(target=run,name='music-job-'+identity[:8],daemon=True)
        studio.music_provider_thread=thread
        try:thread.start()
        except Exception:lock.release();raise

def resume(studio,identity):
    job=get_job(studio,identity)
    if not job['can_resume']:raise StudioError('No ACE-Step task ID was received; an uncertain submission cannot be resumed or resubmitted safely',409)
    if job['status']=='success':return job
    studio.set_setting('music.poll_deadline.'+identity,time.time()+60)
    record_event(studio.store,identity,'resume_requested',poll_only=True)
    return studio.resume(identity)

def import_completed(studio,identity):
    job=get_job(studio,identity)
    if job['status']!='success':raise StudioError('Wait for the owned music result before importing',409)
    done=_completion(studio,identity)
    if not done:raise StudioError('Music completion receipt is missing',409)
    studio.store.verify_master({'id':identity,**done['audio']})
    receipt=studio.store.save_snapshot(done,kind='jobs')
    from . import audio_tracks
    from .generation_timeline import metadata,bounded_provenance
    audio=audio_tracks.import_file(studio,studio.store.resolve(done['audio']['path']),'ace-step-music.wav',job['label'],
        bounded_provenance(studio,{'generation_metadata':_metadata(studio,configuration(studio,identity),done),'kind':'owned_ace_step_music','local_job_id':identity,'task_id':done['task_id'],
                      'recipe_sha256':done['recipe']['recipe_sha256'],'generation_receipt':receipt,'original_sha256':done['audio']['sha256'],
                      'requested_duration_seconds':done.get('requested_duration_seconds',30),
                      'returned_duration_seconds':done.get('returned_duration_seconds'),
                      'decoded_duration_seconds':done['audio']['inspection']['duration_seconds'],
                      'lyrics_receipt':studio.store.save_snapshot({'lyrics':configuration(studio,identity)['parameters'].get('lyrics','[Instrumental]'),'structure':configuration(studio,identity)['parameters'].get('structure','')})}))
    studio.set_setting('music.import.'+identity,{'audio_asset_id':audio['id'],'receipt':receipt})
    return {'audio':audio,'job':studio.job(identity)}
