"""Write the dashboard's data files ({rows, meta} JSON, one per dataset) from Eleven Table Tennis game logs.
Usage: python -m elevendash.builddata <logs-dir> <out-dir> [<videos.json> [auto|right|left]]   (elevendash build runs it)
Text the page shows is written in English and Traditional Chinese (i18n.T): a field, and the same field with _zh.

Coordinates are "your view": your half of the table is z < 0, the AI's half z > 0, +x is your right
(checked against video of 2026-11-03: a serve logged at x = +0.67 came to your right).
"""
import glob, json, math, os, sys
from collections import Counter, defaultdict
from .extract import extract_log
from .i18n import Bi, T, W, join, put
from .i18n import listing as bilist
from .metrics import player_metrics, match_metrics, metric_sums

logs_dir, out_dir = sys.argv[1], sys.argv[2]
videos_path = sys.argv[3] if len(sys.argv) > 3 else None
hand_setting = sys.argv[4] if len(sys.argv) > 4 else 'auto'     # 'right', 'left', or 'auto' (from the logs)
os.makedirs(out_dir, exist_ok=True)
r1 = lambda x: None if x is None else round(x, 1)
pc = lambda a, b: round(100 * a / b, 1) if b else None
SPIN_T = 20
METRICS = ['serveSpeed', 'serveTop', 'serveBack', 'rallySpeed', 'rallyTop', 'rallyBack', 'serveScore', 'returnScore',
           'thirdBallScore', 'wonAsServer', 'wonAsReturner', 'serveSuccess', 'returnSuccess', 'openUpAttempt',
           'openUpSuccess', 'wonByOppServiceError', 'wonByServe', 'wonByReturn', 'wonByThird', 'wonByFourth', 'wonByLater']
SHOT_ORDER = ['Drive', 'SlowLoop', 'FastLoop', 'Push', 'Chop']
ENDS = {0: 'your winner', 1: 'AI error', 2: 'your error', 3: 'AI winner', 4: 'other'}

logs = sorted(glob.glob(os.path.join(logs_dir, 'ALL-*.log')))
input_meta = {'label': 'Input', 'value': f'{len(logs)} Eleven Table Tennis game logs (ALL-*.log) copied from the Quest'}


def write(name, rows):
    with open(os.path.join(out_dir, name + '.json'), 'w', encoding='utf-8') as f:
        json.dump({'rows': rows, 'meta': [input_meta]}, f, separators=(',', ':'))
    print(f'{name}: {len(rows)} rows, {os.path.getsize(os.path.join(out_dir, name + ".json")) // 1024} KB')


def spin_kind(h):
    return 'topspin' if h['top'] > SPIN_T else 'backspin' if h['top'] < -SPIN_T else 'little spin'


def ending(p, you):
    h = p['hits']
    if not h:
        return 4
    last = h[-1]
    if last['ok']:
        return 0 if last['side'] == you else 3
    return 2 if last['side'] == you else 1


SIDE_OF = lambda x: 'left' if x < -0.25 else 'right' if x > 0.25 else 'middle'     # x in your view: + is your right


def zone(x, z):
    """Zone of a bounce in your-view coordinates: (col by your left/right, depth from the net)."""
    col = SIDE_OF(x)
    d = abs(z)
    return col, ('short' if d < 0.5 else 'mid' if d < 1.0 else 'long')


# ---------------- extract ----------------
M = []   # (match dict, you, ai, points)
for path in logs:
    for m in extract_log(path):
        if m['games'] and m.get('end'):
            you = m['you']
            M.append((m, you, 'B' if you == 'A' else 'A', [p for g in m['games'] for p in g['points']]))
M.sort(key=lambda t: (t[0]['date'], t[0]['start']))

# Your paddle hand decides which side is your backhand. The game's paddle settings say which hand holds the paddle;
# the hand used in most AI matches counts, unless the workspace sets one (elevendash config hand=left).
if hand_setting in ('right', 'left'):
    HAND = hand_setting
else:
    HAND = (Counter(m['hand'] for m, *_ in M if m['ai'] and m.get('hand')).most_common(1) or [('right', 0)])[0][0]
BH, FH = ('left', 'right') if HAND == 'right' else ('right', 'left')     # your backhand and forehand side, as you face the AI

matches, serves, points, shot_mix, replay = [], [], [], [], []
level_items = defaultdict(list)          # level -> [(you, point)]
day_items = defaultdict(list)            # date -> [(match row, you, points)]
ai_items = {}                            # match key -> (you, points), AI matches only
day_n = Counter()


def mix_rows(scope, items):
    acc = defaultdict(lambda: [0, 0, 0.0, 0.0, 0])
    tot = Counter()
    for you, p in items:
        for h in p['hits']:
            if h['serve']:
                continue
            who = 'You' if h['side'] == you else 'AI'
            a = acc[(who, h['shot'])]
            a[0] += 1; a[1] += h['ok']; a[2] += h['speed']; a[3] += h['spin']; a[4] += h['win']
            tot[who] += 1
    rows = []
    for who in ('You', 'AI'):
        for s in SHOT_ORDER:
            a = acc.get((who, s))
            if not a:
                continue
            rows.append({'key': f'{scope}|{who}|{s}', 'scope': scope, 'who': who, 'shot': s, 'shots': a[0],
                         'share': pc(a[0], tot[who]), 'landed': pc(a[1], a[0]), 'speed': r1(a[2] / a[0]),
                         'spin': r1(a[3] / a[0]), 'winners': a[4]})
    return rows


SHOT_CODE = {'Serve': 'S', 'Drive': 'D', 'SlowLoop': 'L', 'FastLoop': 'F', 'Push': 'P', 'Chop': 'C'}


def replay_track(p, you, sx):
    """One point for the replay: every ball contact from the serve on, as 'kind,x,z,y,t' joined by ';'.
    Your view, in cm and 1/1000 s from the serve. kind: h bat, b table, n net, o anything else (nearly always the floor),
    x where the ball was heading when the log stops (estimated, not logged). A bat contact adds: y or a (you or the
    opponent), speed in 0.1 m/s, topspin (+) or backspin (-) in r/s, shot letter, and 1 if the shot landed.
    Then, for the 3D view, every logged contact ends with the ball's velocity as it arrived (x, y up, z; 0.1 m/s), and
    a bat contact with two more triples: its velocity just after the hit, and its spin just after it (the turning axis
    times r/s). A triple the log does not have is left empty (an online opponent's hit has no arriving velocity)."""
    tr = [e for e in (p.get('track') or []) if e['k'] != 'toss']
    first = next((i for i, e in enumerate(tr) if e['k'] == 'hit'), None)
    if first is None:
        return None
    tr = tr[first:]
    t0, last, hi, out, vel = tr[0]['gt'], 0, 0, [], None
    v3 = lambda v, k: [round(v[0] * sx * k), round(v[1] * k), round(v[2] * sx * k)] if v and any(v) else ['', '', '']
    for e in tr:
        t = max(last, round((e['gt'] - t0) * 1000))
        if t - last > 4000:         # a contact long after the rally (the ball rolling away): not part of the point
            break
        last = t
        x, y, z = e['pos']
        k = {'hit': 'h', 'table': 'b', 'net': 'n'}.get(e['k'], 'o')
        f = [k, round(x * sx * 100), round(z * sx * 100), round(y * 100), t]
        if k == 'h':
            h = p['hits'][hi]
            hi += 1
            f += ['y' if e['side'] == you else 'a', round(h['speed'] * 10), round(h['top']), SHOT_CODE[h['shot']], int(h['ok'])]
            vel = e.get('vel')
        f += v3(e.get('pre'), 10)
        if k == 'h':
            f += v3(vel, 10) + v3(e.get('rr'), 1 / 360)
        out.append(f)
        if k == 'o':
            break
    end = out[-1]
    if end[0] != 'o':               # the log stops in mid-air: carry the ball on the way it was going for 0.4 s
        if end[0] == 'h' and vel:
            dx, dz = vel[0] * sx * 0.4, vel[2] * sx * 0.4
        else:
            a = next((f for f in reversed(out[:-1]) if f[4] < end[4]), None)
            dt = (end[4] - a[4]) / 1000 if a else 0
            dx, dz = ((end[1] - a[1]) / 100 / dt * 0.4, (end[2] - a[2]) / 100 / dt * 0.4) if dt else (0, 0)
        out.append(['x', round(end[1] + dx * 100), round(end[2] + dz * 100), end[3], end[4] + 400])
    return ';'.join(','.join(map(str, f)) for f in out)


# ---------------- every shot of yours, for the shot explorer ----------------
# One record for each shot you hit, and one for each ball that beat you without a touch (shot X). It says what came
# at you (the opponent's shot, its speed and spin off their bat, where it bounced on your half), what you did with it
# and, for a miss, how it missed. In your view: your half is z below 0 and your shots travel to z above 0.
TABLE_W, TABLE_L, FAST = 0.7625, 1.37, 10       # half the table's width and length, in metres; a fast ball, in m/s
SPIN_C = {'topspin': 't', 'little spin': 'n', 'backspin': 'b'}
SHOT_FIELDS = ['n', 'role', 'shot', 'ok', 'miss', 'speed', 'top', 'win', 'cx', 'cy', 'inShot', 'inSpeed', 'inTop', 'bx', 'bz',
               'since', 'rise', 'cls']


def miss_kind(e, after, you, sx, serve):
    """How a shot of yours missed: n it never got over the net (into it, short of it, or down on your own half),
    l long past the end of the table, w wide of its side, o anything else, u the log does not say."""
    land = None
    for a in after:
        if a['k'] == 'hit':
            break
        if a['k'] == 'net' or (serve and a['k'] == 'table' and a['side'] == you):
            continue        # a serve bounces on your own half first
        land = a
        break
    if land is None or not land.get('pos'):
        return 'u'
    x, z = land['pos'][0] * sx, land['pos'][2] * sx
    if land['k'] == 'table':
        return 'n' if land['side'] == you else 'o'
    if z <= 0:
        return 'n'
    if z <= TABLE_L:
        return 'w'          # it came down beside the table
    x0, z0 = e['pos'][0] * sx, e['pos'][2] * sx
    across = x0 + (x - x0) * (TABLE_L - z0) / (z - z0) if z > z0 else x     # where its line passes the end of the table
    return 'l' if abs(across) <= TABLE_W else 'w'


def shot_records(p, you, sx):
    tr = [e for e in (p.get('track') or []) if e['k'] != 'toss']
    first = next((i for i, e in enumerate(tr) if e['k'] == 'hit'), None)
    hits = p['hits']
    if first is None or not hits:
        return []
    tr = tr[first:]
    at = [i for i, e in enumerate(tr) if e['k'] == 'hit']
    if len(at) != len(hits):
        return []
    out = []

    def incoming(r, j, contact):
        """Fill in what came at you: the opponent's shot j, and its first bounce on your half."""
        prev = hits[j]
        b = next((e for e in tr[at[j] + 1:at[j + 1] if j + 1 < len(at) else len(tr)] if e['k'] == 'table' and e['side'] == you), None)
        r.update(inShot=SHOT_CODE[prev['shot']], inSpeed=round(prev['speed'] * 10), inTop=round(prev['top']))
        if b:
            r.update(bx=round(b['pos'][0] * sx * 100), bz=round(b['pos'][2] * sx * 100))
        x = b['pos'][0] * sx if b else contact
        side = '-' if x is None else SIDE_OF(x)
        depth = (lambda d: 's' if d < 0.5 else 'h' if d < 1.0 else 'l')(abs(b['pos'][2])) if b else '-'
        r['cls'] = (SPIN_C[spin_kind(prev)] + {BH: 'B', FH: 'F', 'middle': 'M', '-': '-'}[side] + depth
                    + ('f' if prev['speed'] >= FAST else 's'))
        return b

    for i, h in enumerate(hits):
        if h['side'] != you:
            continue
        e = tr[at[i]]
        r = {'n': h['n'], 'role': 'S' if i == 0 else 'R' if i == 1 else 'A', 'shot': SHOT_CODE[h['shot']], 'ok': int(h['ok']),
             'miss': '' if h['ok'] else miss_kind(e, tr[at[i] + 1:], you, sx, i == 0), 'speed': round(h['speed'] * 10),
             'top': round(h['top']), 'win': int(bool(h.get('win'))), 'cx': round(e['pos'][0] * sx * 100), 'cy': round(e['pos'][1] * 100)}
        if i:
            b = incoming(r, i - 1, e['pos'][0] * sx)
            if b and e.get('gt') and b.get('gt'):
                r['since'] = max(0, round((e['gt'] - b['gt']) * 1000))      # from the bounce to your bat, in 1/1000 s
            if e.get('pre') and any(e['pre']):
                r['rise'] = 'r' if e['pre'][1] > 0 else 'f'                 # the ball was still rising, or already falling
        out.append(r)
    last = hits[-1]
    if last['side'] != you and last['ok'] and p['winner'] != you:           # it landed and you never touched it
        r = {'n': last['n'] + 1, 'role': 'R' if len(hits) == 1 else 'A', 'shot': 'X', 'ok': 0, 'miss': 'x', 'win': 0}
        incoming(r, len(hits) - 1, None)
        out.append(r)
    return out


