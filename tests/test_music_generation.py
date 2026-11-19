"""No-GPU ACE-Step lifecycle and music-to-film coverage."""
import copy
import json
import math
import struct
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from urllib.parse import urlencode
from unittest.mock import patch
from last_light_radio import music_generation as music,ace_step_recipe as recipe,film,audio_tracks
from last_light_radio.ace_step_client import AceClient,OUTPUT_ROOT,normalize_url
from last_light_radio.comfy import ComfyError
from last_light_radio.studio import Studio,StudioError
from last_light_radio.server import make_server
from last_light_radio.store import sha256
from last_light_radio.video_tools import ffmpeg_path

TASK='11111111-2222-3333-4444-555555555555'

def envelope(data):return {'code':200,'error':None,'data':data}

class FakeAce:
    base_url='http://127.0.0.1:42003'
    def __init__(self,wav):
        self.wav=wav;self.submits=0;self.downloads=0;self.missing=False;self.ambiguous=False;self.bad_seed=False
        self.block=None;self.entered=threading.Event();self.payload=None
    def probe(self):return {'health':envelope({'status':'ok','service':'ACE-Step Gradio API'}),
                           'models':envelope({'models':[{'name':'acestep-v15-turbo','is_default':True}],'default_model':'acestep-v15-turbo'})}
    def submit(self,payload):
        self.submits+=1;self.payload=copy.deepcopy(payload);self.entered.set()
        if self.block:self.block.wait(3)
        if self.ambiguous:raise ComfyError('SUBMISSION_AMBIGUOUS','Fixture lost release_task response')
        return envelope({'task_id':TASK,'status':'succeeded'})
    def result(self):
        file=str(OUTPUT_ROOT/'api_12345'/'fixture-cue.wav')
        return {'file':file,'url':'/v1/audio?'+urlencode({'path':file}),'status':1,
                'seed':self.payload['seed']+(1 if self.bad_seed else 0),'caption':self.payload['prompt'],'lyrics':'[Instrumental]',
                'bpm':80,'duration':30,'keyscale':'D minor','timesignature':'4'}
    def poll(self,identity):return envelope([{'task_id':identity,'status':0 if self.missing else 1,
                                             'result':'[]' if self.missing else json.dumps([self.result()])}])
    def download(self,result):self.downloads+=1;return self.wav

class MusicGenerationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Native IEEE float32 stereo WAV matches the proven service's container.
        second=b''.join(struct.pack('<ff',.1*math.sin(2*math.pi*440*i/48000),.1*math.sin(2*math.pi*440*i/48000)) for i in range(48000))
        data=second*30
        cls.wav=b'RIFF'+struct.pack('<I',36+len(data))+b'WAVEfmt '+struct.pack('<IHHIIHH',16,3,2,48000,48000*8,8,32)+b'data'+struct.pack('<I',len(data))+data
        cls.temp=tempfile.TemporaryDirectory(prefix='music-video-fixture-');cls.addClassCleanup(cls.temp.cleanup)
        path=Path(cls.temp.name)/'fixture.mp4'
        subprocess.run([ffmpeg_path(),'-v','error','-f','lavfi','-i','color=c=blue:s=64x48:r=24','-frames:v','72',
                        '-an','-c:v','libx264','-pix_fmt','yuv420p',str(path)],capture_output=True,check=True)
        cls.video=path.read_bytes()
    def setUp(self):
        self.tempdir=tempfile.TemporaryDirectory(prefix='music-job-test-');self.addCleanup(self.tempdir.cleanup)
        self.studio=Studio(self.tempdir.name);self.client=FakeAce(self.wav)
        self.studio.music_client_factory=lambda *a,**k:self.client
        self.params={'recipe_id':recipe.RECIPE_ID,'worker_url':self.client.base_url,'brief':'Explicit isolated instrumental cue fixture','seed':123}
    def payload(self,request_id='music-test-request'):
        p=music.preflight(self.studio,self.params);self.assertTrue(p['ready'],p)
        return {**self.params,'label':'Fixture music','preflight_id':p['id'],'request_id':request_id}
    def finished(self):
        job=music.submit(self.studio,self.payload());music.process_owned_job(self.studio,job['id'])
        self.assertEqual(self.studio.job(job['id'])['status'],'queued')
        music.process_owned_job(self.studio,job['id']);current=self.studio.job(job['id'])
        self.assertEqual(current['status'],'success',current)
        return current
    def test_preflight_is_readonly_and_settings_are_bound(self):
        payload=self.payload();self.assertEqual(self.client.submits,0);self.assertEqual(self.studio.jobs(),[])
        for change in ({'brief':'Changed cue'},{'seed':124},{'worker_url':'http://127.0.0.1:40001'}):
            with self.subTest(change=change),self.assertRaises(StudioError):music.submit(self.studio,{**payload,**change})
        with self.assertRaises(StudioError):music.preflight(self.studio,{**self.params,'lyrics':'unrequested vocals'})
        with patch.object(music.time,'time',return_value=time.time()+601),self.assertRaises(StudioError):music.submit(self.studio,payload)
        with self.assertRaises(ComfyError):normalize_url('http://example.com:42003')
        self.assertEqual(self.client.submits,0)
    def test_request_idempotency_and_lost_response_restart_do_not_resubmit(self):
        payload=self.payload();job=music.submit(self.studio,payload)
        self.assertEqual(music.submit(self.studio,payload)['id'],job['id'])
        self.client.ambiguous=True;music.process_owned_job(self.studio,job['id'])
        self.assertEqual(self.studio.job(job['id'])['status'],'submission_unknown')
        reopened=Studio(self.tempdir.name);reopened.music_client_factory=lambda *a,**k:self.client
        music.process_owned_job(reopened,job['id'])
        self.assertEqual(reopened.job(job['id'])['status'],'submission_unknown')
        with self.assertRaises(StudioError):music.resume(reopened,job['id'])
        self.assertEqual(self.client.submits,1)
    def test_accepted_missing_result_stops_and_manual_resume_only_polls(self):
        job=music.submit(self.studio,self.payload());music.process_owned_job(self.studio,job['id']);self.client.missing=True
        with patch.object(music.time,'time',return_value=time.time()+301):music.process_owned_job(self.studio,job['id'])
        self.assertEqual(self.studio.job(job['id'])['status'],'result_unconfirmed')
        self.assertNotIn('result_unconfirmed',music.ACTIVE)
        music.resume(self.studio,job['id']);music.process_owned_job(self.studio,job['id'])
        self.assertEqual(self.studio.job(job['id'])['status'],'running');self.assertEqual(self.client.submits,1)
    def test_long_music_request_does_not_hold_h3_lock_or_duplicate_provider(self):
        payload=self.payload();job=music.submit(self.studio,payload)
        release=threading.Event();self.client.block=release;self.addCleanup(release.set)
        start=time.monotonic();self.studio.process_job(job['id']);self.assertLess(time.monotonic()-start,.5)
        self.assertTrue(self.client.entered.wait(1))
        self.assertTrue(self.studio.job_lock.acquire(timeout=.1));self.studio.job_lock.release()
        self.studio.process_job(job['id']);self.assertEqual(self.client.submits,1)
        other=music.submit(self.studio,self.payload('second-request'));self.studio.process_job(other['id'])
        self.assertEqual(self.client.submits,1)
        release.set();self.studio.music_provider_thread.join(2)
        self.assertEqual(self.studio.job(job['id'])['status'],'queued')
    def test_result_metadata_mismatch_blocks_download(self):
        job=music.submit(self.studio,self.payload());music.process_owned_job(self.studio,job['id']);self.client.bad_seed=True
        music.process_owned_job(self.studio,job['id'])
        current=self.studio.job(job['id']);self.assertEqual(current['status'],'failed')
        self.assertEqual(current['error']['code'],'MUSIC_PROVENANCE_MISMATCH');self.assertEqual(self.client.downloads,0)
    def test_float_wav_receipt_import_and_http_response(self):
        job=self.finished();done=music._completion(self.studio,job['id'])
        self.assertEqual(done['audio']['sha256'],sha256(self.wav))
        self.assertEqual(self.studio.store.resolve(done['audio']['path']).read_bytes(),self.wav)
        with patch('last_light_radio.server.ThreadingHTTPServer') as server_type:
            make_server(self.studio,0);handler=object.__new__(server_type.call_args.args[1])
        handler.close_connection=False
        with patch.object(handler,'guard_host'),patch.object(handler,'path_parts',return_value=['api','film','music','jobs',job['id'],'import']),patch.object(handler,'body',return_value={}),patch.object(handler,'send_json',side_effect=lambda value,*args:value):
            response=handler.dispatch(mutation=True)
        self.assertIn('audio',response);self.assertEqual(response['audio']['status'],'candidate')
        self.assertIn('media_url',response['audio']);self.assertEqual(response['job']['audio_asset_id'],response['audio']['id'])
        again=music.import_completed(self.studio,job['id']);self.assertEqual(again['audio']['id'],response['audio']['id'])
        self.assertEqual(len(audio_tracks.listing(self.studio)['assets']),1);self.assertEqual(self.client.submits,1)
    def test_complete_mock_music_to_reviewed_named_film_mix(self):
        job=self.finished();audio=music.import_completed(self.studio,job['id'])['audio']
        audio_tracks.review(self.studio,audio['id'],{'decision':'approved','expected_version':0,'notes':'Explicit isolated synthetic music test only'})
        video=film.import_bytes(self.studio,self.video,'fixture.mp4','Synthetic fixture picture',{'test_only':True})
        film.review_asset(self.studio,video['id'],{'decision':'approved','expected_version':0,'notes':'Explicit isolated synthetic picture test only'})
        project=film.create_project(self.studio,{'title':'Music pipeline test'});seq=film.create_sequence(self.studio,project['id'],{'title':'Music mix'})
        tracks=[{'id':'music-1','asset_id':audio['id'],'role':'music','start_frame':0,'source_in_frame':24,'duration_frames':72,
                 'gain_db':-3,'fade_in_frames':6,'fade_out_frames':6,'enabled':True}]
        saved=film.save_sequence(self.studio,seq['id'],{'title':'Music mix','expected_revision':0,'width':64,'height':48,
             'shots':[{'id':'shot','asset_id':video['id'],'source_in_frame':0,'duration_frames':72}],'audio_tracks':tracks})
        reopened=Studio(self.tempdir.name);restored=film.sequence(reopened,seq['id']);self.assertEqual(restored['audio_tracks'],tracks)
        film.process_export(reopened,seq['id'],reopened.store.read_snapshot(restored['manifest']))
        final=film.sequence(reopened,seq['id']);self.assertEqual(final['export']['status'],'complete',final['export'])
        self.assertEqual(final['export']['report']['inspection']['frame_count'],72)
        path,_=film.export_media(reopened,seq['id'],'media')
        raw=subprocess.run([ffmpeg_path(),'-v','error','-i',str(path),'-map','0:a:0','-ac','1','-ar','48000','-f','s16le','pipe:1'],capture_output=True,check=True).stdout
        samples=struct.unpack('<'+'h'*(len(raw)//2),raw)
        self.assertGreater(max(abs(v) for v in samples),1000)
        self.assertEqual(self.studio.store.resolve(audio['source']['path']).read_bytes(),self.wav)
        self.assertEqual(self.client.submits,1)
    def test_client_timeout_wrong_task_and_download_url_safety(self):
        client=AceClient(self.client.base_url)
        with patch.object(client.opener,'open',side_effect=TimeoutError('fixture timeout')),self.assertRaises(ComfyError) as caught:client.submit(recipe.REQUEST)
        self.assertEqual(caught.exception.code,'SUBMISSION_AMBIGUOUS')
        with patch.object(client,'_json',return_value=envelope([{'task_id':'not-owned','status':1}])),self.assertRaises(ComfyError):client.poll(TASK)
        self.client.payload=recipe.REQUEST;result=self.client.result()
        for url in ('https://example.com/audio.wav','//example.com/v1/audio','/v1/audio?path=C%3A%5Csecret.wav'):
            with patch.object(client,'_request',side_effect=AssertionError('Must not download')) , self.assertRaises(ComfyError):client.download({**result,'url':url})
        with patch.object(client,'_request',return_value=({'Content-Type':'audio/wav'},self.wav)):
            self.assertEqual(client.download(result),self.wav)

if __name__=='__main__':unittest.main()
