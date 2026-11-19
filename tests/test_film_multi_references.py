"""No-GPU multi-image conditioning contract and immutable provenance tests."""
import copy
import unittest
from last_light_radio import film_generation as av, film_references as refs, film_shot_plan as plans, film
from last_light_radio import h3_joint_av_recipe as recipe
from last_light_radio.studio import StudioError
from tests.test_film_images import ImageReferencesTests as Fixture

class MultiReferenceTests(unittest.TestCase):
    setUpClass=classmethod(Fixture.setUpClass.__func__)
    setUp=Fixture.setUp
    source=Fixture.source
    payload=Fixture.payload

    def setup_refs(self):
        Fixture.nodes(self)
        definition=copy.deepcopy(self.worker.definitions['MiniMaxH3ImageToVideo'])
        definition['input']['optional']={'vae':['VAE',{}], 'ref_images':['COMFY_AUTOGROW_V3',{'template':{
            'input':{'required':{'ref_image':['IMAGE',{}]}},'prefix':'ref_image_','min':0,'max':9}}]}
        definition['input']['required']['ref_image_size']=[['match','max'],{}]
        self.worker.definitions['MiniMaxH3ReferenceToVideo']=definition
        a,b=self.source(),self.source('blue')
        self.params.update(recipe_id=recipe.R2V_RECIPE_ID, reference_images=[
            {'image_id':a['id'],'role':'Character face and outfit'},
            {'image_id':b['id'],'role':'Location geography, not character identity'}])
        return a,b

    def test_actual_order_roles_upload_and_receipt_import(self):
        a,b=self.setup_refs()
        body=self.payload()
        self.assertEqual(self.worker.submits,0)
        job=av.submit(self.studio,body)
        self.studio.process_job(job['id']); self.studio.process_job(job['id'])
        current=self.studio.job(job['id'])
        self.assertEqual(current['status'],'success',current)
        self.assertEqual(len(self.uploads),2)
        request=av._request(self.studio,job['id'])
        graph=self.studio.store.read_snapshot(request['workflow'])
        self.assertEqual(graph['6']['class_type'],'MiniMaxH3ReferenceToVideo')
        self.assertEqual(graph['6']['inputs']['vae'],['4',0])
        self.assertEqual(graph['6']['inputs']['ref_images.ref_image_0'],['18',0])
        self.assertEqual(graph['6']['inputs']['ref_images.ref_image_1'],['19',0])
        self.assertIn('<Picture 2>: Location geography',graph['6']['inputs']['prompt'])
        self.assertEqual(request['references']['reference_1']['png'],a['png'])
        self.assertEqual(request['references']['reference_2']['png'],b['png'])
        imported=av.import_completed(self.studio,job['id'])
        self.assertEqual(imported['video']['status'],'candidate')
        self.assertEqual(self.worker.submits,1)

    def test_nine_unicode_roles_do_not_overflow_import_metadata(self):
        from last_light_radio.generation_timeline import bounded_provenance
        from last_light_radio.store import canonical_bytes
        self.setup_refs()
        records=[self.source((i*20,20,50)) for i in range(9)]
        ordered=[{'image_id':r['id'],'role':'語'*1400} for r in records]
        original={'kind':'fixture','references':{'reference_'+str(i+1):r for i,r in enumerate(records)},
                  'generation_metadata':{'reference_images':ordered,'references':{'reference_'+str(i+1):r for i,r in enumerate(records)}}}
        compact=bounded_provenance(self.studio,original)
        self.assertLess(len(canonical_bytes(compact)),10000)
        self.assertEqual(self.studio.store.read_snapshot(compact['full_provenance_receipt']),original)

    def test_input_limits_mixed_modes_and_stale_order(self):
        self.setup_refs(); body=self.payload()
        for changes in ({'reference_images':[]}, {'reference_images':self.params['reference_images']*5},
                        {'first_frame_id':self.params['reference_images'][0]['image_id']},
                        {'recipe_id':recipe.RECIPE_ID},
                        {'reference_images':[self.params['reference_images'][0]]*2}):
            with self.subTest(changes=changes),self.assertRaises(StudioError):
                av.preflight(self.studio,{**self.params,**changes})
        with self.assertRaises(StudioError):
            av.submit(self.studio,{**body,'reference_images':list(reversed(self.params['reference_images']))})
        self.assertEqual(self.worker.submits,0)

    def test_worker_missing_autogrow_or_invalid_index_fails(self):
        self.setup_refs()
        self.worker.definitions['MiniMaxH3ReferenceToVideo']['input']['optional'].pop('ref_images')
        self.assertFalse(av.preflight(self.studio,self.params)['ready'])
        self.setup_refs()
        from last_light_radio import film_images
        graph,_=film_images.prepare(self.studio,recipe.prepared('test',1,'test',recipe.R2V_RECIPE_ID),self.params,'test')
        graph['6']['inputs']['ref_images.ref_image_9']=['19',0]
        self.assertFalse(av._check(self.worker,graph)['ready'])

    def test_multiple_views_pin_and_bind_to_exact_saved_plan(self):
        a,b=self.setup_refs()
        project=film.create_project(self.studio,{'title':'Isolated multi-ref fixture'})
        value={'kind':'character','label':'Fixture','guidelines':'Keep the same face and outfit.','views':[
            {'name':'front','image_id':a['id']},{'name':'profile','image_id':b['id']}],'expected_revision':0}
        record=refs.save(self.studio,project['id'],value)
        bindings=[{'id':record['id'],'revision':1,'view':v} for v in ('front','profile')]
        compiled=refs.compile_shot(self.studio,project['id'],{'bindings':bindings,'conditioning_mode':'reference_images','action':'Turns toward the window.'})
        self.assertIn('<Picture 1> is character',compiled['brief'])
        selected=refs.compile_shot(self.studio,project['id'],{'bindings':bindings,'conditioning_binding':bindings[1],'action':'Turns.'})
        self.assertEqual(selected['first_frame_id'],b['id'])
        seq=film.create_sequence(self.studio,project['id'],{'title':'Isolated'})
        film.save_sequence(self.studio,seq['id'],{'expected_revision':0,'title':'Isolated','shots':[],
            'timeline_duration_frames':100,'audio_tracks':[],'width':64,'height':48,'markers':[]})
        slot={k:compiled[k] for k in ('brief','first_frame_id','last_frame_id','reference_images','recipe_id','production_reference_bindings')}
        slot.update(id='plannedshot.'+'c'*32,label='Test',start_frame=0,end_frame=100)
        plans.save(self.studio,seq['id'],{'expected_revision':0,'expected_sequence_revision':1,'slots':[slot]})
        self.params.update(brief=compiled['brief'],reference_images=compiled['reference_images'],planned_shot_id=slot['id'],planned_revision=1)
        job=av.submit(self.studio,self.payload())
        refs.save(self.studio,project['id'],{**value,'id':record['id'],'expected_revision':1,'guidelines':'New version'})
        config=av.configuration(self.studio,job['id'])
        self.assertEqual([b['record']['revision'] for b in config['planned_shot']['production_references']],[1,1])
        self.studio.process_job(job['id'])
        self.assertEqual(self.worker.submits,1)
        with self.assertRaises(StudioError):plans.anchor(self.studio,{**self.params,'reference_images':list(reversed(self.params['reference_images']))})

if __name__=='__main__':unittest.main()
