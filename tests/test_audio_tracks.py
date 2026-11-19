"""Audio imports/approval, persistence, exact trims, and real CPU mix coverage."""
import base64
import copy
import io
import math
import struct
import subprocess
import tempfile
import unittest
import wave
from pathlib import Path
from PIL import Image
from last_light_radio import audio_tracks as audio, editor, pilots
from last_light_radio.studio import Studio, StudioError
from last_light_radio.video_tools import ffmpeg_path

class AudioTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='llr-audio-test-')
        self.addCleanup(self.temp.cleanup)
        self.studio = Studio(self.temp.name)
        image = io.BytesIO()
        Image.new('RGB', (64, 48), (70, 90, 60)).save(image, 'PNG')
        self.scene = self.studio.import_scene(image.getvalue(), 'test.png', 'Audio test')
        wav = io.BytesIO()
        with wave.open(wav, 'wb') as source:
            source.setnchannels(1); source.setsampwidth(2); source.setframerate(24000)
            source.writeframes(b''.join(struct.pack('<h', round(4000*math.sin(2*math.pi*440*i/24000))) for i in range(72000)))
        self.upload = {'filename':'tone.wav','audio_base64':base64.b64encode(wav.getvalue()).decode(), 'label':'Fixture tone', 'provenance':{'test':True}}
        self.asset = audio.import_asset(self.studio, self.upload)
        self.track = {'id':'music-1','role':'music','asset_id':self.asset['id'],'start_frame':12,'source_in_frame':12,'duration_frames':48,'gain_db':-6,'fade_in_frames':6,'fade_out_frames':6,'enabled':True}
        self.payload = {'scene_id':self.scene['id'],'title':'Audio fixture','duration_frames':72,'seed':7,'expected_revision':0,'subjects':[],'placements':[],'ambience':[]}
    def approve(self):
        self.asset = audio.review(self.studio,self.asset['id'],{'decision':'approved','notes':'Test-only tone','expected_version':self.asset['version']})
    def test_import_immutable_and_review_required(self):
        self.assertEqual(self.asset['status'],'candidate')
        self.assertEqual(self.asset['duration_seconds'],3)
        self.assertEqual(self.asset['sample_rate'],48000)
        self.assertEqual(audio.import_asset(self.studio,self.upload)['id'],self.asset['id'])
        with self.assertRaises(StudioError): audio.validate_tracks(self.studio,[self.track],72,24)
        with self.assertRaises(StudioError): audio.review(self.studio,self.asset['id'],{'decision':'approved','expected_version':9})
        self.approve()
        self.assertEqual(len(audio.listing(self.studio)['assets']),1)
        audio.validate_tracks(self.studio,[self.track],72,24)
    def test_invalid_trims_gain_paths_and_fades(self):
        self.approve()
        for patch in ({'asset_id':'../../anything'}, {'source_in_frame':50}, {'duration_frames':80}, {'gain_db':float('nan')}, {'gain_db':13}, {'fade_in_frames':30,'fade_out_frames':30}, {'enabled':1}, {'start_frame':True}):
            with self.subTest(patch=patch), self.assertRaises(StudioError):
                audio.validate_tracks(self.studio,[{**self.track,**patch}],72,24)
    def test_save_reopen_and_revoked_approval(self):
        self.approve()
        saved = editor.plan(self.studio,{**self.payload,'audio_tracks':[self.track]})
        reopened = editor.state(Studio(self.temp.name),self.scene['id'])
        self.assertEqual(reopened['config']['audio_tracks'],[self.track])
        manifest = saved['sequence']['manifest']
        self.assertEqual(manifest['audio'],'mixed')
        audio.validate_pinned(self.studio,manifest['audio_tracks'])
        audio.review(self.studio,self.asset['id'],{'decision':'rejected','notes':'Test revoke','expected_version':self.asset['version']})
        with self.assertRaises(StudioError): pilots.validate_approvals(self.studio,manifest)
    def test_empty_audio_preserves_legacy_manifest(self):
        saved = editor.plan(self.studio,self.payload)
        self.assertNotIn('audio_tracks',saved['config'])
        self.assertNotIn('audio_tracks',saved['sequence']['manifest'])
        saved2 = editor.plan(self.studio,{**self.payload,'expected_revision':1,'audio_tracks':[]})
        self.assertEqual(saved['sequence_id'],saved2['sequence_id'])
    def test_real_mix_duration_silence_and_reopen_export(self):
        self.approve()
        saved = editor.plan(self.studio,{**self.payload,'audio_tracks':[self.track]})
        pilots.queue_export(self.studio,saved['sequence_id'])
        pilots.process_export(self.studio,saved['sequence_id'])
        result = pilots.get(self.studio,saved['sequence_id'])
        self.assertEqual(result['status'],'complete',result.get('error'))
        path = self.studio.store.resolve(f"exports/pilots/{saved['sequence_id']}/pilot.mp4")
        decoded = subprocess.run([ffmpeg_path(),'-v','error','-i',str(path),'-map','0:a:0','-f','s16le','-ac','1','-ar','48000','pipe:1'],capture_output=True,check=True)
        samples = struct.unpack('<'+'h'*(len(decoded.stdout)//2),decoded.stdout)
        self.assertGreaterEqual(len(samples),144000)
        self.assertLess(len(samples),145024)
        self.assertLess(max(abs(v) for v in samples[:20000]),5)
        self.assertGreater(max(abs(v) for v in samples[48000:60000]),500)
        self.assertLess(max(abs(v) for v in samples[130000:140000]),5)
        pilots.queue_export(Studio(self.temp.name),saved['sequence_id'])
        pilots.process_export(Studio(self.temp.name),saved['sequence_id'])
        self.assertEqual(pilots.get(self.studio,saved['sequence_id'])['status'],'complete')

if __name__ == '__main__': unittest.main()
