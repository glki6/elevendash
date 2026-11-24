"""The whole path on generated logs: parse, build every dataset, write the dashboard, print the report."""
import contextlib
import io
import json
import math
import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))
from elevendash import cli, extract, i18n, sample, voice  # noqa: E402


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
        self.assertEqual(len(logs), len(sample.SESSIONS) + len(sample.ONLINE))
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
        months = sorted(f[:-5] for f in os.listdir(os.path.join(self.ws, 'build')) if f.startswith('replay'))
        self.assertTrue(months and all(re.fullmatch(r'replay_\d{4}_\d\d', m) for m in months), months)
        replay = [r for m in months for r in self.rows(m)]
        self.assertTrue(replay)
        online = {m['key'] for m in self.rows('matches') if m['vs'] != 'AI'}
        for m in months:                    # one file a month, each holding only its own month's points
            self.assertEqual({'replay_' + r['key'][:7].replace('-', '_') for r in self.rows(m)}, {m})
        self.assertTrue({r['key'] for r in replay} <= {p['key'] for p in self.rows('points')})
        for r in replay:                    # the 3D view's numbers: velocity arriving at every contact; leaving, and spin, on a hit
            ev = [e.split(',') for e in r['track'].split(';')]
            self.assertEqual(ev[0][0], 'h')
            for e in ev:
                self.assertEqual(len(e), {'h': 19, 'x': 5}.get(e[0], 8), r['track'])
                if e[0] == 'h':
                    vx, vy, vz = (int(x) / 10 for x in e[13:16])
                    self.assertAlmostEqual(math.hypot(vx, vy, vz), int(e[6]) / 10, delta=0.2)      # the logged speed
                    # an online opponent's hit comes from their game: it says how the ball left, not how it arrived
                    theirs = e[5] == 'a' and r['key'].split('|')[0] in online
                    self.assertTrue(e[16] != '' and (theirs or e[10] != ''), r['key'])
            ts = [int(e[4]) for e in ev]
            self.assertEqual(ts, sorted(ts))
        # the shot explorer: every shot of yours once, agreeing with the match totals
        sums = {r['key']: r for r in self.rows('match_sums')}
        points = {r['key'] for r in self.rows('points')}
        self.assertTrue(self.rows('shots'))
        for row in self.rows('shots'):
            n = {}
            recs = [s.split(',') for s in row['s'].split(';')]
            self.assertEqual(row['n'], len(recs))
            for a in recs:
                self.assertEqual(len(a), 23, a)
                self.assertEqual(a[21] == '', a[22] == '', a)       # where your shot landed: both or neither
                self.assertTrue(a[21] == '' or (a[4] == '1' and int(a[22]) > 0), a)     # only a shot that landed, on the far half
                self.assertEqual(a[20] == '', a[3] == 'X', a)       # where you met it: every shot you hit
                self.assertTrue(a[3] != 'X' or a[19] == '', a)
                self.assertTrue(a[19] == '' or -900 <= int(a[19]) <= 900, a)    # the angle off your bat, tenths of a degree
                self.assertIn(row['key'] + '|' + a[0].replace('.', '|'), points)
                self.assertIn(a[2], 'SRA')
                self.assertEqual(a[5] == '', a[4] == '1', a)        # a miss says how, a shot that landed does not
                self.assertEqual(a[3] == 'X', a[5] == 'x', a)       # a ball you did not reach
                self.assertEqual(len(a[18]), 0 if a[2] == 'S' else 4, a)
                if a[3] != 'X':
                    n[a[2]] = n.get(a[2], 0) + 1
                    n[a[2] + 'ok'] = n.get(a[2] + 'ok', 0) + int(a[4])
            t = sums[row['key']]
            g = lambda k: n.get(k, 0)
            self.assertEqual([g('S'), g('R'), g('R') + g('A'), g('Sok'), g('Rok'), g('Rok') + g('Aok')],
                             [t['serves'], t['ret'], t['rally'], t['servesOk'], t['retOk'], t['rallyOk']])
        for r in self.rows('shot_groups'):
            self.assertIn(r['scope'], ('recent', 'all'))
            self.assertTrue(r['n'] >= 30 and r['rate'] > r['usual'] and r['extra'] >= 0, r)
            self.assertTrue(r['failed'] >= r['net'] + r['long'] + r['wide'] + r['unreached'], r)
            self.assertTrue(r['label'] and r['label_zh'])
        # form: the rolling shares are the plain shares over the last matches at the level, inside their ranges
        ms = [r for r in self.rows('matches') if r['vs'] == 'AI']
        form = self.rows('form')
        self.assertEqual(len(form), len(ms))
        for r in form:
            at = [m for m in ms if m['level'] == r['level']]
            self.assertEqual(at[r['i'] - 1]['key'], r['key'])
            for w in (10, 20, 50):
                last = at[r['i'] - w:r['i']] if r['i'] >= w else []
                if not last:
                    self.assertIsNone(r[f'm{w}'])
                    continue
                self.assertAlmostEqual(r[f'm{w}'], 100 * sum(m['result'] == 'Won' for m in last) / w, delta=0.06)
                self.assertAlmostEqual(r[f'p{w}'], 100 * sum(m['pointsWonN'] for m in last) / sum(m['points'] for m in last), delta=0.06)
                for f in ('m', 'p'):
                    self.assertTrue(0 <= r[f'{f}{w}lo'] <= r[f'{f}{w}'] <= r[f'{f}{w}hi'] <= 100, r)
        for r in self.rows('session_shape'):
            self.assertTrue(r['matches'] >= 5 and r['lo'] <= r['diff'] <= r['hi'], r)
            self.assertEqual(r['move'], 1 if r['lo'] > 0 else -1 if r['hi'] < 0 else 0, r)     # coloured when the range clears zero
            self.assertAlmostEqual(r['diff'], r['rate'] - r['rest'], delta=0.11)
        self.assertTrue(all(r['text'] and r['text_zh'] for r in self.rows('form_notes')))
        # plan progress: one row per plan item, agreeing with the plan as it stands
        plan = {r['key']: r for r in self.rows('plan')}
        prog = self.rows('plan_progress')
        self.assertEqual(sorted(g['key'] for g in prog), sorted(plan))
        # a target comes from 10 or more matches at the level (all of them, not only the ones won)
        for r in plan.values():
            self.assertEqual(r['target'] is None, r['targetMatches'] < 10, r['key'])
            self.assertTrue(r['target'] is None or 0 <= r['target'] <= 100, r)
            self.assertEqual(r['status'] == 'none', r['target'] is None, r['key'])
        self.assertTrue(any(r['target'] is not None for r in plan.values()))
        # plan history: a row for every item and session at the plan's level, spelling out the same states
        hist = self.rows('plan_history')
        self.assertEqual(len({h['key'] for h in hist}), len(hist))
        for g in prog:
            mine = sorted((h for h in hist if h['item'] == g['key']), key=lambda h: h['session'])
            self.assertEqual(''.join(h['state'] for h in mine), g['states'], g['key'])
            self.assertEqual(mine[-1]['gain'], plan[g['key']]['gain'], g['key'])
            self.assertTrue(all((h['gain'] is None) == (h['state'] == '-') for h in mine), g['key'])
        for g in prog:
            r, st = plan[g['key']], g['states']
            self.assertEqual(len(st), sum(x['level'] == r['level'] for x in sessions))
            self.assertEqual((g['state'], g['ever']), (st[-1], int('1' in st)), g)
            want = '-' if r['status'] == 'none' else '0' if r['status'] == 'reached' or r['gain'] < 0.15 else '1'
            self.assertEqual(g['state'], want, g)
            self.assertLessEqual(g['runSession'], sessions[-1]['n'])
            if g['ever']:
                e = st.index('1')
                self.assertEqual((g['sessionsFrom'], g['sessionsSince'], g['sessionsOn']), (len(st) - e, len(st) - e - 1, st[e:].count('1')), g)
                self.assertTrue(0 <= g['then'] <= 100 and g['thenTries'] > 0 and g['move'] in (-1, 0, 1), g)
                self.assertEqual(g['since'] is None, g['sinceTries'] == 0, g)
                if g['move']:
                    self.assertEqual(g['move'], 1 if g['since'] > g['then'] else -1, g)
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
                if m.get('session') == ses['key'] and m['vs'] == 'AI':
                    for k, v in by[m['key']].items():
                        if k != 'key':
                            t[k] = t.get(k, 0) + v
            self.assertAlmostEqual(100 * t['won'] / t['pts'], ses['pointRate'], delta=0.051)
            self.assertAlmostEqual(100 * t['servesOk'] / t['serves'], ses['servesLanded'], delta=0.051)
            self.assertAlmostEqual(100 * t['lostMiss'] / t['lost'], ses['missShare'], delta=0.051)
            self.assertAlmostEqual(t['spd'] / t['rally'], ses['rallySpeed'], delta=0.051)

    def test_online_logs(self):
        """The generated online sessions: matches against people, each with both ratings as the game logs them."""
        logs = sorted(os.listdir(os.path.join(self.ws, 'logs')))[len(sample.SESSIONS):]
        rating = sample.START_RATING
        for name, session in zip(logs, sample.ONLINE):
            ms = extract.extract_log(os.path.join(self.ws, 'logs', name))
            self.assertEqual(len(ms), len(session))
            for m, ranked in zip(ms, session):
                self.assertFalse(m['ai'])
                self.assertIsNone(m['difficulty'])
                r = m['rating']
                self.assertEqual((r['you'], r['ranked']), (rating, ranked), name)
                self.assertTrue(1000 < r['opp'] < 2000, r)
                if ranked:
                    self.assertTrue(r['win'] > 0 > r['lose'], r)
                    games = [g['score'] for g in m['games']]
                    mine = 0 if m['you'] == 'A' else 1
                    won = sum(g[mine] > g[1 - mine] for g in games) * 2 > len(games)
                    rating += r['win'] if won else r['lose']
                else:
                    self.assertIsNone(r['win'])

    def test_online_side(self):
        """The online pass: the same sums over the online matches in datasets ending _h, in words that name no AI and
        no level, and the ratings on top."""
        ms = [r for r in self.rows('matches') if r['vs'] != 'AI']
        ranked = [r for r in ms if r['ranked']]
        self.assertEqual(len(ms), sum(len(s) for s in sample.ONLINE))
        self.assertEqual(len(ranked), sum(sum(s) for s in sample.ONLINE))
        self.assertTrue(all(r['level'] == 999 and r['rYou'] and r['rOpp'] for r in ms))
        self.assertEqual(next(r for r in self.rows('summary') if r['key'] == 'online')['matches'], len(ms))
        sessions = self.rows('sessions_h')
        self.assertEqual([s['matches'] for s in sessions], [len(s) for s in sample.ONLINE])
        self.assertEqual({r['session'] for r in ms}, {s['key'] for s in sessions})
        ai = {f[:-5] for f in os.listdir(os.path.join(self.ws, 'build'))}
        sums = {n[:-2] for n in ai if n.endswith('_h')}
        self.assertTrue({'summary', 'sessions', 'plan', 'form', 'findings', 'levels', 'insights', 'zones', 'rating', 'rating_bands',
                         'rating_notes'} <= sums, sums)
        self.assertTrue(sums - {'rating', 'rating_bands', 'rating_notes'} <= ai)       # each stands beside its AI dataset
        # ratings: every match once, each rating following from the one before, the sums agreeing with the matches
        rating = self.rows('rating_h')
        self.assertEqual([r['key'] for r in rating], [r['key'] for r in ms])
        for r, m in zip(rating, ms):
            self.assertEqual((r['you'], r['opp'], r['ranked'], r['won']), (m['rYou'], m['rOpp'], m['ranked'], int(m['result'] == 'Won')))
            self.assertEqual(r['after'], r['you'] + r['change'])
            self.assertEqual(r['change'], 0 if not r['ranked'] else m['rWin'] if r['won'] else m['rLose'])
            self.assertAlmostEqual(r['exp'], 100 / (1 + 10 ** ((r['opp'] - r['you']) / 400)), delta=0.06)
        for a, b in zip(rating, rating[1:]):
            self.assertEqual(b['you'], a['after'])
        top = next(r for r in self.rows('summary_h') if r['key'] == 'all')
        self.assertEqual((top['matches'], top['rankedMatches'], top['rating'], top['ratingFirst']),
                         (len(ms), len(ranked), rating[-1]['after'], sample.START_RATING))
        self.assertEqual(top['ratingChange'], top['rating'] - top['ratingFirst'])
        self.assertTrue(top['ratingLow'] <= top['rating'] <= top['ratingPeak'])
        bands = {r['key']: r for r in self.rows('rating_bands_h')}
        self.assertEqual(bands['all']['matches'], sum(bands[k]['matches'] for k in ('lower', 'near', 'higher')))
        self.assertAlmostEqual(bands['all']['expWins'], sum(r['exp'] for r in rating) / 100, delta=0.06)
        self.assertEqual(bands['all']['wins'], sum(r['won'] for r in rating))
        self.assertTrue(all(r['text'] and r['text_zh'] for r in self.rows('rating_notes_h')))
        # the words: no AI, no level, in either language. Left as they are: key-like fields, and the drills, which send
        # you to practise against the AI whoever your matches are against
        for name in sorted(sums):
            for row in self.rows(name + '_h'):
                for k, v in row.items():
                    if isinstance(v, str) and k not in ('key', 'server', 'levels', 'drill', 'drill_zh'):
                        self.assertIsNone(re.search(r'\bAI\b|[Ll]evel|等級|999', v), (name, k, v))
        self.assertIn('online', self.printed)
        self.assertIn('rating', self.printed)

    def test_site(self):
        path = os.path.join(self.ws, 'site', 'index.html')
        with open(path, encoding='utf-8') as f:
            html = f.read()
        self.assertGreater(len(html), 300_000)
        self.assertIn('d3js.org', html)
        self.assertNotIn('ALL-01.', html)                     # no log file names in the shared file
        self.assertIn('<title>Eleven Dashboard</title>', html)
        self.assertIn('<link rel="icon" href="data:image/svg+xml,', html)
        self.assertNotIn('Eleven vs AI', html)

    def test_last_day_only_when_it_adds(self):
        """The Overview names the last day played only when it held more matches than the last session."""
        rows = {r['key']: r for r in self.rows('summary')}
        day, last = rows['lastDay'], rows['last']
        self.assertEqual(day['moreThanLast'], int(day['matches'] > last['matches']))


