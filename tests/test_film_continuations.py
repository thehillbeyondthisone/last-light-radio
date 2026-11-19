import unittest
from unittest.mock import patch
from tests import test_film_generation as fixture, test_film_images as image_fixture
from last_light_radio import film, film_generation as av, film_continuations as continuation, generation_timeline as timeline, audio_tracks
from last_light_radio.studio import StudioError

class ContinuationTests(unittest.TestCase):
    setUpClass=classmethod(fixture.JointAVTests.setUpClass.__func__)
    setUp=fixture.JointAVTests.setUp
    payload=fixture.JointAVTests.payload
    nodes=image_fixture.ImageReferencesTests.nodes
    def prepare(self):
        self.nodes()
        asset=film.import_bytes(self.studio,self.video,'fixture.mp4','Fixture',{'test_only':True,'unicode_note':'FABLE — café · 演出 🎬'})
        film.review_asset(self.studio,asset['id'],{'decision':'approved','expected_version':0,'notes':'Isolated fixture'})
        project=film.create_project(self.studio,{'title':'Continuation fixture'})
        seq=film.create_sequence(self.studio,project['id'],{'title':'Trimmed source'})
        self.seq=film.save_sequence(self.studio,seq['id'],{'expected_revision':0,'title':'Trimmed source','width':64,'height':48,
            'shots':[{'id':'first','asset_id':asset['id'],'source_in_frame':10,'duration_frames':20},
                     {'id':'second','asset_id':asset['id'],'source_in_frame':40,'duration_frames':12}]})
        film.process_export(self.studio,self.seq['id'],self.studio.store.read_snapshot(self.seq['manifest']))
        return continuation.prepare(self.studio,{'sequence_id':seq['id'],'shot_id':'first','expected_revision':1})
    def body(self,c):
        self.params.update(first_frame_id=c['first_frame_id'],continuation_id=c['id'])
        return {**self.payload(),'destination':c['destination']}
    def finish(self,c):
        job=av.submit(self.studio,self.body(c));self.studio.process_job(job['id']);self.studio.process_job(job['id'])
        self.assertEqual(self.studio.job(job['id'])['status'],'success')
        record=timeline.placement(self.studio,job['id'])
        # Same-byte original video is already approved; imported production PCM still needs review.
        audio_tracks.review(self.studio,record['audio_asset_id'],{'decision':'approved','expected_version':0,'notes':'Fixture production review'})
        return job
    def test_trimmed_boundary_uses_actual_export_not_file_end(self):
        c=self.prepare()
        self.assertEqual(c['source']['last_used_source_frame'],29)
        self.assertEqual(c['source']['rendered_frame'],19)
        self.assertEqual((c['image']['width'],c['image']['height']),(64,48))
        self.assertEqual(c['destination']['insert_index'],1)
        self.assertEqual(c['id'],continuation.prepare(self.studio,{'sequence_id':self.seq['id'],'shot_id':'first','expected_revision':1})['id'])
        self.assertEqual(self.worker.submits,0)
    def test_adjacent_picture_audio_offsets_and_duplicate_retry(self):
        c=self.prepare();job=self.finish(c)
        self.assertEqual(job['metadata']['continuation']['id'],c['id'])
        result=timeline.place(self.studio,job['id'],{'expected_revision':1,'insert_index':1})['sequence']
        self.assertEqual(result['shots'][0],self.seq['shots'][0]);self.assertEqual(result['shots'][2],self.seq['shots'][1])
        self.assertEqual(result['shots'][1]['source_in_frame'],1);self.assertEqual(result['shots'][1]['duration_frames'],123)
        track=result['audio_tracks'][0]
        self.assertEqual((track['source_in_frame'],track['duration_frames'],track['start_frame']),(1,123,20))
        self.assertEqual(timeline.place(self.studio,job['id'],{'expected_revision':1,'insert_index':1})['sequence']['revision'],2)
        self.assertEqual(self.worker.submits,1)
    def test_stale_lineage_blocks_preflight_submission_and_placement(self):
        c=self.prepare();body=self.body(c)
        film.save_sequence(self.studio,self.seq['id'],{**self.seq,'expected_revision':1,'title':'Changed'})
        with self.assertRaises(StudioError):av.preflight(self.studio,self.params)
        with self.assertRaises(StudioError):av.submit(self.studio,body)
        self.assertEqual(self.worker.submits,0)
    def test_wrong_destination_and_missing_shot_rejected(self):
        c=self.prepare();body=self.body(c)
        with self.assertRaises(StudioError):av.submit(self.studio,{**body,'destination':{**c['destination'],'insert_index':2}})
        with self.assertRaises(StudioError):continuation.prepare(self.studio,{'sequence_id':self.seq['id'],'shot_id':'absent','expected_revision':1})
        job=self.finish(c)
        with self.assertRaises(StudioError):timeline.place(self.studio,job['id'],{'expected_revision':1,'insert_index':2})
        film.save_sequence(self.studio,self.seq['id'],{**self.seq,'expected_revision':1,'title':'Changed after generation'})
        with self.assertRaises(StudioError):timeline.place(self.studio,job['id'],{'expected_revision':2,'insert_index':1})
    def test_single_generated_frame_guard_preserves_original(self):
        c=self.prepare();job=self.finish(c);original=film.asset
        def one(studio,identity):return {**original(studio,identity),'frame_count':1}
        with patch.object(film,'asset',side_effect=one),self.assertRaises(StudioError):
            timeline.place(self.studio,job['id'],{'expected_revision':1,'insert_index':1})
        self.assertEqual(film.sequence(self.studio,self.seq['id'])['revision'],1)

if __name__=='__main__':unittest.main()
