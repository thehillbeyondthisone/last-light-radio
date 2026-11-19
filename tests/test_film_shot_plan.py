import base64,copy,io,json,threading,unittest,wave
from urllib.request import Request,urlopen
from tests import test_film_generation as fixture
from last_light_radio import film,film_generation as av,film_shot_plan as plans,generation_timeline as timeline,audio_tracks
from last_light_radio.studio import Studio,StudioError
from last_light_radio.server import make_server

class ShotPlanTests(unittest.TestCase):
    setUpClass=classmethod(fixture.JointAVTests.setUpClass.__func__)
    setUp=fixture.JointAVTests.setUp
    payload=fixture.JointAVTests.payload
    def prepare(self):
        buf=io.BytesIO()
        with wave.open(buf,'wb') as w:
            w.setnchannels(2);w.setsampwidth(2);w.setframerate(48000);w.writeframes(b'\0'*(2000*4*248))
        a=audio_tracks.import_asset(self.studio,{'filename':'bed.wav','label':'Fixture audio','audio_base64':base64.b64encode(buf.getvalue()).decode(),'provenance':{'test_only':True}})
        audio_tracks.review(self.studio,a['id'],{'decision':'approved','expected_version':0,'notes':'Fixture'})
        self.audio={'id':'fixed-bed','asset_id':a['id'],'role':'music','start_frame':0,'source_in_frame':0,'duration_frames':248,'gain_db':0,'fade_in_frames':0,'fade_out_frames':0,'enabled':True}
        project=film.create_project(self.studio,{'title':'Plan fixture'});seq=film.create_sequence(self.studio,project['id'],{'title':'Audio led'})
        self.seq=film.save_sequence(self.studio,seq['id'],{'expected_revision':0,'title':'Audio led','shots':[],
            'timeline_duration_frames':248,'audio_tracks':[self.audio],'width':64,'height':48,'markers':[{'id':'beat','frame':10,'label':'Beat'}]})
        self.slots=[{'id':'plannedshot.'+str(i)*32,'label':'Shot '+str(i),'brief':self.params['brief'],'start_frame':(i-1)*62,'end_frame':i*62,'first_frame_id':None,'last_frame_id':None} for i in (1,2)]
        self.plan=plans.save(self.studio,seq['id'],{'expected_revision':0,'expected_sequence_revision':1,'slots':self.slots})
        return self.plan
    def existing(self,slot=0,data=None):
        asset=film.import_bytes(self.studio,data or self.video,'fixture.mp4','Existing fixture',{'test_only':True})
        if asset['status']!='approved':film.review_asset(self.studio,asset['id'],{'decision':'approved','expected_version':asset['version'],'notes':'Fixture'})
        p=plans.attach(self.studio,self.seq['id'],self.slots[slot]['id'],{'asset_id':asset['id']})
        return p['slots'][slot]['candidates'][-1]
    def fit(self,slot,candidate,revision,**extra):
        return plans.place(self.studio,self.seq['id'],self.slots[slot]['id'],{'candidate_id':candidate['id'],'expected_revision':1,'expected_sequence_revision':revision,'source_in_frame':0,'trim_to_fit':True,**extra})
    def generated(self,slot):
        self.params.update(planned_shot_id=self.slots[slot]['id'],planned_revision=1)
        body={**self.payload(),'request_id':'slot-'+str(slot)}
        job=av.submit(self.studio,body);self.studio.process_job(job['id']);self.studio.process_job(job['id'])
        self.assertEqual(self.studio.job(job['id'])['status'],'success')
        return job,body
    def test_save_reopen_contiguous_validation_and_sequence_isolation(self):
        self.prepare();self.assertEqual(plans.get(Studio(self.tempdir.name),self.seq['id']),self.plan)
        for slots in ([{**self.slots[0],'start_frame':1}],self.slots*2,[{**self.slots[0],'end_frame':999}]):
            with self.assertRaises(StudioError):plans.save(self.studio,self.seq['id'],{'expected_revision':1,'expected_sequence_revision':1,'slots':slots})
        with self.assertRaises(StudioError):plans.save(self.studio,self.seq['id'],{'expected_revision':0,'expected_sequence_revision':1,'slots':self.slots})
    def test_existing_candidates_order_fit_retry_replace_and_fixed_audio(self):
        self.prepare();first=self.existing(0);second=self.existing(1)
        with self.assertRaises(StudioError):self.fit(1,second,1)
        with self.assertRaises(StudioError):self.fit(0,first,1,trim_to_fit=False)
        r=self.fit(0,first,1);self.assertEqual(r['plan']['revision'],1);self.assertEqual(r['plan']['sequence_revision'],2)
        self.fit(1,second,2)
        retry=self.fit(0,first,1);self.assertEqual(retry['sequence']['revision'],3)
        alternate=self.existing(0,self.video+b'\0\0\0\x08free')
        replaced=self.fit(0,alternate,3)['sequence']
        self.assertEqual(replaced['shots'][1]['id'],self.slots[1]['id'])
        self.assertEqual(replaced['audio_tracks'],[self.audio]);self.assertEqual(replaced['markers'],self.seq['markers'])
        self.assertEqual(replaced['duration_frames'],248)
        self.assertEqual(alternate['kind'],'existing_asset');self.assertIsNone(alternate['job_id'])
    def test_parallel_owned_take_groups_survive_other_slot_placement(self):
        self.prepare();first,b1=self.generated(0);second,b2=self.generated(1)
        asset=av.get_job(self.studio,first['id'])['video_asset_id'];film.review_asset(self.studio,asset,{'decision':'approved','expected_version':0,'notes':'Fixture'})
        # Generated A1 remains unapproved; picture-only fit does not require or place it.
        with self.assertRaises(StudioError):timeline.place(self.studio,second['id'],{'expected_revision':1,'trim_to_fit':True})
        timeline.place(self.studio,first['id'],{'expected_revision':1,'trim_to_fit':True})
        self.assertEqual(timeline.placement(self.studio,second['id'])['stage'],'ready_to_place')
        result=timeline.place(self.studio,second['id'],{'expected_revision':2,'trim_to_fit':True})
        self.assertEqual(result['sequence']['audio_tracks'],[self.audio]);self.assertEqual(result['plan']['revision'],1)
        self.assertEqual(av.submit(self.studio,b1)['id'],first['id'])
        self.assertEqual(len(plans.get(self.studio,self.seq['id'])['slots'][0]['candidates']),1)
    def test_authoring_change_retains_candidates_and_blocks_old_lineage(self):
        self.prepare();job,body=self.generated(0)
        changed=copy.deepcopy(self.slots);changed[0]['brief']='Explicit revised assignment'
        plan=plans.save(self.studio,self.seq['id'],{'expected_revision':1,'expected_sequence_revision':1,'slots':changed})
        self.assertEqual(len(plan['slots'][0]['candidates']),1)
        self.assertEqual(timeline.placement(self.studio,job['id'])['stage'],'conflict')
        with self.assertRaises(StudioError):av.preflight(self.studio,self.params)
        plans.save(self.studio,self.seq['id'],{'expected_revision':2,'expected_sequence_revision':1,'slots':[]})
        self.assertEqual(timeline.placement(self.studio,job['id'])['stage'],'conflict')
    def test_unrelated_sequence_change_marks_plan_stale(self):
        self.prepare();film.save_sequence(self.studio,self.seq['id'],{**self.seq,'expected_revision':1,'title':'Changed'})
        self.assertTrue(plans.get(self.studio,self.seq['id'])['stale'])
        self.params.update(planned_shot_id=self.slots[0]['id'],planned_revision=1)
        with self.assertRaises(StudioError):av.preflight(self.studio,self.params)
    def test_http_existing_asset_candidate_and_picture_fit(self):
        self.prepare();candidate=self.existing(0);server=make_server(self.studio,0)
        threading.Thread(target=server.serve_forever,daemon=True).start();self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        base=f'http://127.0.0.1:{server.server_port}/api/film/sequences/{self.seq["id"]}/shot-plan'
        with urlopen(base) as r:self.assertEqual(json.load(r)['revision'],1)
        body={'candidate_id':candidate['id'],'expected_revision':1,'expected_sequence_revision':1,'trim_to_fit':True}
        req=Request(base+'/'+self.slots[0]['id']+'/place',data=json.dumps(body).encode(),headers={'Content-Type':'application/json','X-LLR-Client':'studio'})
        with urlopen(req) as r:self.assertEqual(json.load(r)['sequence']['shots'][0]['duration_frames'],62)

    def test_long_brief_two_references_plan_autoimport_retains_full_receipts(self):
        from PIL import Image
        from tests import test_film_images as image_fixture
        from last_light_radio import film_images
        self.params['brief']='Long explicit fixture direction. '+('x'*3967)
        self.assertEqual(len(self.params['brief']),4000)
        self.prepare();image_fixture.ImageReferencesTests.nodes(self)
        refs=[]
        for color in ('red','blue'):
            buffer=io.BytesIO();Image.new('RGB',(64,48),color).save(buffer,format='PNG')
            refs.append(film_images.import_bytes(self.studio,buffer.getvalue(),color+'.png',color,
                                                {'test_only':True,'detail':'p'*5000}))
        slots=copy.deepcopy(self.slots);slots[0].update(first_frame_id=refs[0]['id'],last_frame_id=refs[1]['id'])
        plans.save(self.studio,self.seq['id'],{'expected_revision':1,'expected_sequence_revision':1,'slots':slots})
        self.params.update(planned_shot_id=slots[0]['id'],planned_revision=2,first_frame_id=refs[0]['id'],last_frame_id=refs[1]['id'])
        job=av.submit(self.studio,self.payload());self.studio.process_job(job['id']);self.studio.process_job(job['id'])
        job=self.studio.job(job['id']);self.assertEqual(job['status'],'success')
        self.assertIsNotNone(job['video_asset_id']);self.assertIsNotNone(job['audio_asset_id'])
        asset=film.asset(self.studio,job['video_asset_id']);provenance=asset['provenance']
        self.assertLess(len(json.dumps(provenance)),12000)
        full=self.studio.store.read_snapshot(provenance['full_provenance_receipt'])
        self.assertEqual(full['generation_metadata']['brief'],self.params['brief'])
        self.assertEqual(full['generation_metadata']['planned_shot']['slot']['brief'],self.params['brief'])
        self.assertEqual(full['references']['first_frame']['provenance']['detail'],'p'*5000)
        compact=provenance['generation_metadata']
        self.assertEqual(compact['seed'],123);self.assertEqual(compact['references']['last_frame']['id'],refs[1]['id'])
        self.assertEqual(self.studio.store.read_snapshot(compact['brief_receipt'])['brief'],self.params['brief'])
        self.assertEqual(job['metadata']['references']['first_frame']['provenance']['detail'],'p'*5000)
        self.assertEqual(timeline.placement(self.studio,job['id'])['stage'],'ready_to_place')

if __name__=='__main__':unittest.main()
