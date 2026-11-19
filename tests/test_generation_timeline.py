import copy
import unittest
from unittest.mock import patch
from tests import test_film_generation as av_fixture, test_music_generation as music_fixture
from last_light_radio import film, audio_tracks, film_generation as av, music_generation as music, generation_timeline as timeline
from last_light_radio.studio import Studio,StudioError

class TimelineAVTests(unittest.TestCase):
    setUpClass=classmethod(av_fixture.JointAVTests.setUpClass.__func__)
    setUp=av_fixture.JointAVTests.setUp
    payload=av_fixture.JointAVTests.payload
    def begin(self):
        project=film.create_project(self.studio,{'title':'Isolated generation destination'})
        self.seq=film.create_sequence(self.studio,project['id'],{'title':'Generated cut'})
        self.body={**self.payload(),'destination':{'sequence_id':self.seq['id'],'expected_revision':0,'track':'V1','insert_index':0}}
        return av.submit(self.studio,self.body)
    def finish(self,job):
        self.studio.process_job(job['id']);self.studio.process_job(job['id'])
        return timeline.placement(self.studio,job['id'])
    def approve(self,record):
        film.review_asset(self.studio,record['video_asset_id'],{'decision':'approved','expected_version':0,'notes':'Isolated fixture review'})
        audio_tracks.review(self.studio,record['audio_asset_id'],{'decision':'approved','expected_version':0,'notes':'Isolated fixture review'})
    def test_placeholder_metadata_candidate_approval_place_reopen_duplicate(self):
        job=self.begin()
        self.assertEqual(timeline.listing(self.studio,self.seq['id'])['placements'][0]['stage'],'pending')
        self.assertEqual(job['metadata']['seed'],123);self.assertIsNone(job['metadata']['completed'])
        self.assertEqual(av.submit(self.studio,self.body)['id'],job['id'])
        # No approve/reject (2026-11-19): an imported take is ready to place straight away.
        record=self.finish(job);self.assertEqual(record['stage'],'ready_to_place')
        self.assertIsNotNone(record['job']['metadata']['completed'])
        self.assertEqual(film.sequence(self.studio,self.seq['id'])['shots'],[])
        self.assertEqual(film.asset(self.studio,record['video_asset_id'])['status'],'candidate')
        saved=timeline.place(self.studio,job['id'],{'expected_revision':0,'insert_index':0})
        self.assertEqual(len(saved['sequence']['shots']),1);self.assertEqual(len(saved['sequence']['audio_tracks']),1)
        reopened=Studio(self.tempdir.name)
        retried=timeline.place(reopened,job['id'],{'expected_revision':0,'insert_index':0})
        self.assertEqual(retried['sequence']['revision'],1)
        self.assertEqual(av.submit(reopened,self.body)['id'],job['id'])
        self.assertEqual(self.worker.submits,1)
    def test_conflict_explicit_reselection_and_ripple(self):
        job=self.begin();record=self.finish(job);self.approve(record)
        first=timeline.place(self.studio,job['id'],{'expected_revision':0,'insert_index':0})['sequence']
        # Use the same approved picture twice; two audio clips prove boundary policy.
        tracks=[{**first['audio_tracks'][0],'id':'spanning','start_frame':0,'duration_frames':124},
                {**first['audio_tracks'][0],'id':'downstream','start_frame':124,'duration_frames':124}]
        seq=film.save_sequence(self.studio,self.seq['id'],{'expected_revision':1,'title':'Before','shots':[
            {**first['shots'][0],'id':'one'},{**first['shots'][0],'id':'two'}],'audio_tracks':tracks})
        body={**self.payload(),'request_id':'second','destination':{'sequence_id':seq['id'],'expected_revision':2,'track':'V1','insert_index':1}}
        second=av.submit(self.studio,body)
        # Advance cut revision while the owned job runs.
        film.save_sequence(self.studio,seq['id'],{**seq,'expected_revision':2,'title':'New edit'})
        record=self.finish(second);self.assertEqual(record['stage'],'conflict')
        with self.assertRaises(StudioError):timeline.place(self.studio,second['id'],{'expected_revision':2,'insert_index':1})
        result=timeline.place(self.studio,second['id'],{'expected_revision':3,'insert_index':1})['sequence']
        audio={a['id']:a for a in result['audio_tracks']}
        self.assertEqual(audio['spanning']['start_frame'],0)
        self.assertEqual(audio['downstream']['start_frame'],248)
        self.assertEqual(audio['gen-'+second['id']+'-production']['start_frame'],124)
    def test_import_failure_retry_preserves_success_and_no_submit(self):
        job=self.begin();self.studio.process_job(job['id'])
        with patch.object(av,'import_completed',side_effect=RuntimeError('Fixture import interrupted')):
            self.studio.process_job(job['id'])
        self.assertEqual(self.studio.job(job['id'])['status'],'success')
        self.assertEqual(timeline.placement(self.studio,job['id'])['stage'],'awaiting_import')
        av.import_completed(self.studio,job['id'])
        self.assertEqual(timeline.placement(self.studio,job['id'])['stage'],'ready_to_place')
        self.assertEqual(self.worker.submits,1)
    def test_ambiguous_submission_keeps_placeholder_without_placement(self):
        job=self.begin();self.worker.ambiguous=True;self.studio.process_job(job['id'])
        self.assertEqual(timeline.placement(self.studio,job['id'])['stage'],'submission_unknown')
        with self.assertRaises(StudioError):timeline.place(self.studio,job['id'],{'expected_revision':0,'insert_index':0})
        with self.assertRaises(StudioError):av.submit(self.studio,{**self.body,'destination':{**self.body['destination'],'insert_index':1}})
        self.assertEqual(self.worker.submits,1)

    def test_placement_receipt_interruption_recovers_without_duplicate(self):
        job=self.begin();record=self.finish(job);self.approve(record)
        original=self.studio.set_setting
        def fail_receipt(key,value):
            if key=='film.generation.destination.'+job['id'] and value.get('placed_revision'):
                raise RuntimeError('Fixture interrupted receipt write')
            return original(key,value)
        with patch.object(self.studio,'set_setting',side_effect=fail_receipt),self.assertRaises(RuntimeError):
            timeline.place(self.studio,job['id'],{'expected_revision':0,'insert_index':0})
        result=timeline.place(Studio(self.tempdir.name),job['id'],{'expected_revision':0,'insert_index':0})
        self.assertEqual(result['sequence']['revision'],1)
        self.assertEqual(len(result['sequence']['shots']),1)
        self.assertEqual(result['placement']['stage'],'placed')

    def test_http_status_metadata_place_and_pending_guard(self):
        import json,threading
        from urllib.request import Request,urlopen
        from urllib.error import HTTPError
        from last_light_radio.server import make_server
        job=self.begin();server=make_server(self.studio,0)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        base=f'http://127.0.0.1:{server.server_port}'
        with urlopen(base+'/api/film/sequences/'+self.seq['id']+'/generations') as r:
            record=json.load(r)['placements'][0]
        self.assertEqual(record['job']['metadata']['seed'],123)
        self.assertIn('2:unet_name',record['job']['metadata']['models'])
        request=Request(base+'/api/film/generations/'+job['id']+'/place',data=b'{"expected_revision":0,"insert_index":0}',
                        headers={'Content-Type':'application/json','X-LLR-Client':'studio'})
        with self.assertRaises(HTTPError) as caught:urlopen(request)
        self.assertEqual(caught.exception.code,409)
        record=self.finish(job);self.approve(record)
        with urlopen(request) as r:self.assertEqual(json.load(r)['placement']['stage'],'placed')

    def test_audio_first_explicit_duration_expands_for_disclosed_v1_ripple(self):
        import io,wave,base64
        job=self.begin()
        # Prepare a new independent audio-first timeline before generation submission.
        buf=io.BytesIO()
        with wave.open(buf,'wb') as wav:
            wav.setnchannels(2);wav.setsampwidth(2);wav.setframerate(48000);wav.writeframes(b'\0'*(48000*4*30))
        audio=audio_tracks.import_asset(self.studio,{'filename':'fixture.wav','label':'30 second fixture bed',
              'audio_base64':base64.b64encode(buf.getvalue()).decode(),'provenance':{'test_only':True}})
        audio_tracks.review(self.studio,audio['id'],{'decision':'approved','expected_version':0,'notes':'Fixture'})
        track={'id':'bed','asset_id':audio['id'],'role':'music','start_frame':0,'source_in_frame':0,'duration_frames':720,
               'gain_db':0,'fade_in_frames':0,'fade_out_frames':0,'enabled':True}
        seq=film.save_sequence(self.studio,self.seq['id'],{'expected_revision':0,'title':'Audio first','shots':[],
                               'audio_tracks':[track],'timeline_duration_frames':720})
        record=self.finish(job);self.approve(record)
        result=timeline.place(self.studio,job['id'],{'expected_revision':1,'insert_index':0,'audio_policy':'ripple'})['sequence']
        self.assertEqual(result['timeline_duration_frames'],844)
        self.assertEqual(result['duration_frames'],844)
        self.assertEqual(next(a for a in result['audio_tracks'] if a['id']=='bed')['start_frame'],124)
        self.assertEqual(result['picture_duration_frames'],124)

    def test_audio_first_default_preserves_fixed_audio_timing(self):
        import io,wave,base64
        job=self.begin()
        # Prepare a new independent audio-first timeline before generation submission.
        buf=io.BytesIO()
        with wave.open(buf,'wb') as wav:
            wav.setnchannels(2);wav.setsampwidth(2);wav.setframerate(48000);wav.writeframes(b'\0'*(48000*4*30))
        audio=audio_tracks.import_asset(self.studio,{'filename':'fixture.wav','label':'30 second fixture bed',
              'audio_base64':base64.b64encode(buf.getvalue()).decode(),'provenance':{'test_only':True}})
        audio_tracks.review(self.studio,audio['id'],{'decision':'approved','expected_version':0,'notes':'Fixture'})
        track={'id':'bed','asset_id':audio['id'],'role':'music','start_frame':0,'source_in_frame':0,'duration_frames':720,
               'gain_db':0,'fade_in_frames':0,'fade_out_frames':0,'enabled':True}
        seq=film.save_sequence(self.studio,self.seq['id'],{'expected_revision':0,'title':'Audio first','shots':[],
                               'audio_tracks':[track],'timeline_duration_frames':720})
        record=self.finish(job);self.approve(record)
        result=timeline.place(self.studio,job['id'],{'expected_revision':1,'insert_index':0})['sequence']
        self.assertEqual(result['timeline_duration_frames'],720)
        self.assertEqual(result['duration_frames'],720)
        self.assertEqual(next(a for a in result['audio_tracks'] if a['id']=='bed')['start_frame'],0)
        self.assertEqual(result['picture_duration_frames'],124)

