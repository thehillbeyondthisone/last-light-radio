import copy
import json
import threading
import unittest
from urllib.request import urlopen, Request
from last_light_radio import film, film_story as story
from last_light_radio.studio import Studio, StudioError
from last_light_radio.server import make_server
from tests import test_film as fixtures

class StoryTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.FilmTests.setUpClass.__func__)
    setUp = fixtures.FilmTests.setUp
    approve = fixtures.FilmTests.approve
    save = fixtures.FilmTests.save

    def prepare(self):
        # Include UTF-8-only provenance in the actual exported source manifest.
        from last_light_radio.store import canonical_bytes
        with self.studio.db() as db:
            asset=film.asset(self.studio,self.assets[0]['id'])
            asset['provenance']['unicode_note']='FABLE — café · 演出 🎬'
            film._write(db,'film.asset.'+asset['id'],asset)
        self.approve(); seq = self.save()
        film.process_export(self.studio, seq['id'], self.studio.store.read_snapshot(seq['manifest']))
        self.body = {'expected_revision':0, 'title':'Isolated branching fixture', 'start_node_id':'opening',
                     'nodes':[{'id':'opening','title':'Opening','sequence_id':seq['id'],'terminal':False,
                               'choices':[{'id':'continue','label':'Continue','target_node_id':'ending'}]},
                              {'id':'ending','title':'Ending','sequence_id':seq['id'],'terminal':True,'choices':[]}]}
        return story.save(self.studio, self.project['id'], self.body)

    def test_save_reopen_stale_revision_and_project_isolation(self):
        saved=self.prepare()
        self.assertEqual(story.story(Studio(self.tempdir.name),self.project['id']),saved)
        with self.assertRaises(StudioError):story.save(self.studio,self.project['id'],self.body)
        other=film.create_project(self.studio,{'title':'Other'})
        with self.assertRaises(StudioError):story.save(self.studio,other['id'],self.body)
        self.assertEqual(story.story(self.studio,other['id'])['nodes'],[])

    def test_graph_validation_and_cycles_bounded(self):
        self.prepare()
        for update in ('missing','duplicate','terminal','start'):
            body=copy.deepcopy(self.body);body['expected_revision']=1
            if update=='missing':body['nodes'][0]['choices'][0]['target_node_id']='absent'
            if update=='duplicate':body['nodes'][1]['id']='opening'
            if update=='terminal':body['nodes'][0]['terminal']=True
            if update=='start':body['start_node_id']='absent'
            with self.subTest(update=update),self.assertRaises(StudioError):story.save(self.studio,self.project['id'],body)
        body=copy.deepcopy(self.body);body['expected_revision']=1
        body['nodes'][1].update(terminal=False,choices=[{'id':'again','label':'Again','target_node_id':'opening'}])
        story.save(self.studio,self.project['id'],body)
        story.export(self.studio,self.project['id'],{'expected_revision':2})
        self.assertEqual(story.frozen(self.studio,self.project['id'])['max_transitions'],256)

    def test_frozen_media_survives_cut_change_and_story_edit(self):
        self.prepare(); result=story.export(self.studio,self.project['id'],{'expected_revision':1})
        digest=result['export']['manifest_hash'];manifest=story.frozen(self.studio,self.project['id'])
        original=story.media(self.studio,self.project['id'],digest,'opening').read_bytes()
        film.save_sequence(self.studio,self.seq['id'],{**self.payload,'expected_revision':1,'title':'Edited cut','shots':list(reversed(self.payload['shots']))})
        changed=film.sequence(self.studio,self.seq['id'])
        film.process_export(self.studio,changed['id'],self.studio.store.read_snapshot(changed['manifest']))
        self.assertEqual(story.media(self.studio,self.project['id'],digest,'opening').read_bytes(),original)
        story.save(self.studio,self.project['id'],{**self.body,'expected_revision':1,'title':'Edited story'})
        self.assertIsNone(story.story(self.studio,self.project['id'])['export'])
        self.assertEqual(story.frozen(self.studio,self.project['id'],digest)['story_revision'],1)
        self.assertEqual(manifest['nodes'][0]['sequence_revision'],1)
        updated=story.export(self.studio,self.project['id'],{'expected_revision':2})
        self.assertNotEqual(updated['export']['manifest_hash'],digest)
        self.assertEqual(story.frozen(self.studio,self.project['id'])['nodes'][0]['sequence_revision'],2)

    def test_revocation_and_tampering_block_frozen_playback(self):
        self.prepare();result=story.export(self.studio,self.project['id'],{'expected_revision':1})
        film.review_asset(self.studio,self.assets[0]['id'],{'decision':'rejected','expected_version':1,'notes':'Isolated revoke'})
        story.frozen(self.studio,self.project['id'])  # review status no longer gates Film (2026-11-19)
        self.studio.store.resolve(self.assets[0]['source']['path']).write_bytes(b'tamper')
        with self.assertRaises((StudioError,ValueError)):story.frozen(self.studio,self.project['id'])

    def test_missing_source_and_export_corruption(self):
        self.prepare()
        path,_=film.export_media(self.studio,self.seq['id'],'media');path.write_bytes(b'corrupt')
        with self.assertRaises(StudioError):story.export(self.studio,self.project['id'],{'expected_revision':1})
        self.studio.store.resolve(self.assets[0]['source']['path']).unlink()
        with self.assertRaises((ValueError,OSError)):story.export(self.studio,self.project['id'],{'expected_revision':1})

    def test_http_contract_and_frozen_hash_enforcement(self):
        self.prepare(); server=make_server(self.studio,0)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        base=f'http://127.0.0.1:{server.server_port}'
        route=f'/api/film/projects/{self.project["id"]}/story'
        with urlopen(base+route) as r:self.assertEqual(json.load(r)['revision'],1)
        request=Request(base+route+'/export',data=json.dumps({'expected_revision':1}).encode(),headers={'Content-Type':'application/json','Origin':base,'X-LLR-Client':'studio'})
        with urlopen(request) as r:export=json.load(r)['export']
        with urlopen(base+export['manifest_url']) as r:manifest=json.load(r)
        with urlopen(base+manifest['nodes'][0]['media_url']) as r:self.assertEqual(r.headers['Content-Type'],'video/mp4')
        path=story.media(self.studio,self.project['id'],export['manifest_hash'],'opening');path.write_bytes(b'tampered')
        with self.assertRaises(ValueError):story.frozen(self.studio,self.project['id'])

    def test_empty_unreachable_and_node_bounds(self):
        self.prepare()
        body=copy.deepcopy(self.body);body['expected_revision']=1
        body['nodes'][0].update(terminal=True,choices=[])
        story.save(self.studio,self.project['id'],body)
        with self.assertRaises(StudioError):story.export(self.studio,self.project['id'],{'expected_revision':2})
        with self.assertRaises(StudioError):story.save(self.studio,self.project['id'],{**body,'expected_revision':2,'nodes':body['nodes']*65})
        story.save(self.studio,self.project['id'],{**body,'expected_revision':2,'nodes':[],'start_node_id':None})
        with self.assertRaises(StudioError):story.export(self.studio,self.project['id'],{'expected_revision':3})

    def test_audio_review_provenance_and_revocation(self):
        import io, wave, base64
        from last_light_radio import audio_tracks
        self.prepare()
        buf=io.BytesIO()
        with wave.open(buf,'wb') as w:
            w.setnchannels(2);w.setsampwidth(2);w.setframerate(48000);w.writeframes(b'\0'*48000*4)
        audio=audio_tracks.import_asset(self.studio,{'filename':'fixture.wav','label':'Isolated audio',
              'audio_base64':base64.b64encode(buf.getvalue()).decode(),'provenance':{'test_only':True}})
        audio=audio_tracks.review(self.studio,audio['id'],{'decision':'approved','expected_version':0,'notes':'Test fixture'})
        track={'id':'production','asset_id':audio['id'],'role':'production','start_frame':0,'source_in_frame':0,
               'duration_frames':13,'gain_db':0,'fade_in_frames':0,'fade_out_frames':0,'enabled':True}
        seq=self.save({**self.payload,'expected_revision':1,'audio_tracks':[track]})
        film.process_export(self.studio,seq['id'],self.studio.store.read_snapshot(seq['manifest']))
        story.export(self.studio,self.project['id'],{'expected_revision':1})
        manifest=story.frozen(self.studio,self.project['id'])
        self.assertEqual(manifest['nodes'][0]['review_provenance']['audio'][0]['id'],audio['id'])
        audio_tracks.review(self.studio,audio['id'],{'decision':'rejected','expected_version':1,'notes':'Test revocation'})
        story.frozen(self.studio,self.project['id'])  # review status no longer gates Film (2026-11-19)

if __name__=='__main__':unittest.main()


