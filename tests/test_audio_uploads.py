"""Actual multi-minute upload, bounded transport and immutable audio coverage."""
import io
import tempfile
import time
import unittest
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from last_light_radio import audio_tracks, audio_uploads, film
from last_light_radio.store import file_sha256, StoreError
from last_light_radio.studio import Studio, StudioError

class WholeSongTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.studio=Studio(self.root/'library')

    def wav(self,name,seconds,rate=48000):
        path=self.root/name
        with wave.open(str(path),'wb') as out:
            out.setnchannels(2);out.setsampwidth(2);out.setframerate(rate)
            block=(b'\x00\x20\x00\xe0')*rate
            for _ in range(seconds):out.writeframesraw(block)
        return path

    def test_three_minute_stream_import_cache_and_excerpt_export(self):
        path=self.wav('song.wav',180);original=file_sha256(path)
        self.assertGreater(path.stat().st_size,20*1024*1024)
        ticket=audio_uploads.begin(self.studio,{'filename':'song.wav','bytes':path.stat().st_size,'provenance':{'test_only':True}})
        with path.open('rb') as stream:asset=audio_uploads.receive(self.studio,ticket['upload_id'],stream,path.stat().st_size)
        self.assertEqual(asset['sample_count'],180*48000);self.assertEqual(asset['source']['sha256'],original)
        self.assertEqual(file_sha256(path),original)
        with patch.object(audio_tracks,'waveform_file',side_effect=AssertionError('cache miss')):
            start=time.monotonic();envelope=film.audio_waveform(self.studio,asset['id']);elapsed=time.monotonic()-start
        self.assertEqual(envelope['bins'],1024);self.assertGreater(max(envelope['peaks']),.2)
        print(f'Whole-song 180s source={path.stat().st_size} bytes cached waveform={elapsed:.3f}s')
        asset=audio_tracks.review(self.studio,asset['id'],{'expected_version':0,'decision':'approved','notes':'Synthetic test'})
        project=film.create_project(self.studio,{'title':'Synthetic'});seq=film.create_sequence(self.studio,project['id'],{'title':'Excerpt'})
        seq=film.save_sequence(self.studio,seq['id'],{'expected_revision':0,'title':'Excerpt','timeline_duration_frames':48,'shots':[],
            'audio_tracks':[{'id':'music','asset_id':asset['id'],'role':'music','start_frame':0,'source_in_frame':2400,'duration_frames':48}]})
        film.process_export(self.studio,seq['id'],self.studio.store.read_snapshot(seq['manifest']))
        result=film.sequence(self.studio,seq['id']);self.assertEqual(result['export']['status'],'complete',result['export'])
        self.assertEqual(result['export']['report']['audio_sample_count'],96000)
        self.studio.store.resolve(asset['pcm']['path']).write_bytes(b'tampered')
        with self.assertRaises(StoreError):film.audio_waveform(self.studio,asset['id'])

    def test_limits_interrupt_expiration_and_one_use(self):
        for size in (43,audio_tracks.FILE_LIMIT+1,True):
            with self.assertRaises(StudioError):audio_uploads.begin(self.studio,{'filename':'x.wav','bytes':size})
        for length,data in ((44,b'short'),(45,b'x'*45)):
            ticket=audio_uploads.begin(self.studio,{'filename':'x.wav','bytes':44})
            with self.assertRaises(StudioError):audio_uploads.receive(self.studio,ticket['upload_id'],io.BytesIO(data),length)
            with self.assertRaises(StudioError):audio_uploads.receive(self.studio,ticket['upload_id'],io.BytesIO(data),length)
        self.assertFalse(list(self.studio.store.root.glob('audio-upload-*')))
        ticket=audio_uploads.begin(self.studio,{'filename':'x.wav','bytes':44})
        self.studio.audio_upload_tickets[ticket['upload_id']]['expires']=0
        with self.assertRaises(StudioError):audio_uploads.receive(self.studio,ticket['upload_id'],io.BytesIO(b'x'*44),44)

    def test_upload_slots_and_filename_paths(self):
        for name in ('../bad.wav', 'C:\\bad.wav', 'sub/bad.wav'):
            with self.assertRaises(StudioError):audio_uploads.begin(self.studio,{'filename':name,'bytes':44})
        ticket=audio_uploads.begin(self.studio,{'filename':'x.wav','bytes':44})
        self.studio.audio_upload_active=2
        with self.assertRaises(StudioError):audio_uploads.receive(self.studio,ticket['upload_id'],io.BytesIO(b'x'*44),44)
        self.assertEqual(self.studio.audio_upload_active,2)
        self.studio.audio_upload_active=0
        ticket=audio_uploads.begin(self.studio,{'filename':'x.wav','bytes':44})
        with self.assertRaises(StudioError):audio_uploads.receive(self.studio,ticket['upload_id'],io.BytesIO(b'x'),44)
        self.assertEqual(self.studio.audio_upload_active,0)

    def test_ten_minute_boundary_cache_performance(self):
        path=self.wav('ten-minutes.wav',600,1000)
        start=time.monotonic()
        asset=audio_tracks.import_file(self.studio,path,'ten-minutes.wav','Boundary',{})
        imported=time.monotonic()-start
        with patch.object(audio_tracks,'waveform_file',side_effect=AssertionError('cache miss')):
            start=time.monotonic();data=film.audio_waveform(self.studio,asset['id']);elapsed=time.monotonic()-start
        self.assertEqual(data['sample_count'],600*48000)
        self.assertEqual(data['duration_seconds'],600)
        print(f'Ten-minute canonical import={imported:.3f}s cached verified envelope={elapsed:.3f}s')

    def test_duration_and_concurrent_dedup(self):
        path=self.wav('too-long.wav',601,1000)
        with self.assertRaisesRegex(StudioError,'ten minutes'):audio_tracks.import_file(self.studio,path,'long.wav','Long',{})
        path=self.wav('short.wav',1)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:audio_tracks.import_file(self.studio,path,'short.wav','Short',{}),range(2)))
        self.assertEqual(results[0]['id'],results[1]['id']);self.assertEqual(len(audio_tracks.listing(self.studio)['assets']),1)
        target=self.studio.store.write_file_once('test/immutable.wav',path,file_sha256(path))
        path.write_bytes(b'changed')
        with self.assertRaises(StoreError):self.studio.store.write_file_once('test/immutable.wav',path)
        self.assertNotEqual(target.read_bytes(),b'changed')

if __name__=='__main__':unittest.main()
