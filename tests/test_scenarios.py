"""Logs shaped like the awkward cases of real play: a match stopped part way, a session past midnight, the same log
copied twice under two names. Each is generated with sample.py, then built the way the app builds."""
import contextlib
import datetime as dt
import io
import json
import os
import random
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))
from elevendash import cli, sample  # noqa: E402

MISS = {'A': 0.2, 'B': 0.25}


def session(start, full, stopped):
    """A log of `full` matches against the AI at 75, then one stopped after a game (a quit)."""
    rng = random.Random(3)
    log = sample.Log(start)
    log.say(0, 'elevendash test log: generated, not recorded from a game.')
    log.say(0.5, '[Settings] Paddle settings loaded: {"paddleHand":"Right","gripAngle":50}')
    t = 40.0
    for _ in range(full):
        t = sample.play_match(log, rng, t, 75, MISS) + 30
    if stopped:
        log.say(t, '[AI] Difficulty: 75 chosen for the next match')
        log.say(t, '[Match] Starting a single player match against AI')
        log.say(t, '[Match] MoveUserIntoPosition(TableSideA)')
        log.say(t + 2, '[GameState] [matchRunning] from [False] to [True]')
        first, t = sample.play_game(log, rng, t + 2, 'A', MISS)
        log.say(t, '[Match] adding a round')             # a second game, given up after three points
        score = {'A': 0, 'B': 0}
        for _ in range(3):
            winner, t = sample.play_point(log, rng, t + 4, 'B', MISS)
            log.say(t + 0.3, f'[Score] updating gameScore side {winner} from {score[winner]} to {score[winner] + 1}')
            score[winner] += 1
    log.say(t + 5, '[App] Quit')
    return '\n'.join(log.lines) + '\n', (first if stopped else None)


class Scenarios(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        ws = cls.ws = cls.tmp.name
        logs = os.path.join(ws, 'logs')
        os.makedirs(logs)
        with open(os.path.join(ws, 'elevendash.json'), 'w') as f:
            f.write('{}')
        late = dt.datetime(2026, 3, 1, 23, 52, 0)          # three matches from 23:52: the session runs past midnight
        text, cls.first = session(late, 3, stopped=True)
        for when in (late, late + dt.timedelta(seconds=1)):   # the same log twice, under two names the game could use
            with open(os.path.join(logs, sample.log_name(when)), 'w', encoding='utf-8', newline='\n') as f:
                f.write(text)
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            cls.code = cli.main(['--dir', ws, 'build'])
        cls.printed = out.getvalue()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def rows(self, name):
        with open(os.path.join(self.ws, 'build', name + '.json'), encoding='utf-8') as f:
            return json.load(f)['rows']

    def test_built(self):
        self.assertEqual(self.code, 0, self.printed)
        self.assertNotIn('warning', self.printed)

    def test_copies_counted_once(self):
        self.assertEqual(len(self.rows('matches')), 3)          # three played out; the stopped one is left out

    def test_stopped_match_left_out(self):
        ms = self.rows('matches')
        self.assertTrue(all('stopped' not in r and r['gamesWon'] + r['gamesLost'] in (2, 3) for r in ms))
        self.assertTrue(all(max(r['gamesWon'], r['gamesLost']) == 2 for r in ms))
        allrow = [r for r in self.rows('summary') if r['key'] == 'all'][0]
        self.assertEqual(allrow['stopped'], 1)
        self.assertGreaterEqual(allrow['stoppedPoints'], 11 + 3)    # a game played out, then three points
        self.assertEqual(allrow['matches'], 3)
        self.assertEqual(allrow['points'], sum(r['points'] for r in ms))
        self.assertIn('1 match stopped before the end (a restart or a quit) left out', self.printed)

    def test_one_session_past_midnight(self):
        ms = self.rows('matches')
        self.assertEqual(len({r['date'] for r in ms}), 2, [(r['date'], r['start']) for r in ms])
        sessions = self.rows('sessions')
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]['matches'], 3)

    def test_endings_agree_with_the_score(self):
        for p in self.rows('points'):
            self.assertIn(p['ending'], ('your winner', 'AI error', 'other') if p['won'] else
                          ('your error', 'AI winner', 'other'))


if __name__ == '__main__':
    unittest.main()