shots, shot_items = [], {}              # the packed rows; match key -> its records, AI matches only


# ---------------- session recordings on YouTube ----------------
# videos.json in the workspace lists what was uploaded (always unlisted). A full recording carries, for each log it covers, the
# offset between the app's clock and the video, found from the sound of the ball (youtube/session_video.py). That
# places every point of that log in the video: video seconds = app seconds - lag + audio_start.
def read_videos(path):
    if not path or not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as f:
        return json.load(f)


VIDEOS = [v for v in read_videos(videos_path) if v.get('kind') in ('full', 'highlights', 'mistakes') and v.get('privacy') == 'unlisted']
video_matches = defaultdict(list)       # video id -> the match rows it shows


def video_time(log, at):
    """(video id, seconds into it) for a moment on a log's app clock, or None. The latest upload that covers it wins."""
    if at is None:
        return None
    for v in reversed(VIDEOS):
        for s in v.get('sync') or []:
            t = at - s['lag'] + v.get('audio_start', 0)
            if s['log'] == log and 0 <= t < v['duration']:
                return v['id'], t
    return None


for m, you, ai, pts in M:
    sx = 1 if you == 'A' else -1
    flip = lambda s: list(s) if you == 'A' else [s[1], s[0]]
    games = [flip(g['score']) for g in m['games']]
    gw = sum(a > b for a, b in games); gl = len(games) - gw
    mid = f"{m['date']} {m['start']}"
    day_n[m['date']] += 1
    pm_you, pm_ai, mm = player_metrics(pts, you), player_metrics(pts, ai), match_metrics(pts)
    won_n = sum(p['winner'] == you for p in pts)
    mshots = []
    row = {'key': mid, 'date': m['date'], 'start': m['start'], 'end': m['end'], 'dayMatch': day_n[m['date']],
           'vs': 'AI' if m['ai'] else 'Online', 'level': m['difficulty'], 'result': 'Won' if gw > gl else 'Lost',
           'gamesWon': gw, 'gamesLost': gl, 'score': ', '.join(f'{a}-{b}' for a, b in games),
           'points': len(pts), 'pointsWonN': won_n, 'pointRate': pc(won_n, len(pts)),
           'rallyLength': r1(mm['rallyLength']), 'ballDistance': r1(mm['ballDistance'])}
    for k in METRICS:
        row['you_' + k] = r1(pm_you[k]); row['ai_' + k] = r1(pm_ai[k])
    matches.append(row)
    for gi, g in enumerate(m['games']):
        for pi, p in enumerate(g['points']):
            sc = flip(p['score'])
            points.append({'key': f'{mid}|{gi + 1}|{pi + 1}', 'match': mid, 'game': gi + 1, 'point': pi + 1,
                           'youBefore': sc[0], 'aiBefore': sc[1], 'won': int(p['winner'] == you),
                           'served': 'You' if p['server'] == you else 'AI', 'hits': len(p['hits']),
                           'ending': ENDS[ending(p, you)]})
            vt = video_time(m['log'], p.get('t0'))
            if vt:      # a link starts 2 s before the toss; a match link 5 s before its first point on video
                points[-1].update(video=vt[0], videoT=max(0, int(vt[1] - 2)))
                if 'video' not in row:
                    row.update(video=vt[0], videoT=max(0, int(vt[1] - 5)))
                    video_matches[vt[0]].append(row)
            trk = replay_track(p, you, sx)
            if trk:
                replay.append({'key': f'{mid}|{gi + 1}|{pi + 1}', 'track': trk})
                mshots.extend(dict(r, at=f'{gi + 1}.{pi + 1}') for r in shot_records(p, you, sx))
            if p['hits']:
                sv = p['hits'][0]
                rb = next((b for b in p['bounces'] if b['side'] != sv['side']), None)
                serves.append({'key': f'{mid}|{gi + 1}|{pi + 1}', 'match': mid, 'server': 'You' if sv['side'] == you else 'AI',
                               'youWon': int(p['winner'] == you), 'landed': int(sv['ok']), 'speed': r1(sv['speed']),
                               'spin': r1(sv['spin']), 'top': r1(sv['top']), 'kind': spin_kind(sv),
                               'x': None if not rb else round(rb['pos'][0] * sx, 3),
                               'z': None if not rb else round(rb['pos'][2] * sx, 3)})
    shot_mix.extend(mix_rows(mid, [(you, p) for p in pts]))
    if mshots:      # one row a match: its shots as at,n,role,... (SHOT_FIELDS) joined by semicolons
        shots.append({'key': mid, 'n': len(mshots),
                      's': ';'.join(','.join(str(r.get(f, '')) for f in ['at'] + SHOT_FIELDS) for r in mshots)})
    if m['ai']:
        shot_items[mid] = mshots
        level_items[m['difficulty']].extend((you, p) for p in pts)
        day_items[m['date']].append((row, you, pts))
        ai_items[mid] = (you, pts)


# ---------------- aggregates ----------------
def tally(items):
    c = Counter()
    for you, p in items:
        won = p['winner'] == you
        c['pts'] += 1; c['won'] += won
        if p['server'] == you:
            c['sv'] += 1; c['svWon'] += won
        elif p['server']:
            c['rv'] += 1; c['rvWon'] += won
        for h in p['hits']:
            if h['side'] != you:
                continue
            if h['serve']:
                c['serves'] += 1; c['servesOk'] += h['ok']
            else:
                c['rally'] += 1; c['rallyOk'] += h['ok']; c['spd'] += h['speed']
                if h['n'] == 2:
                    c['ret'] += 1; c['retOk'] += h['ok']
        c['hits'] += len(p['hits'])
        if len(p['hits']) >= 3:
            c['p3'] += 1; c['p3Won'] += won
        if not won:
            c['lost'] += 1
            c['lostMiss'] += bool(p['hits']) and p['hits'][-1]['side'] == you and not p['hits'][-1]['ok']
    return c


def rates(c):
    return {'points': c['pts'], 'pointRate': pc(c['won'], c['pts']), 'servePointRate': pc(c['svWon'], c['sv']),
            'returnPointRate': pc(c['rvWon'], c['rv']), 'servesLanded': pc(c['servesOk'], c['serves']),
            'returnsLanded': pc(c['retOk'], c['ret']), 'rallyLanded': pc(c['rallyOk'], c['rally']),
            'reach3Rate': pc(c['p3Won'], c['p3']), 'missShare': pc(c['lostMiss'], c['lost']),
            'rallySpeed': r1(c['spd'] / c['rally']) if c['rally'] else None,
            'rallyLength': r1(c['hits'] / c['pts']) if c['pts'] else None}


def agg(items):
    return rates(tally(items))


# ---------------- per-match sums, for the numbers over any matches you pick ----------------
# One flat row per match (same order as matches): the tally behind rates(), how its points ended (e0-e4, ENDS order),
# and both players' metric sums (metrics.SUMS). The page adds up the rows of the matches picked.
TALLY = ['pts', 'won', 'sv', 'svWon', 'rv', 'rvWon', 'serves', 'servesOk', 'rally', 'rallyOk', 'spd', 'ret', 'retOk',
         'hits', 'p3', 'p3Won', 'lost', 'lostMiss']
match_sums = []
for (m, you, ai, pts), row in zip(M, matches):
    c = tally([(you, p) for p in pts])
    ends = Counter(ending(p, you) for p in pts)
    r = {'key': row['key'], **{f: round(c[f], 3) if isinstance(c[f], float) else int(c[f]) for f in TALLY},
         **{f'e{i}': ends[i] for i in ENDS}}
    for side, pre in ((you, 'you_'), (ai, 'ai_')):
        r.update({pre + k: v for k, v in metric_sums(pts, side).items()})
    match_sums.append(r)


def summary_row(key, label, ms):
    n, w = len(ms), sum(r['result'] == 'Won' for r in ms)
    g, gw = sum(r['gamesWon'] + r['gamesLost'] for r in ms), sum(r['gamesWon'] for r in ms)
    p, pw = sum(r['points'] for r in ms), sum(r['pointsWonN'] for r in ms)
    return {'key': key, 'label': label, 'from': ms[0]['date'], 'to': ms[-1]['date'], 'start': ms[0]['start'],
            'end': ms[-1]['end'], 'matches': n, 'wins': w, 'losses': n - w,
            'matchRate': pc(w, n), 'games': g, 'gamesWon': gw, 'gamesLost': g - gw, 'gameRate': pc(gw, g),
            'points': p, 'pointsWonN': pw, 'pointRate': pc(pw, p)}


def split_sessions(ms, gap_min=45):
    """A session is a run of AI matches with less than gap_min minutes between one ending and the next starting."""
    from datetime import datetime
    ts = lambda d, t: datetime.strptime(f'{d} {t}', '%Y-%m-%d %H:%M:%S')
    out = []
    for r in ms:
        if out and (ts(r['date'], r['start']) - ts(out[-1][-1]['date'], out[-1][-1]['end'])).total_seconds() < gap_min * 60:
            out[-1].append(r)
        else:
            out.append([r])
    return out


ai_ms = [r for r in matches if r['vs'] == 'AI']
last_day = ai_ms[-1]['date']
summary = [summary_row('all', 'All AI matches', ai_ms)]
for lvl in sorted({r['level'] for r in ai_ms}):
    summary.append(summary_row(f'L{lvl}', f'Level {lvl}', [r for r in ai_ms if r['level'] == lvl]))
sessions = split_sessions(ai_ms)
last_row = summary_row('last', 'Last session', sessions[-1])
if len(sessions) > 1:
    prev_row = summary_row('prev', 'Session before', sessions[-2])
    for f in ('matchRate', 'gameRate', 'pointRate'):  # change in percentage points against the session before
        last_row[f + 'Change'] = r1(last_row[f] - prev_row[f])
    summary.append(prev_row)
summary.append(last_row)
summary.append(summary_row('lastDay', 'Last day played', [r for r in ai_ms if r['date'] == last_day]))
online = [r for r in matches if r['vs'] == 'Online']
if online:
    summary.append(summary_row('online', 'Online', online))
write('summary', summary)

# ---------------- sessions: one row each, compared with your earlier average at the same AI level ----------------
# (rate field, count of successes, count of tries, label, higher is better)
MOVERS = [('pointRate', 'won', 'pts', W('Points won'), True),
          ('servePointRate', 'svWon', 'sv', W('Points won on your serve'), True),
          ('returnPointRate', 'rvWon', 'rv', W("Points won on the AI's serve"), True),
          ('servesLanded', 'servesOk', 'serves', W('Serves that landed'), True),
          ('returnsLanded', 'retOk', 'ret', W('Returns that landed'), True),
          ('rallyLanded', 'rallyOk', 'rally', W('Rally shots that landed'), True),
          ('reach3Rate', 'p3Won', 'p3', W('Points won once a point reaches a third shot'), True),
          ('missShare', 'lostMiss', 'lost', W('Lost points that ended on your own miss'), False)]
COMPARE = ['pointRate', 'servePointRate', 'returnPointRate', 'servesLanded', 'returnsLanded', 'rallyLanded',
           'reach3Rate', 'missShare', 'rallySpeed', 'rallyLength']
# MIN_Z 1.64: a gap that large turns up by chance about one time in ten in a session of that size
SMALL_SESSION, MIN_BASE, MIN_TRIES, MIN_Z = 200, 150, 20, 1.64
p1 = lambda x: f'{x:.1f}%'

