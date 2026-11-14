"""Made-up game logs, for trying elevendash without a Quest and for its tests.

A seeded random player plays a few sessions against the AI at levels 75 and 100. The files use the lines elevendash
reads from real Eleven Table Tennis logs (match start and end, AI level, scores, and every ball contact with its
position, velocity and spin), and nothing else: no account data at all. The first line of each file says it was
generated.
"""
import datetime as dt
import math
import os
import random

# (AI level, matches) for each session, one day apart. Two levels, so the level picker has something to pick.
SESSIONS = ((75, 5), (75, 6), (100, 7), (100, 8))
FIRST = dt.datetime(2026, 1, 5, 18, 0, 0)
NET_Y, TABLE_Y = 0.85, 0.78


def other(side):
    return 'B' if side == 'A' else 'A'


def end(side):
    """Which end of the table a side plays from: A at z < 0, B at z > 0."""
    return -1.0 if side == 'A' else 1.0


def vec(v):
    return '(' + ', '.join(f'{x:.4f}' for x in v) + ')'


class Log:
    def __init__(self, start):
        self.start = start          # the wall clock at app second 0
        self.lines = []
        self.prev = None            # where and when the ball last touched something

    def say(self, t, text):
        w = self.start + dt.timedelta(seconds=t)
        self.lines.append(f'[{w:%m/%d/%Y %H:%M:%S}][{int(t * 1000)},{int(t * 72)}] {text}')

    def contact(self, t, kind, pos, vel=(0.0, 0.0, 0.0), rr=(0.0, 0.0, 0.0), sender='', game_time=None):
        # A contact's own block gives the ball's velocity as it arrived, as the game logs it: here, what a free flight
        # under gravity from the contact before arrives with. (The 3D replay curves its flights from these.)
        pre = vel
        if not kind.startswith('Toss') and self.prev and t > self.prev[1]:
            (x0, y0, z0), T = self.prev[0], t - self.prev[1]
            pre = ((pos[0] - x0) / T, (pos[1] - y0) / T - 4.905 * T, (pos[2] - z0) / T)
        self.prev = (pos, t)
        if kind.startswith('Hit'):  # the physics block with the ball's state after the hit comes first, as in the game
            self.say(t, '[Physics-BallCollisions]Dynamic Collision...')
            self.say(t, f'[Physics-BallCollisions]postCollisionState:{{pos:{vec(pos)},vel:{vec(vel)},rRate:{vec(rr)}}}')
        self.say(t, '[Physics-BallCollisions]MyCollision:')
        self.lines += [f'\tpongGameCollisionType: {kind}', f'\tposition: {vec(pos)}', f'\tvelocity: {vec(pre)}',
                       f'\trotationRate: {vec(rr)}', f'\tgameTime: {t if game_time is None else game_time:.4f}']
        if sender:
            self.lines.append(f'\trelativeSender: {sender}')


def shot(rng, pos, target, speed, top, side_spin=0.0):
    """Velocity and rotation rate (degrees a second) for a hit from pos towards target with `top` r/s of top (+) or
    back (-) spin, as the log records them."""
    dx, dz = target[0] - pos[0], target[2] - pos[2]
    n = math.hypot(dx, dz)
    flat = speed * 0.97
    vel = (flat * dx / n, rng.uniform(0.3, 1.2), flat * dz / n)
    ax, az = vel[2] / math.hypot(vel[0], vel[2]), -vel[0] / math.hypot(vel[0], vel[2])
    return vel, (ax * top * 360, side_spin * 360, az * top * 360)


