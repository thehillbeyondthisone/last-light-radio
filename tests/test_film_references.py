import io, tempfile, unittest
from PIL import Image
from last_light_radio import film, film_images, film_references as refs
from last_light_radio.studio import Studio, StudioError

class ProductionReferenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.studio = Studio(self.temp.name)
        self.project = film.create_project(self.studio, {'title':'Reference fixture'})['id']
        image = io.BytesIO(); Image.new('RGB',(16,16),'red').save(image,format='PNG')
        self.image = film_images.import_bytes(self.studio,image.getvalue(),'test.png','Test',{'test_only':True})
        self.payload = {'expected_revision':0,'kind':'location','label':'Van','guidelines':'Window left, kettle right.',
                        'views':[{'name':'master','image_id':self.image['id'],'description':'Interior master'}]}
    def saved(self): return refs.save(self.studio,self.project,self.payload)
    def test_revision_pinning_and_reopen(self):
        first=self.saved()
        second=refs.save(self.studio,self.project,{**self.payload,'id':first['id'],'expected_revision':1,'guidelines':'Revised explicit guideline'})
        self.assertEqual(refs.get(Studio(self.temp.name),self.project,first['id'],1),first)
        self.assertEqual(refs.listing(self.studio,self.project)['references'],[second])
        with self.assertRaises(StudioError): refs.save(self.studio,self.project,{**self.payload,'id':first['id']})
    def test_compile_actual_conditioning_and_no_timeline_change(self):
        r=self.saved(); binding={'id':r['id'],'revision':1,'view':'master'}
        before=film.listing(self.studio)
        c=refs.compile_shot(self.studio,self.project,{'bindings':[binding],'conditioning_reference_id':r['id'],'action':'Mara puts down her mug.'})
        self.assertEqual(c['first_frame_id'],self.image['id'])
        self.assertIn('Window left, kettle right.',c['brief'])
        self.assertFalse(c['conditioning']['additional_image_conditioning'])
        self.assertEqual(c['production_reference_bindings'],[binding])
        self.assertEqual(film.listing(self.studio),before)
    def test_project_isolation_bad_views_and_tamper(self):
        r=self.saved(); other=film.create_project(self.studio,{'title':'Other'})['id']
        with self.assertRaises(StudioError): refs.get(self.studio,other,r['id'])
        with self.assertRaises(StudioError): refs.resolve(self.studio,self.project,[{'id':r['id'],'revision':1,'view':'invented'}])
        with self.assertRaises(StudioError): refs.save(self.studio,self.project,{**self.payload,'views':self.payload['views']*2})
        self.studio.store.resolve(self.image['png']['path']).write_bytes(b'tampered')
        with self.assertRaises(Exception): refs.get(self.studio,self.project,r['id'],1)
    def test_shot_plan_and_frozen_generation_anchor(self):
        from last_light_radio import film_shot_plan as plans
        r=self.saved(); binding={'id':r['id'],'revision':1,'view':'master'}
        seq=film.create_sequence(self.studio,self.project,{'title':'Test'})
        seq=film.save_sequence(self.studio,seq['id'],{'expected_revision':0,'title':'Test','shots':[],
            'timeline_duration_frames':100,'audio_tracks':[],'width':64,'height':48,'markers':[]})
        slot={'id':'plannedshot.'+'a'*32,'label':'Test','brief':'Mug action','start_frame':0,'end_frame':100,
              'first_frame_id':self.image['id'],'last_frame_id':None,'production_reference_bindings':[binding]}
        plans.save(self.studio,seq['id'],{'expected_revision':0,'expected_sequence_revision':1,'slots':[slot]})
        params={'planned_shot_id':slot['id'],'planned_revision':1,'brief':slot['brief'],'first_frame_id':self.image['id']}
        anchored=plans.anchor(self.studio,params)
        self.assertEqual(anchored['production_references'][0]['record'],r)
        refs.save(self.studio,self.project,{**self.payload,'id':r['id'],'expected_revision':1,'guidelines':'New version'})
        self.assertEqual(plans.anchor(self.studio,params)['production_references'][0]['record'],r)

    def test_http_api_save_list_compile(self):
        import threading, json
        from urllib.request import Request, urlopen
        from last_light_radio.server import make_server
        server=make_server(self.studio,port=0)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        base='http://127.0.0.1:'+str(server.server_address[1])
        def request(path,payload=None):
            data=json.dumps(payload).encode() if payload is not None else None
            req=Request(base+path,data=data,headers={'Content-Type':'application/json','Origin':base,'X-LLR-Client':'studio'})
            with urlopen(req) as response:return json.load(response)
        route='/api/film/projects/'+self.project+'/references'
        saved=request(route,self.payload)
        self.assertEqual(request(route)['references'],[saved])
        result=request(route+'/compile',{'bindings':[{'id':saved['id'],'revision':1,'view':'master'}],
            'conditioning_reference_id':saved['id'],'action':'Set down mug'})
        self.assertEqual(result['first_frame_id'],self.image['id'])



class BoundGenerationTests(unittest.TestCase):
    from tests.test_film_images import ImageReferencesTests as Fixture
    setUpClass=classmethod(Fixture.setUpClass.__func__)
    setUp=Fixture.setUp
    source=Fixture.source
    nodes=Fixture.nodes
    payload=Fixture.payload
    def test_compiled_image_and_pinned_canon_reach_job_and_graph(self):
        from last_light_radio import film_generation as av, film_shot_plan as plans
        self.nodes(); image=self.source()
        project=film.create_project(self.studio,{'title':'Bound generation fixture'})
        r=refs.save(self.studio,project['id'],{'expected_revision':0,'kind':'location','label':'Van','guidelines':'Window left.',
            'views':[{'name':'master','image_id':image['id']}]})
        c=refs.compile_shot(self.studio,project['id'],{'bindings':[{'id':r['id'],'revision':1,'view':'master'}],
            'conditioning_reference_id':r['id'],'action':'Mug on table.'})
        seq=film.create_sequence(self.studio,project['id'],{'title':'Bound'})
        seq=film.save_sequence(self.studio,seq['id'],{'expected_revision':0,'title':'Bound','shots':[],
            'timeline_duration_frames':100,'audio_tracks':[],'width':64,'height':48,'markers':[]})
        slot={k:c[k] for k in ('brief','first_frame_id','last_frame_id','production_reference_bindings')}
        slot.update(id='plannedshot.'+'b'*32,label='Bound',start_frame=0,end_frame=100)
        plans.save(self.studio,seq['id'],{'expected_revision':0,'expected_sequence_revision':1,'slots':[slot]})
        self.params.update(brief=c['brief'],first_frame_id=c['first_frame_id'],planned_shot_id=slot['id'],planned_revision=1)
        job=av.submit(self.studio,self.payload())
        config=av.configuration(self.studio,job['id'])
        self.assertEqual(config['references']['first_frame']['id'],image['id'])
        self.assertEqual(config['planned_shot']['production_references'][0]['record'],r)
        graph=self.studio.store.read_snapshot(config['workflow'])
        self.assertEqual(graph['6']['inputs']['first_frame'],['18',0])
        self.assertEqual(self.worker.submits,0)
