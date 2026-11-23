"""sweep: what is left in an album's folder goes with it.

Run: python3 tests/test_sweep.py"""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sweep  # noqa: E402


def touch(path, text='x'):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


class Sweep(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _picard_saves(self, files, new_dir_of):
        """Move each audio file as Picard does (only the file itself); returns old and new dirs."""
        old, new = set(), set()
        for f in files:
            dst = Path(new_dir_of(f)) / f.name
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(f, dst)
            old.add(str(f.parent))
            new.add(str(dst.parent))
        return old, new

    def test_disc_folders(self):
        self.assertTrue(sweep.is_disc_dir('CD1'))
        self.assertTrue(sweep.is_disc_dir('Disc 2 - Live'))
        self.assertTrue(sweep.is_disc_dir('cd 01'))
        self.assertTrue(sweep.is_disc_dir('Side A'))
        for name in ('Covers', 'Discography', 'CDs', 'Vol. 2', '2011 - Lumiere', 'Scans'):
            self.assertFalse(sweep.is_disc_dir(name), name)

    def test_album_root(self):
        self.assertEqual(sweep.album_root(['/m/A/CD1', '/m/A/CD2']), '/m/A')
        self.assertEqual(sweep.album_root(['/m/A/CD1']), '/m/A')
        self.assertEqual(sweep.album_root(['/m/A']), '/m/A')
        self.assertIsNone(sweep.album_root(['/m/A', '/m/B']))

    def test_a_set_of_discs_takes_its_covers_and_log(self):
        old = self.tmp / 'in' / 'Album'
        disc_files = [old / 'CD1' / '01.flac', old / 'CD1' / '02.flac', old / 'CD2' / '01.flac']
        for f in disc_files:
            touch(f)
        touch(old / 'covers' / 'front.jpg')
        touch(old / 'covers' / 'back.jpg')
        touch(old / 'Album.log')
        touch(old / 'CD1' / 'CD1.cue')                  # left beside a disc's files
        new = self.tmp / 'out' / 'Artist' / '2011 - Album'
        olds, news = self._picard_saves(disc_files, lambda f: new / f.parent.name)
        moves = sweep.plan(sweep.album_root(olds), sweep.album_root(news), olds, news)
        moved, skipped = sweep.apply(moves)
        self.assertEqual(skipped, [])
        self.assertTrue((new / 'covers' / 'front.jpg').exists())
        self.assertTrue((new / 'covers' / 'back.jpg').exists())
        self.assertTrue((new / 'Album.log').exists())
        self.assertTrue((new / 'CD1' / 'CD1.cue').exists())    # into the new CD1, not CD1/CD1
        self.assertTrue(sweep.remove_if_empty(str(old)))

    def test_discs_saved_into_one_folder(self):
        old = self.tmp / 'in' / 'Album'
        files = [old / 'CD1' / '01.flac', old / 'CD2' / '01.flac']
        for f in files:
            touch(f)
        touch(old / 'Scans' / 'disc.png')
        new = self.tmp / 'out' / 'Album'
        olds, news = self._picard_saves(files, lambda f: new)
        sweep.apply(sweep.plan(sweep.album_root(olds), sweep.album_root(news), olds, news))
        self.assertTrue((new / 'Scans' / 'disc.png').exists())

    def test_nothing_moves_while_audio_is_left(self):
        old = self.tmp / 'in' / 'Album'
        touch(old / 'CD1' / '01.flac')
        touch(old / 'CD2' / '01.flac')                  # disc 2 not saved yet
        touch(old / 'covers' / 'front.jpg')
        new = self.tmp / 'out' / 'Album'
        olds, news = self._picard_saves([old / 'CD1' / '01.flac'], lambda f: new / 'CD1')
        self.assertEqual(sweep.plan(sweep.album_root(olds), sweep.album_root(news), olds, news), [])

    def test_an_artist_folder_with_other_albums_is_never_swept(self):
        artist = self.tmp / 'in' / 'Artist'
        touch(artist / 'CD1' / '01.flac')
        touch(artist / 'Other Album' / '01.flac')
        touch(artist / 'artist.jpg')
        new = self.tmp / 'out' / 'Album'
        olds, news = self._picard_saves([artist / 'CD1' / '01.flac'], lambda f: new)
        self.assertEqual(sweep.plan(sweep.album_root(olds), sweep.album_root(news), olds, news), [])

    def test_not_into_itself(self):
        old = self.tmp / 'Album'
        touch(old / 'cover.jpg')
        self.assertEqual(sweep.plan(str(old), str(old / 'Sub')), [])
        self.assertEqual(sweep.plan(str(old / 'Sub'), str(old)), [])

    def test_what_is_there_already_is_kept(self):
        old, new = self.tmp / 'old', self.tmp / 'new'
        touch(old / 'covers' / 'front.jpg', 'old')
        touch(old / 'covers' / 'back.jpg', 'old')
        touch(new / 'covers' / 'front.jpg', 'new')
        moved, skipped = sweep.apply(sweep.plan(str(old), str(new)))
        self.assertEqual((new / 'covers' / 'front.jpg').read_text(), 'new')
        self.assertTrue((new / 'covers' / 'back.jpg').exists())
        self.assertEqual([os.path.basename(s) for s, _ in skipped], ['front.jpg'])
        moved, skipped = sweep.apply(sweep.plan(str(old), str(new)), overwrite=True)
        self.assertEqual((new / 'covers' / 'front.jpg').read_text(), 'old')


if __name__ == '__main__':
    unittest.main()