session_rows, session_notes = [], []
level_before = defaultdict(Counter)       # level -> tally of every earlier session's points at that level
matches_before = Counter()                # level -> matches in those earlier sessions
for si, ms in enumerate(sessions):
    skey = f"{ms[0]['date']} {ms[0]['start']}"
    lv = Counter(r['level'] for r in ms).most_common(1)[0][0]
    items = [(ai_items[r['key']][0], p) for r in ms for p in ai_items[r['key']][1]]
    sc, bc = tally(items), level_before[lv]
    has_base = bc['pts'] >= MIN_BASE
    row = {**summary_row(skey, f"{ms[0]['date']} {ms[0]['start'][:5]}", ms), 'n': si + 1, 'date': ms[0]['date'], 'level': lv,
           'levels': ' / '.join(map(str, sorted({r['level'] for r in ms}))), **rates(sc),
           'baseMatches': matches_before[lv] if has_base else None, 'basePoints': bc['pts'] if has_base else None}
    base = rates(bc) if has_base else {}
    for f in COMPARE:
        row['base_' + f] = base.get(f)
        row['d_' + f] = r1(row[f] - base[f]) if base.get(f) is not None and row[f] is not None else None
    for f, *_ in MOVERS:
        row['m_' + f] = 0      # 1 = clearly better than before, -1 = clearly worse
    session_rows.append(row)
    for i, r in enumerate(ms):
        r['session'] = skey; r['sessionMatch'] = i + 1

    notes = []
    wins = [r for r in ms if r['result'] == 'Won']
    if wins:
        which = bilist(r['sessionMatch'] for r in wins)
        scores = join('; ', [f"{r['gamesWon']}–{r['gamesLost']} ({r['score'].replace('-', '–')})" for r in wins], '；')
        notes.append(('good', T('You won matches {which} of {n}: {scores}.' if len(wins) > 1 else 'You won match {which} of {n}: {scores}.',
                                which=which, n=len(ms), scores=scores)))
    else:
        best = max(ms, key=lambda r: r['pointRate'] or 0)
        notes.append(('note', T('No match won. The closest was match {m} of {n}, lost {score} with {rate} of points.',
                                m=best['sessionMatch'], n=len(ms), rate=p1(best['pointRate']),
                                score=f"{best['gamesWon']}–{best['gamesLost']} ({best['score'].replace('-', '–')})")))
    if has_base:
        movers = []
        for f, num, den, label, up_good in MOVERS:
            n = sc[den]
            if n < MIN_TRIES or not bc[den]:
                continue
            pb, ps = bc[num] / bc[den], sc[num] / n
            se = math.sqrt(pb * (1 - pb) / n)
            if se and abs(ps - pb) / se >= MIN_Z:
                movers.append((abs(ps - pb) / se, ps > pb, f, n, label, up_good, ps, pb))
                row['m_' + f] = 1 if (ps > pb) == up_good else -1
        movers.sort(reverse=True)
        top = movers[:3]
        for want in (True, False):      # never leave out the biggest gain or the biggest drop
            rest = [m for m in movers[3:] if (m[1] == m[5]) == want]
            if rest and not any((m[1] == m[5]) == want for m in top):
                top[-1] = rest[0]
        for _, up, f, n, label, up_good, ps, pb in top:
            notes.append(('good' if up == up_good else 'bad',
                          T('{label}: {now} of {n}, up from {before} at level {lv} before.' if up else
                            '{label}: {now} of {n}, down from {before} at level {lv} before.',
                            label=label, now=p1(100 * ps), n=f'{n:,}', before=p1(100 * pb), lv=lv)))
        if not movers:
            notes.append(('note', T('Nothing moved far from your earlier level-{lv} average: {now} of points won against {before} before.',
                                    lv=lv, now=p1(row['pointRate']), before=p1(base['pointRate']))))
    else:
        notes.append(('note', T('Your first session at level {lv} in the logs, so there is no earlier average to compare with.', lv=lv)))
    longest = max(((len(p['hits']), r, p) for r in ms for p in ai_items[r['key']][1]), key=lambda t: t[0])
    notes.append(('note', T('Longest point: {shots} shots, in match {m}, which you won.'
                            if longest[2]['winner'] == ai_items[longest[1]['key']][0] else
                            'Longest point: {shots} shots, in match {m}, which you lost.', shots=longest[0], m=longest[1]['sessionMatch'])))
    if sc['pts'] < SMALL_SESSION:
        notes.append(('note', T('Only {pts} points in this session, so its percentages swing easily.', pts=sc['pts'])))
    for i, (tone, text) in enumerate(notes):
        session_notes.append(put({'key': f'{skey}|{i + 1}', 'session': skey, 'rank': i + 1, 'tone': tone}, 'text', text))
    level_before[lv].update(sc)
    matches_before[lv] += len(ms)
write('sessions', session_rows)
write('session_notes', session_notes)

# ---------------- training plan ----------------
# Built for the AI level you have been playing lately. Everything you hit falls in exactly one of five parts
# (serve; return from the backhand side; return from the middle or forehand side; rally shot against a slower ball;
# rally shot against a fast ball). Each part is counted on one thing, except the slower ball, which is counted on two
# that work separately (how often it lands, and how often you hit it firmly), so the estimated gains can be added up.
#   now    = your recent sessions at that level, pooled (the latest ones holding at least RECENT_POINTS points)
#   target = the same number in the matches you won at that level
#   gain   = tries a match x (target - now) x what one more success is worth in points, from all your points there
PACE, HARD, RECENT_POINTS, MIN_TARGET = 10, 12, 1000, 40      # m/s, m/s, points, tries


def plan_tally(items):
    c = Counter()
    for you, p in items:
        hits, won = p['hits'], p['winner'] == you
        c['pts'] += 1; c['won'] += won
        if not hits:
            continue
        sv, sx = hits[0], 1 if you == 'A' else -1
        rb = next((b for b in p['bounces'] if b['side'] != sv['side']), None)
        if sv['side'] == you:
            top = spin_kind(sv) == 'topspin'
            c['sv'] += 1; c['svTop'] += top; c['svTopWon'] += top and won; c['svFlatWon'] += (not top) and won
            if rb:
                band = 'svShort' if abs(rb['pos'][2]) < 0.5 else 'svMid' if abs(rb['pos'][2]) < 1.0 else 'svLong'
                c[band] += 1; c[band + 'Won'] += won
        for i, h in enumerate(hits):
            if h['side'] != you or h['serve'] or i == 0:
                continue
            ok, pace = h['ok'], h['speed'] >= PACE
            if h['n'] == 2:
                if rb and SIDE_OF(rb['pos'][0] * sx) == BH:  # the serve came to your backhand side
                    c['bh'] += 1; c['bhOk'] += ok; c['bhWon'] += won; c['bhPace'] += pace
                else:
                    c['fh'] += 1; c['fhOk'] += ok; c['fhWon'] += won; c['fhOkWon'] += ok and won; c['fhPace'] += pace
                    k = 'fhHard' if h['speed'] >= HARD else 'fhFirm' if pace else 'fhSoft'
                    c[k] += 1; c[k + 'Ok'] += ok; c[k + 'Won'] += won
            elif hits[i - 1]['speed'] >= PACE:
                c['fast'] += 1; c['fastOk'] += ok; c['fastOkWon'] += ok and won
            else:
                k = 'easyPace' if pace else 'easySoft'
                c['easy'] += 1; c['easyOk'] += ok; c['easyOkWon'] += ok and won; c[k] += 1; c[k + 'Ok'] += ok; c[k + 'Won'] += won
    return c


fr = lambda c, a, b: c[a] / c[b] if c[b] else None       # a share from 0 to 1, or None
pf = lambda x: '–' if x is None else f'{100 * x:.1f}%'
# key, title, what is counted, numerator, denominator, what one more success is worth in points, drill
PLAN = [
    ('easy', W('Put pace on the slower ball'), W("Rally shots hit at 10 m/s or more when the AI's ball comes in under 10 m/s"),
     'easyPace', 'easy', lambda c: (fr(c, 'easyPaceWon', 'easyPace') or 0) - (fr(c, 'easySoftWon', 'easySoft') or 0),
     W("Have slow balls fed to you (the ball machine, or the AI at a low level) and play every one as a firm topspin stroke: "
       "not a push, not a smash. Sets of 20, counting the ones that land. Once 15 land, have the feed moved around.")),
    ('steady', W('Keep the slower ball on the table'), W("Rally shots you land when the AI's ball comes in under 10 m/s"),
     'easyOk', 'easy', lambda c: fr(c, 'easyOkWon', 'easyOk') or 0,
     W("Rally at a steady, firm pace with the ball machine, or with the AI at a level you beat comfortably, and count shots "
       "in a row, starting again at every miss. Aim for runs of 10 before you go back to matches.")),
    ('fast', W('Get the fast ball back'), W("Shots you land when the AI's ball arrives at 10 m/s or more"),
     'fastOk', 'fast', lambda c: fr(c, 'fastOkWon', 'fastOk') or 0,
     W("Have hard balls sent at you and only block them: short stroke, bat angle closed, no backswing. Sets of 20. "
       "Add pace of your own only after 12 go back.")),
    ('bh', W('A firmer backhand return'), W('Points won when the AI serves to your backhand side'),
     'bhWon', 'bh', lambda c: 1.0,
     W("Serve practice to your backhand side only. Return every serve with a short topspin backhand at a corner, firm enough "
       "that it cannot be attacked. Sets of 20 serves.")),
    ('fh', W('Land the other returns'), W("Returns you land when the AI serves to the middle or your forehand side"),
     'fhOk', 'fh', lambda c: fr(c, 'fhOkWon', 'fhOk') or 0,
     W("Serve practice to the middle and your forehand side. Keep attacking, at three-quarter pace, aiming a hand's width "
       "inside the lines. Sets of 20 serves, aiming for 15 on the table.")),
    ('serve', W('Serve with topspin'), W('Serves you hit with topspin'),
     'svTop', 'sv', lambda c: (fr(c, 'svTopWon', 'svTop') or 0) - ((c['svFlatWon'] / (c['sv'] - c['svTop'])) if c['sv'] > c['svTop'] else 0),
     W("Ten minutes of serves on their own: topspin, to both corners, bouncing in the middle of the AI's half rather than "
       "close to the net.")),
]


