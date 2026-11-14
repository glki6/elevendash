"""The whole path on generated logs: parse, build every dataset, write the dashboard, print the report."""
import contextlib
import io
import json
import math
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))
from elevendash import cli, extract, i18n, sample  # noqa: E402


class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.ws = os.path.join(cls.tmp.name, 'demo')
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cls.code = cli.main(['demo', cls.ws])
        cls.printed = out.getvalue()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def rows(self, name):
        with open(os.path.join(self.ws, 'build', name + '.json'), encoding='utf-8') as f:
            return json.load(f)['rows']

    def test_demo_ran(self):
        self.assertEqual(self.code, 0, self.printed)
        self.assertIn('ALL TIME', self.printed)

    def test_parse(self):
        logs = sorted(os.listdir(os.path.join(self.ws, 'logs')))
        self.assertEqual(len(logs), len(sample.SESSIONS))
        for name, (level, count) in zip(logs, sample.SESSIONS):
            ms = extract.extract_log(os.path.join(self.ws, 'logs', name))
            self.assertEqual(len(ms), count)
            for m in ms:
                self.assertTrue(m['ai'])
                self.assertEqual(m['difficulty'], level)
                self.assertEqual(m['hand'], 'right')
                wins = [g['score'][0] > g['score'][1] for g in m['games']]
                self.assertEqual(max(wins.count(True), wins.count(False)), 2)
                for g in m['games']:
                    a, b = g['score']
                    self.assertTrue(max(a, b) >= 11 and abs(a - b) >= 2, g['score'])
                    for p in g['points']:
                        self.assertTrue(p['hits'])
                        self.assertEqual(p['hits'][0]['shot'], 'Serve')

    def test_datasets(self):
        sessions = self.rows('sessions')
        self.assertEqual(len(sessions), len(sample.SESSIONS))
        self.assertEqual(sum(s['matches'] for s in sessions), sum(n for _, n in sample.SESSIONS))
        self.assertEqual(sorted({s['level'] for s in sessions}), [75, 100])
        self.assertTrue(self.rows('replay'))
        for r in self.rows('replay'):       # the 3D view's numbers: velocity arriving at every contact; leaving, and spin, on a hit
            ev = [e.split(',') for e in r['track'].split(';')]
            self.assertEqual(ev[0][0], 'h')
            for e in ev:
                self.assertEqual(len(e), {'h': 19, 'x': 5}.get(e[0], 8), r['track'])
                if e[0] == 'h':
                    vx, vy, vz = (int(x) / 10 for x in e[13:16])
                    self.assertAlmostEqual(math.hypot(vx, vy, vz), int(e[6]) / 10, delta=0.2)      # the logged speed
                    self.assertTrue(e[16] != '' and e[10] != '')
            ts = [int(e[4]) for e in ev]
            self.assertEqual(ts, sorted(ts))
        main = next(r for r in self.rows('findings') if r['key'] == 'main')
        self.assertEqual(main['level'], 100)                    # the level of the latest sessions
        self.assertTrue(0.3 < main['shotSecs'] < 1.5)
        for name in os.listdir(os.path.join(self.ws, 'build')):
            with open(os.path.join(self.ws, 'build', name), encoding='utf-8') as f:
                for row in json.load(f)['rows']:          # flat rows only: hosts may turn nested values into text
                    self.assertFalse([k for k, v in row.items() if isinstance(v, (list, dict))], name)

    def test_match_sums(self):
        """Each match's sums give back its 11hero metrics, and added up over a session they give the session's rates
        (the page adds them up over the matches picked)."""
        from elevendash.metrics import SUMS, from_sums
        matches, sums = self.rows('matches'), self.rows('match_sums')
        self.assertEqual([m['key'] for m in matches], [s['key'] for s in sums])
        for m, s in zip(matches, sums):
            self.assertEqual((s['pts'], s['won']), (m['points'], m['pointsWonN']))
            self.assertEqual(sum(s[f'e{i}'] for i in range(5)), s['pts'])
            for side in ('you_', 'ai_'):
                one = {k[len(side):]: v for k, v in s.items() if k.startswith(side)}
                for name in SUMS:
                    want, got = m[side + name], from_sums(one, name)
                    if want is None:
                        self.assertIsNone(got, name)
                    else:
                        self.assertAlmostEqual(got, want, delta=0.051, msg=f'{m["key"]} {side}{name}')
        by = {s['key']: s for s in sums}
        for ses in self.rows('sessions'):
            t = {}
            for m in matches:
                if m.get('session') == ses['key']:
                    for k, v in by[m['key']].items():
                        if k != 'key':
                            t[k] = t.get(k, 0) + v
            self.assertAlmostEqual(100 * t['won'] / t['pts'], ses['pointRate'], delta=0.051)
            self.assertAlmostEqual(100 * t['servesOk'] / t['serves'], ses['servesLanded'], delta=0.051)
            self.assertAlmostEqual(100 * t['lostMiss'] / t['lost'], ses['missShare'], delta=0.051)
            self.assertAlmostEqual(t['spd'] / t['rally'], ses['rallySpeed'], delta=0.051)

    def test_site(self):
        path = os.path.join(self.ws, 'site', 'index.html')
        with open(path, encoding='utf-8') as f:
            html = f.read()
        self.assertGreater(len(html), 300_000)
        self.assertIn('d3js.org', html)
        self.assertNotIn('ALL-01.', html)                     # no log file names in the shared file


class Translations(unittest.TestCase):
    def test_complete(self):
        self.assertEqual(i18n.check(out=io.StringIO()), 0)


if __name__ == '__main__':
    unittest.main()