class TimelineMusicTests(unittest.TestCase):
    setUpClass=classmethod(music_fixture.MusicGenerationTests.setUpClass.__func__)
    setUp=music_fixture.MusicGenerationTests.setUp
    payload=music_fixture.MusicGenerationTests.payload
    def test_music_candidate_review_trim_confirmation_and_placement(self):
        asset=film.import_bytes(self.studio,self.video,'fixture.mp4','Fixture',{'test_only':True})
        film.review_asset(self.studio,asset['id'],{'decision':'approved','expected_version':0,'notes':'Fixture'})
        project=film.create_project(self.studio,{'title':'Fixture'});seq=film.create_sequence(self.studio,project['id'],{'title':'Cut'})
        seq=film.save_sequence(self.studio,seq['id'],{'expected_revision':0,'title':'Cut','shots':[{'id':'first','asset_id':asset['id'],'source_in_frame':0,'duration_frames':72}]})
        body={**self.payload(),'destination':{'sequence_id':seq['id'],'expected_revision':1,'track':'A2','start_frame':24}}
        job=music.submit(self.studio,body);music.process_owned_job(self.studio,job['id']);music.process_owned_job(self.studio,job['id'])
        record=timeline.placement(self.studio,job['id']);self.assertEqual(record['stage'],'ready_to_place')  # no review step (2026-11-19)
        with self.assertRaises(StudioError):timeline.place(self.studio,job['id'],{'expected_revision':1,'start_frame':24})
        placed=timeline.place(self.studio,job['id'],{'expected_revision':1,'start_frame':24,'accept_trim':True})
        self.assertEqual(placed['placement']['placement']['requested_duration_frames'],720)
        self.assertEqual(placed['sequence']['audio_tracks'][0]['duration_frames'],48)
        self.assertEqual(timeline.place(self.studio,job['id'],{'expected_revision':1,'start_frame':24})['sequence']['revision'],2)
        self.assertEqual(self.client.submits,1)

if __name__=='__main__':unittest.main()
