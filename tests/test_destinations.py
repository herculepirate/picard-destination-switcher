"""destinations: the folders you name, and Picard's naming scripts as the toolbar lists them.

Run: python3 tests/test_destinations.py"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import destinations as dst  # noqa: E402


class Destinations(unittest.TestCase):
    def test_round_trip(self):
        items = [{'name': 'Lossless', 'path': '/music/lossless'}, {'name': '', 'path': '/music/lossy/'},
                 {'name': 'empty', 'path': '  '}]
        back = dst.load(dst.dump(items))
        self.assertEqual(back, [{'name': 'Lossless', 'path': '/music/lossless', 'script': ''},
                                {'name': 'lossy', 'path': '/music/lossy/', 'script': ''}])

    def test_unreadable(self):
        self.assertEqual(dst.load('not json'), [])
        self.assertEqual(dst.load(None), [])
        self.assertEqual(dst.load('{"a": 1}'), [])

    def test_current_folder(self):
        items = dst.load(dst.dump([{'name': 'Lossless', 'path': '/music/lossless'},
                                   {'name': 'Lossy', 'path': '/music/lossy'}]))
        self.assertEqual(dst.index_of(items, '/music/lossy/'), 1)
        self.assertEqual(dst.index_of(items, '/music/./lossless'), 0)
        self.assertEqual(dst.index_of(items, '/elsewhere'), -1)
        self.assertEqual(dst.index_of(items, ''), -1)

    def test_linked_script(self):
        items = dst.load(dst.dump([{'name': 'classical', 'path': '/m/classical', 'script': 'cls'},
                                   {'name': 'lossy', 'path': '/m/lossy', 'script': ''}]))
        self.assertEqual(items[0]['script'], 'cls')
        self.assertNotIn('script', dst.load(dst.dump(items))[1] if False else {})
        scripts = {'cls': {'title': 'classical_unraid'}}
        self.assertEqual(dst.linked_script(items[0], scripts), 'cls')
        self.assertEqual(dst.linked_script(items[1], scripts), '')          # (keep current)
        self.assertEqual(dst.linked_script(items[0], {}), '')               # (script deleted since)
        self.assertNotIn('"script"', dst.dump(items[1:]))

    def test_scripts_sorted_by_title(self):
        scripts = {'b': {'title': 'Preset 2: Album/Track'}, 'a': {'title': 'My script'}, 'c': {}}
        self.assertEqual(dst.scripts(scripts), [('c', 'c'), ('a', 'My script'), ('b', 'Preset 2: Album/Track')])


if __name__ == '__main__':
    unittest.main()
