"""Reading an online match: the opponent's tosses and hits come from the messages their game sent."""
import math
import os
import sys
import tempfile
import unittest
import datetime as dt

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))
from elevendash import extract, sample  # noqa: E402

TY = sample.TABLE_Y
SERVE = ((0.25, 1.0, -1.8), (-0.5, -0.6, 4.5), (9970.0, 1475.0, 23.0))     # the opponent's serve: pos, vel, rrate


def remote(log, t, kind, pos, vel, rr=(0.0, 0.0, 0.0)):
    log.say(t, f'[MPMatch]Received ball {kind} from opponent: pos:{sample.vec(pos)} vel:{sample.vec(vel)} rrate:{sample.vec(rr)}')


def online_log(path):
    """Two points of an online match, you on side B: the opponent serves the first and you win it; you serve the
    second and lose it. Around them: what the game also sends that is not a shot."""
    log = sample.Log(dt.datetime(2026, 2, 1, 20, 0, 0))
    log.say(1, '[Match] MoveUserIntoPosition(TableSideB)')
    log.say(2, '[GameState] [matchRunning] from [False] to [True]')
    log.say(2, '[Match] adding a round')
    remote(log, 2.1, 'hit', (0, -10, 0), (0, 0, 0))                          # a ball at rest out of play
    remote(log, 3.0, 'hit', (0.2, 0.8, -0.76), (0.1, 0.4, 0.2), (90, 0, 0))     # playing with the ball before the toss
    remote(log, 4.0, 'toss', (0.3, 1.1, -1.6), (0.0, 2.5, 0.0))
    remote(log, 4.6, 'hit', *SERVE)
    remote(log, 4.6, 'hit', *SERVE)                                             # logged twice
    log.contact(4.8, 'TableA', (0.2, TY, -0.9), sender='BallA')
    log.contact(5.2, 'TableB', (0.1, TY, 0.8), sender='BallA')
    log.contact(5.5, 'HitB', (0.1, 1.0, 1.6), (0.3, 0.8, -6.0), (-3000.0, 0.0, 200.0), 'PaddleB')
    log.contact(6.0, 'TableA', (0.2, TY, -0.7), sender='BallB')
    log.say(7.0, '[Score] updating gameScore side B from 0 to 1')
    remote(log, 7.2, 'hit', (0.4, 1.0, -1.7), (0.2, 0.5, 5.0), (100, 0, 0))      # a shot sent after the point was given
    log.contact(9.0, 'TossB', (-0.2, 1.4, 1.6), (0.0, 2.6, 0.0), game_time=0)
    log.contact(9.6, 'HitB', (-0.2, 1.0, 1.65), (0.1, -0.5, -5.0), (1500.0, 0.0, 0.0), 'PaddleB')
    log.contact(9.8, 'TableB', (-0.2, TY, 0.9), sender='BallB')
    log.contact(10.2, 'TableA', (-0.2, TY, -0.9), sender='BallB')
    remote(log, 10.5, 'hit', (-0.2, 0.96, -1.4), (0.3, 2.0, 4.4), (2359.0, -729.0, -414.0))
    log.contact(10.9, 'TableB', (-0.1, TY, 0.5), sender='BallA')
    log.say(11.5, '[Score] updating gameScore side A from 0 to 1')
    log.say(12, '[GameState] [matchRunning] from [True] to [False]')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(log.lines) + '\n')


class Online(unittest.TestCase):
    def test_opponent_shots(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'ALL-02.01.2026.8.00.00.PM.log')
            online_log(path)
            (m,) = extract.extract_log(path)
        self.assertFalse(m['ai'])
        self.assertEqual(m['you'], 'B')
        p1, p2 = m['games'][0]['points']

        self.assertEqual([h['side'] for h in p1['hits']], ['A', 'B'])
        self.assertEqual((p1['server'], p1['toss']['side'], p1['winner']), ('A', 'A', 'B'))
        sv = p1['hits'][0]
        self.assertTrue(sv['serve'] and sv['ok'])
        self.assertAlmostEqual(sv['speed'], math.hypot(*SERVE[1]), places=3)
        self.assertAlmostEqual(sv['spin'], math.hypot(*SERVE[2]) / 360, places=3)
        self.assertAlmostEqual(sv['top'], extract.top_back(SERVE[1], SERVE[2]), places=3)
        self.assertTrue(p1['hits'][1]['ok'] and p1['hits'][1]['win'])

        self.assertEqual([h['side'] for h in p2['hits']], ['B', 'A'])
        self.assertEqual((p2['server'], p2['winner']), ('B', 'A'))
        self.assertTrue(p2['hits'][1]['ok'] and p2['hits'][1]['win'])
        self.assertEqual(p2['hits'][1]['shot'], 'Drive')


if __name__ == '__main__':
    unittest.main()