def plan_why(key, c, m):
    """One or two sentences of evidence for a plan item, from every point at the plan's level (c) over m matches."""
    if key == 'easy':
        a, b = fr(c, 'easyPaceOk', 'easyPace'), fr(c, 'easySoftOk', 'easySoft')
        s = T("When the AI's ball comes in under {pace} m/s and you answer at {pace} m/s or more, you win {firm} of those points. "
              "When you answer slower, you win {soft}.",
              pace=PACE, firm=pf(fr(c, 'easyPaceWon', 'easyPace')), soft=pf(fr(c, 'easySoftWon', 'easySoft')))
        if a is not None and b is not None:
            s += (T(' The firmer shot lands {a} of the time and the slower one {b}, so holding back buys no safety.', a=pf(a), b=pf(b))
                  if a >= b - 0.02 else T(' The firmer shot lands {a} of the time, the slower one {b}.', a=pf(a), b=pf(b)))
        return s
    if key == 'steady':
        kw = dict(n=f"{c['easy'] / m:.0f}", pace=PACE, land=pf(fr(c, 'easyOk', 'easy')), won=pf(fr(c, 'easyOkWon', 'easyOk')))
        if (fr(c, 'easyOkWon', 'easyOk') or 0) > 0.5 and c['easy'] > c['fast'] + c['bh'] + c['fh']:
            return T('About {n} of your rally shots a match are against balls under {pace} m/s, more than your returns and your shots '
                     'against fast balls put together, and {land} of them land. When one lands you go on to win the point '
                     '{won} of the time, so every extra ball on the table is worth over half a point.', **kw)
        return T('About {n} of your rally shots a match are against balls under {pace} m/s and {land} of them land. '
                 'When one lands you go on to win the point {won} of the time.', **kw)
    if key == 'fast':
        return T('About {n} balls a match reach you at {pace} m/s or more and you put {back} of them back, against {slow} of slower '
                 'balls. When one does go back, you win the point {won} of the time.',
                 n=f"{c['fast'] / m:.0f}", pace=PACE, back=pf(fr(c, 'fastOk', 'fast')), slow=pf(fr(c, 'easyOk', 'easy')),
                 won=pf(fr(c, 'fastOkWon', 'fastOk')))
    if key == 'bh':
        return T('The AI serves to your backhand side about {n} times a match and you win {won} of those points, against {other} on '
                 'its other serves. The returns land about as often on both sides ({bh} and {fh}), but only {pace_bh} of the backhand '
                 'ones are hit at {pace} m/s or more, against {pace_fh} of the others.',
                 n=f"{c['bh'] / m:.0f}", won=pf(fr(c, 'bhWon', 'bh')), other=pf(fr(c, 'fhWon', 'fh')), bh=pf(fr(c, 'bhOk', 'bh')),
                 fh=pf(fr(c, 'fhOk', 'fh')), pace_bh=pf(fr(c, 'bhPace', 'bh')), pace=PACE, pace_fh=pf(fr(c, 'fhPace', 'fh')))
    if key == 'fh':
        a, b = fr(c, 'fhHardOk', 'fhHard'), fr(c, 'fhFirmOk', 'fhFirm')
        wa, wb = fr(c, 'fhHardWon', 'fhHard'), fr(c, 'fhFirmWon', 'fhFirm')
        if None not in (a, b, wa, wb) and b > a + 0.05 and wb >= wa - 0.03:
            return T('From the middle and forehand side, your returns at {hard} m/s or more land {a} of the time and win {wa} of '
                     'points. At {pace} to {hard} m/s they land {b} and win {wb}: taking a little off costs you nothing.',
                     hard=HARD, pace=PACE, a=pf(a), b=pf(b), wa=pf(wa), wb=pf(wb))
        return T('You land {land} of returns from the middle and forehand side, and win {won} of the points when one lands.',
                 land=pf(fr(c, 'fhOk', 'fh')), won=pf(fr(c, 'fhOkWon', 'fhOk')))
    flat = c['sv'] - c['svTop']
    s = T('Your topspin serves win {top} of points and your other serves {other}.',
          top=pf(fr(c, 'svTopWon', 'svTop')), other=pf(c['svFlatWon'] / flat if flat else None))
    if c['svShort'] >= MIN_TARGET and c['svMid'] >= MIN_TARGET:
        s += T(" Serves that bounce within 50 cm of the net win {short}; those in the middle of the AI's half win {mid}.",
               short=pf(fr(c, 'svShortWon', 'svShort')), mid=pf(fr(c, 'svMidWon', 'svMid')))
    return s


recent_pts = Counter()
for row in session_rows[-5:]:
    recent_pts[row['level']] += row['points']
plan_level = recent_pts.most_common(1)[0][0]
lv_sessions = [(row, ms) for row, ms in zip(session_rows, sessions) if row['level'] == plan_level]
sess_items = lambda ms: [(ai_items[r['key']][0], p) for r in ms for p in ai_items[r['key']][1] if r['level'] == plan_level]
sess_tallies = [(row, plan_tally(sess_items(ms))) for row, ms in lv_sessions]
n_recent, c_recent = 0, Counter()
while n_recent < len(sess_tallies) and c_recent['pts'] < RECENT_POINTS:
    n_recent += 1
    c_recent.update(sess_tallies[-n_recent][1])
c_before = Counter()
for _, c in sess_tallies[:-n_recent]:
    c_before.update(c)
lv_ms = [r for r in ai_ms if r['level'] == plan_level]
c_all = plan_tally(level_items[plan_level])
c_won = plan_tally([(ai_items[r['key']][0], p) for r in lv_ms if r['result'] == 'Won' for p in ai_items[r['key']][1]])
per_match = c_all['pts'] / len(lv_ms)
recent_rate = c_recent['won'] / c_recent['pts']
plan, plan_trend = [], []
for key, title, metric, num, den, worth, drill in PLAN:
    now, was, target = fr(c_recent, num, den), fr(c_before, num, den), fr(c_won, num, den) if c_won[den] >= MIN_TARGET else None
    tries = c_all[den] / len(lv_ms)
    gain = None if target is None or now is None else max(0.0, tries * (target - now) * worth(c_all))
    move = 0        # 1 = recent sessions clearly above the earlier ones, -1 = clearly below
    if was is not None and now is not None and c_recent[den] >= MIN_TRIES and c_before[den] >= MIN_BASE:
        pool = (c_recent[num] + c_before[num]) / (c_recent[den] + c_before[den])
        se = math.sqrt(pool * (1 - pool) * (1 / c_recent[den] + 1 / c_before[den]))
        move = 0 if not se or abs(now - was) / se < MIN_Z else 1 if now > was else -1
    row = {'key': key, 'now': pc(c_recent[num], c_recent[den]), 'nowTries': c_recent[den],
           'was': pc(c_before[num], c_before[den]), 'all': pc(c_all[num], c_all[den]),
           'target': None if target is None else r1(100 * target), 'targetTries': c_won[den],
           'perMatch': r1(tries), 'gain': None if gain is None else round(gain, 2), 'move': move,
           'status': 'none' if gain is None else 'reached' if now >= target else 'gap'}
    for f, v in (('title', title), ('metric', metric), ('why', plan_why(key, c_all, len(lv_ms))), ('drill', drill)):
        put(row, f, v)
    plan.append(row)
    for row, c in sess_tallies:
        if c[den] >= MIN_TRIES:
            plan_trend.append({'key': f"{key}|{row['n']}", 'item': key, 'session': row['n'], 'sessionKey': row['key'],
                               'date': row['date'], 'value': pc(c[num], c[den]), 'tries': c[den],
                               'recent': int(row['n'] >= sess_tallies[-n_recent][0]['n'])})
plan.sort(key=lambda r: -(r['gain'] or 0))      # stable: equal gains keep the order above
total_gain = sum(r['gain'] or 0 for r in plan)
for i, r in enumerate(plan):
    r.update({'rank': i + 1, 'level': plan_level, 'levelMatches': len(lv_ms), 'levelWins': sum(x['result'] == 'Won' for x in lv_ms),
              'recentSessions': n_recent, 'recentPoints': c_recent['pts'], 'recentRate': r1(100 * recent_rate),
              'recentFrom': sess_tallies[-n_recent][0]['date'], 'recentTo': sess_tallies[-1][0]['date'],
              'pointsPerMatch': r1(per_match), 'wonPerMatch': r1(per_match * recent_rate),
              'shortBy': r1(max(0.0, per_match * (0.5 - recent_rate))), 'totalGain': r1(total_gain)})
write('plan', plan)
write('plan_trend', plan_trend)

# ---------------- plan progress: each item since it joined the list ----------------
# The plan keeps no history: it is rebuilt from the logs at every update. So the same sums are done again as they would
# have stood after each earlier session at the plan's level (the sessions up to that one only), which gives every item a
# state session by session: on the list (1), already working (0: at its target, or worth under PLAN_KEEP points a
# match) or without a target yet (-). An item joined the list at the first session that put it there. Its number then
# (the recent sessions as they stood at that session) is set against its number over the sessions played since, with
# the same one-in-ten rule for calling a change clear. An item joins when its number is low, and a low number is partly
# bad luck, so some rise afterwards would come without any practice: read a small rise with that in mind.
PLAN_KEEP = 0.15        # points a match; the page uses the same value to split the list from "Already working"
sess_won = [plan_tally([(ai_items[r['key']][0], q) for r in ms if r['level'] == plan_level and r['result'] == 'Won'
                        for q in ai_items[r['key']][1]]) for _, ms in lv_sessions]
sess_n = [sum(r['level'] == plan_level for r in ms) for _, ms in lv_sessions]


def plan_asof(k):
    """The plan as it stood after session k (an index into sess_tallies): {item: state, gain, and the recent tallies}."""
    rec, n = Counter(), 0
    while n <= k and rec['pts'] < RECENT_POINTS:
        rec.update(sess_tallies[k - n][1])
        n += 1
    tot, won = Counter(), Counter()
    for j in range(k + 1):
        tot.update(sess_tallies[j][1])
        won.update(sess_won[j])
    m, out = sum(sess_n[:k + 1]), {}
    for key, _title, _metric, num, den, worth, _drill in PLAN:
        now, target = fr(rec, num, den), fr(won, num, den) if won[den] >= MIN_TARGET else None
        gain = None if target is None or now is None else round(max(0.0, tot[den] / m * (target - now) * worth(tot)), 2)
        state = '-' if gain is None else '0' if now >= target or gain < PLAN_KEEP else '1'
        out[key] = {'state': state, 'gain': gain, 'num': rec[num], 'den': rec[den]}
    return out


plan_hist = [plan_asof(k) for k in range(len(sess_tallies))]
for r in plan:      # the last step of the history is the plan itself
    assert plan_hist[-1][r['key']]['gain'] == r['gain'], (r['key'], plan_hist[-1][r['key']]['gain'], r['gain'])
plan_progress = []
for key, title, metric, num, den, worth, drill in PLAN:
    states = ''.join(h[key]['state'] for h in plan_hist)
    run = len(states.rstrip(states[-1]))      # where the latest unbroken run of the current state began
    row = {'key': key, 'level': plan_level, 'state': states[-1], 'states': states, 'ever': int('1' in states),
           'runSession': sess_tallies[run][0]['n'], 'runDate': sess_tallies[run][0]['date'],
           'sessionsKnown': len(states) - states.count('-')}
    if row['ever']:
        e = states.index('1')
        then, since = plan_hist[e][key], Counter()
        for _, c in sess_tallies[e + 1:]:
            since.update(c)
        move = 0
        if then['den'] >= MIN_TRIES and since[den] >= MIN_TRIES:
            pool = (then['num'] + since[num]) / (then['den'] + since[den])
            se = math.sqrt(pool * (1 - pool) * (1 / then['den'] + 1 / since[den]))
            d = since[num] / since[den] - then['num'] / then['den']
            move = 0 if not se or abs(d) / se < MIN_Z else 1 if d > 0 else -1
        row.update({'session': sess_tallies[e][0]['n'], 'sessionKey': sess_tallies[e][0]['key'], 'date': sess_tallies[e][0]['date'],
                    'sessionsOn': states[e:].count('1'), 'sessionsFrom': len(states) - e,
                    'sessionsSince': len(states) - 1 - e, 'matchesSince': sum(sess_n[e + 1:]),
                    'then': pc(then['num'], then['den']), 'thenTries': then['den'], 'thenGain': then['gain'],
                    'since': pc(since[num], since[den]), 'sinceTries': since[den], 'move': move})
    plan_progress.append(row)
write('plan_progress', plan_progress)

# ---------------- form: your latest matches at a level, and how a session goes from its first match to its last ----------------
# form: one row per AI match, in order at its level, with the share of matches and of points won over the last 10, 20
# and 50 matches at that level up to it, each with the range the true share most likely sits in (9 times in 10, Wilson's
# interval, every match or point taken as a separate try; the same one-in-ten rule as MIN_Z). Empty until the level has that many matches.
FORM_WINDOWS = (10, 20, 50)


def likely_range(k, n, z=MIN_Z):
    c, d = k / n + z * z / (2 * n), 1 + z * z / n
    h = z * math.sqrt(k / n * (1 - k / n) / n + z * z / (4 * n * n))
    return r1(100 * max(0.0, (c - h) / d)), r1(100 * min(1.0, (c + h) / d))


form = []
for lvl in sorted({r['level'] for r in ai_ms}):
    ms = [r for r in ai_ms if r['level'] == lvl]
    for i, r in enumerate(ms):
        row = {'key': r['key'], 'level': lvl, 'i': i + 1, 'date': r['date'], 'session': r['session']}
        for w in FORM_WINDOWS:
            last = ms[i + 1 - w:i + 1] if i + 1 >= w else []
            for f, k, n in (('m', sum(x['result'] == 'Won' for x in last), len(last)),
                            ('p', sum(x['pointsWonN'] for x in last), sum(x['points'] for x in last))):
                lo, hi = likely_range(k, n) if n else (None, None)
                row.update({f'{f}{w}': pc(k, n), f'{f}{w}lo': lo, f'{f}{w}hi': hi})
        form.append(row)
write('form', form)

# session_shape: points won in each match against the other matches of the same session at the same level, added up by
# the match's place in the session. A place is clearly better or worse (move) when a gap that large turns up by chance
# about one time in ten (MIN_Z), as in the session report.
SHAPE_PLACES = [(1, 1), (2, 2), (3, 5), (6, 10), (11, 15), (16, 20), (21, 9999)]
SHAPE_MIN, LATE_FROM, LATE_MIN = 5, 11, 10       # matches for a place to be shown; where late in a session starts; matches for a word on it


