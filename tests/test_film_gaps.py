"""Optional gaps, tested only in disposable libraries."""
import copy, importlib.util, json, subprocess, unittest
from pathlib import Path
from last_light_radio import film, film_continuations, film_story
from last_light_radio.studio import Studio, StudioError
from last_light_radio.video_tools import ffmpeg_path
from tests import test_film as fixture

class GapTests(unittest.TestCase):
    setUpClass=classmethod(fixture.FilmTests.setUpClass.__func__)
    setUp=fixture.FilmTests.setUp
    approve=fixture.FilmTests.approve
    def save(self,gap=None):
        self.approve()
        self.body=copy.deepcopy(self.payload)
        self.body['shots'].insert(1,gap or {'id':'gap','kind':'gap','duration_frames':24})
        return film.save_sequence(self.studio,self.seq['id'],self.body)
    def test_roundtrip_and_starts(self):
        seq=self.save()
        reopened=Studio(self.tempdir.name)
        self.assertEqual(film.sequence(reopened,seq['id'])['shots'],self.body['shots'])
        m=reopened.store.read_snapshot(seq['manifest'])
        self.assertEqual([s['start_frame'] for s in m['shots']],[0,6,30])
        self.assertEqual(m['duration_frames'],37)
        self.assertEqual(m['renderer_version'],film.GAP_VERSION)
    def test_invalid_gap_fields(self):
        self.approve()
        for change in ({'duration_frames':0},{'duration_frames':True},{'asset_id':None},{'source_in_frame':0},{'kind':'unknown'}):
            body=copy.deepcopy(self.payload)
            body['shots']=[{'id':'gap','kind':'gap','duration_frames':24,**change}]
            with self.subTest(change=change),self.assertRaises(StudioError):
                film.save_sequence(self.studio,self.seq['id'],body)
    def test_adjacent_trailing_and_limit(self):
        self.approve()
        body={**self.payload,'shots':[{'id':'g1','kind':'gap','duration_frames':1},{'id':'g2','kind':'gap','duration_frames':14399}]}
        seq=film.save_sequence(self.studio,self.seq['id'],body)
        self.assertEqual(seq['shots'],body['shots'])
        body['expected_revision']=1;body['shots'][1]['duration_frames']=14400
        with self.assertRaises(StudioError):film.save_sequence(self.studio,self.seq['id'],body)
    def test_unreviewed_video_places_after_gap(self):
        # No approve/reject in Film (2026-11-19); a gap before an unreviewed clip saves.
        saved=film.save_sequence(self.studio,self.seq['id'],{**self.payload,'shots':[{'id':'g','kind':'gap','duration_frames':1}]+self.payload['shots']})
        self.assertEqual(saved['shots'][0]['kind'],'gap')
    def test_legacy_manifest_matches_original_code(self):
        path=Path(__file__).parents[1]/'artifacts/gap-backend-20261114/before/film.py'
        spec=importlib.util.spec_from_file_location('last_light_radio._gap_baseline',path)
        baseline=importlib.util.module_from_spec(spec);spec.loader.exec_module(baseline)
        self.approve()
        old=baseline.save_sequence(self.studio,self.seq['id'],self.payload)
        new=film.save_sequence(self.studio,self.seq['id'],{**self.payload,'expected_revision':1})
        self.assertEqual(old['manifest_hash'],new['manifest_hash'])
        self.assertEqual(old['manifest'],new['manifest'])
    def test_render_black_and_pts(self):
        seq=self.save()
        film.process_export(self.studio,seq['id'],self.studio.store.read_snapshot(seq['manifest']))
        seq=film.sequence(self.studio,seq['id'])
        self.assertEqual(seq['export']['status'],'complete',seq['export'])
        path,_=film.export_media(self.studio,seq['id'],'media')
        raw=subprocess.run([ffmpeg_path(),'-v','error','-i',str(path),'-vf','scale=1:1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],capture_output=True,check=True).stdout
        self.assertEqual(len(raw),37*3)
        for i in range(37):
            rgb=raw[i*3:i*3+3]
            if 6<=i<30:self.assertLessEqual(max(rgb),3)
            else:self.assertGreater(rgb[0 if i<6 else 2],180)
        self.assertEqual(seq['export']['report']['frames_written'],37)
        self.assertEqual(seq['export']['report']['renderer_version'],film.GAP_VERSION)
    def test_gap_only_renders_video(self):
        self.approve()
        seq=film.save_sequence(self.studio,self.seq['id'],{**self.payload,'shots':[{'id':'g','kind':'gap','duration_frames':3}]})
        film.process_export(self.studio,seq['id'],self.studio.store.read_snapshot(seq['manifest']))
        self.assertEqual(film.export_media(self.studio,seq['id'],'media')[1],'video/mp4')
    def test_continue_gap_refused(self):
        seq=self.save()
        with self.assertRaisesRegex(StudioError,'gap has no picture'):
            film_continuations.prepare(self.studio,{'sequence_id':seq['id'],'expected_revision':1,'shot_id':'gap'})
    def test_exact_gap_fill_fixed_duration(self):
        seq=self.save({'id':'gap','kind':'gap','duration_frames':8})
        seq=film.save_sequence(self.studio,seq['id'],{**self.body,'expected_revision':1,'timeline_duration_frames':21})
        result=film.place_picture_interval(self.studio,seq['id'],{'expected_revision':2,'start_frame':6,'end_frame':14,'shot_id':'fill','asset_id':self.assets[0]['id'],'source_in_frame':0,'trim_to_fit':True})
        self.assertEqual(result['duration_frames'],21)
        self.assertEqual(result['shots'][1]['id'],'fill')
        self.assertEqual(result['audio_tracks'],seq['audio_tracks'])
    def test_changed_gap_invalidates_export(self):
        seq=self.save()
        body=copy.deepcopy(self.body);body['expected_revision']=1;body['shots'][1]['duration_frames']=25
        changed=film.save_sequence(self.studio,seq['id'],body)
        self.assertNotEqual(seq['manifest_hash'],changed['manifest_hash'])
        self.assertEqual(changed['export']['status'],'draft')
    def test_fmv_gap_provenance(self):
        seq=self.save()
        film.process_export(self.studio,seq['id'],self.studio.store.read_snapshot(seq['manifest']))
        film_story.save(self.studio,self.project['id'],{'expected_revision':0,'title':'Gap node','start_node_id':'one',
            'nodes':[{'id':'one','title':'One','sequence_id':seq['id'],'terminal':True,'choices':[]}]})
        film_story.export(self.studio,self.project['id'],{'expected_revision':1})
        frozen=film_story.frozen(self.studio,self.project['id'])
        self.assertEqual(len(frozen['nodes'][0]['review_provenance']['video']),2)
    def test_gap_save_preserves_audio_timing(self):
        from tests.test_film_audiofirst import AudioFirstTests
        seq=AudioFirstTests.prepare(self)
        saved=film.save_sequence(self.studio,seq['id'],{**self.body,'expected_revision':1,
            'shots':[{'id':'g','kind':'gap','duration_frames':48}]})
        self.assertEqual(saved['audio_tracks'],seq['audio_tracks'])
        self.assertEqual(saved['markers'],seq['markers'])
        self.assertEqual(saved['selection'],seq['selection'])

if __name__=='__main__':unittest.main()


