"""Frozen successful ACE-Step instrumental request; only brief and seed may change."""
import copy
import json
from .store import canonical_bytes, sha256

SOURCE_RAW_SHA256 = 'a75c245bae340da94fa75f7b3f4670595ba109ed0805ebd3fa709887d12057a8'
REQUEST = json.loads('{"use_random_seed": false, "use_format": false, "audio_format": "wav", "model": "acestep-v15-turbo", "key_scale": "D minor", "batch_size": 1, "thinking": false, "prompt": "Instrumental cinematic discovery cue. Soft felt piano plays a simple repeating four-note motif over warm analog synth pads and restrained bowed strings. A quiet mysterious opening gradually becomes hopeful, with a gentle rising swell and a clean resolved ending. Intimate, spacious, detailed, no vocals, no speech, no drums.", "use_cot_caption": false, "lyrics": "[Instrumental]", "use_cot_language": false, "time_signature": "4", "inference_steps": 8, "seed": 20261112, "bpm": 80, "audio_duration": 30, "sample_mode": false}')
RECIPE_SHA256 = sha256(canonical_bytes(REQUEST))
RECIPE_ID = 'ace_step_music.' + RECIPE_SHA256
PIPELINE = 'ace_step_music_v1'
DEFAULT_URL = 'http://127.0.0.1:42003'

def _short_recipe():
    return {'id':RECIPE_ID,'name':'ACE-Step instrumental discovery cue (tested recipe)','pipeline':PIPELINE,
            'model':'acestep-v15-turbo','duration_seconds':30,'bpm':80,'key_scale':'D minor','time_signature':'4',
            'steps':8,'default_seed':20261112,'instrumental':True,'recipe_sha256':RECIPE_SHA256,
            'source_raw_sha256':SOURCE_RAW_SHA256,'service_flavor':'ACE-Step Gradio API',
            'endpoint_note':'Observed Pinokio loopback endpoint; update explicitly if its dynamic port changes',
            'submission_note':'This service returns its task ID only after generation; an uncertain request is never retried'}

def prepared(brief, seed, duration_seconds=30, lyrics="[Instrumental]", structure=""):
    request = copy.deepcopy(REQUEST)
    request['prompt'] = brief + ('\n\nSong structure:\n'+structure if structure else '')
    request['lyrics'] = lyrics
    request['seed'] = seed
    request['audio_duration'] = duration_seconds
    return request


FULL_DURATIONS = (180, 210, 240)
FULL_SPEC = {'kind':'ace_step_bounded_full_song_v2','base_recipe_sha256':RECIPE_SHA256,
             'duration_options':list(FULL_DURATIONS),'batch_size':1,'max_duration_seconds':240,
             'lyrics_max_chars':20000,'structure_max_chars':4000,'brief_max_chars':8000,'explicit_instrumental_choice':True}
FULL_SHA256 = sha256(canonical_bytes(FULL_SPEC))
FULL_RECIPE_ID = 'ace_step_music_full.'+FULL_SHA256

def public_recipe(identity=None, duration_seconds=None, instrumental=True):
    if identity in (None, RECIPE_ID):return _short_recipe()
    if identity != FULL_RECIPE_ID:raise ValueError('Unknown music recipe')
    duration=180 if duration_seconds is None else duration_seconds
    if type(duration) is not int or duration not in FULL_DURATIONS:raise ValueError('Choose 180, 210 or 240 seconds')
    return {**_short_recipe(),'id':FULL_RECIPE_ID,'name':'ACE-Step bounded full song (not yet rendered in this integration)',
            'instrumental':instrumental,'supports_lyrics':True,'instrumental_options':[True,False],
            'max_lyrics_chars':20000,'max_structure_chars':4000,'max_brief_chars':8000,'vocal_generation_tested':False,
            'duration_seconds':duration,'duration_options':list(FULL_DURATIONS),'duration_tested':False,
            'recipe_sha256':FULL_SHA256,'recipe_version':2,'batch_size':1,'max_duration_seconds':240,
            'capability_note':'API accepts duration; full-song output is not yet empirically verified. Runtime LM state is unknown; this recipe does not change model or LM settings.'}