def shape_tally(pairs):
    """pairs: (match, the matches it is set against). Points won against what the others' rate would give."""
    t = {'matches': 0, 'wins': 0, 'points': 0, 'won': 0, 'exp': 0.0, 'var': 0.0}
    for r, rest in pairs:
        pts = sum(x['points'] for x in rest)
        if not pts or not r['points']:
            continue
        e = sum(x['pointsWonN'] for x in rest) / pts
        t['matches'] += 1
        t['wins'] += r['result'] == 'Won'
        t['points'] += r['points']
        t['won'] += r['pointsWonN']
        t['exp'] += e * r['points']
        t['var'] += e * (1 - e) * (r['points'] + r['points'] ** 2 / pts)      # the match's own luck, and the others'
    return t


def shape_row(key, t):
    se = math.sqrt(t['var']) / t['points'] if t['points'] else 0
    d = (t['won'] - t['exp']) / t['points'] if t['points'] else 0
    return {'key': key, 'matches': t['matches'], 'wins': t['wins'], 'matchRate': pc(t['wins'], t['matches']), 'points': t['points'],
            'rate': pc(t['won'], t['points']), 'rest': r1(100 * t['exp'] / t['points']) if t['points'] else None,
            'diff': r1(100 * d), 'lo': r1(100 * (d - MIN_Z * se)), 'hi': r1(100 * (d + MIN_Z * se)),
            'move': 0 if not se or abs(d) / se < MIN_Z else 1 if d > 0 else -1}


shape_groups = defaultdict(list)        # the matches of one session at one level
for r in ai_ms:
    shape_groups[r['session'], r['level']].append(r)
shape_groups = [g for g in shape_groups.values() if len(g) >= 3]
session_shape, form_notes = [], []
for a, b in SHAPE_PLACES:
    t = shape_tally([(r, [x for x in g if x is not r]) for g in shape_groups for r in g if a <= r['sessionMatch'] <= b])
    if t['matches'] >= SHAPE_MIN:
        row = dict(shape_row(f'{a}', t), order=a, to=min(b, max(r['sessionMatch'] for g in shape_groups for r in g)))
        put(row, 'label', T('Match {a}', a=a) if a == b else T('Matches {a} on', a=a) if b > 999 else T('Matches {a} to {b}', a=a, b=b))
        session_shape.append(row)
write('session_shape', session_shape)
# two sentences, by fixed rules: the first match of a session, and the matches late in one
first = next((r for r in session_shape if r['key'] == '1'), None)
if first:
    gap = T('{d} percentage points', d=f"{abs(first['diff']):.1f}")
    form_notes.append(('good' if first['move'] > 0 else 'bad' if first['move'] < 0 else 'note',
                       T('Your first match of a session runs {gap} above the rest of the session ({n} first matches).', gap=gap, n=first['matches'])
                       if first['move'] > 0 else
                       T('Your first match of a session runs {gap} below the rest of the session ({n} first matches): a longer warm-up may be worth points.',
                         gap=gap, n=first['matches']) if first['move'] < 0 else
                       T('No warm-up effect: your first match of a session is within chance of the rest of it ({n} first matches).', n=first['matches'])))
late = shape_tally([(r, [x for x in g if x['sessionMatch'] < LATE_FROM]) for g in shape_groups for r in g if r['sessionMatch'] >= LATE_FROM])
if late['matches'] >= LATE_MIN:
    lr = shape_row('late', late)
    gap = T('{d} percentage points', d=f"{abs(lr['diff']):.1f}")
    form_notes.append(('bad' if lr['move'] < 0 else 'good' if lr['move'] > 0 else 'note',
                       T('From match {a} of a session on you win {gap} fewer of the points than in its first {b} matches ({n} matches): the sign of tiring.',
                         a=LATE_FROM, b=LATE_FROM - 1, gap=gap, n=lr['matches']) if lr['move'] < 0 else
                       T('From match {a} of a session on you win {gap} more of the points than in its first {b} matches ({n} matches): you play yourself in.',
                         a=LATE_FROM, b=LATE_FROM - 1, gap=gap, n=lr['matches']) if lr['move'] > 0 else
                       T('No sign of tiring: from match {a} of a session on, your points won stay within chance of its first {b} matches ({n} matches).',
                         a=LATE_FROM, b=LATE_FROM - 1, n=lr['matches'])))
else:
    form_notes.append(('note', T('Too few long sessions to say anything about tiring: {n} matches came after the first {b} of a session.',
                                 n=late['matches'], b=LATE_FROM - 1)))
write('form_notes', [put({'key': str(i + 1), 'rank': i + 1, 'tone': tone}, 'text', text) for i, (tone, text) in enumerate(form_notes)])


# ---------------- serves and returns, level by level ----------------
# who 'recv' = points the AI served, 'serve' = points you served. Sides are as you face the AI; for the AI's serves your
# left is your backhand side. Depth is the first bounce on the receiver's half: short = within 50 cm of the net,
# half-long = 50 cm to 1 m, long = the last 37 cm.
# Every point falls in one of five stages, in the order a point runs:
#   recv:  miss = return missed or serve not touched | next = lost to the AI's third ball (not reached, or missed)
#          | lostLater | wonLater | early = won by the return (not reached, or the AI missed it) or an AI service fault
#   serve: miss = serve missed | next = lost on your third ball (the return not reached, or the third ball missed)
#          | lostLater | wonLater | early = won by the serve or the third ball (not reached, or the AI missed it)
STAGES = ['miss', 'next', 'lostLater', 'wonLater', 'early']
MIN_ROW, MIN_NOTE = 30, 50
DEPTH_OF = lambda z: 'short' if abs(z) < 0.5 else 'half-long' if abs(z) < 1.0 else 'long'
SIDE_ORDER, DEPTH_ORDER, SPIN_ORDER = ['left', 'middle', 'right'], ['short', 'half-long', 'long'], ['topspin', 'little spin', 'backspin']
RECV_ORDER = [BH, 'middle', FH]          # the AI's serves, by the side they come to: backhand first
RECV_SIDE = {BH: W('Backhand side'), 'middle': W('Middle'), FH: W('Forehand side')}
SERVE_SIDE = {'left': W('To your left'), 'middle': W('To the middle'), 'right': W('To your right')}
SERVE_SIDE_LOW = {'left': W('to your left'), 'middle': W('to the middle'), 'right': W('to your right')}
LAND_SIDE = {'left': W('your left'), 'middle': W('the middle'), 'right': W('your right')}
LAND_SIDE_CAP = {'left': W('Your left'), 'middle': W('The middle'), 'right': W('Your right')}
SPIN_WORD = {'topspin': W('topspin'), 'little spin': W('little spin'), 'backspin': W('backspin')}
SPIN_CAP = {'topspin': W('Topspin'), 'little spin': W('Little spin'), 'backspin': W('Backspin')}
DEPTH_WORD = {'short': W('short'), 'half-long': W('half-long'), 'long': W('long')}
DEPTH_CAP = {'short': W('Short'), 'half-long': W('Half-long'), 'long': W('Long')}
RETURN_BANDS = [(0, 8, W('Under 8 m/s')), (8, 10, W('8 to 10 m/s')), (10, 12, W('10 to 12 m/s')), (12, 99, W('12 m/s or more'))]
AI_RETURN_BANDS = [(0, 7, W('Under 7 m/s')), (7, 9, W('7 to 9 m/s')), (9, 11, W('9 to 11 m/s')), (11, 99, W('11 m/s or more'))]
lower = lambda b: b.map(lambda s: s[:1].lower() + s[1:], lambda s: s)      # a label inside a sentence
rbi = lambda r, f: Bi(r[f], r.get(f + '_zh'))                               # a row's text in both languages
band_of = lambda v, bands: next(i for i, (lo, hi, _) in enumerate(bands) if lo <= v < hi)


def stage_of(hits, serving, won):
    n, ok = len(hits), hits[-1]['ok']
    if n == 1:
        return ('early' if ok else 'miss') if serving else ('miss' if ok else 'early')
    if n == 2:
        return ('next' if ok else 'early') if serving else ('early' if ok else 'miss')
    if n == 3:
        return ('early' if ok else 'next') if serving else ('next' if ok else 'early')
    if n == 4:
        return ('lostLater' if ok else 'early') if serving else ('wonLater' if ok else 'next')
    return 'wonLater' if won else 'lostLater'


def sr_tally(items):
    """Counters keyed (who, table, key): flow groups, serve types, and what the next shot looked like."""
    ST = defaultdict(Counter)
    for you, p in items:
        hits, won = p['hits'], p['winner'] == you
        if not hits:
            continue
        sv, sx = hits[0], 1 if you == 'A' else -1
        serving = sv['side'] == you
        who = 'serve' if serving else 'recv'
        rb = next((b for b in p['bounces'] if b['side'] != sv['side']), None)
        st, kind = stage_of(hits, serving, won), spin_kind(sv)
        groups = [('all', 'all'), ('spin', kind)]
        if rb:
            side, depth = SIDE_OF(rb['pos'][0] * sx), DEPTH_OF(rb['pos'][2])
            groups += [('side', side), ('depth', depth), ('type', (side, kind, depth))]
        for g, v in groups:
            c = ST[who, g, v]
            c['n'] += 1; c['won'] += won; c[st] += 1; c['speed'] += sv['speed']
            c['untouched'] += (not serving) and len(hits) == 1 and sv['ok']
            if len(hits) > 1:
                r = hits[1]
                c['ret'] += 1; c['retOk'] += r['ok']; c['retSpeed'] += r['speed']
            if len(hits) > 2:
                c['third'] += 1; c['thirdOk'] += hits[2]['ok']
        if len(hits) < 2:
            continue
        r = hits[1]
        if not serving:                 # your return: its pace, and where it landed
            c = ST[who, 'pace', band_of(r['speed'], RETURN_BANDS)]
            c['n'] += 1; c['won'] += won; c['ok'] += r['ok']
            land = next((b for b in p['bounces'] if b['by'] == you and b['side'] != you), None) if r['ok'] else None
            if land:
                for g, v in (('land-depth', DEPTH_OF(land['pos'][2])), ('land-side', SIDE_OF(land['pos'][0] * sx))):
                    c = ST[who, g, v]
                    c['n'] += 1; c['won'] += won
        elif r['ok']:                   # the AI's return of your serve: its pace and where it landed, and your third ball
            third_ok = len(hits) > 2 and hits[2]['ok']
            land = next((b for b in p['bounces'] if b['by'] != you and b['side'] == you), None)
            for g, v in [('pace', band_of(r['speed'], AI_RETURN_BANDS))] + ([('zone', (SIDE_OF(land['pos'][0] * sx), DEPTH_OF(land['pos'][2])))] if land else []):
                c = ST[who, g, v]
                c['n'] += 1; c['won'] += won; c['third'] += len(hits) > 2; c['thirdOk'] += third_ok
    return ST


def type_label(who, side, kind, depth):
    return join(', ', [(RECV_SIDE if who == 'recv' else SERVE_SIDE)[side], SPIN_WORD[kind], DEPTH_WORD[depth]], '、')


