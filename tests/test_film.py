"""Isolated coverage for reusable named film projects, reviewed sources and real cuts."""
import base64
import copy
import io
import json
import shutil
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from last_light_radio import film
from last_light_radio.studio import Studio, StudioError
from last_light_radio.server import make_server
from last_light_radio.video_tools import ffmpeg_path
from last_light_radio.store import sha256, canonical_bytes

class FilmTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='film-test-sources-')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.videos=[]
        for index,color in enumerate(('red','blue')):
            path=Path(cls.temp.name)/f'{color}.mp4'
            subprocess.run([ffmpeg_path(),'-v','error','-f','lavfi','-i',f'color=c={color}:s=64x48:r=24',
                            '-frames:v','12','-an','-c:v','libx264','-pix_fmt','yuv420p',str(path)],check=True,capture_output=True)
            cls.videos.append(path.read_bytes())
    def setUp(self):
        self.tempdir=tempfile.TemporaryDirectory(prefix='film-test-')
        self.addCleanup(self.tempdir.cleanup)
        self.studio=Studio(self.tempdir.name)
        self.assets=[film.import_bytes(self.studio,data,f'{i}.mp4',f'Fixture {i}',{'test_only':True}) for i,data in enumerate(self.videos)]
        self.project=film.create_project(self.studio,{'title':'Fixture project'})
        self.seq=film.create_sequence(self.studio,self.project['id'],{'title':'Cut one'})
        self.payload={'title':'Cut one','expected_revision':0,'width':64,'height':48,'audio_tracks':[],
                      'shots':[{'id':'red','asset_id':self.assets[0]['id'],'source_in_frame':2,'duration_frames':6},
                               {'id':'blue','asset_id':self.assets[1]['id'],'source_in_frame':3,'duration_frames':7}]}
    def approve(self):
        self.assets=[film.review_asset(self.studio,a['id'],{'decision':'approved','expected_version':a['version'],'notes':'Isolated test source only'}) for a in self.assets]
    def save(self,payload=None):
        return film.save_sequence(self.studio,self.seq['id'],payload or self.payload)
    def test_import_retains_bytes_and_requires_review(self):
        self.assertEqual(self.assets[0]['status'],'candidate')
        self.assertEqual(self.assets[0]['frame_count'],12)
        self.assertEqual(film.asset_media(self.studio,self.assets[0]['id']).read_bytes(),self.videos[0])
        self.save()  # No approve/reject in Film (2026-11-19): imported clips place directly.
        duplicate=film.import_bytes(self.studio,self.videos[0],'other.mp4','Other',{})
        self.assertEqual(duplicate['label'],'Fixture 0')
        self.assertEqual(duplicate['status'],'candidate')
    def test_invalid_upload_paths_and_trim_bounds(self):
        with self.assertRaises(StudioError): film.import_asset(self.studio,{'video_base64':'https://evil.example/clip','filename':'clip.mp4'})
        with self.assertRaises(StudioError): film.asset_media(self.studio,'../../secret')
        self.approve()
        for change in ({'source_in_frame':-1},{'duration_frames':99},{'asset_id':'video.'+'f'*64}):
            payload=copy.deepcopy(self.payload); payload['shots'][0].update(change)
            with self.subTest(change=change),self.assertRaises(StudioError):self.save(payload)
        with self.assertRaises(StudioError): self.save({**self.payload,'width':63})
        with self.assertRaises(StudioError): self.save({**self.payload,'shots':[]})
    def test_named_sequences_reopen_independently_and_stale_save_rejected(self):
        self.approve(); saved=self.save()
        second=film.create_sequence(self.studio,self.project['id'],{'title':'Another cut'})
        film.save_sequence(self.studio,second['id'],{**self.payload,'title':'Another cut','shots':list(reversed(self.payload['shots']))})
        reopened=Studio(self.tempdir.name)
        self.assertEqual(film.sequence(reopened,self.seq['id'])['shots'],self.payload['shots'])
        self.assertEqual(film.sequence(reopened,second['id'])['shots'],list(reversed(self.payload['shots'])))
        self.assertEqual(len(film.project(reopened,self.project['id'])['sequences']),2)
        self.assertEqual(film.sequence(reopened,self.seq['id'])['revision'],1)
        with self.assertRaises(StudioError): self.save()
    def test_review_revocation_and_tamper_block_export(self):
        self.approve(); saved=self.save(); manifest=self.studio.store.read_snapshot(saved['manifest'])
        film.review_asset(self.studio,self.assets[0]['id'],{'decision':'rejected','expected_version':1,'notes':'Test revocation'})
        film.validate_manifest(self.studio,manifest)  # review status no longer gates Film
        self.studio.store.resolve(self.assets[1]['source']['path']).write_bytes(b'tamper')
        with self.assertRaises(ValueError): film.validate_manifest(self.studio,manifest)
        with self.assertRaises(ValueError): film.asset_media(self.studio,self.assets[1]['id'])
    def test_real_cut_export_frame_order_duration_and_retry(self):
        self.approve(); saved=self.save(); manifest=self.studio.store.read_snapshot(saved['manifest'])
        film.process_export(self.studio,saved['id'],manifest)
        result=film.sequence(self.studio,saved['id'])
        self.assertEqual(result['export']['status'],'complete',result['export'])
        self.assertEqual(result['export']['report']['frames_written'],13)
        path,_=film.export_media(self.studio,saved['id'],'media')
        raw=subprocess.run([ffmpeg_path(),'-v','error','-i',str(path),'-vf','scale=1:1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],capture_output=True,check=True).stdout
        self.assertEqual(len(raw),13*3)
        for i in range(13):
            r,g,b=raw[i*3:i*3+3]
            self.assertGreater(r if i<6 else b,180)
            self.assertLess(b if i<6 else r,40)
        digest=sha256(path.read_bytes())
        film.process_export(self.studio,saved['id'],manifest)
        self.assertEqual(sha256(path.read_bytes()),digest)
    def make_completed_take(self):
        image=io.BytesIO(); Image.new('RGB',(64,48),(30,50,70)).save(image,'PNG')
        scene=self.studio.import_scene(image.getvalue(),'test.png','Take test')
        identity='a'*32
        workflow={'large_provenance':'x'*20000}
        metadata={'local_job_id':identity,'master':scene['master'],'pipeline':'actor_motion_v1',
                  'workflow':self.studio.store.save_snapshot(workflow,kind='workflows'),'workflow_sha256':'f'*64,
                  'outputs':[{**self.assets[0]['source'],'properties':{'container':'mp4','frame_count':12,'effective_fps':24,'width':64,'height':48}}]}
        self.studio.register_candidate(scene['id'],'Completed fixture take',metadata)
        self.studio.review(identity,{'decision':'approved','expected_version':0,'notes':'Isolated source approval',
                                    'entry_anchor':'rest','exit_anchor':'rest','visual_checked':True,'request_id':'test-source-review'})
        request={'kind':'live_generation_request','local_job_id':identity,'master':scene['master'],'parameters':{'seed':123,'motion_prompt':'fixture only'}}
        pointer=self.studio.store.save_snapshot(request,kind='jobs')
        self.studio.store.write_once(f'records/live_jobs/{identity}/request.json',canonical_bytes(pointer))
        self.studio.store.write_once(f'records/live_jobs/{identity}/accepted.json',canonical_bytes({'local_job_id':identity,'prompt_id':'fixture-owned-prompt'}))
        return identity

    def test_completed_take_bridge_preserves_full_receipt_without_generation_or_approval(self):
        identity=self.make_completed_take()
        before=self.studio.candidate(identity)
        with patch.object(self.studio,'submit',side_effect=AssertionError('No submission permitted')),patch.object(self.studio,'client_factory',side_effect=AssertionError('No worker contact permitted')):
            listed=film.takes(self.studio)['takes']
            self.assertEqual(listed[0]['candidate_id'],identity)
            imported=film.import_take(self.studio,{'candidate_id':identity,'output_index':0})
            again=film.import_take(self.studio,{'candidate_id':identity,'output_index':0})
        self.assertEqual(imported['status'],'candidate')
        self.assertEqual(imported['version'],0)
        self.assertEqual(len(again['generation_receipts']),1)
        bundle=self.studio.store.read_snapshot(imported['generation_receipts'][0])
        self.assertEqual(bundle['workflow']['large_provenance'],'x'*20000)
        self.assertEqual(bundle['accepted_receipt']['prompt_id'],'fixture-owned-prompt')
        self.assertEqual(bundle['generation_request']['parameters']['seed'],123)
        self.assertEqual(bundle['candidate']['metadata'],before['metadata'])
        self.assertEqual(self.studio.candidate(identity),before)
        self.assertEqual(self.studio.jobs(),[])

    def test_completed_take_bridge_rejects_corrupted_output_and_bad_index(self):
        identity=self.make_completed_take()
        with self.assertRaises(StudioError):film.import_take(self.studio,{'candidate_id':identity,'output_index':7})
        take=self.studio.candidate(identity)
        self.studio.store.resolve(take['metadata']['outputs'][0]['path']).write_bytes(b'changed source')
        self.assertEqual(film.takes(self.studio)['takes'][0]['candidate_id'],identity)
        with self.assertRaises(ValueError):film.import_take(self.studio,{'candidate_id':identity})

    def test_http_contract_project_sequence_listing_and_review(self):
        with patch('last_light_radio.server.ThreadingHTTPServer') as server_type:
            make_server(self.studio,0)
            handler=object.__new__(server_type.call_args.args[1])
        handler.close_connection=False
        def request(parts,payload=None):
            with patch.object(handler,'guard_host'),patch.object(handler,'path_parts',return_value=parts),patch.object(handler,'body',return_value=payload),patch.object(handler,'send_json',side_effect=lambda value,*args:value):
                return handler.dispatch(mutation=payload is not None)
        state=request(['api','film'])
        self.assertEqual(state['projects'][0]['id'],self.project['id'])
        reviewed=request(['api','film','assets',self.assets[0]['id'],'review'],{'decision':'approved','expected_version':0,'notes':'Test only'})
        self.assertEqual(reviewed['status'],'approved')
        project=request(['api','film','projects'],{'title':'HTTP project'})
        sequence=request(['api','film','projects',project['id'],'sequences'],{'title':'HTTP sequence'})
        self.assertEqual(request(['api','film','sequences',sequence['id']])['title'],'HTTP sequence')

if __name__=='__main__':unittest.main()
