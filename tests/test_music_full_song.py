import copy,io,json,shutil,subprocess,tempfile,threading,unittest,http.client,socket
from pathlib import Path
from unittest.mock import patch
from tests import test_music_generation as fixture
from last_light_radio import music_generation as music,ace_step_recipe as recipe,audio_tracks
from last_light_radio.ace_step_client import AceClient
from last_light_radio.studio import Studio,StudioError
from last_light_radio.store import file_sha256
from last_light_radio.comfy import ComfyError
from last_light_radio.server import make_server
from last_light_radio.video_tools import ffmpeg_path

class FullAce(fixture.FakeAce):
    def __init__(self,path):super().__init__(b'');self.path=path
    def result(self):
        result=super().result();result.update(duration=self.payload['audio_duration'],lyrics=self.payload['lyrics']);return result
    def download_to(self,result,destination):
        shutil.copyfile(self.path,destination)
        return {'sha256':file_sha256(destination),'bytes':Path(destination).stat().st_size}

class FullSongTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='full-song-source-');cls.addClassCleanup(cls.temp.cleanup)
        cls.path=Path(cls.temp.name)/'180-second-fixture.wav'
        subprocess.run([ffmpeg_path(),'-v','error','-f','lavfi','-i','sine=frequency=220:sample_rate=48000','-t','180','-ac','2','-c:a','pcm_f32le',str(cls.path)],capture_output=True,check=True)
    def setUp(self):
        self.tempdir=tempfile.TemporaryDirectory(prefix='full-song-test-');self.addCleanup(self.tempdir.cleanup)
        self.studio=Studio(self.tempdir.name);self.client=FullAce(self.path);self.studio.music_client_factory=lambda *a,**k:self.client
        self.params={'recipe_id':recipe.FULL_RECIPE_ID,'worker_url':self.client.base_url,'brief':'Explicit synthetic technical fixture, not a creative song',
            'seed':123,'duration_seconds':180,'instrumental':False,'lyrics':'\n[Verse 1]\n'+('Original fixture lyric line.\n'*400)+'[Chorus]\nFixture refrain.\n',
            'structure':'Intro, verse, chorus, instrumental bridge, final chorus, resolved ending.'}
    def body(self):
        token=music.preflight(self.studio,self.params);self.assertTrue(token['ready'],token)
        return {**self.params,'label':'Isolated full-song fixture','preflight_id':token['id'],'request_id':'full-song-fixture'}
    def test_versioned_bounds_exact_lyrics_and_readonly_preflight(self):
        short=recipe.prepared('brief',1)
        self.assertEqual(short['audio_duration'],30);self.assertEqual(short['lyrics'],'[Instrumental]')
        self.assertEqual(recipe.public_recipe()['id'],recipe.RECIPE_ID)
        for duration in (0,179,181,241,600,True):
            with self.assertRaises(StudioError):music.preflight(self.studio,{**self.params,'duration_seconds':duration})
        body=self.body();self.assertEqual(self.client.submits,0)
        for change in ({'duration_seconds':210},{'lyrics':self.params['lyrics']+'changed'},{'structure':'Changed ending'}):
            with self.assertRaises(StudioError):music.submit(self.studio,{**body,**change})
        job=music.submit(self.studio,body)
        config=music.configuration(self.studio,job['id']);request=self.studio.store.read_snapshot(config['request'])
        self.assertEqual(request['lyrics'],self.params['lyrics']);self.assertEqual(request['batch_size'],1)
        self.assertEqual(request['prompt'],self.params['brief']+'\n\nSong structure:\n'+self.params['structure'])
        self.assertFalse(request['thinking']);self.assertFalse(request['use_format']);self.assertFalse(request['sample_mode'])
        self.assertEqual(self.client.submits,0)
    def test_full_180_seconds_filebacked_result_and_candidate_import(self):
        job=music.submit(self.studio,self.body());music.process_owned_job(self.studio,job['id']);music.process_owned_job(self.studio,job['id'])
        done=self.studio.job(job['id']);self.assertEqual(done['status'],'success',done)
        self.assertEqual(done['requested_duration_seconds'],180);self.assertEqual(done['returned_duration_seconds'],180)
        self.assertAlmostEqual(done['decoded_duration_seconds'],180);self.assertGreaterEqual(done['elapsed_seconds'],0)
        imported=music.import_completed(self.studio,job['id'])['audio']
        self.assertEqual(imported['status'],'candidate');self.assertAlmostEqual(imported['duration_seconds'],180)
        self.assertEqual(imported['source']['sha256'],file_sha256(self.path))
        lyrics=self.studio.store.read_snapshot(imported['provenance']['lyrics_receipt'])
        self.assertEqual(lyrics['lyrics'],self.params['lyrics']);self.assertEqual(lyrics['structure'],self.params['structure'])
        self.assertEqual(self.client.submits,1)
    def test_long_request_unknown_never_resubmits_and_client_budget(self):
        job=music.submit(self.studio,self.body());self.client.ambiguous=True
        music.process_owned_job(self.studio,job['id']);self.assertEqual(self.studio.job(job['id'])['status'],'submission_unknown')
        music.process_owned_job(self.studio,job['id']);self.assertEqual(self.client.submits,1)
        with self.assertRaises(StudioError):music.resume(self.studio,job['id'])
        client=AceClient(self.client.base_url)
        response=fixture.envelope({'task_id':fixture.TASK,'status':'succeeded'})
        with patch.object(client,'_json',return_value=response) as call:
            client.submit(recipe.prepared('fixture',1,180));self.assertEqual(call.call_args.kwargs['timeout'],1800)
            client.submit(recipe.prepared('fixture',1));self.assertEqual(call.call_args.kwargs['timeout'],300)
    def test_wrong_returned_and_decoded_duration_rejected_without_truncation(self):
        job=music.submit(self.studio,self.body());music.process_owned_job(self.studio,job['id'])
        original=self.client.result
        with patch.object(self.client,'result',side_effect=lambda:{**original(),'duration':179}):music.process_owned_job(self.studio,job['id'])
        self.assertEqual(self.studio.job(job['id'])['status'],'failed')
        with self.assertRaises(ComfyError):music._inspect_wav(self.studio,self.path,30)
    def test_real_client_stream_download_bound_header_and_no_redirect(self):
        self.client.payload=recipe.prepared('fixture',1,180);result=self.client.result()
        client=AceClient(self.client.base_url)
        class Response(io.BytesIO):
            headers={'Content-Type':'audio/wav','Content-Length':'48'}
        data=b'RIFF'+b'\0'*4+b'WAVE'+b'\0'*36
        destination=Path(self.tempdir.name)/'stream.wav'
        with patch.object(client.opener,'open',return_value=Response(data)):
            copied=client.download_to(result,destination);self.assertEqual(copied['bytes'],48)
        with self.assertRaises(ComfyError):client.download_to({**result,'url':'http://elsewhere/track.wav'},Path(self.tempdir.name)/'bad.wav')
        response=Response(data);response.headers={'Content-Type':'audio/wav','Content-Length':'999999999'}
        with patch.object(client.opener,'open',return_value=response),self.assertRaises(ComfyError):client.download_to(result,Path(self.tempdir.name)/'too-large.wav')
    def test_binary_upload_http_authorization_length_and_one_use(self):
        # Small valid WAV exercises the actual server route without duplicating the large fixture.
        import wave
        buf=io.BytesIO()
        with wave.open(buf,'wb') as w:w.setnchannels(2);w.setsampwidth(2);w.setframerate(48000);w.writeframes(b'\0'*(48000*4))
        data=buf.getvalue();server=make_server(self.studio,0);threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        def begin():
            c=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
            c.request('POST','/api/audio/uploads',json.dumps({'filename':'fixture.wav','label':'Fixture','bytes':len(data)}),{'Content-Type':'application/json','X-LLR-Client':'studio'})
            r=c.getresponse();self.assertEqual(r.status,201);body=json.loads(r.read());c.close();return body['upload_url']
        url=begin()
        for changes,expected in [({'Origin':'https://untrusted.example'},403),({'Content-Length':str(len(data)-1)},400),({'Transfer-Encoding':'chunked'},400)]:
            headers={'Content-Type':'application/octet-stream','X-LLR-Client':'studio','Content-Length':str(len(data)),**changes}
            c=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5);c.request('POST',url,data,headers);r=c.getresponse();self.assertEqual(r.status,expected);r.read();c.close()
            url=begin()
        c=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
        c.request('POST',url,data,{'Content-Type':'application/octet-stream','X-LLR-Client':'studio'})
        r=c.getresponse();self.assertEqual(r.status,201);self.assertEqual(json.loads(r.read())['status'],'candidate');c.close()
        c=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5);c.request('POST',url,data,{'Content-Type':'application/octet-stream','X-LLR-Client':'studio'})
        r=c.getresponse();self.assertEqual(r.status,409);r.read();c.close()

if __name__=='__main__':unittest.main()