serve_flow, serve_types, serve_next, serve_notes = [], [], [], []
for lvl in sorted(level_items):
    ST = sr_tally(level_items[lvl])
    for who in ('recv', 'serve'):
        tot = ST[who, 'all', 'all']
        if not tot['n']:
            continue
        side_names = RECV_SIDE if who == 'recv' else SERVE_SIDE
        order = 0
        flow = {}
        for g, values, name in (('all', ['all'], lambda v: W("All the AI's serves") if who == 'recv' else W('All your serves')),
                                ('side', RECV_ORDER if who == 'recv' else SIDE_ORDER, lambda v: side_names[v]),
                                ('spin', SPIN_ORDER, lambda v: SPIN_CAP[v]),
                                ('depth', DEPTH_ORDER, lambda v: DEPTH_CAP[v])):
            for v in values:
                c = ST[who, g, v]
                if c['n'] < (1 if g == 'all' else MIN_ROW):
                    continue
                order += 1
                row = {'key': f'{lvl}|{who}|{g}|{v}', 'level': lvl, 'who': who, 'group': g, 'value': v, 'order': order,
                       'n': c['n'], 'pointRate': pc(c['won'], c['n']), **{s: pc(c[s], c['n']) for s in STAGES},
                       'untouched': pc(c['untouched'], c['n']) if who == 'recv' else None,
                       'speed': r1(c['speed'] / c['n']), 'returnsLanded': pc(c['retOk'], c['ret']),
                       'returnSpeed': r1(c['retSpeed'] / c['ret']) if c['ret'] else None,
                       'thirdLanded': pc(c['thirdOk'], c['third']) if who == 'serve' else None}
                serve_flow.append(put(row, 'label', name(v)))
                flow[g, v] = row
        landed = sum(c['n'] for (w, g, v), c in ST.items() if w == who and g == 'type')
        types = []
        for (w, g, v), c in ST.items():
            if w != who or g != 'type' or c['n'] < MIN_ROW:
                continue
            side, kind, depth = v
            types.append(put({'key': f'{lvl}|{who}|{side}|{kind}|{depth}', 'level': lvl, 'who': who, 'side': side, 'spin': kind, 'depth': depth,
                              'n': c['n'], 'share': pc(c['n'], landed),
                              'speed': r1(c['speed'] / c['n']), 'returnsLanded': pc(c['retOk'], c['ret']),
                              'returnSpeed': r1(c['retSpeed'] / c['ret']) if c['ret'] else None,
                              'thirdLanded': pc(c['thirdOk'], c['third']) if who == 'serve' else None, 'pointRate': pc(c['won'], c['n'])},
                             'label', type_label(who, side, kind, depth)))
        types.sort(key=lambda r: (-r['pointRate'], -r['n']))
        for i, r in enumerate(types):
            r['rank'] = i + 1
        serve_types.extend(types)

        nxt = []
        bands = RETURN_BANDS if who == 'recv' else AI_RETURN_BANDS
        pace_n = sum(ST[who, 'pace', i]['n'] for i in range(len(bands)))
        for i, (_, _, label) in enumerate(bands):
            c = ST[who, 'pace', i]
            if c['n']:
                nxt.append(put({'key': f'{lvl}|{who}|pace|{i}', 'kind': 'pace', 'n': c['n'], 'share': pc(c['n'], pace_n),
                                'landed': pc(c['ok'], c['n']) if who == 'recv' else pc(c['thirdOk'], c['third']),
                                'pointRate': pc(c['won'], c['n'])}, 'label', label))
        if who == 'recv':
            for g, values, name in (('land-depth', DEPTH_ORDER, lambda v: DEPTH_CAP[v]), ('land-side', SIDE_ORDER, lambda v: SERVE_SIDE[v])):
                gn = sum(ST[who, g, v]['n'] for v in values)
                for v in values:
                    c = ST[who, g, v]
                    if c['n'] >= MIN_ROW:
                        nxt.append(put({'key': f'{lvl}|{who}|{g}|{v}', 'kind': g, 'n': c['n'], 'share': pc(c['n'], gn),
                                        'landed': None, 'pointRate': pc(c['won'], c['n'])}, 'label', name(v)))
        else:
            zones_ = [(v, c) for (w, g, v), c in ST.items() if w == who and g == 'zone' and c['n'] >= MIN_ROW]
            zn = sum(c['n'] for (w, g, v), c in ST.items() if w == who and g == 'zone')
            for v, c in sorted(zones_, key=lambda t: -t[1]['won'] / t[1]['n']):
                nxt.append(put({'key': f'{lvl}|{who}|zone|{v[0]}|{v[1]}', 'kind': 'zone', 'n': c['n'], 'share': pc(c['n'], zn),
                                'landed': pc(c['thirdOk'], c['third']), 'pointRate': pc(c['won'], c['n'])},
                               'label', join(', ', [LAND_SIDE_CAP[v[0]], DEPTH_WORD[v[1]]], '、')))
        for i, r in enumerate(nxt):
            r.update({'level': lvl, 'who': who, 'order': i + 1})
        serve_next.extend(nxt)

        # ---- notes: each is written only when its numbers are there and say what the sentence says
        notes = []
        big = lambda g, v: (g, v) in flow and flow[g, v]['n'] >= MIN_NOTE
        f = lambda g, v: flow[g, v]
        best = [r for r in types if r['n'] >= MIN_NOTE]
        if who == 'recv':
            if all(big('side', s) for s in SIDE_ORDER):
                miss = [f('side', s)['miss'] for s in SIDE_ORDER]
                bh, fh, mid = f('side', BH), f('side', FH), f('side', 'middle')
                kw = dict(bh=p1(bh['pointRate']), mid=p1(mid['pointRate']), fh=p1(fh['pointRate']))
                if max(miss) - min(miss) <= 8 and fh['early'] - bh['early'] >= 10:
                    notes.append(T('From the forehand side your return settles the point at once: it wins it {fh_early} of the time and '
                                   'misses {fh_miss}. From the backhand side it misses about as often ({bh_miss}) but wins the point only '
                                   '{bh_early} of the time{rallies}. Points won: {bh} from the backhand side, {mid} from the middle, {fh} '
                                   'from the forehand side.',
                                   fh_early=p1(fh['early']), fh_miss=p1(fh['miss']), bh_miss=p1(bh['miss']), bh_early=p1(bh['early']),
                                   rallies=T(', and the rallies that follow go against you') if bh['next'] + bh['lostLater'] > bh['wonLater'] else '',
                                   **kw))
                else:
                    notes.append(T('You win {bh} of points when the serve comes to your backhand side, {mid} from the middle and {fh} '
                                   'from the forehand side.', **kw))
            if big('depth', 'long') and big('depth', 'half-long') and f('depth', 'long')['miss'] - f('depth', 'half-long')['miss'] >= 5:
                notes.append(T("Long serves are the ones you miss: {long} of them, against {half} of half-long ones. {share} of the AI's "
                               "serves are long.", long=p1(f('depth', 'long')['miss']), half=p1(f('depth', 'half-long')['miss']),
                               share=p1(pc(f('depth', 'long')['n'], landed))))
            if big('spin', 'topspin') and big('spin', 'little spin') and f('spin', 'topspin')['early'] - f('spin', 'little spin')['early'] >= 5:
                notes.append(T('Against its serves with little spin your return wins the point only {little} of the time, against {top} '
                               'on its topspin serves.', little=p1(f('spin', 'little spin')['early']), top=p1(f('spin', 'topspin')['early'])))
            dl, dh = ST[who, 'land-depth', 'long'], ST[who, 'land-depth', 'half-long']
            if dl['n'] >= MIN_NOTE and dh['n'] >= MIN_NOTE and dl['won'] / dl['n'] - dh['won'] / dh['n'] >= 0.05:
                notes.append(T('A return that lands long wins you {long} of points, a half-long one {half}.',
                               long=p1(pc(dl['won'], dl['n'])), half=p1(pc(dh['won'], dh['n']))))
            if tot['untouched'] and pc(tot['untouched'], tot['n']) >= 2:
                notes.append(T('On {share} of its serves ({n}) you did not get a bat on the ball.',
                               share=p1(pc(tot['untouched'], tot['n'])), n=f"{tot['untouched']:,}"))
            if len(best) >= 2:
                notes.append(T('Hardest serve to face: {hard}, {hard_rate} of points won over {hard_n} serves. Easiest: {easy}, {easy_rate} '
                               'over {easy_n}.', hard=lower(rbi(best[-1], 'label')), hard_rate=p1(best[-1]['pointRate']),
                               hard_n=f"{best[-1]['n']:,}", easy=lower(rbi(best[0], 'label')), easy_rate=p1(best[0]['pointRate']),
                               easy_n=f"{best[0]['n']:,}"))
        else:
            a = f('all', 'all')
            if a['next'] + a['early'] >= 40:
                notes.append(T('On your serve the third ball decides most points: you lose {next} of your service points on it and win '
                               '{early} with it or with the serve itself. Your serve misses {miss} of the time.',
                               next=p1(a['next']), early=p1(a['early']), miss=p1(a['miss'])))
            lo, hi = ST[who, 'pace', 0], ST[who, 'pace', len(bands) - 1]
            if lo['third'] >= MIN_NOTE and hi['third'] >= MIN_NOTE and lo['thirdOk'] / lo['third'] - hi['thirdOk'] / hi['third'] >= 0.1:
                notes.append(T("The pace of the AI's return sets up your third ball. When the return comes at under {slow} m/s you land "
                               '{lo_land} of third balls and win {lo_won} of points; at {fast} m/s or more, {hi_land} and {hi_won}.',
                               slow=bands[0][1], fast=bands[-1][0], lo_land=p1(pc(lo['thirdOk'], lo['third'])), lo_won=p1(pc(lo['won'], lo['n'])),
                               hi_land=p1(pc(hi['thirdOk'], hi['third'])), hi_won=p1(pc(hi['won'], hi['n']))))
            zs = sorted(((c['won'] / c['n'], v, c) for (w, g, v), c in ST.items() if w == who and g == 'zone' and c['n'] >= MIN_NOTE), key=lambda t: t[0])
            if len(zs) >= 2 and zs[-1][0] - zs[0][0] >= 0.1:
                (_, wv, wc), (_, bv, bc) = zs[0], zs[-1]
                notes.append(T("Where the AI's return lands decides a lot: {worst}, and you win {worst_rate} of points ({worst_n} returns); "
                               '{best}, and you win {best_rate} ({best_n}).',
                               worst=join(', ', [LAND_SIDE[wv[0]], DEPTH_WORD[wv[1]]], '、'), worst_rate=p1(pc(wc['won'], wc['n'])),
                               worst_n=f"{wc['n']:,}", best=join(', ', [LAND_SIDE[bv[0]], DEPTH_WORD[bv[1]]], '、'),
                               best_rate=p1(pc(bc['won'], bc['n'])), best_n=f"{bc['n']:,}"))
            if big('depth', 'long') and big('depth', 'half-long') and f('depth', 'long')['returnSpeed'] - f('depth', 'half-long')['returnSpeed'] >= 0.5:
                notes.append(T('Your long serves come back faster: {long} m/s on average, against {half} for half-long ones. You land '
                               '{long_land} of third balls after a long serve and {half_land} after a half-long one.',
                               long=f('depth', 'long')['returnSpeed'], half=f('depth', 'half-long')['returnSpeed'],
                               long_land=p1(f('depth', 'long')['thirdLanded']), half_land=p1(f('depth', 'half-long')['thirdLanded'])))
            if big('spin', 'topspin') and big('spin', 'little spin') and abs(f('spin', 'topspin')['pointRate'] - f('spin', 'little spin')['pointRate']) >= 3:
                notes.append(T('Topspin serves win {top} of points, serves with little spin {little}.',
                               top=p1(f('spin', 'topspin')['pointRate']), little=p1(f('spin', 'little spin')['pointRate'])))
            rare = [s for s in SIDE_ORDER if ST[who, 'side', s]['n'] < 0.05 * landed]
            if rare and landed >= 200:
                notes.append(join(' ', [T('You have served {where} only {n} times in {total}.', where=SERVE_SIDE_LOW[s],
                                          n=f"{ST[who, 'side', s]['n']:,}", total=f'{landed:,}') for s in rare], ''))
            if len(best) >= 2:
                notes.append(T('Best serve: {best}, {best_rate} of points won over {best_n} serves. Weakest: {worst}, {worst_rate} over '
                               '{worst_n}.', best=lower(rbi(best[0], 'label')), best_rate=p1(best[0]['pointRate']),
                               best_n=f"{best[0]['n']:,}", worst=lower(rbi(best[-1], 'label')), worst_rate=p1(best[-1]['pointRate']),
                               worst_n=f"{best[-1]['n']:,}"))
        for i, text in enumerate(notes):
            serve_notes.append(put({'key': f'{lvl}|{who}|{i + 1}', 'level': lvl, 'who': who, 'rank': i + 1}, 'text', text))
write('serve_flow', serve_flow)
write('serve_types', serve_types)
write('serve_next', serve_next)
write('serve_notes', serve_notes)

days = []
for d in sorted(day_items):
    rows = [r for r, _, _ in day_items[d]]
    lv = sorted({r['level'] for r in rows})
    days.append({'key': d, 'date': d, 'level': lv[-1], 'levels': ' / '.join(map(str, lv)), 'matches': len(rows),
                 'wins': sum(r['result'] == 'Won' for r in rows), 'games': sum(r['gamesWon'] + r['gamesLost'] for r in rows),
                 'gamesWon': sum(r['gamesWon'] for r in rows),
                 'gameRate': pc(sum(r['gamesWon'] for r in rows), sum(r['gamesWon'] + r['gamesLost'] for r in rows)),
                 **agg([(y, p) for _, y, pts in day_items[d] for p in pts])})
