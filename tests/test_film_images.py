import base64
import io
import unittest
from unittest.mock import patch
from PIL import Image
from tests import test_film_generation as fixture
from last_light_radio import film_images as images, film_generation as av, film
from last_light_radio.studio import StudioError

class ImageReferencesTests(unittest.TestCase):
    setUpClass=classmethod(fixture.JointAVTests.setUpClass.__func__)
    setUp=fixture.JointAVTests.setUp
    payload=fixture.JointAVTests.payload
    def source(self,color='red'):
        output=io.BytesIO();Image.new('RGB',(64,48),color).save(output,format='PNG')
        return images.import_image(self.studio,{'filename':'fixture.png','label':'Isolated source',
            'image_base64':base64.b64encode(output.getvalue()).decode(),'provenance':{'test_only':True}})
    def nodes(self):
        self.worker.definitions['LoadImage']={'input':{'required':{'image':[[],{'image_upload':True}]}},'output':['IMAGE','MASK']}
        self.worker.definitions['MiniMaxH3ImageToVideo']['input']['optional']={'first_frame':['IMAGE',{}],'last_frame':['IMAGE',{}]}
        self.uploads=[]
        def upload(data,filename,subfolder):
            self.uploads.append((data,filename,subfolder));return {'path':subfolder+'/'+filename,'name':filename,'subfolder':subfolder,'type':'input'}
        self.worker.upload_image=upload
    def test_image_bytes_immutable_import_dedup_and_frame_provenance(self):
        source=self.source();self.assertEqual(self.source()['id'],source['id'])
        video=film.import_bytes(self.studio,self.video,'fixture.mp4','Fixture',{'test_only':True})
        frame=images.from_frame(self.studio,{'video_asset_id':video['id'],'frame':24})
        self.assertEqual(frame['provenance']['frame_rate'],24)
        self.assertEqual(frame['provenance']['source']['sha256'],video['source']['sha256'])
        self.assertEqual(frame['provenance']['source_review_status'],'candidate')
        self.assertEqual(images.verify(self.studio,frame['id'])['width'],672)
        with self.assertRaises(StudioError):images.from_frame(self.studio,{'video_asset_id':video['id'],'frame':999})
    def test_first_last_mock_upload_frozen_graph_receipt_import(self):
        self.nodes();first=self.source();last=self.source('blue')
        self.params.update(first_frame_id=first['id'],last_frame_id=last['id'])
        preflight=av.preflight(self.studio,self.params)
        self.assertTrue(preflight['ready'],preflight)
        self.assertFalse(any(w['code']=='LAST_FRAME_UNTESTED' for w in preflight['warnings']))
        self.assertEqual(sum(w['code']=='REFERENCE_UPLOAD_ON_GENERATE' for w in preflight['warnings']),2)
        self.assertEqual(self.uploads,[]);self.assertEqual(self.worker.submits,0)
        job=av.submit(self.studio,self.payload())
        self.studio.process_job(job['id']);self.studio.process_job(job['id'])
        self.assertEqual(self.studio.job(job['id'])['status'],'success')
        self.assertEqual(len(self.uploads),2)
        request=av._request(self.studio,job['id'])
        graph=self.studio.store.read_snapshot(request['workflow'])
        self.assertEqual(graph['6']['inputs']['first_frame'],['18',0]);self.assertEqual(graph['6']['inputs']['last_frame'],['19',0])
        self.assertEqual(request['references']['first_frame']['source'],first['source'])
        imported=av.import_completed(self.studio,job['id'])
        self.assertTrue(imported['video']['provenance']['reference_conditioning'])
        self.assertEqual(imported['video']['status'],'candidate')
    def test_changed_reference_or_corruption_blocks_submission(self):
        self.nodes();first=self.source();self.params['first_frame_id']=first['id']
        body=self.payload()
        with self.assertRaises(StudioError):av.submit(self.studio,{**body,'first_frame_id':self.source('blue')['id']})
        self.studio.store.resolve(first['png']['path']).write_bytes(b'broken')
        with self.assertRaises(ValueError):av.submit(self.studio,body)
        self.assertEqual(self.worker.submits,0)
    def test_missing_node_or_role_not_silently_ignored(self):
        first=self.source();self.params['first_frame_id']=first['id']
        self.assertFalse(av.preflight(self.studio,self.params)['ready'])
        self.nodes();self.worker.definitions['MiniMaxH3ImageToVideo']['input']['optional'].pop('last_frame')
        self.params['last_frame_id']=first['id']
        self.assertFalse(av.preflight(self.studio,self.params)['ready'])
    def test_upload_interruption_never_resubmits_gpu(self):
        self.nodes();self.params['first_frame_id']=self.source()['id'];job=av.submit(self.studio,self.payload())
        with patch.object(self.worker,'upload_image',side_effect=RuntimeError('Interrupted upload')):
            self.studio.process_job(job['id'])
        self.assertEqual(self.worker.submits,0)
        with self.assertRaises(Exception):av._start(self.studio,av.configuration(self.studio,job['id']))
        self.assertEqual(self.worker.submits,0)

    def test_only_verified_owned_staged_image_warnings_are_reworded(self):
        self.nodes();self.params['first_frame_id']=self.source()['id']
        unrelated={'code':'IMAGE_NOT_IN_CHOICES','message':'Keep unrelated warning','node_id':'22','input':'image','value':'unknown.png'}
        original=av._check
        def check(client,graph):
            result=original(client,graph);result['warnings'].append(unrelated);return result
        with patch.object(av,'_check',side_effect=check):result=av.preflight(self.studio,self.params)
        self.assertIn(unrelated,result['warnings'])
        self.assertEqual(sum(w['code']=='REFERENCE_UPLOAD_ON_GENERATE' for w in result['warnings']),1)
        self.assertEqual(self.uploads,[]);self.assertEqual(self.worker.submits,0)

if __name__=='__main__':unittest.main()
