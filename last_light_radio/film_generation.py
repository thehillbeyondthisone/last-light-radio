"""Explicit text-to-joint-AV jobs using the existing Studio-owned job lifecycle.

Preflight is read-only. Only an explicit jobs POST may create a pending job.
Polling and import never submit. Text-only requests have no invented scene/master.
"""
from __future__ import annotations
import base64
import copy
import io
import json
import re
import subprocess
import tempfile
import time
import wave
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from . import h3_joint_av_recipe as recipe
from .comfy import ComfyClient, ComfyError, inspect_workflow, workflow_sha256
from .generation import utc_now, job_folder, record_event
from .store import canonical_bytes, sha256
from .studio import StudioError, text
from .video_tools import ffmpeg_path
from .pilot_media import inspect_video

TOKEN_SECONDS = 600

def _stamp(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat()

def _parameters(payload, *, submission=False):
    allowed = {'recipe_id','worker_url','brief','seed','first_frame_id','last_frame_id','continuation_id','planned_shot_id','planned_revision','reference_images','length_frames'}
    if submission:
        allowed |= {'label','preflight_id','request_id','destination'}
    if set(payload)-allowed:
        raise StudioError('Choose brief, seed and imported first/last-frame sources; other overrides are not supported')
    if payload.get('recipe_id') not in (recipe.RECIPE_ID, recipe.R2V_RECIPE_ID):
        raise StudioError('Choose the installed joint-AV recipe',409)
    brief = text(payload.get('brief'),'Shot and sound brief',4000)
    seed = payload.get('seed')
    if type(seed) is not int or not 0 <= seed <= 2147483647:
        raise StudioError('Seed must be an integer from 0 to 2147483647')
    url = ComfyClient(text(payload.get('worker_url'),'Worker URL',500)).base_url
    params={'recipe_id':payload['recipe_id'],'worker_url':url,'brief':brief,'seed':seed}
    if payload.get('length_frames') is not None:
        try:params['length_frames']=recipe.frames(payload['length_frames'])
        except ValueError as error:raise StudioError(str(error)) from None
    for key in ('first_frame_id','last_frame_id','continuation_id','planned_shot_id'):
        if payload.get(key) is not None:params[key]=text(payload[key],key,100)
    if payload.get('planned_shot_id'):
        if type(payload.get('planned_revision')) is not int:raise StudioError('Planned shot revision is required')
        params['planned_revision']=payload['planned_revision']
    elif 'planned_revision' in payload:raise StudioError('Choose a planned shot for this revision')
    from . import film_images
    if params['recipe_id'] == recipe.R2V_RECIPE_ID:
        if any(params.get(k) for k in ('first_frame_id','last_frame_id','continuation_id')):
            raise StudioError('Reference-to-video cannot combine first/last-frame or continuation conditioning')
        params['reference_images'] = film_images.reference_parameters(payload.get('reference_images'))
    elif payload.get('reference_images'):
        raise StudioError('Choose the reference-to-video recipe for multiple reference images')
    return params

def normalized_definitions(graph, definitions):
    """Expand the worker's selected V3 nested combo branches, without skipping them."""
    result = copy.deepcopy(definitions)
    for node in graph.values():
        definition = result.get(node['class_type'])
        if not isinstance(definition,dict):
            continue
        flat = {'required':{},'optional':{}}
        values = node['inputs']
        def add(name, spec, category):
            if not isinstance(spec,list) or not spec:
                flat[category][name] = spec
                return
            kind = spec[0]
            options = spec[1] if len(spec)>1 and isinstance(spec[1],dict) else {}
            if kind == 'COMBO':
                choices = options.get('options')
                if not isinstance(choices,list):
                    raise ComfyError('INVALID_NODE_DEFINITION','Worker COMBO is missing its choices',input=name)
                flat[category][name] = [choices,{k:v for k,v in options.items() if k!='options'}]
            elif kind == 'COMFY_AUTOGROW_V3':
                template = options.get('template', {})
                prefix = template.get('prefix')
                minimum, maximum = template.get('min'), template.get('max')
                required = template.get('input', {}).get('required', {})
                if (not isinstance(prefix, str) or type(minimum) is not int or type(maximum) is not int
                        or not 0 <= minimum <= maximum <= 32 or len(required) != 1):
                    raise ComfyError('INVALID_NODE_DEFINITION','Worker autogrow template is malformed',input=name)
                child_spec = next(iter(required.values()))
                selected = []
                for index in range(maximum):
                    key = name+'.'+prefix+str(index)
                    if key in values:
                        selected.append(index)
                        add(key, child_spec, 'required')
                if len(selected) < minimum or selected != list(range(len(selected))):
                    raise ComfyError('INVALID_NODE_INPUT','Autogrow inputs must be contiguous within worker limits',input=name)
            elif kind == 'COMFY_DYNAMICCOMBO_V3':
                branches = options.get('options')
                if not isinstance(branches,list) or any(not isinstance(b,dict) or 'key' not in b for b in branches):
                    raise ComfyError('INVALID_NODE_DEFINITION','Worker dynamic combo is malformed',input=name)
                flat[category][name] = [[b['key'] for b in branches],{}]
                if name not in values:
                    return
                selected = next((b for b in branches if b['key']==values[name]),None)
                if selected:
                    for nested_category in ('required','optional'):
                        for child, child_spec in selected.get('inputs',{}).get(nested_category,{}).items():
                            add(name+'.'+child,child_spec,nested_category)
            else:
                flat[category][name] = copy.deepcopy(spec)
        original = definition.get('input',{})
        for category in ('required','optional'):
            for name,spec in original.get(category,{}).items():
                add(name,spec,category)
        definition['input'] = flat
    return result

def _check(client, graph):
    probe = client.probe()
    definitions = probe.get('object_info') or {}
    errors = list(probe.get('errors',[]))
    if not probe.get('connected') and not errors:
        errors.append({'code':'WORKER_OFFLINE','message':'Worker probe did not confirm connectivity'})
    if definitions:
        try:
            checked = inspect_workflow(graph,normalized_definitions(graph,definitions))
        except ComfyError as error:
            checked = {'valid':False,'errors':[error.to_dict()],'warnings':[]}
        errors += checked['errors']
    else:
        checked = {'valid':False,'warnings':[]}
        errors.append({'code':'NO_NODE_DEFINITIONS','message':'Worker did not return node definitions'})
    return {'ready':not errors and bool(checked.get('valid')),'errors':errors,
            'warnings':checked.get('warnings',[]),'probe':probe}

def preflight(studio, payload):
    params = _parameters(payload)
    if params.get('planned_shot_id'):
        from .film_shot_plan import anchor
        anchor(studio,params)
    if params.get('continuation_id'):
        from .film_continuations import validate
        validate(studio,params['continuation_id'],params)
    from . import film_images
    graph,refs = film_images.prepare(studio,recipe.prepared(params['brief'],params['seed'],'Film/preflight/take',params['recipe_id'],params.get('length_frames')),params,'Film/preflight')
    result = _check(studio.client_factory(params['worker_url'],timeout=10),graph)
    # Only replace warnings for verified local references staged by this exact preflight.
    # Unrelated missing inputs and worker diagnostics remain visible unchanged.
    planned = {film_images.reference_node(role):f'Film/preflight/{role}.png' for role in refs}
    result['warnings'] = [
        {**warning,'code':'REFERENCE_UPLOAD_ON_GENERATE',
         'message':'Selected image is verified locally and will upload to the worker when you choose Generate.'}
        if (warning.get('code')=='IMAGE_NOT_IN_CHOICES' and warning.get('input')=='image'
            and warning.get('node_id') in planned and warning.get('value')==planned[warning['node_id']])
        else warning for warning in result['warnings']]
    if params.get('last_frame_id') and not recipe.public_recipe(params['recipe_id']).get('last_frame_tested',False):
        result['warnings'].append({'code':'LAST_FRAME_UNTESTED','message':'Last-frame conditioning has not been empirically validated in this integration.'})
    now = time.time()
    record = {'references':refs,'kind':'film_av_preflight','parameters':params,'recipe':recipe.public_recipe(params['recipe_id']),
              'checked_at':_stamp(now),'expires_at':_stamp(now+TOKEN_SECONDS),'expires_epoch':now+TOKEN_SECONDS,
              'ready':result['ready'],'errors':result['errors'],'warnings':result['warnings'],
              'prepared_workflow':studio.store.save_snapshot(graph,kind='workflows'),
              'worker_evidence':studio.store.save_snapshot(result['probe'],kind='jobs')}
    ref = studio.store.save_snapshot(record,kind='jobs')
    identity = ref['sha256']
    studio.set_setting('film.preflight.'+identity,ref)
    return {'id':identity,'ready':record['ready'],'checked_at':record['checked_at'],'expires_at':record['expires_at'],
            'errors':record['errors'],'warnings':record['warnings'],'recipe_id':params['recipe_id'],'worker_url':params['worker_url']}

def configuration(studio, identity):
    if not isinstance(identity,str) or not re.fullmatch(r'[0-9a-f]{32}',identity):
        return None
    path = studio.store.resolve(f'records/film_generation/{identity}.json')
    return studio.store.read_snapshot(json.loads(path.read_text())) if path.is_file() else None

def _completion(studio, identity):
    path = studio.store.resolve(f'candidates/{identity}/joint_av.json')
    return studio.store.read_snapshot(json.loads(path.read_text())) if path.is_file() else None

def job_details(studio, identity):
    config = configuration(studio,identity)
    if config is None:
        return {}
    done = _completion(studio,identity)
    imported = studio.setting('film.generation.import.'+identity,{})
    # Why an automatic import failed, so the Queue card can say so (guardrail 8).
    state = {} if imported else studio.setting('film.generation.import_state.'+identity,{})
    from .generation_timeline import metadata
    return {'pipeline':recipe.PIPELINE,'recipe_id':config['parameters']['recipe_id'],'import_error':state.get('error'),'import_stage':state.get('stage'),
            'ready_to_import':bool(done),'video_asset_id':imported.get('video_asset_id'),
            'audio_asset_id':imported.get('audio_asset_id'),'reference_supported':True,'references':config.get('references',{}),
            'destination':config.get('destination'),'metadata':metadata(config,done,studio)}

def state(studio):
    try:
        url = studio.worker_url()
    except StudioError:
        url = ''
    return {'recipe':recipe.public_recipe(),'recipes':recipe.public_recipes(),'worker_url':url,
            'jobs':[j for j in studio.jobs() if j.get('pipeline')==recipe.PIPELINE]}

def get_job(studio, identity):
    if configuration(studio,identity) is None:
        raise StudioError('Joint-AV job not found',404)
    return studio.job(identity)

def submit(studio, payload):
    from . import generation_timeline as timeline
    params = _parameters(payload,submission=True)
    label = text(payload.get('label'),'Shot name',100)
    request_id = text(payload.get('request_id'),'Generation request ID',100)
    # Resolve a prior explicit request before token expiry checks, allowing safe retry.
    with studio.lock,studio.db() as db:
        prior = db.execute('SELECT id FROM jobs WHERE request_id=?',(request_id,)).fetchone()
        if prior:
            config = configuration(studio,prior[0])
            same_destination=(payload.get('destination') is None if params.get('planned_shot_id') else config and config.get('destination') == timeline.destination(studio,payload.get('destination'),validate_revision=False))
            if not config or config['parameters'] != params or config['label'] != label or not same_destination:
                raise StudioError('This request ID belongs to a different generation request',409)
            return studio.job(prior[0])
        token = payload.get('preflight_id')
        if not isinstance(token,str) or not re.fullmatch(r'[0-9a-f]{64}',token):
            raise StudioError('Run preflight for this exact brief before generating',409)
        ref = studio.setting('film.preflight.'+token)
        if not ref:
            raise StudioError('Preflight token not found; run preflight again',409)
        checked = studio.store.read_snapshot(ref)
        if (not checked['ready'] or checked['expires_epoch'] < time.time() or checked['parameters'] != params
                or checked.get('recipe') != recipe.public_recipe(params['recipe_id'])):
            raise StudioError('Preflight is stale, failed, or for different settings; run it again',409)
        planned=None
        if params.get('planned_shot_id'):
            from . import film_shot_plan
            if payload.get('destination') is not None:raise StudioError('Planned shots derive their destination from the saved assignment')
            planned=film_shot_plan.anchor(studio,params)
            dest=film_shot_plan.destination(studio,planned)
        else:
            dest = timeline.destination(studio,payload.get('destination'))
        continuation=None
        if params.get('continuation_id'):
            from .film_continuations import validate
            continuation=validate(studio,params['continuation_id'],params,dest)
            if dest is None:raise StudioError('Continuation requires its adjacent timeline destination',409)
        identity = uuid4().hex
        from . import film_images
        graph,refs = film_images.prepare(studio,recipe.prepared(params['brief'],params['seed'],f'Film/{identity}/take',params['recipe_id'],params.get('length_frames')),params,f'Film/{identity}')
        if refs != checked.get('references',{}):raise StudioError('Image references changed; preflight again',409)
        config = {'schema_version':1,'kind':'film_av_job','pipeline':recipe.PIPELINE,'local_job_id':identity,
                  'created':utc_now(),'parameters':params,'label':label,'request_id':request_id,'destination':dest,
                  'recipe':recipe.public_recipe(params['recipe_id']),'preflight':ref,'references':refs,'continuation':continuation,'planned_shot':planned,
                  'workflow':studio.store.save_snapshot(graph,kind='workflows'),'workflow_sha256':workflow_sha256(graph)}
        pointer = studio.store.save_snapshot(config,kind='jobs')
        studio.store.write_once(f'records/film_generation/{identity}.json',canonical_bytes(pointer))
        db.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?)',
                   (identity,'',label,params['brief'],params['seed'],'pending',None,utc_now(),request_id))
        timeline.register(db,identity,dest)
        if planned:
            from .film_shot_plan import register
            register(db,identity,planned)
    return studio.job(identity)

