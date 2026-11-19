"""Share some matches: a dashboard file built from only the matches you pick."""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))
from elevendash import cli, sample, workspace  # noqa: E402


def quiet(*a):
    pass


class Share(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.ws = workspace.init(os.path.join(cls.tmp.name, 'ws'))
        sample.write_logs(cls.ws.logs)
        with contextlib.redirect_stdout(io.StringIO()):
            cli.do_build(cls.ws)
        cls.rows = cli.match_rows(cls.ws)
        cls.ai = [r['key'] for r in cls.rows if r['vs'] == 'AI']
        cls.online = [r['key'] for r in cls.rows if r['vs'] != 'AI']

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def built(self, keys):
        """What a build of those matches alone holds: {dataset: rows}."""
        with tempfile.TemporaryDirectory() as out:
            cli.do_build(self.ws, say=quiet, only=keys, out=out)
            got = {}
            for name in os.listdir(out):
                with open(os.path.join(out, name), encoding='utf-8') as f:
                    got[name[:-5]] = json.load(f)['rows']
        return got

    def test_only_those_matches_are_in_it(self):
        self.assertTrue(self.ai and self.online)
        for keys in (self.ai[:1], self.online[:1], self.ai[:3], self.ai[2:7] + self.online[:5], self.online):
            got = self.built(keys)
            self.assertEqual(sorted(r['key'] for r in got['matches']), sorted(keys))
            self.assertEqual({r['match'] for r in got['points']}, set(keys))
            self.assertEqual({r['key'] for r in got['shots']}, set(keys))
            # nothing of the other matches: not a key, and no count that reaches past the ones shared
            left = [k for k in self.ai + self.online if k not in keys]
            text = json.dumps(got)
            self.assertFalse([k for k in left if k in text])
            self.assertEqual(sum(r['points'] for r in got['matches']), len(got['points']))
            self.assertFalse(any(r.get('video') for r in got['matches']))

    def test_your_own_data_is_as_it_was(self):
        path = os.path.join(self.ws.build, 'matches.json')
        before = os.path.getmtime(path), sorted(os.listdir(self.ws.build))
        out, n = cli.do_share(self.ws, self.ai[:2], say=quiet)
        self.assertEqual((os.path.getmtime(path), sorted(os.listdir(self.ws.build))), before)
        self.assertEqual(n, 2)
        self.assertEqual(os.path.dirname(out), os.path.join(self.ws.root, 'share'))
        self.assertIn('elevendash-2-matches-', os.path.basename(out))
        self.assertEqual([x for x in os.listdir(self.ws.root) if x.startswith('.share-')], [])
        with open(out, encoding='utf-8') as f:
            page = f.read()
        self.assertIn('<html', page)
        for word in ('AuthToken', 'PlatformAccessToken'):
            self.assertFalse(word in page, word)

    def test_what_cannot_be_shared(self):
        with self.assertRaises(SystemExit) as e:
            cli.do_share(self.ws, ['2001-01-01 00:00:00'], say=quiet)
        self.assertIn('None of those matches', str(e.exception))
        empty = workspace.init(os.path.join(self.tmp.name, 'empty'))
        with self.assertRaises(SystemExit):
            cli.do_share(empty, self.ai[:1], say=quiet)

    def test_command_line(self):
        sessions = sorted({r['session'] for r in self.rows})
        last = [r['key'] for r in self.rows if r['session'] == sessions[-1]]
        self.assertEqual(cli.share_keys(self.ws, last=1), last)
        day = self.rows[0]['date']
        self.assertEqual(cli.share_keys(self.ws, since=day, until=day), [r['key'] for r in self.rows if r['date'] == day])
        self.assertEqual(cli.share_keys(self.ws, matches=[self.ai[3], 'no such match']), [self.ai[3]])
        self.assertEqual(len(cli.share_keys(self.ws, since='2000-01-01')), len(self.rows))
        out = io.StringIO()
        dest = os.path.join(self.tmp.name, 'coach.html')
        with contextlib.redirect_stdout(out):
            self.assertEqual(cli.main(['--dir', self.ws.root, 'share', '--last', '1', '--out', dest, '--lang', 'zh']), 0)
        self.assertIn(f'{len(last)} match', out.getvalue())
        self.assertIn('no logs, tokens', out.getvalue())
        self.assertTrue(os.path.isfile(dest))
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(['--dir', self.ws.root, 'share']), 2)


if __name__ == '__main__':
    unittest.main()
