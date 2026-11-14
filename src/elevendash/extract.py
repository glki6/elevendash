"""Extract matches -> games -> points -> hits/bounces from an Eleven Table Tennis VR log (ALL-*.log).

Calibrated against 11hero.com (see CALIBRATION.md): hit speed/spin/top-back component and shot types match exactly.
Usage: python -m elevendash.extract <log> [<log> ...] > matches.json   (or import extract_log)
"""
import json, math, re, sys

# [MM/DD/YYYY HH:MM:SS][ms,frame]: wall clock to the second, then milliseconds since the app started
TS = re.compile(r'^\[(\d+)/(\d+)/(\d+) (\d+:\d+:\d+)\](?:\[(\d+),)?')
VEC = re.compile(r'\(([^)]*)\)')
POST = re.compile(r'postCollisionState:\{pos:\(([^)]*)\),vel:\(([^)]*)\),rRate:\(([^)]*)\)')
# Online, the opponent's game sends each of their tosses and hits: where the ball was and its state just after
# (the same post-hit velocity and rotation rate a local hit logs). These are the only record of the opponent's shots.
REMOTE = re.compile(r'\[MPMatch\]Received ball (hit|toss) from opponent: pos:\(([^)]*)\) vel:\(([^)]*)\) rrate:\(([^)]*)\)')
ATTACK = ('Drive', 'SlowLoop', 'FastLoop')


def v3(s):
    return tuple(float(x) for x in s.split(','))


def top_back(vel, rrate):
    """Top(+)/back(-) spin component in rev/s: spin projected on the horizontal axis perpendicular to travel."""
    vx, _, vz = vel
    n = math.hypot(vx, vz) or 1e-9
    wx, _, wz = (r / 360 for r in rrate)
    return wx * (vz / n) + wz * (-vx / n)


def shot_type(h):
    if h['top'] < 0:
        return 'Push' if abs(h['pos'][2]) < 1.35 else 'Chop'
    if h['spin'] >= 50:
        return 'FastLoop' if h['speed'] >= 10.5 else 'SlowLoop'
    return 'Drive'


def finish_point(pt):
    """Derive serve/success/winning/open-up flags for one finished point (11hero definitions)."""
    ev = pt.pop('_ev')
    hits = []
    for i, e in enumerate(ev):
        if e['k'] != 'hit':
            continue
        h = {k: e[k] for k in ('side', 'pos', 'speed', 'spin', 'top', 'gt')}
        h['n'] = len(hits) + 1
        h['serve'] = h['n'] == 1
        # bounces after this hit, up to the next hit
        nb = []
        for f in ev[i + 1:]:
            if f['k'] == 'hit':
                break
            if f['k'] == 'table':
                nb.append(f['side'])
        opp = 'B' if h['side'] == 'A' else 'A'
        if h['serve']:
            h['ok'] = len(nb) >= 2 and nb[0] == h['side'] and nb[1] == opp
        else:
            h['ok'] = bool(nb) and nb[0] == opp
        h['shot'] = 'Serve' if h['serve'] else shot_type(h)
        hits.append(h)
    for a, b in zip(hits, hits[1:]):
        b['open'] = (not b['serve']) and b['shot'] in ATTACK and a['top'] < 0
    for h in hits:
        h.setdefault('open', False)
        h['win'] = False
    mine = [h for h in hits if h['side'] == pt['winner']]
    if mine and mine[-1]['ok']:
        mine[-1]['win'] = True          # the winner's last (successful) shot won the point
    pt['hits'] = hits
    pt['bounces'] = [{'side': e['side'], 'pos': e['pos'], 'by': e['by']} for e in ev if e['k'] == 'table']
    toss = next((e for e in ev if e['k'] == 'toss'), None)
    pt['toss'] = toss and {'side': toss['side'], 'pos': toss['pos'], 'speed': toss['speed']}
    pt['server'] = hits[0]['side'] if hits else (toss['side'] if toss else None)
    # every ball contact in order, for the point replay: toss, hits, table, net, and anything else it touched
    # (vel, rr: the ball's velocity and rotation rate just after a hit; pre, prr: as it arrived at any contact)
    pt['track'] = [{k: e[k] for k in ('k', 'side', 'pos', 'gt', 'by', 'vel', 'rr', 'pre', 'prr') if e.get(k) is not None}
                   for e in ev if e.get('pos')]
    pts = [e['pos'] for e in ev if e.get('pos')]
    pt['dist'] = sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))
    # when the point ran, in seconds since the app started: the clock a session recording is lined up against
    ats = [e['at'] for e in ev if e.get('at') is not None]
    pt['t0'], pt['t1'] = (min(ats), max(ats)) if ats else (None, None)
    return pt