def _status(studio, identity, status, error=None):
    with studio.db() as db:
        db.execute('UPDATE jobs SET status=?,error=? WHERE id=?',(status,json.dumps(error) if error else None,identity))

def _request(studio, identity):
    pointer = json.loads(studio.store.resolve(job_folder(identity)+'/request.json').read_text())
    request = studio.store.read_snapshot(pointer)
    if request.get('kind')!='film_av_generation_request' or request.get('local_job_id')!=identity or request.get('pipeline')!=recipe.PIPELINE:
        raise ComfyError('INVALID_JOB_RECORD','Joint-AV request ownership does not match')
    graph = studio.store.read_snapshot(request['workflow'])
    if workflow_sha256(graph)!=request['workflow_sha256']:
        raise ComfyError('WORKFLOW_CHECKSUM_MISMATCH','Frozen joint-AV workflow changed')
    return request

def _start(studio, config):
    identity = config['local_job_id']
    folder = job_folder(identity)
    if studio.store.resolve(folder).exists():
        raise ComfyError('SUBMISSION_UNRESOLVED','A durable request already exists; never submit it again')
    if config.get('planned_shot'):
        from .film_shot_plan import anchor
        if anchor(studio,config['parameters'])!=config['planned_shot']:raise StudioError('Planned assignment changed before generation',409)
    if config.get('continuation'):
        from .film_continuations import validate
        validate(studio,config['continuation']['id'],config['parameters'],config['destination'])
    ffmpeg_path()  # Fail before GPU work if local decoding is unavailable.
    graph = studio.store.read_snapshot(config['workflow'])
    if workflow_sha256(graph)!=config['workflow_sha256']:
        raise ComfyError('WORKFLOW_CHECKSUM_MISMATCH','Saved joint-AV workflow changed')
    client = studio.client_factory(config['parameters']['worker_url'],timeout=15)
    check = _check(client,graph)
    if not check['ready']:
        raise ComfyError('PREFLIGHT_CHANGED','Worker no longer meets this recipe; nothing was submitted',errors=check['errors'])
    references=config.get('references',{})
    uploads={}
    if references:
        from . import film_images
        # Durable intent before any upload; an interrupted upload never triggers an automatic submit retry.
        studio.store.write_once(folder+'/reference-upload-intent.json',canonical_bytes({'references':references,'created':utc_now()}))
        for role,reference in references.items():
            current=film_images.verify(studio,reference['id'])
            if current!=reference:raise StudioError('Frozen image reference changed',409)
            upload=client.upload_image(studio.store.resolve(reference['png']['path']).read_bytes(),role+'.png',f'Film/{identity}')
            uploads[role]=upload
            graph[film_images.reference_node(role)]['inputs']['image']=upload['path']
        check=_check(client,graph)
        if not check['ready']:raise ComfyError('REFERENCE_PREFLIGHT_FAILED','Uploaded reference graph did not pass worker validation',errors=check['errors'])
    frozen_workflow=studio.store.save_snapshot(graph,kind='workflows')
    submitted_hash=workflow_sha256(graph)
    request = {'kind':'film_av_generation_request','pipeline':recipe.PIPELINE,'local_job_id':identity,
               'client_id':str(uuid4()),'base_url':client.base_url,'workflow':frozen_workflow,'references':references,'uploads':uploads,
               'workflow_sha256':submitted_hash,'parameters':config['parameters'],
               'recipe':config['recipe'],'bindings':recipe.BINDINGS,'preflight':config['preflight'],
               'worker_evidence':studio.store.save_snapshot(check['probe'],kind='jobs'),'created_at_utc':utc_now()}
    studio.store.write_once(folder+'/request.json',canonical_bytes(studio.store.save_snapshot(request,kind='jobs')))
    record_event(studio.store,identity,'submitting',pipeline=recipe.PIPELINE)
    response = client.submit(graph,client_id=request['client_id'],local_job_id=identity)
    accepted = {key:request[key] for key in ('local_job_id','client_id','base_url','workflow_sha256')}
    accepted.update(prompt_id=response['prompt_id'],response=response)
    studio.store.write_once(folder+'/accepted.json',canonical_bytes(accepted))
    record_event(studio.store,identity,'queued',prompt_id=response['prompt_id'])
    _status(studio,identity,'queued')

