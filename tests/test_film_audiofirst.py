"""Real audio-first sequences: no placeholder video source or GPU required."""
import base64
import copy
import io
import json
import math
import struct
import wave
import unittest
from last_light_radio import film, audio_tracks
from last_light_radio.studio import Studio, StudioError
from last_light_radio.store import canonical_bytes, sha256
from tests import test_film as fixtures


class AudioFirstTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.FilmTests.setUpClass.__func__)
    setUp = fixtures.FilmTests.setUp
    approve = fixtures.FilmTests.approve

    def prepare(self):
        data=io.BytesIO()
        with wave.open(data,'wb') as out:
            out.setnchannels(2);out.setsampwidth(2);out.setframerate(48000)
            out.writeframes(b''.join(struct.pack('<hh',int(8000*math.sin(i*2*math.pi*440/48000)),int(8000*math.sin(i*2*math.pi*440/48000))) for i in range(48000)))
        self.original=data.getvalue()
        self.audio=audio_tracks.import_asset(self.studio,{'filename':'tone.wav','label':'Isolated tone','audio_base64':base64.b64encode(self.original).decode(),'provenance':{'test_only':True}})
        self.audio=audio_tracks.review(self.studio,self.audio['id'],{'expected_version':0,'decision':'approved','notes':'Technical isolated fixture'})
        self.track={'id':'sound','asset_id':self.audio['id'],'role':'production','start_frame':12,'source_in_frame':0,
                    'duration_frames':24,'gain_db':-3,'fade_in_frames':2,'fade_out_frames':2,'enabled':True}
        self.body={'expected_revision':0,'title':'Sound before picture','shots':[],'audio_tracks':[self.track],
                   'timeline_duration_frames':48,'width':64,'height':48,
                   'markers':[{'id':'word','label':'First beat','frame':12}],
                   'selection':{'in_frame':12,'out_frame':36}}
        return film.save_sequence(self.studio,self.seq['id'],self.body)

    def export(self,seq):
        film.process_export(self.studio,seq['id'],self.studio.store.read_snapshot(seq['manifest']))
        seq=film.sequence(self.studio,seq['id']);self.assertEqual(seq['export']['status'],'complete',seq['export'])
        return seq

    def test_audio_only_save_reopen_real_wav_and_source_unchanged(self):
        seq=self.prepare();self.assertEqual(seq['shots'],[]);self.assertEqual(seq['media_kind'],'audio')
        self.assertEqual(seq['duration_frames'],48);self.assertEqual(seq['picture_duration_frames'],0)
        reopened=film.sequence(Studio(self.tempdir.name),seq['id']);self.assertEqual(reopened,seq)
        seq=self.export(seq);path,mime=film.export_media(self.studio,seq['id'],'media');self.assertEqual(mime,'audio/wav')
        self.assertEqual(path.name,'mix.wav')
        with wave.open(str(path),'rb') as wav:
            self.assertEqual((wav.getnframes(),wav.getframerate(),wav.getnchannels(),wav.getsampwidth()),(96000,48000,2,3))
            raw=wav.readframes(wav.getnframes());self.assertEqual(raw[:20000*6],b'\0'*(20000*6));self.assertTrue(any(raw[30000*6:60000*6]))
        self.assertEqual(self.studio.store.resolve(self.audio['source']['path']).read_bytes(),self.original)
        self.assertEqual(seq['export']['report']['frames_written'],0)
        self.assertFalse(path.with_name('film.mp4').exists())

    def test_markers_selection_revision_and_duration_validation(self):
        seq=self.prepare()
        for change in ({'timeline_duration_frames':24},{'timeline_duration_frames':0},{'timeline_duration_frames':14401},
                       {'selection':{'in_frame':5,'out_frame':5}}, {'markers':[{'id':'x','label':'Past end','frame':48}]}):
            with self.subTest(change=change),self.assertRaises(StudioError):film.save_sequence(self.studio,seq['id'],{**self.body,'expected_revision':1,**change})
        with self.assertRaises(StudioError):film.save_sequence(self.studio,seq['id'],self.body)
        changed=film.save_sequence(self.studio,seq['id'],{**self.body,'expected_revision':1,'markers':[],'selection':None})
        self.assertEqual(changed['manifest_hash'],seq['manifest_hash'])
        self.assertEqual(changed['markers'],[]);self.assertIsNone(changed['selection'])

    def test_picture_added_keeps_audio_clock_and_declared_black_tail(self):
        seq=self.prepare();self.approve()
        payload={**self.body,'expected_revision':1,'shots':self.payload['shots']};payload.pop('timeline_duration_frames')
        seq=film.save_sequence(self.studio,seq['id'],payload)
        self.assertEqual(seq['duration_frames'],48);self.assertEqual(seq['picture_duration_frames'],13)
        self.assertEqual(seq['media_kind'],'video');self.assertEqual(seq['audio_tracks'][0]['duration_frames'],24)
        seq=self.export(seq);path,mime=film.export_media(self.studio,seq['id'],'media')
        self.assertEqual(mime,'video/mp4');self.assertEqual(seq['export']['report']['inspection']['frame_count'],48)
        self.assertEqual(seq['export']['report']['audio'],'mixed')

    def test_picture_can_extend_existing_explicit_clock_without_shortening_audio(self):
        seq=self.prepare();self.approve()
        payload={**self.body,'expected_revision':1,'shots':[{'id':f'part-{i}','asset_id':self.assets[0]['id'],'source_in_frame':0,'duration_frames':12} for i in range(5)]}
        payload.pop('timeline_duration_frames')
        seq=film.save_sequence(self.studio,seq['id'],payload)
        self.assertEqual(seq['duration_frames'],60);self.assertEqual(seq['timeline_duration_frames'],60)
        self.assertEqual(seq['audio_tracks'][0],self.track)

    def placement(self, seq, **changes):
        return film.place_picture_interval(self.studio, seq['id'], {
            'expected_revision':seq['revision'], 'shot_id':'planned-first',
            'asset_id':self.assets[0]['id'], 'start_frame':0, 'end_frame':12,
            **changes})

    def test_planned_picture_preserves_audio_clock_markers_and_real_export(self):
        seq=self.prepare();self.approve()
        original=copy.deepcopy(seq)
        seq=self.placement(seq)
        self.assertEqual(seq['duration_frames'],48)
        for field in ('audio_tracks','markers','selection','timeline_duration_frames'):
            self.assertEqual(seq[field],original[field])
        seq=self.placement(seq,shot_id='planned-second',start_frame=12,end_frame=20,source_in_frame=2,trim_to_fit=True)
        self.assertEqual([s['duration_frames'] for s in seq['shots']],[12,8])
        self.assertEqual(seq['picture_duration_frames'],20)
        self.assertEqual(seq['audio_tracks'],original['audio_tracks'])
        seq=self.export(seq)
        self.assertEqual(seq['export']['report']['frames_written'],48)
        self.assertEqual(seq['export']['report']['audio'],'mixed')
        reopened=film.sequence(Studio(self.tempdir.name),seq['id'])
        self.assertEqual(reopened['shots'],seq['shots'])

    def test_planned_picture_explicit_trim_short_source_gaps_and_revision(self):
        seq=self.prepare();self.approve()
        for change in ({'end_frame':10}, {'end_frame':13}, {'start_frame':4,'end_frame':16},
                       {'end_frame':49}, {'expected_revision':0}, {'end_frame':10,'trim_to_fit':'true'}):
            with self.subTest(change=change),self.assertRaises(StudioError):
                self.placement(seq,**change)
            self.assertEqual(film.sequence(self.studio,seq['id']),seq)
        seq=self.placement(seq,end_frame=10,trim_to_fit=True)
        self.assertEqual(seq['shots'][0]['duration_frames'],10)
        for change in ({'start_frame':5,'end_frame':15}, {'start_frame':12,'end_frame':24},
                       {'start_frame':10,'end_frame':22}):
            with self.subTest(change=change),self.assertRaises(StudioError):self.placement(seq,**change)
        before=copy.deepcopy(seq)
        seq=self.placement(seq,end_frame=10,asset_id=self.assets[1]['id'],trim_to_fit=True)
        self.assertEqual(len(seq['shots']),1)
        self.assertEqual(seq['shots'][0]['asset_id'],self.assets[1]['id'])
        self.assertEqual(seq['audio_tracks'],before['audio_tracks'])
        self.assertEqual(seq['duration_frames'],before['duration_frames'])

    def test_planned_picture_approval_and_source_integrity_gates(self):
        seq=self.prepare()
        self.studio.store.resolve(self.assets[0]['source']['path']).write_bytes(b'tampered')
        with self.assertRaises(ValueError):self.placement(seq)
        self.assertEqual(film.sequence(self.studio,seq['id']),seq)

    def test_waveform_is_real_bounded_pcm_and_tamper_detected(self):
        self.prepare();result=film.audio_waveform(self.studio,self.audio['id'])
        self.assertEqual(result['sample_count'],48000);self.assertEqual(result['bins'],1024)
        self.assertTrue(all(0<=v<=1 for v in result['peaks']));self.assertGreater(max(result['peaks']),.2)
        self.assertEqual(result['source_sha256'],self.audio['pcm']['sha256'])
        self.studio.store.resolve(self.audio['pcm']['path']).write_bytes(b'bad')
        with self.assertRaises(ValueError):film.audio_waveform(self.studio,self.audio['id'])

    def test_audio_approval_revocation_blocks_render(self):
        seq=self.prepare();audio_tracks.review(self.studio,self.audio['id'],{'decision':'rejected','expected_version':1,'notes':'Test revoke'})
        film.validate_manifest(self.studio,self.studio.store.read_snapshot(seq['manifest']))  # review status no longer gates Film
        self.studio.store.resolve(self.audio['pcm']['path']).write_bytes(b'tampered')
        with self.assertRaises((StudioError,ValueError)):film.validate_manifest(self.studio,self.studio.store.read_snapshot(seq['manifest']))
        film.process_export(self.studio,seq['id'],self.studio.store.read_snapshot(seq['manifest']))
        self.assertEqual(film.sequence(self.studio,seq['id'])['export']['status'],'failed')

    def test_explicit_empty_audio_clock_exports_silence(self):
        seq=film.save_sequence(self.studio,self.seq['id'],{'expected_revision':0,'title':'Empty audio clock','shots':[],'audio_tracks':[],'timeline_duration_frames':12})
        seq=self.export(seq);path,_=film.export_media(self.studio,seq['id'],'media')
        with wave.open(str(path),'rb') as wav:self.assertEqual(wav.readframes(24000),b'\0'*(24000*6))

    def test_legacy_picture_manifest_unchanged(self):
        self.approve();seq=film.save_sequence(self.studio,self.seq['id'],self.payload)
        manifest=self.studio.store.read_snapshot(seq['manifest'])
        self.assertNotIn('timeline_duration_frames',seq);self.assertNotIn('media_kind',manifest)
        self.assertEqual(manifest['duration_frames'],13)
        digest=manifest.pop('manifest_hash');self.assertEqual(digest,sha256(canonical_bytes(manifest)))


if __name__=='__main__':unittest.main()