def play_point(log, rng, t, server, miss):
    """One point from app second t. miss[side] is how often that side misses a shot. Returns (winner, time it ended)."""
    s = end(server)
    x = rng.uniform(-0.5, 0.5)
    log.contact(t, f'Toss{server}', (x, 0.95, s * 1.55), (0.0, 2.6, 0.0), game_time=0)
    t += rng.uniform(0.55, 0.75)
    pos = (x, rng.uniform(0.85, 1.0), s * rng.uniform(1.45, 1.6))
    land = (rng.uniform(-0.6, 0.6), TABLE_Y, -s * rng.uniform(0.4, 1.2))
    top = rng.choice((-1, -1, 1)) * rng.uniform(15, 45)
    vel, rr = shot(rng, pos, land, rng.uniform(5.0, 8.0), top, rng.uniform(-20, 20))
    log.contact(t, f'Hit{server}', pos, vel, rr, f'Paddle{server}')
    if rng.random() < 0.03:                       # a serve into the net
        log.contact(t + 0.3, 'Net', (x, NET_Y, 0.0), sender=f'Ball{server}')
        log.contact(t + 0.8, 'Floor', (x, 0.0, s * 0.6), sender=f'Ball{server}')
        return other(server), t + 0.8
    log.contact(t + 0.22, f'Table{server}', (x * 0.8, TABLE_Y, s * rng.uniform(0.5, 0.9)), sender=f'Ball{server}')
    t += 0.5
    log.contact(t, f'Table{other(server)}', land, sender=f'Ball{server}')
    hitter, incoming, n = other(server), top, 1
    while True:
        h = end(hitter)
        t += rng.uniform(0.25, 0.35)
        push = incoming < 0 and rng.random() < 0.5
        pos = (max(-0.8, min(0.8, land[0] * 1.2)), rng.uniform(0.82, 1.05), h * (rng.uniform(1.15, 1.3) if push else rng.uniform(1.45, 1.85)))
        if push:
            top, speed = -rng.uniform(20, 45), rng.uniform(4.0, 6.0)
        elif rng.random() < 0.45:
            top, speed = rng.uniform(50, 90), rng.uniform(7.5, 14.0)
        else:
            top, speed = rng.uniform(5, 45), rng.uniform(6.5, 10.0)
        land = (rng.uniform(-0.65, 0.65), TABLE_Y, -h * rng.uniform(0.3, 1.25))
        vel, rr = shot(rng, pos, land, speed, top, rng.uniform(-15, 15))
        log.contact(t, f'Hit{hitter}', pos, vel, rr, f'Paddle{hitter}')
        risk = miss[hitter] + (0.06 if speed >= 10.5 else 0) - (0.05 if push else 0) + (0.03 if n == 1 else 0)
        flight = math.dist((pos[0], pos[2]), (land[0], land[2])) / (speed * 0.9)
        if rng.random() < risk:                   # into the net or off the end
            if rng.random() < 0.5:
                log.contact(t + flight * 0.5, 'Net', (pos[0], NET_Y, 0.0), sender=f'Ball{hitter}')
                log.contact(t + flight + 0.3, 'Floor', (pos[0], 0.0, h * 0.5), sender=f'Ball{hitter}')
            else:
                log.contact(t + flight + 0.15, 'Floor', (land[0], 0.0, -h * rng.uniform(2.0, 2.7)), sender=f'Ball{hitter}')
            return other(hitter), t + flight + 0.3
        t += flight
        log.contact(t, f'Table{other(hitter)}', land, sender=f'Ball{hitter}')
        if rng.random() < (0.10 if speed >= 10.5 else 0.04):     # out of the other side's reach: a winner
            log.contact(t + 0.45, 'Floor', (land[0] * 1.5, 0.0, -h * 2.6), sender=f'Ball{hitter}')
            return hitter, t + 0.45
        hitter, incoming, n = other(hitter), top, n + 1


def play_game(log, rng, t, first, miss):
    score = {'A': 0, 'B': 0}
    log.say(t, '[Match] adding a round')
    n = 0
    while True:
        deuce = score['A'] >= 10 and score['B'] >= 10
        server = first if (n % 2 == 0 if deuce else (n // 2) % 2 == 0) else other(first)
        t += rng.uniform(3.0, 6.0)
        winner, t = play_point(log, rng, t, server, miss)
        log.say(t + 0.2, '[Match] Local Response:Continue')
        log.say(t + 0.3, f'[Score] updating gameScore side {winner} from {score[winner]} to {score[winner] + 1}')
        score[winner] += 1
        n += 1
        a, b = score['A'], score['B']
        if max(a, b) >= 11 and abs(a - b) >= 2:
            return ('A' if a > b else 'B'), t + 1


def play_match(log, rng, t, level, miss):
    log.say(t, f'[AI] Difficulty: {level} chosen for the next match')
    log.say(t, '[Match] Starting a single player match against AI')
    log.say(t, '[Match] MoveUserIntoPosition(TableSideA)')
    log.say(t, '[Settings] Setting StrictServingRules from False to True')
    log.say(t + 2, '[GameState] [matchRunning] from [False] to [True]')
    t += 2
    won = {'A': 0, 'B': 0}
    g = 0
    while max(won.values()) < 2:
        winner, t = play_game(log, rng, t, 'A' if g % 2 == 0 else 'B', miss)
        won[winner] += 1
        g += 1
        t += rng.uniform(15, 30)
    log.say(t, '[GameState] [matchRunning] from [True] to [False]')
    return t


def log_name(when):
    hour = when.hour % 12 or 12
    return f'ALL-{when:%m.%d.%Y}.{hour}.{when:%M.%S}.{"AM" if when.hour < 12 else "PM"}.log'


def write_logs(logs_dir, seed=8):
    """Write one generated log per session into logs_dir. Returns the file names."""
    rng = random.Random(seed)
    os.makedirs(logs_dir, exist_ok=True)
    names = []
    for i, (level, count) in enumerate(SESSIONS):
        start = FIRST + dt.timedelta(days=i, minutes=rng.randint(0, 50))
        log = Log(start)
        log.say(0, 'elevendash sample log: generated by elevendash (src/elevendash/sample.py), not recorded from a game. '
                   'It holds no account data.')
        log.say(0.5, '[Settings] Paddle settings loaded: {"paddleHand":"Right","gripAngle":50}')
        # the made-up player gets a little steadier with every session; the AI at 100 misses less than at 75
        miss = {'A': 0.25 - 0.015 * i, 'B': 0.27 if level == 75 else 0.21}
        t = 40.0
        for _ in range(count):
            t = play_match(log, rng, t, level, miss) + rng.uniform(40, 80)
        log.say(t, '[App] Quit')
        name = log_name(start)
        with open(os.path.join(logs_dir, name), 'w', encoding='utf-8', newline='\n') as f:
            f.write('\n'.join(log.lines) + '\n')
        names.append(name)
    return names
