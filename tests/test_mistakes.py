"""The misses reel's plan, on generated logs: which shots it picks and when each clip runs. Nothing is cut or uploaded."""
import contextlib
import io
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))
from elevendash import cli  # noqa: E402


class Mistakes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.ws = os.path.join(cls.tmp.name, 'demo')
        with contextlib.redirect_stdout(io.StringIO()):
            cli.main(['demo', cls.ws])
        cls.home = os.environ.get('ELEVENDASH_HOME')
        os.environ['ELEVENDASH_HOME'] = cls.ws          # the reel scripts find their workspace when they are loaded
        sys.path.insert(0, os.path.join(ROOT, 'youtube'))
        import mistakes
        cls.mk = mistakes

    @classmethod
    def tearDownClass(cls):
        if cls.home is None:
            os.environ.pop('ELEVENDASH_HOME', None)
        else:
            os.environ['ELEVENDASH_HOME'] = cls.home
        cls.tmp.cleanup()

    def test_plan(self):
        mk = self.mk
        log = sorted(os.listdir(os.path.join(self.ws, 'logs')))[-1]
        row = {'sync': [{'log': log, 'lag': -30.0}], 'audio_start': 0.1, 'duration': 1e6}
        cands, missing = mk.candidates(row, os.path.join(self.ws, 'logs'), os.path.join(self.ws, 'build'))
        self.assertEqual(missing, [])
        self.assertTrue(len(cands) > 50)
        for c in cands:
            self.assertTrue(c['b'] - c['a'] >= 1.5 and c['a'] >= 0, c)
            self.assertEqual(c['ok'], c['miss'] == '', c)
            self.assertIn(c['group'][0], 'RA')
        reel = mk.plan(cands, 100)
        self.assertTrue(1 <= len(reel) <= mk.GROUPS)
        clips = mk.captions(reel)
        self.assertEqual(len({c['key'] for c in clips}), len(clips))
        spans = sorted((c['a'], c['b']) for c in clips)
        self.assertTrue(all(b <= a2 for (_, b), (a2, _) in zip(spans, spans[1:])))        # no moment twice
        self.assertLessEqual(sum(b - a for a, b in spans), 104)
        counts = []
        for part in reel:
            mine = [c for c in cands if c['group'] == part['group']]
            self.assertEqual((part['n'], part['missed']), (len(mine), sum(not c['ok'] for c in mine)))
            oks = [c['ok'] for c in part['clips']]
            self.assertEqual(oks, sorted(oks))                                           # the misses first, then the ones that landed
            self.assertTrue(2 <= oks.count(False) <= mk.MISSES and oks.count(True) <= mk.MADE)
            self.assertTrue(all(c['caption'].startswith(f"{len(counts) + 1} · {part['label']}") for c in part['clips']))
            counts.append(part['missed'])
        self.assertEqual(counts, sorted(counts, reverse=True))                           # most-missed kind of ball first
        # a recording too short for the log leaves nothing to pick
        self.assertEqual(mk.candidates(dict(row, duration=1.0), os.path.join(self.ws, 'logs'), os.path.join(self.ws, 'build'))[0], [])

    def test_labels(self):
        mk = self.mk
        self.assertEqual(mk.label(('A', 't', 'B', 'f')), 'Fast topspin to your backhand side')
        self.assertEqual(mk.label(('A', 'n', 'M', 's')), 'Slower ball with little spin to the middle')
        self.assertEqual(mk.label(('R', 'n', 'F', 'h')), 'Returning a half-long no-spin serve to your forehand side')
        self.assertIsNone(mk.group_of({'role': 'S', 'cls': ''}))
        self.assertIsNone(mk.group_of({'role': 'A', 'cls': 't-hf'}))
        self.assertEqual(mk.group_of({'role': 'R', 'cls': 'bBsf'}), ('R', 'b', 'B', 's'))
        self.assertEqual(mk.spread(list(range(10)), 4), [0, 3, 6, 9])
        self.assertEqual(mk.spread([1, 2], 4), [1, 2])


if __name__ == '__main__':
    unittest.main()
