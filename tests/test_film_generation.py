"""No-GPU verification of proven joint-AV recipe, preflight and owned jobs."""
import copy
import json
import subprocess
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from last_light_radio import film_generation as fg, h3_joint_av_recipe as recipe, film, audio_tracks
from last_light_radio.comfy import ComfyError, inspect_workflow
from last_light_radio.live import LiveComfyClient
from last_light_radio.studio import Studio, StudioError
from last_light_radio.video_tools import ffmpeg_path

ROOT=Path(__file__).resolve().parents[1]

def definitions():
    outputs={'UNETLoader':['MODEL'],'CLIPLoader':['CLIP'],'VAELoader':['VAE'],'LoraLoaderModelOnly':['MODEL'],
             'MiniMaxH3ImageToVideo':['CONDITIONING','LATENT'],'BasicGuider':['GUIDER'],'RandomNoise':['NOISE'],
             'KSamplerSelect':['SAMPLER'],'BasicScheduler':['SIGMAS'],'SamplerCustomAdvanced':['LATENT'],
             'VAEDecode':['IMAGE'],'CreateVideo':['VIDEO'],'SaveVideo':[],'LTXVSeparateAVLatent':['LATENT','LATENT'],'VAEDecodeAudio':['AUDIO']}
    result={}
    for node in recipe.GRAPH.values():
        specs={}
        for name,value in node['inputs'].items():
            if isinstance(value,list):kind=outputs[recipe.GRAPH[value[0]]['class_type']][value[1]]
            elif type(value) is int:kind='INT'
            elif type(value) is float:kind='FLOAT'
            else:kind='STRING'
            specs[name]=[kind,{}]
        result[node['class_type']]={'input':{'required':specs},'output':outputs[node['class_type']]}
    # Actual saved live schemas exercise V3 nested combo declarations.
    result.update(json.loads((ROOT/'tests/fixtures/h3_joint_av_node_definitions.json').read_text()))
    return result

class FakeWorker:
    base_url='http://worker:8188'
    def __init__(self,video):
        self.video=video;self.definitions=definitions();self.submits=0;self.downloads=0;self.graph=None
        self.ambiguous=False;self.foreign_output=False;self.wrong_history=False
    def probe(self):return {'connected':True,'errors':[],'system_stats':{'fixture':True},'object_info':self.definitions}
    def submit(self,graph,**kwargs):
        self.submits+=1;self.graph=copy.deepcopy(graph)
        if self.ambiguous:raise ComfyError('SUBMISSION_AMBIGUOUS','Fixture lost response')
        return {'prompt_id':'fixture-owned-prompt','number':1}
    def poll(self,prompt_id):
        graph=copy.deepcopy(self.graph)
        if self.wrong_history:graph['8']['inputs']['noise_seed']+=1
        folder=self.graph['14']['inputs']['filename_prefix'].rsplit('/',1)[0]
        return {'status':'success','history':{'prompt':[0,prompt_id,graph]},
                'outputs':{'14':{'images':[{'filename':'../bad.mp4' if self.foreign_output else 'take_00001_.mp4','subfolder':folder,'type':'output'}]}}}
    def download_mp4_output(self,reference):self.downloads+=1;return self.video

class JointAVTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='joint-av-fixture-');cls.addClassCleanup(cls.temp.cleanup)
        path=Path(cls.temp.name)/'fixture.mp4'
        subprocess.run([ffmpeg_path(),'-v','error','-f','lavfi','-i','color=c=darkblue:s=672x384:r=24',
                        '-f','lavfi','-i','sine=frequency=440:sample_rate=32000','-t',str(124/24),'-frames:v','124',
                        '-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-ac','2',str(path)],check=True,capture_output=True)
        cls.video=path.read_bytes()
    def setUp(self):
        self.tempdir=tempfile.TemporaryDirectory(prefix='joint-av-test-');self.addCleanup(self.tempdir.cleanup)
        self.worker=FakeWorker(self.video)
        self.studio=Studio(self.tempdir.name,client_factory=lambda *a,**k:self.worker)
        self.params={'recipe_id':recipe.RECIPE_ID,'worker_url':self.worker.base_url,'brief':'Explicit isolated test brief, not a creative submission','seed':123}
    def payload(self):
        preflight=fg.preflight(self.studio,self.params)
        self.assertTrue(preflight['ready'],preflight)
        return {**self.params,'label':'Joint AV fixture','preflight_id':preflight['id'],'request_id':'test-request'}
    def finished(self):
        job=fg.submit(self.studio,self.payload())
        self.studio.process_job(job['id']);self.assertEqual(self.studio.job(job['id'])['status'],'queued')
        self.studio.process_job(job['id'])
        current=self.studio.job(job['id']);self.assertEqual(current['status'],'success',current)
        return current
    def test_recipe_is_text_only_and_v3_nested_fields_are_validated(self):
        graph=recipe.prepared('test',1,'Film/test/take')
        self.assertNotIn('first_frame',graph['6']['inputs'])
        self.assertNotIn('last_frame',graph['6']['inputs'])
        defs=fg.normalized_definitions(graph,self.worker.definitions)
        self.assertTrue(inspect_workflow(graph,defs)['valid'])
        graph['14']['inputs']['format.codec.encoding.crf']=90
        self.assertFalse(inspect_workflow(graph,fg.normalized_definitions(graph,self.worker.definitions))['valid'])
        with self.assertRaises(StudioError):fg.preflight(self.studio,{**self.params,'reference_scene_id':'not-proven'})
        self.assertEqual(self.worker.submits,0)
    def test_preflight_is_read_only_and_exact_settings_are_required(self):
        payload=self.payload();self.assertEqual(self.studio.jobs(),[]);self.assertEqual(self.worker.submits,0)
        for change in ({'brief':'Changed brief'},{'seed':124},{'worker_url':'http://other:8188'}):
            with self.subTest(change=change),self.assertRaises(StudioError):fg.submit(self.studio,{**payload,**change})
        with patch.object(fg.time,'time',return_value=fg.time.time()+601),self.assertRaises(StudioError):fg.submit(self.studio,payload)
        self.worker.definitions.pop('VAEDecodeAudio')
        self.assertFalse(fg.preflight(self.studio,self.params)['ready'])
        self.assertEqual(self.worker.submits,0)
    def test_explicit_job_request_retries_are_idempotent(self):
        payload=self.payload();job=fg.submit(self.studio,payload)
        self.assertEqual(fg.submit(self.studio,payload)['id'],job['id'])
        self.assertEqual(self.worker.submits,0)
        self.studio.process_job(job['id']);self.assertEqual(self.worker.submits,1)
        self.assertEqual(fg.submit(self.studio,payload)['id'],job['id'])
        with self.assertRaises(StudioError):fg.submit(self.studio,{**payload,'seed':234})
        self.assertEqual(self.studio.job(job['id'])['scene_id'],'')
    def test_ambiguous_submission_never_resubmits_or_resumes_without_receipt(self):
        job=fg.submit(self.studio,self.payload());self.worker.ambiguous=True
        self.studio.process_job(job['id'])
        self.assertEqual(self.studio.job(job['id'])['status'],'submission_unknown')
        with self.assertRaises(StudioError):fg.resume(self.studio,job['id'])
        self.studio.process_job(job['id'])
        self.assertEqual(self.worker.submits,1)
    def test_take_length_is_bound_into_graph_and_validated(self):
        self.assertEqual(recipe.prepared('b',1,'p')['6']['inputs']['length'],124)
        self.assertEqual(recipe.prepared('b',1,'p',None,96)['6']['inputs']['length'],96)
        for bad in (47,50,244,'96',True):
            with self.assertRaises(StudioError):fg.preflight(self.studio,{**self.params,'length_frames':bad})
        self.params={**self.params,'length_frames':96}
        job=fg.submit(self.studio,self.payload())
        graph=self.studio.store.read_snapshot(fg.configuration(self.studio,job['id'])['workflow'])
        self.assertEqual(graph['6']['inputs']['length'],96)
        self.assertEqual(fg._length(fg.configuration(self.studio,job['id'])),96)
    def test_completed_job_preserves_muxed_video_and_exact_audio_clock(self):
        job=self.finished();done=fg._completion(self.studio,job['id'])
        self.assertEqual(self.studio.store.resolve(done['video']['path']).read_bytes(),self.video)
        self.assertEqual(done['audio']['sample_count'],248000)
        self.assertEqual(done['recipe']['source_raw_sha256'],recipe.SOURCE_RAW_SHA256)
        self.assertTrue(job['ready_to_import'])
        # Finished takes import by themselves (2026-11-19).
        self.assertEqual(len(film.listing(self.studio)['assets']),1);self.assertIsNotNone(self.studio.job(job['id'])['video_asset_id'])
        fg.resume(self.studio,job['id']);self.studio.process_job(job['id'])
        self.assertEqual(self.worker.submits,1);self.assertEqual(self.worker.downloads,1)
    def test_foreign_output_and_changed_history_are_rejected_before_download(self):
        job=fg.submit(self.studio,self.payload());self.studio.process_job(job['id'])
        self.worker.foreign_output=True;self.studio.process_job(job['id'])
        self.assertEqual(self.studio.job(job['id'])['status'],'failed');self.assertEqual(self.worker.downloads,0)
        self.worker.foreign_output=False;self.worker.wrong_history=True
        fg.resume(self.studio,job['id']);self.studio.process_job(job['id'])
        self.assertEqual(self.worker.submits,1);self.assertEqual(self.worker.downloads,0)
    def test_partial_import_retries_keep_one_pending_video_and_audio(self):
        job=self.finished()
        with patch.object(audio_tracks,'import_asset',side_effect=StudioError('Test interrupted audio import')),self.assertRaises(StudioError):
            fg.import_completed(self.studio,job['id'])
        self.assertEqual(len(film.listing(self.studio)['assets']),1)
        result=fg.import_completed(self.studio,job['id'])
        self.assertEqual(result['video']['status'],'candidate');self.assertEqual(result['audio']['status'],'candidate')
        again=fg.import_completed(self.studio,job['id'])
        self.assertEqual(result['video']['id'],again['video']['id']);self.assertEqual(result['audio']['id'],again['audio']['id'])
        self.assertEqual(len(film.listing(self.studio)['assets']),1);self.assertEqual(len(audio_tracks.listing(self.studio)['assets']),1)
        self.assertEqual(self.worker.submits,1)
    def test_mock_job_to_reviewed_film_sequence_reopen_and_mixed_export(self):
        job=self.finished()
        imported=fg.import_completed(self.studio,job['id'])
        video,audio=imported['video'],imported['audio']
        source_path=self.studio.store.resolve(video['source']['path'])
        original=source_path.read_bytes()
        film.review_asset(self.studio,video['id'],{'decision':'approved','expected_version':video['version'],
                                                'notes':'Explicit isolated synthetic pipeline test only'})
        audio_tracks.review(self.studio,audio['id'],{'decision':'approved','expected_version':audio['version'],
                                                   'notes':'Explicit isolated synthetic pipeline test only'})
        project=film.create_project(self.studio,{'title':'Synthetic joint-AV pipeline verification'})
        sequence=film.create_sequence(self.studio,project['id'],{'title':'Reviewed mock shot with its production sound'})
        shots=[{'id':'shot-1','asset_id':video['id'],'source_in_frame':0,'duration_frames':124}]
        tracks=[{'id':'sound-1','asset_id':audio['id'],'role':'production','start_frame':0,'source_in_frame':0,
                 'duration_frames':124,'gain_db':0,'fade_in_frames':0,'fade_out_frames':0,'enabled':True}]
        saved=film.save_sequence(self.studio,sequence['id'],{'title':sequence['title'],'expected_revision':0,
                                  'width':336,'height':192,'shots':shots,'audio_tracks':tracks})
        reopened=Studio(self.tempdir.name)
        restored=film.sequence(reopened,sequence['id'])
        self.assertEqual(restored['shots'],shots);self.assertEqual(restored['audio_tracks'],tracks)
        film.process_export(reopened,sequence['id'],reopened.store.read_snapshot(restored['manifest']))
        result=film.sequence(reopened,sequence['id'])
        self.assertEqual(result['export']['status'],'complete',result['export'])
        self.assertEqual(result['export']['report']['inspection']['frame_count'],124)
        self.assertEqual(result['export']['report']['audio'],'mixed')
        path,_=film.export_media(reopened,sequence['id'],'media')
        raw=subprocess.run([ffmpeg_path(),'-v','error','-i',str(path),'-map','0:a:0','-f','s16le','-ac','1','-ar','48000','pipe:1'],capture_output=True,check=True).stdout
        samples=struct.unpack('<'+'h'*(len(raw)//2),raw)
        self.assertGreaterEqual(len(samples),248000);self.assertLess(len(samples),250048)
        self.assertGreater(max(abs(v) for v in samples),1000)
        self.assertEqual(source_path.read_bytes(),original)
        self.assertEqual(self.worker.submits,1)

    def test_mp4_downloader_rejects_unsafe_paths_and_wrong_mime(self):
        client=LiveComfyClient('http://worker:8188')
        with self.assertRaises(ComfyError):client.download_mp4_output({'filename':'../bad.mp4','subfolder':'','type':'output'})
        with patch.object(client,'_request',return_value=(200,{'content-type':'image/png'},self.video)),self.assertRaises(ComfyError):
            client.download_mp4_output({'filename':'take.mp4','subfolder':'safe','type':'output'})
        with patch.object(client,'_request',return_value=(200,{'content-type':'video/mp4'},self.video)):
            self.assertEqual(client.download_mp4_output({'filename':'take.mp4','subfolder':'safe','type':'output'}),self.video)

if __name__=='__main__':unittest.main()