def extract_log(path):
    matches, m, game, pt = [], None, None, None
    user_side, ai, diff, strict = 'A', False, None, None
    hand = None              # 'right' or 'left': the player's paddle hand, from the paddle settings the game loads
    pending_post = None      # post-hit state from the latest Dynamic Collision block
    block = None             # MyCollision block being read
    score = {'A': 0, 'B': 0}
    date = None
    ms = None                # milliseconds since app start, from the latest line that carried them

    def close_block():
        nonlocal block, pending_post
        b, block = block, None
        if not b or pt is None or 'type' not in b:
            return
        typ = b['type']
        side = typ[-1] if typ[-1] in 'AB' else None
        # pre, prr: the ball's velocity and rotation rate as it arrived at this contact
        e = {'gt': b.get('gameTime'), 'pos': b.get('position'), 'pre': b.get('velocity'), 'prr': b.get('rotationRate')}
        # gameTime is the app clock in seconds, except on a toss, where it is 0: then the line's own clock stands in
        e['at'] = e['gt'] if e['gt'] else (b['ms'] / 1000 if b.get('ms') is not None else None)
        if typ.startswith('Toss'):
            e.update(k='toss', side=side, speed=math.hypot(*b.get('velocity', (0, 0, 0))))
        elif typ.startswith('Hit'):
            vel = rr = None
            if isinstance(pending_post, tuple) and b.get('position') and math.dist(pending_post[0], b['position']) < 1e-4:
                vel, rr = pending_post[1], pending_post[2]
            if vel is None:          # no matching post-hit state: fall back to the pre-hit values
                vel, rr = b.get('velocity', (0, 0, 0)), b.get('rotationRate', (0, 0, 0))
            e.update(k='hit', side=side, speed=math.hypot(*vel), spin=math.hypot(*rr) / 360, top=top_back(vel, rr), vel=vel, rr=rr)
            pending_post = None
        elif typ.startswith('Table'):
            e.update(k='table', side=side, by=b.get('relativeSender', '')[-1:])
        elif typ == 'Net':
            e.update(k='net')
        else:
            e.update(k='other')
        pt['_ev'].append(e)

    def remote(kind, pos, vel, rr):
        """The opponent's toss or hit in an online match, from the message their game sent."""
        if not any(vel):         # between points the game sends a ball at rest out of play, at (0,-10,0)
            return
        ev = pt['_ev']
        if any(x.get('remote') and x['pos'] == pos for x in ev[-4:]):
            return               # the same message logged twice
        if kind == 'hit' and not any(x['k'] == 'toss' for x in ev):
            return               # before the toss the ball is out of play: a serve sent after the point was given,
                                 # or the opponent playing with the ball between points
        at = ms / 1000 if ms is not None else None
        # the time it arrived: the bounces that follow are timed by the local game from then on
        e = {'gt': at, 'at': at, 'pos': pos, 'side': 'B' if user_side == 'A' else 'A', 'remote': True}
        if kind == 'toss':
            e.update(k='toss', speed=math.hypot(*vel))
        else:
            e.update(k='hit', speed=math.hypot(*vel), spin=math.hypot(*rr) / 360, top=top_back(vel, rr), vel=vel, rr=rr)
        ev.append(e)

    with open(path, encoding='utf-8', errors='replace') as f:
        lines = f.readlines()
    for line in lines:
        if block is not None:
            if line.startswith('\t'):
                k, _, val = line.strip().partition(':')
                if k in ('position', 'velocity', 'rotationRate'):
                    mm = VEC.search(val)
                    block[k] = v3(mm.group(1)) if mm else None
                elif k == 'gameTime':
                    block[k] = float(val)
                elif k == 'pongGameCollisionType':
                    block['type'] = val.strip()
                elif k == 'relativeSender':
                    block[k] = val.strip()
                continue
            close_block()
        t = TS.match(line)
        if t:
            date = f'{t[3]}-{t[1]}-{t[2]}'
            clock = t[4]
            if t[5]:
                ms = int(t[5])
        if 'MyCollision:' in line:
            block = {'ms': ms}
            continue
        if 'from opponent: pos:' in line:
            mm = REMOTE.search(line)
            if mm and m is not None and pt is not None:
                remote(mm[1], v3(mm[2]), v3(mm[3]), v3(mm[4]))
            continue
        if 'Dynamic Collision...' in line:
            pending_post = 'wait'
            continue
        if pending_post == 'wait' and 'postCollisionState:' in line:
            mm = POST.search(line)
            pending_post = (v3(mm[1]), v3(mm[2]), v3(mm[3])) if mm else None
            continue
        if '"paddleHand":"' in line:
            hand = 'left' if line.split('"paddleHand":"')[1][:1].upper() == 'L' else 'right'
        elif 'Difficulty:' in line and '[AI]' in line:
            diff = int(line.split('Difficulty:')[1].split()[0])
        elif 'against AI' in line:
            ai = True
        elif 'MoveUserIntoPosition(TableSide' in line:
            user_side = line.split('MoveUserIntoPosition(TableSide')[1][0]
        elif 'Setting StrictServingRules from' in line:
            strict = line.strip().endswith('True')
        elif '[matchRunning] from [False] to [True]' in line:
            m = {'log': path.replace('\\', '/').split('/')[-1], 'date': date, 'start': clock, 'ai': ai,
                 'difficulty': diff if ai else None, 'strict': strict, 'you': user_side, 'hand': hand, 'games': [],
                 't0': ms / 1000 if ms is not None else None}
            matches.append(m)
            ai = False
            game = None
        elif 'adding a round' in line and m is not None:
            game = {'points': []}
            m['games'].append(game)
            score = {'A': 0, 'B': 0}
            pt = {'_ev': []}
        elif m is not None and pt is not None and ('Local Response:Let' in line or 'Local Response:Reset' in line):
            pt = {'_ev': []}          # let/reset: point replayed
        elif m is not None and game is not None and 'Local Response:' in line:
            resp = line.split('Local Response:')[1].strip()
            if resp != 'Continue' and pt is not None:
                pt['reason'] = resp
        elif m is not None and game is not None and 'updating gameScore side' in line:
            parts = line.split()
            side, old, new = parts[-5], int(parts[-3]), int(parts[-1])
            if new == old + 1 and pt is not None:
                pt['score'] = [score['A'], score['B']]
                pt['winner'] = side
                score[side] = new
                game['points'].append(finish_point(pt))
                pt = {'_ev': []}
        elif '[matchRunning] from [True] to [False]' in line and m is not None:
            m['end'] = clock
            m['t1'] = ms / 1000 if ms is not None else None
            m['games'] = [g for g in m['games'] if g['points']]
            for g in m['games']:
                g['score'] = [sum(p['winner'] == 'A' for p in g['points']), sum(p['winner'] == 'B' for p in g['points'])]
            m = game = pt = None
    return matches


if __name__ == '__main__':
    out = []
    for p in sys.argv[1:]:
        out.extend(extract_log(p))
    json.dump(out, sys.stdout)