def _length(config):
    return recipe.frames(config['parameters'].get('length_frames'))

def _soundtrack(studio, video_path, identity, frames=recipe.DEFAULT_FRAMES):
    """Preserve embedded sound as a separately reviewable, clock-aligned PCM derivative."""
    with tempfile.TemporaryDirectory(prefix='joint-av-audio-',dir=studio.store.root) as temporary:
        output = Path(temporary)/'decoded.wav'
        result = subprocess.run([ffmpeg_path(),'-v','error','-nostdin','-protocol_whitelist','file,pipe','-i',str(video_path),
                                 '-map','0:a:0','-vn','-t',str(frames/24+1),'-ac','2','-ar','48000','-c:a','pcm_s24le',str(output)],
                                capture_output=True,timeout=90)
        if result.returncode or not output.is_file():
            raise ComfyError('MISSING_JOINT_AUDIO','Completed video has no decodable embedded audio')
        with wave.open(str(output),'rb') as source:
            count,rate,channels,width = source.getnframes(),source.getframerate(),source.getnchannels(),source.getsampwidth()
            samples = source.readframes(count)
    expected = frames*48000//24
    if (rate,channels,width)!=(48000,2,3) or abs(count-expected)>2048:
        raise ComfyError('AUDIO_CLOCK_MISMATCH','Joint soundtrack differs materially from the fixed video duration',samples=count,expected=expected)
    # AAC tail/padding may differ by a fraction of a frame. Keep the original MP4
    # unchanged and explicitly pin the trimmed/padded derivative to 124 frames.
    samples = (samples + b'\0'*(max(0,expected-count)*channels*width))[:expected*channels*width]
    data = io.BytesIO()
    with wave.open(data,'wb') as destination:
        destination.setnchannels(channels); destination.setsampwidth(width); destination.setframerate(rate)
        destination.writeframes(samples)
    value = data.getvalue()
    relative = f'candidates/{identity}/production.wav'
    studio.store.write_once(relative,value)
    return {'path':relative,'sha256':sha256(value),'bytes':len(value),'sample_rate':rate,'channels':channels,
            'sample_count':expected,'duration_seconds':frames/24,'decoded_samples':count,'clock_adjustment_samples':expected-count,
            'derivation':'Embedded original sound decoded to PCM; AAC tail trimmed/padded to exact video clock'}

