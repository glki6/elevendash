"""The warning for logs that do not read as expected (a game update that changed the log format)."""
import contextlib
import io
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))
from elevendash import cli, extract, health, sample  # noqa: E402


class Health(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.logs = os.path.join(cls.tmp.name, 'logs')
        cls.names = sample.write_logs(cls.logs)
        with open(os.path.join(cls.logs, cls.names[0]), encoding='utf-8') as f:
            cls.text = f.read()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def found(self, old, new):
        """The problems of the first log after a line of the game's changed its wording."""
        self.assertIn(old, self.text)
        path = os.path.join(self.tmp.name, 'changed.log')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(self.text.replace(old, new))
        return health.check_log(path, extract.extract_log(path))

    def test_usual_logs_have_nothing_to_report(self):
        for name in self.names:
            path = os.path.join(self.logs, name)
            self.assertEqual(health.check_log(path, extract.extract_log(path)), [])
        self.assertEqual(health.advice({}), [])

    def test_match_start_reworded(self):
        got = self.found('[matchRunning] from [False] to [True]', '[matchRunning] changed [False] -> [True]')
        self.assertEqual(len(got), 1)
        self.assertIn('no match was found', got[0])

    def test_score_line_reworded(self):
        got = self.found('updating gameScore side', 'gameScore update, side')
        self.assertTrue(any('no points' in s for s in got), got)

    def test_contact_block_reworded(self):
        got = self.found('pongGameCollisionType', 'collisionKind')
        self.assertTrue(any('have no shots' in s for s in got), got)

    def test_state_after_hit_gone(self):
        got = self.found('postCollisionState:', 'stateAfter:')
        self.assertTrue(any('after a hit is missing' in s for s in got), got)
        said = health.pairs({'a.log': got, 'b.log': []})
        self.assertEqual(list(said), ['a.log'])
        self.assertTrue(all(x['en'] and x['zh'] and x['zh'] != x['en'] for x in said['a.log']), said)

    def test_opponent_not_recognised(self):
        got = self.found('against AI', 'versus the computer')
        self.assertTrue(any('neither against the AI nor online' in s for s in got), got)

    def test_build_says_so_and_goes_on(self):
        ws = os.path.join(self.tmp.name, 'ws')
        with contextlib.redirect_stdout(io.StringIO()):
            cli.main(['init', ws])
        os.makedirs(os.path.join(ws, 'logs'), exist_ok=True)
        for name in self.names[1:]:
            with open(os.path.join(self.logs, name), encoding='utf-8') as f, \
                    open(os.path.join(ws, 'logs', name), 'w', encoding='utf-8') as g:
                g.write(f.read())
        with open(os.path.join(ws, 'logs', self.names[0]), 'w', encoding='utf-8') as g:
            g.write(self.text.replace('postCollisionState:', 'stateAfter:'))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(['--dir', ws, 'build'])
        self.assertEqual(code, 0)
        said = out.getvalue()
        self.assertIn('Warning: some logs did not read as expected', said)
        self.assertIn(self.names[0], said)
        self.assertNotIn(self.names[1] + ':', said)
        self.assertTrue(os.path.exists(os.path.join(ws, 'build', 'matches.json')))


if __name__ == '__main__':
    unittest.main()