write('days', days)

levels, insights, zones, wvl = [], [], [], []
for lvl in sorted(level_items):
    items = level_items[lvl]
    ms = [r for r in ai_ms if r['level'] == lvl]
    pa = [p for y, p in items if y == 'A']      # all AI matches put you on side A
    pm_you, pm_ai = player_metrics(pa, 'A'), player_metrics(pa, 'B')
    row = {'key': lvl, 'level': lvl, 'from': ms[0]['date'], 'to': ms[-1]['date'], 'matches': len(ms), **agg(items)}
    for k in METRICS:
        row['you_' + k] = r1(pm_you[k]); row['ai_' + k] = r1(pm_ai[k])
    levels.append(row)
    shot_mix.extend(mix_rows(f'L{lvl}', items))

    def ins(topic, item, n, k=None, k2=None, total=None):
        insights.append({'key': f'{lvl}|{topic}|{item}', 'level': lvl, 'topic': topic, 'item': item, 'n': n,
                         'share': pc(n, total) if total else None, 'k': k, 'rate': pc(k, n) if k is not None else None,
                         'k2': k2, 'rate2': pc(k2, n) if k2 is not None else None})

    lost = [(y, p) for y, p in items if p['winner'] != y]
    won = [(y, p) for y, p in items if p['winner'] == y]
    lc, wc = Counter(), Counter()
    for y, p in lost:
        h = p['hits']
        if h and h[-1]['side'] == y and not h[-1]['ok']:
            lc['serveMiss' if h[-1]['serve'] else 'returnMiss' if h[-1]['n'] == 2 else 'rallyMiss'] += 1
        elif h and h[-1]['side'] != y and h[-1]['ok']:
            lc['aiAce' if h[-1]['serve'] else 'aiWinner'] += 1
        else:
            lc['other'] += 1
    for y, p in won:
        h = p['hits']
        if h and h[-1]['side'] == y and h[-1]['ok']:
            wc['ace' if h[-1]['serve'] else 'winner'] += 1
        elif h and h[-1]['side'] != y and not h[-1]['ok']:
            wc['aiServeMiss' if h[-1]['serve'] else 'aiReturnMiss' if h[-1]['n'] == 2 else 'aiMiss'] += 1
        else:
            wc['other'] += 1
    for k in ('rallyMiss', 'returnMiss', 'serveMiss', 'aiWinner', 'aiAce', 'other'):
        ins('lost', k, lc[k], total=len(lost))
    ins('lost', 'yourMisses', lc['rallyMiss'] + lc['returnMiss'] + lc['serveMiss'], total=len(lost))
    ins('lost', 'aiOutright', lc['aiWinner'] + lc['aiAce'], total=len(lost))
    for k in ('winner', 'aiMiss', 'aiReturnMiss', 'aiServeMiss', 'ace', 'other'):
        ins('won', k, wc[k], total=len(won))
    for name, lo, hi in [('1', 1, 1), ('2', 2, 2), ('3', 3, 3), ('4', 4, 4), ('5-6', 5, 6), ('7-9', 7, 9), ('10+', 10, 999)]:
        xs = [p['winner'] == y for y, p in items if lo <= len(p['hits']) <= hi]
        ins('rally', name, len(xs), sum(xs), total=len(items))
    ins('rally', '1-2', sum(1 for y, p in items if len(p['hits']) <= 2),
        sum(1 for y, p in items if len(p['hits']) <= 2 and p['winner'] == y), total=len(items))
    ins('rally', '3+', sum(1 for y, p in items if len(p['hits']) >= 3),
        sum(1 for y, p in items if len(p['hits']) >= 3 and p['winner'] == y), total=len(items))
    for who in ('you', 'ai'):
        acc = defaultdict(lambda: [0, 0, 0])      # n, landed (or your return landed), you won
        for y, p in items:
            h = p['hits']
            if not h or (h[0]['side'] == y) != (who == 'you'):
                continue
            a = acc[spin_kind(h[0])]
            if who == 'you':
                a[0] += 1; a[1] += h[0]['ok']; a[2] += p['winner'] == y
            elif h[0]['ok']:                       # AI serves that landed: how your return did
                a[0] += 1; a[1] += len(h) >= 2 and h[1]['ok']; a[2] += p['winner'] == y
        tot = sum(a[0] for a in acc.values())
        for kind in ('topspin', 'little spin', 'backspin'):
            if kind in acc:
                a = acc[kind]
                ins(who + 'Serve', kind, a[0], a[2], a[1], total=tot)
    # serve zones, your view; youWon from your side
    zacc = defaultdict(lambda: [0, 0])
    for y, p in items:
        h = p['hits']
        if not h or not h[0]['ok']:
            continue
        rb = next((b for b in p['bounces'] if b['side'] != h[0]['side']), None)
        if not rb:
            continue
        server = 'You' if h[0]['side'] == y else 'AI'
        sx = 1 if y == 'A' else -1
        col, dep = zone(rb['pos'][0] * sx, rb['pos'][2] * sx)
        for c, d in ((col, dep), (col, 'all'), ('all', dep), ('all', 'all')):
            z = zacc[(server, c, d)]; z[0] += 1; z[1] += p['winner'] == y
    for (server, c, d), (n, w) in sorted(zacc.items()):
        zones.append({'key': f'{lvl}|{server}|{c}|{d}', 'level': lvl, 'server': server, 'col': c, 'depth': d,
                      'serves': n, 'youWon': w, 'youWonRate': pc(w, n)})
    for res in ('Won', 'Lost'):
        its = [(y, p) for d in day_items.values() for (r, y, pts) in d if r['level'] == lvl and r['result'] == res for p in pts]
        if its:
            wvl.append({'key': f'{lvl}|{res}', 'level': lvl, 'result': res,
                        'matches': sum(1 for r in ms if r['result'] == res), **agg(its)})

# ---------------- shot explorer: the kinds of ball that cost you most ----------------
# At the plan's level, your returns are grouped by the serve (side, spin, depth) and your rally shots by the ball that
# came (spin, side, fast or slower). A try is a ball you hit or one that landed untouched; it fails when you miss it or
# never reach it. A group's cost is how many more of its balls fail in a match than would at your usual rate for that
# kind of shot. Two scopes: recent (every match at that level from the plan's recent sessions on) and all.
assert FAST == PACE
MIN_GROUP, TOP_GROUPS = 30, 8
SIDE_TO = {'B': W('to your backhand side'), 'M': W('into the middle'), 'F': W('to your forehand side')}
PACE_WORD = {'f': W('fast'), 's': W('slower')}
C_SPIN = {v: k for k, v in SPIN_C.items()}
C_DEPTH = {'s': 'short', 'h': 'half-long', 'l': 'long'}
shot_groups = []
recent_from = plan[0]['recentFrom']
for scope, ms in (('recent', [r for r in lv_ms if r['date'] >= recent_from]), ('all', lv_ms)):
    base, groups = defaultdict(Counter), defaultdict(Counter)
    for r in (r for m in ms for r in shot_items.get(m['key'], [])):
        c = r.get('cls')
        if r['role'] == 'S' or not c or c[1] == '-' or (r['role'] == 'R' and c[2] == '-'):
            continue
        key = (r['role'], c[0], c[1], c[2], '') if r['role'] == 'R' else (r['role'], c[0], c[1], '', c[3])
        for t in (base[r['role']], groups[key]):
            t['n'] += 1
            t['failed'] += not r['ok']
            t['miss_' + r['miss']] += 1
    found = []
    for (role, spin, side, depth, pace), t in groups.items():
        usual = base[role]['failed'] / base[role]['n']
        if t['n'] >= MIN_GROUP and t['failed'] / t['n'] > usual:
            found.append((round((t['failed'] / t['n'] - usual) * t['n'] / len(ms), 3), role, spin, side, depth, pace, t, usual))
    found.sort(key=lambda g: (-g[0], g[1:6]))
    for i, (extra, role, spin, side, depth, pace, t, usual) in enumerate(found[:TOP_GROUPS]):
        row = {'key': f'{scope}|{i + 1}', 'scope': scope, 'rank': i + 1, 'level': plan_level, 'matches': len(ms),
               'from': recent_from if scope == 'recent' else None, 'role': role, 'spin': spin, 'side': side, 'depth': depth,
               'pace': pace, 'n': t['n'], 'failed': t['failed'], 'rate': pc(t['failed'], t['n']), 'usual': r1(100 * usual),
               'extra': round(extra, 2), 'net': t['miss_n'], 'long': t['miss_l'], 'wide': t['miss_w'], 'unreached': t['miss_x']}
        put(row, 'label', T('Returns of serves: {type}', type=lower(type_label('recv', {'B': BH, 'M': 'middle', 'F': FH}[side],
                                                                                C_SPIN[spin], C_DEPTH[depth])))
            if role == 'R' else T('Rally shots against {pace} {spin} {side}', pace=PACE_WORD[pace], spin=SPIN_WORD[C_SPIN[spin]],
                                  side=SIDE_TO[side]))
        shot_groups.append(row)
write('shots', shots)
write('shot_groups', shot_groups)


# ---------------- findings: what decides your points at your main level ----------------
# The six findings at the top of the page. Each headline is picked by a fixed rule from the numbers in its text, so it
# holds for any player and changes when the numbers do. A finding without enough matches or shots behind it is left
# out. The main level is the training plan's: the AI level with the most points in your last five sessions.
LEVEL_WORDS = {100: (W('legendary'), W('Legendary'))}
FIND_GAP = 5            # percentage points between two rates before a headline calls one better
FIND_LAND_GAP = 3       # the same for landing rates, which rest on thousands of shots
FIND_PACE_GAP = 0.5     # m/s of rally speed
FIND_MIN = 30           # fewest serves behind a serve comparison
FIND_MIN_SHOTS = 50     # fewest shots of a type behind a shot comparison
FIND_MIN_MATCHES = 3    # fewest matches won (and lost) behind the won-versus-lost finding
SHOT_ONE = {'Drive': W('drive'), 'SlowLoop': W('slow loop'), 'FastLoop': W('fast loop'), 'Push': W('push'), 'Chop': W('chop')}
SHOT_MANY = {'Drive': W('drives'), 'SlowLoop': W('slow loops'), 'FastLoop': W('fast loops'), 'Push': W('pushes'), 'Chop': W('chops')}
SERVE_SUBJECT = {'topspin': W('Your topspin serves'), 'backspin': W('Your backspin serves'),
                 'little spin': W('Your serves with little spin')}
SERVE_ADJ = {'topspin': W('topspin'), 'backspin': W('backspin'), 'little spin': W('little-spin')}
AI_SERVES = {'topspin': W('its topspin serves'), 'backspin': W('its backspin serves'), 'little spin': W('its serves with little spin')}
cap = lambda b: b.map(lambda s: s[:1].upper() + s[1:], lambda s: s)


def level_words(lv):
    name, title = LEVEL_WORDS.get(lv, (None, None))
    row = {}
    put(row, 'levelName', name or T('level {lv}', lv=lv))
    put(row, 'levelTitle', title or T('Level {lv}', lv=lv))
    put(row, 'levelText', T('{name} (level {lv})', name=name, lv=lv) if name else T('level {lv}', lv=lv))
    return row


def bold(v, fmt=p1):
    return f'**{fmt(v)}**' if v is not None else '**—**'


