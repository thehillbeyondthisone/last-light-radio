"""Isolated coverage for removing film clips from the library and from disk."""
import io
import subprocess
import tempfile
import unittest
import wave
from pathlib import Path
from last_light_radio import film, audio_tracks
from last_light_radio.studio import Studio, StudioError
from last_light_radio.video_tools import ffmpeg_path


def _wav():
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as out:
        out.setnchannels(1); out.setsampwidth(2); out.setframerate(48000)
        out.writeframes(b'\x01\x00' * 4800)
    return buffer.getvalue()


class FilmDeleteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='film-delete-sources-')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.videos = []
        for color in ('red', 'blue'):
            path = Path(cls.temp.name) / f'{color}.mp4'
            subprocess.run([ffmpeg_path(), '-v', 'error', '-f', 'lavfi', '-i', f'color=c={color}:s=64x48:r=24',
                            '-frames:v', '12', '-an', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(path)], check=True, capture_output=True)
            cls.videos.append(path.read_bytes())
        cls.wav = Path(cls.temp.name) / 'sound.wav'
        cls.wav.write_bytes(_wav())

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory(prefix='film-delete-')
        self.addCleanup(self.tempdir.cleanup)
        self.studio = Studio(self.tempdir.name)
        self.assets = [film.import_bytes(self.studio, data, f'{i}.mp4', f'Fixture {i}', {'test_only': True}) for i, data in enumerate(self.videos)]
        self.sound = audio_tracks.import_file(self.studio, self.wav, 'take.wav', 'Fixture production sound', {'test_only': True})
        self.job = 'a' * 32
        self.studio.set_setting('film.generation.import.' + self.job, {'video_asset_id': self.assets[0]['id'], 'audio_asset_id': self.sound['id']})

    def path(self, record):
        return self.studio.store.resolve(record['source']['path'])

    def remove(self, index=0, **extra):
        record = self.assets[index]
        return film.delete_asset(self.studio, record['id'], {'expected_version': record['version'], **extra})

    def test_dry_run_reports_without_changing_anything(self):
        report = self.remove(mode='disk', dry_run=True)
        self.assertTrue(report['dry_run'])
        self.assertEqual(report['used_by'], [])
        self.assertTrue(report['sound']['will_delete'])
        self.assertEqual(len(report['files']), 3)
        self.assertGreater(report['bytes'], 0)
        self.assertEqual(report['generation_jobs'], [self.job])
        self.assertIsNotNone(self.studio.setting('film.asset.' + self.assets[0]['id']))
        self.assertTrue(self.path(self.assets[0]).is_file())

    def test_library_mode_keeps_files_and_reimport_works(self):
        report = self.remove(mode='library')
        self.assertEqual(report['bytes_freed'], 0)
        self.assertIsNone(self.studio.setting('film.asset.' + self.assets[0]['id']))
        self.assertIsNone(self.studio.setting(self.sound['id']))
        self.assertIsNone(self.studio.setting('film.generation.import.' + self.job))
        self.assertIsNotNone(self.studio.setting('film.deleted.' + self.assets[0]['id']))
        self.assertTrue(self.path(self.assets[0]).is_file())
        self.studio.store.read_snapshot(report['receipt'])
        again = film.import_bytes(self.studio, self.videos[0], 'again.mp4', 'Again', {})
        self.assertEqual(again['id'], self.assets[0]['id'])
        self.assertEqual(again['status'], 'candidate')

    def test_disk_mode_removes_exactly_its_files(self):
        other = self.path(self.assets[1])
        report = self.remove(mode='disk')
        self.assertEqual(report['files_left'], [])
        self.assertEqual(report['bytes_freed'], report['bytes'])
        self.assertFalse(self.path(self.assets[0]).exists())
        self.assertFalse(self.path(self.sound).exists())
        self.assertFalse(self.path(self.assets[0]).parent.exists())
        self.assertTrue(other.is_file())
        self.assertIsNotNone(self.studio.setting('film.asset.' + self.assets[1]['id']))

    def test_keep_sound_when_asked(self):
        report = self.remove(mode='disk', include_sound=False)
        self.assertFalse(report['sound']['will_delete'])
        self.assertIsNotNone(self.studio.setting(self.sound['id']))
        self.assertTrue(self.path(self.sound).is_file())

    def test_refused_while_used_by_a_sequence(self):
        self.assets = [film.review_asset(self.studio, a['id'], {'decision': 'approved', 'expected_version': a['version'], 'notes': 'Isolated test'}) for a in self.assets]
        project = film.create_project(self.studio, {'title': 'Fixture project'})
        seq = film.create_sequence(self.studio, project['id'], {'title': 'Cut using clip'})
        film.save_sequence(self.studio, seq['id'], {'title': 'Cut using clip', 'expected_revision': 0, 'width': 64, 'height': 48, 'audio_tracks': [],
                                                    'shots': [{'id': 'red', 'asset_id': self.assets[0]['id'], 'source_in_frame': 0, 'duration_frames': 6}]})
        report = self.remove(mode='disk', dry_run=True)
        self.assertEqual([u['title'] for u in report['used_by']], ['Cut using clip'])
        with self.assertRaises(StudioError) as caught:
            self.remove(mode='disk')
        self.assertEqual(caught.exception.status, 409)
        self.assertIn('Cut using clip', str(caught.exception))
        self.assertTrue(self.path(self.assets[0]).is_file())

    def test_shot_plan_candidate_blocks_with_readable_name(self):
        self.studio.set_setting('film.plan.candidate.plannedshot.' + 'd' * 32 + '.existing.x', {'kind': 'existing_asset', 'asset_id': self.assets[1]['id']})
        report = self.remove(1, mode='disk', dry_run=True)
        self.assertEqual([u['title'] for u in report['used_by']], ['a shot plan slot (attached candidate)'])
        with self.assertRaises(StudioError) as caught:
            self.remove(1, mode='disk')
        self.assertIn('shot plan slot', str(caught.exception))

    def test_sound_used_elsewhere_is_kept(self):
        self.studio.set_setting('film.sequence.sequence.' + 'b' * 32, {'title': 'Uses the sound', 'audio_tracks': [{'asset_id': self.sound['id']}]})
        report = self.remove(mode='disk')
        self.assertFalse(report['sound']['will_delete'])
        self.assertEqual([u['title'] for u in report['sound']['used_by']], ['Uses the sound'])
        self.assertTrue(self.path(self.sound).is_file())
        self.assertFalse(self.path(self.assets[0]).exists())

    def test_stale_version_bad_id_and_mode(self):
        with self.assertRaises(StudioError) as caught:
            film.delete_asset(self.studio, self.assets[0]['id'], {'expected_version': 7, 'mode': 'library'})
        self.assertEqual(caught.exception.status, 409)
        for bad in ('../../secret', 'video.' + 'z' * 64, 'audio.' + 'a' * 64):
            with self.subTest(bad=bad), self.assertRaises(StudioError):
                film.delete_asset(self.studio, bad, {'expected_version': 0, 'mode': 'disk'})
        with self.assertRaises(StudioError):
            self.remove(mode='trash')
        with self.assertRaises(StudioError) as caught:
            film.delete_asset(self.studio, 'video.' + 'f' * 64, {'expected_version': 0, 'mode': 'disk'})
        self.assertEqual(caught.exception.status, 404)


if __name__ == '__main__':
    unittest.main()