class Translations(unittest.TestCase):
    def test_complete(self):
        self.assertEqual(i18n.check(out=io.StringIO()), 0)

    def test_online_wording(self):
        """Every sentence has a wording for matches against people that names no AI and no level (voice.py)."""
        out = io.StringIO()
        self.assertEqual(voice.check(out=out), 0, out.getvalue())
        self.assertEqual(voice.pair("Points won on the AI's serve", 'AI 發球時的得分率'), ("Points won on your opponent's serve", '對手發球時的得分率'))
        self.assertEqual(voice.en('At level {0} over {1} ({2}, {3} points): {4} of points.'), 'Online over {1} ({2}, {3} points): {4} of points.')
        page = __import__('elevendash.page', fromlist=['fill']).fill()
        self.assertIn('data-v="people"', page)
        self.assertNotIn('{{', page)


class Resilience(unittest.TestCase):
    def test_online_side_fails_alone(self):
        """If the online pass breaks, the AI side is still built and no half-made online data is left behind."""
        from elevendash import workspace
        with tempfile.TemporaryDirectory() as tmp:
            ws = workspace.init(os.path.join(tmp, 'w'))
            sample.write_logs(ws.logs)
            real = i18n.set_voice

            def broken(who):
                real(who)
                if who == 'people':
                    raise RuntimeError('made to fail')
            i18n.set_voice = broken
            said = []
            try:
                cli.do_build(ws, say=said.append)
            finally:
                i18n.set_voice = real
            names = os.listdir(ws.build)
            self.assertIn('summary.json', names)
            self.assertFalse([n for n in names if n.endswith('_h.json')], names)
            self.assertTrue(any('online side could not be built' in line for line in said), said)
            with open(os.path.join(ws.build, 'matches.json'), encoding='utf-8') as f:
                self.assertTrue(any(r['vs'] != 'AI' for r in json.load(f)['rows']))


if __name__ == '__main__':
    unittest.main()