def _poll(studio, config):
    identity = config['local_job_id']
    done = _completion(studio,identity)
    if done:
        for name in ('video','audio'):
            studio.store.verify_master({'id':identity,**done[name]})
        _status(studio,identity,'success')
        return
    request = _request(studio,identity)
    accepted_path = studio.store.resolve(job_folder(identity)+'/accepted.json')
    if not accepted_path.is_file():
        raise ComfyError('SUBMISSION_UNRESOLVED','No accepted prompt is recorded; resume never submits')
    accepted = json.loads(accepted_path.read_text())
    if any(accepted.get(k)!=request.get(k) for k in ('local_job_id','client_id','base_url','workflow_sha256')):
        raise ComfyError('INVALID_JOB_RECORD','Joint-AV accepted prompt ownership differs')
    client = studio.client_factory(request['base_url'],timeout=15)
    result = client.poll(accepted['prompt_id'])
    if result['status']!='success':
        _status(studio,identity,result['status'],result.get('error'))
        return
    history = result.get('history',{})
    prompt = history.get('prompt')
    if not isinstance(prompt,list) or len(prompt)<3 or prompt[1]!=accepted['prompt_id']:
        raise ComfyError('HISTORY_ID_MISMATCH','Joint-AV history belongs to a different prompt')
    extra = prompt[3] if len(prompt)>3 and isinstance(prompt[3],dict) else {}
    owned = extra.get('last_light_radio',{})
    if (('client_id' in extra and extra['client_id']!=request['client_id'])
            or (isinstance(owned,dict) and 'local_job_id' in owned and owned['local_job_id']!=identity)):
        raise ComfyError('HISTORY_ID_MISMATCH','Joint-AV history ownership metadata differs')
    executed = prompt[2]
    if executed is None or workflow_sha256(executed)!=request['workflow_sha256']:
        raise ComfyError('HISTORY_WORKFLOW_MISMATCH','Completed history must contain the exact owned joint-AV graph')
    references = result.get('outputs',{}).get('14',{}).get('images')
    if not isinstance(references,list) or len(references)!=1 or not isinstance(references[0],dict):
        raise ComfyError('INVALID_JOINT_OUTPUT','Expected the single proven SaveVideo node 14 MP4 result')
    reference = references[0]
    folder = reference.get('subfolder','')
    filename = reference.get('filename','')
    if (not isinstance(folder,str) or folder.replace('\\','/')!=f'Film/{identity}'
            or not isinstance(filename,str) or not re.fullmatch(r'take_[0-9]+_?\.mp4',filename)
            or reference.get('type')!='output'):
        raise ComfyError('UNOWNED_OUTPUT','Joint-AV output does not belong to this job prefix')
    data = client.download_mp4_output(reference)
    relative = f'candidates/{identity}/joint-av.mp4'
    studio.store.write_once(relative,data)
    path = studio.store.resolve(relative)
    frames = _length(config)
    inspection = inspect_video(path,frames,24,(672,384))
    video = {'path':relative,'sha256':sha256(data),'bytes':len(data),'reference':reference,'inspection':inspection}
    audio = _soundtrack(studio,path,identity,frames)
    history_ref = studio.store.save_snapshot(result,kind='jobs')
    completion = {'schema_version':1,'kind':'joint_av_completion','pipeline':recipe.PIPELINE,'local_job_id':identity,
                  'prompt_id':accepted['prompt_id'],'request':request,'accepted_receipt':accepted,'history':history_ref,
                  'workflow':request['workflow'],'workflow_sha256':request['workflow_sha256'],'recipe':request['recipe'],
                  'video':video,'audio':audio,'created':utc_now(),'review_status':'candidate','history_workflow_verified':True}
    studio.store.write_once(f'candidates/{identity}/joint_av.json',canonical_bytes(studio.store.save_snapshot(completion,kind='jobs')))
    record_event(studio.store,identity,'downloaded',video_sha256=video['sha256'],audio_sha256=audio['sha256'])
    _status(studio,identity,'success')