def findings_rows(L):
    keyed = lambda rows: {str(r['key']): r for r in rows}
    I, Wv, LV, Z, S = keyed(insights), keyed(wvl), keyed(levels), keyed(zones), keyed(shot_mix)
    g = lambda d, k, f: (d.get(k) or {}).get(f)
    out = []

    # Bars go in flat columns (bar1, bar1_label, bar1_tone, bar2 ...; `bars` is how many): a dashboard host hands a
    # nested list in a row to the page as JSON text, so rows hold plain values only.
    def add(key, title, text, bars):
        row = put(put({'key': key, 'rank': len(out) + 1, 'level': L}, 'title', title), 'text', text)
        n = 0
        for a, v, t in bars:
            if v is not None:
                n += 1
                row[f'bar{n}'] = v
                row[f'bar{n}_tone'] = t
                put(row, f'bar{n}_label', a)
        row['bars'] = n
        out.append(row)

    # how the points you lose end
    miss, ai_out = g(I, f'{L}|lost|yourMisses', 'share'), g(I, f'{L}|lost|aiOutright', 'share')
    if miss is not None and ai_out is not None:
        title = (W('Most lost points are your own misses') if miss >= 50 else
                 W("Most lost points are the AI's winners") if ai_out >= 50 else
                 W("Your misses and the AI's winners split your lost points"))
        add('misses', title,
            T("Of the points you lose, {miss} end with your shot missing: rally shots {rally}, returns {ret}, serves {serve}. "
              "The AI wins {ai} with a shot you can't get back.",
              miss=bold(miss), rally=bold(g(I, f'{L}|lost|rallyMiss', 'share')), ret=bold(g(I, f'{L}|lost|returnMiss', 'share')),
              serve=bold(g(I, f'{L}|lost|serveMiss', 'share')), ai=bold(ai_out)),
            [(W('Lost to your own miss'), miss, 'you'), (W('Lost to an AI winner'), ai_out, 'ai')])

    # matches won against matches lost: landing the ball, and pace
    w, l = Wv.get(f'{L}|Won'), Wv.get(f'{L}|Lost')
    if (w and l and w['matches'] >= FIND_MIN_MATCHES and l['matches'] >= FIND_MIN_MATCHES
            and None not in (w['rallyLanded'], l['rallyLanded'], w['rallySpeed'], l['rallySpeed'])):
        dl, ds = w['rallyLanded'] - l['rallyLanded'], w['rallySpeed'] - l['rallySpeed']
        land, pace = dl >= FIND_LAND_GAP, abs(ds) >= FIND_PACE_GAP
        title = (W('Landing the ball wins matches, not speed') if land and not pace else
                 W('In matches you win, you land more and hit harder') if land and ds > 0 else
                 W('In matches you win, you land more and hit softer') if land else
                 W('Pace, more than landing, sets your wins apart') if pace and ds > 0 else
                 W('You hit softer in the matches you win') if pace else
                 W('Your wins and losses look alike on landing and pace'))
        add('landing', title,
            T('In matches you won, {w_rally} of your rally shots and {w_ret} of your returns landed. In matches you lost: {l_rally} '
              'and {l_ret}. Your rally speed was {w_speed} m/s in matches won and {l_speed} m/s in matches lost.',
              w_rally=bold(w['rallyLanded']), w_ret=bold(w['returnsLanded']), l_rally=bold(l['rallyLanded']),
              l_ret=bold(l['returnsLanded']), w_speed=bold(w['rallySpeed'], ER1), l_speed=bold(l['rallySpeed'], ER1)),
            [(W('Rally shots landed, matches won'), w['rallyLanded'], 'you'), (W('Rally shots landed, matches lost'), l['rallyLanded'], 'ai')])

    # the return
    lv = LV.get(str(L))
    if lv and lv.get('you_returnSuccess') is not None and lv.get('ai_returnSuccess') is not None:
        yr, ar = lv['you_returnSuccess'], lv['ai_returnSuccess']
        own = [lv.get('servesLanded'), lv.get('returnsLanded'), lv.get('rallyLanded')]
        weakest = None not in own and own[1] <= min(own[0], own[2])
        title = ((W('The return is your weakest shot') if weakest else W('The AI returns better than you do')) if yr <= ar - FIND_GAP else
                 W('You return better than the AI does') if yr >= ar + FIND_GAP else W('You return about as well as the AI'))
        text = T('You land {you} of returns; the AI lands {ai}.', you=bold(yr), ai=bold(ar))
        bh, fh = Z.get(f'{L}|AI|{BH}|all'), Z.get(f'{L}|AI|{FH}|all')
        if bh and fh and bh['serves'] >= FIND_MIN and fh['serves'] >= FIND_MIN:
            text += T(' When its serve lands on your backhand side ({where}) you win {bh} of points, on your forehand side {fh}.',
                      where=LAND_SIDE[BH], bh=bold(bh['youWonRate']), fh=bold(fh['youWonRate']))
        spins = [(k, I[f'{L}|aiServe|{k}']) for k in ('topspin', 'backspin', 'little spin')
                 if f'{L}|aiServe|{k}' in I and I[f'{L}|aiServe|{k}']['n'] >= FIND_MIN and I[f'{L}|aiServe|{k}']['rate'] is not None]
        if len(spins) >= 2:
            parts = [T('{rate} of points against {what}' if i == 0 else '{rate} against {what}', rate=bold(r['rate']), what=AI_SERVES[k])
                     for i, (k, r) in enumerate(spins)]
            text += T(' You win {parts}.', parts=bilist(parts, '，'))
        add('return', title, text, [(W('Your returns that land'), yr, 'you'), (W("The AI's returns that land"), ar, 'ai')])

    # short points against rallies
    r12, r3 = g(I, f'{L}|rally|1-2', 'rate'), g(I, f'{L}|rally|3+', 'rate')
    if r12 is not None and r3 is not None:
        d = r3 - r12
        title = ((W("You're stronger once a rally starts") if r3 >= 55 else
                  W("Past the first two shots you're close to even") if r3 >= 45 else
                  W('You do better once a rally starts')) if d >= FIND_GAP else
                 W('The first two shots are your better chance') if d <= -FIND_GAP else
                 W('Short points and rallies go about the same for you'))
        add('rally', title,
            T('Points that end on the serve or the return give you {short}. Once a point reaches a third shot, you win {long} of them.',
              short=bold(r12), long=bold(r3)),
            [(W('Won when it ends by shot 2'), r12, 'you'), (W('Won when it reaches shot 3'), r3, 'you')])

    # your serve: spin and depth
    kinds = [(k, I[f'{L}|youServe|{k}']) for k in ('topspin', 'backspin', 'little spin')
             if f'{L}|youServe|{k}' in I and I[f'{L}|youServe|{k}']['n'] >= FIND_MIN and I[f'{L}|youServe|{k}']['rate'] is not None]
    # depth: short serves (first bounce within 50 cm of the net) against all your other serves that landed
    short, every = Z.get(f'{L}|You|all|short'), Z.get(f'{L}|You|all|all')
    depth, rest = None, None
    if short and every and short['serves'] >= FIND_MIN and every['serves'] - short['serves'] >= FIND_MIN:
        rest = pc(every['youWon'] - short['youWon'], every['serves'] - short['serves'])
        if short['youWonRate'] <= rest - FIND_GAP:
            depth = 'short'
        elif short['youWonRate'] >= rest + FIND_GAP:
            depth = 'long'
    if kinds and (len(kinds) >= 2 or depth):
        used = max(kinds, key=lambda t: t[1]['n'])
        best = max(kinds, key=lambda t: t[1]['rate'])
        spin = None
        if best[0] != used[0] and best[1]['rate'] - used[1]['rate'] >= FIND_GAP:
            spin = W('Serve with less spin') if best[0] == 'little spin' else T('Serve with more {kind}', kind=SPIN_WORD[best[0]])
        title = (T('{spin}, and not too short', spin=spin) if spin and depth == 'short' else
                 T('{spin}, and keep it short', spin=spin) if spin and depth == 'long' else
                 spin if spin else W('Your short serves win less than the rest') if depth == 'short' else
                 W('Your short serves win more than the rest') if depth == 'long' else
                 W('Your serves win about the same whatever the spin'))
        text = T('{share} of your serves carry {kind} and win {rate} of points.',
                 share=bold(used[1]['share']), kind=SPIN_WORD[used[0]], rate=bold(used[1]['rate']))
        for k, r in kinds:
            if k != used[0]:
                text += T(' {what} win {rate}.', what=SERVE_SUBJECT[k], rate=bold(r['rate']))
        if rest is not None:
            text += T(' Serves that bounce within 50 cm of the net win {short} ({n} serves); the rest win {rest}.',
                      short=bold(short['youWonRate']), n=f"{short['serves']:,}", rest=bold(rest))
        if len(kinds) >= 2 and (spin or not depth):
            other = best if best[0] != used[0] else max((t for t in kinds if t[0] != used[0]), key=lambda t: t[1]['rate'])
            bars = [(T('Points won, {kind} serves', kind=SERVE_ADJ[other[0]]), other[1]['rate'], 'you'),
                    (T('Points won, {kind} serves', kind=SERVE_ADJ[used[0]]), used[1]['rate'], 'you')]
        else:
            bars = [(W('Points won, short serves'), short['youWonRate'], 'you'), (W('Points won, other serves'), rest, 'you')]
        add('serve', title, text, bars)

    # rally shots by type
    mine = [S[f'L{L}|You|{s}'] for s in SHOT_ORDER if f'L{L}|You|{s}' in S and S[f'L{L}|You|{s}']['shots'] >= FIND_MIN_SHOTS]
    theirs = [S[f'L{L}|AI|{s}'] for s in SHOT_ORDER if f'L{L}|AI|{s}' in S and S[f'L{L}|AI|{s}']['shots'] >= FIND_MIN_SHOTS]
    if len(mine) >= 2:
        most = max(mine, key=lambda r: r['shots'])
        best = max(mine, key=lambda r: r['landed'] or 0)
        one, many = lambda r: SHOT_ONE[r['shot']], lambda r: SHOT_MANY[r['shot']]
        if best is not most and (best['landed'] or 0) - (most['landed'] or 0) >= FIND_LAND_GAP:
            title = T('Your {best} lands more often than your {most}', best=one(best), most=one(most))
        elif best is most:
            title = T('Your {shot} is your most used and your surest shot', shot=one(most))
            best = max((r for r in mine if r is not most), key=lambda r: r['landed'] or 0)
        else:
            title = W('Your shots land about equally often, whatever the type')
        text = T('{most} are {share} of your rally shots and land {land} of the time. {best} land {best_land} and were your last '
                 'shot in {wins} points you won.', most=cap(many(most)), share=bold(most['share']), land=bold(most['landed']),
                 best=cap(many(best)), best_land=bold(best['landed']), wins=bold(best['winners'], INT))
        if theirs:
            t = max(theirs, key=lambda r: r['shots'])
            text += T(" The AI's most used shot is the {shot}: {share} of its rally shots, and it lands {land}.",
                      shot=one(t), share=bold(t['share']), land=bold(t['landed']))
        add('shots', title, text,
            [(T('Your {shots} that land', shots=many(best)), best['landed'], 'you'),
             (T('Your {shots} that land', shots=many(most)), most['landed'], 'you')])
    return out


ER1 = lambda v: f'{v:.1f}'
INT = lambda v: f'{v:,}'
def shot_secs(rows):
    """How long a typical shot takes from one bat to the next, in seconds: the median gap between bat contacts over
    every replayed rally. The page's switches fade in over this time, so a change takes as long as a ball crossing."""
    gaps = []
    for r in rows:
        hs = [int(e.split(',')[4]) / 1000 for e in r['track'].split(';') if e.startswith('h,')]
        gaps += [b - a for a, b in zip(hs, hs[1:]) if 0.15 < b - a < 2.5]
    if not gaps:
        return None
    gaps.sort()
    n = len(gaps)
    return round(gaps[n // 2] if n % 2 else (gaps[n // 2 - 1] + gaps[n // 2]) / 2, 2)


findings = []
if level_items:
    main = plan_level if session_rows else max(level_items, key=lambda k: len(level_items[k]))
    ms_main = [r for r in ai_ms if r['level'] == main]
    findings.append({'key': 'main', 'rank': 0, 'level': main, 'matches': len(ms_main), 'hand': HAND, 'shotSecs': shot_secs(replay),
                     'from': ms_main[0]['date'] if ms_main else None, 'to': ms_main[-1]['date'] if ms_main else None,
                     **level_words(main)})
    findings += findings_rows(main)

write('findings', findings)
write('levels', levels)
write('insights', insights)
write('zones', zones)
write('won_vs_lost', wvl)
write('matches', matches)
write('match_sums', match_sums)
write('shot_mix', shot_mix)
write('serves', serves)
write('points', points)
write('replay', replay)
write('videos', [{'key': v['id'], 'kind': v['kind'], 'title': v['title'], 'url': v['url'], 'uploaded': v['at'],
                  'session': ms[0].get('session') if ms else v.get('session'), 'matches': len(ms),
                  'duration': round(v.get('duration') or 0)}
                 for v in VIDEOS for ms in [video_matches.get(v['id'], [])]])