def process_job(studio, job):
    config = configuration(studio,job['id'])
    if not config:
        raise StudioError('Joint-AV job configuration is missing',409)
    if job['status']=='pending':
        _status(studio,job['id'],'submitting')
        _start(studio,config)
    else:
        _poll(studio,config)
    from .generation_timeline import auto_import
    auto_import(studio,job['id'])

def resume(studio, identity):
    get_job(studio,identity)
    return studio.resume(identity)

def import_completed(studio, identity):
    job = get_job(studio,identity)
    if job['status']!='success':
        raise StudioError('Wait for this owned joint-AV job to complete before importing',409)
    completed = _completion(studio,identity)
    if not completed:
        raise StudioError('Completed joint-AV receipt is missing',409)
    for part in ('video','audio'):
        studio.store.verify_master({'id':identity,**completed[part]})
    receipt = studio.store.save_snapshot(completed,kind='jobs')
    from .generation_timeline import metadata,bounded_provenance
    provenance = {'generation_metadata':metadata(configuration(studio,identity),completed,studio),'kind':'owned_h3_joint_av','local_job_id':identity,'prompt_id':completed['prompt_id'],
                  'workflow_sha256':completed['workflow_sha256'],'source_recipe_raw_sha256':completed['recipe'].get('source_raw_sha256'),
                  'generation_receipt':receipt,'reference_conditioning':bool(completed['request'].get('references')),
                  'references':completed['request'].get('references',{})}
    provenance=bounded_provenance(studio,provenance)
    from . import film,audio_tracks
    video = film.import_bytes(studio,studio.store.resolve(completed['video']['path']).read_bytes(),
                              'joint-av.mp4',job['label'],provenance)
    wav = studio.store.resolve(completed['audio']['path']).read_bytes()
    audio = audio_tracks.import_asset(studio,{'filename':'joint-av-production.wav','label':job['label']+' — production sound',
                                            'audio_base64':base64.b64encode(wav).decode(),
                                            'provenance':{**provenance,'source_video_sha256':completed['video']['sha256'],
                                                          'clock_adjustment_samples':completed['audio']['clock_adjustment_samples']}})
    studio.set_setting('film.generation.import.'+identity,{'video_asset_id':video['id'],'audio_asset_id':audio['id'],'receipt':receipt})
    return {'video':video,'audio':audio,'job':studio.job(identity)}
