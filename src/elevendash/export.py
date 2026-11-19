"""Matches, points and shots as CSV or JSON, for other tools.

Written from the built data, never from the logs, so it holds match data only: no log lines, no account tokens, no
account details and no names (the built data has none). Links to your video uploads are left out as well.

Three tables, AI and online matches together:
  matches   one row a match: when, against what, the score, and the 11hero-style numbers for both sides
  points    one row a point: who served, how long it was, how it ended
  shots     one row for every shot of yours, and for every ball that beat you without a touch
columns.txt, written beside them, says what each column of points and shots holds.
"""
import csv
import json
import os

# a shot as the builder packs it (builddata.SHOT_FIELDS; a test holds the two lists together), and what each number
# is divided by to give metres, metres a second, seconds or degrees
SHOT_FIELDS = ['n', 'role', 'shot', 'ok', 'miss', 'speed', 'top', 'win', 'cx', 'cy', 'inShot', 'inSpeed', 'inTop', 'bx', 'bz',
               'since', 'rise', 'cls', 'up', 'cz', 'lx', 'lz']
SCALE = {'speed': 10, 'inSpeed': 10, 'cx': 100, 'cy': 100, 'cz': 100, 'bx': 100, 'bz': 100, 'lx': 100, 'lz': 100, 'since': 1000, 'up': 10}
WHOLE = ('n', 'ok', 'win', 'top', 'inTop')
LEAVE = ('video', 'videoT')
FIRST = ['key', 'date', 'start', 'end', 'vs', 'level', 'ranked', 'result', 'score', 'gamesWon', 'gamesLost', 'points', 'pointsWonN',
         'pointRate', 'session', 'sessionMatch', 'dayMatch', 'rallyLength', 'ballDistance']
FORMATS = ('csv', 'json')

COLUMNS = """elevendash export: what the columns hold

Coordinates are in your view of the table, in metres: x is across (plus is your right), z is along it from the net
(your half is below 0, the far half above 0), y is the height, as the game logs it. Speeds are metres a second, spin is
turns a second (top: plus is topspin, minus is backspin).

matches   one row a match. key is the match's start (date and time) and ties the three tables together.
          vs is AI or Online; level is the AI's level (999 for an online match); you_ and ai_ columns are the same
          measure for you and for the other side (the AI or your opponent).

points    one row a point.
  match, game, point   which point
  served               You or AI (the other side, also online)
  hits                 shots in the point, both players
  won                  1 when you won it
  ending               your winner, AI error, your error, AI winner or other
  youBefore, aiBefore  the score in the game before the point

shots     one row for every shot of yours, and for every ball that landed and you did not reach (shot X).
  match, game, point   which point
  n                    the shot's number in the point (the serve is 1)
  role                 S serve, R return of serve, A any later shot
  shot                 S serve, D drive, L slow loop, F fast loop, P push, C chop, X a ball you did not reach
  ok                   1 when it landed
  miss                 for a miss: n into or short of the net, l long, w wide, o other, u unknown, x not reached
  speed, top           your shot off the bat
  win                  1 when the game counted it as a winner
  cx, cy, cz           where your bat met the ball
  up                   the angle the ball left your bat at, in degrees above level
  lx, lz               where your shot bounced on the far half, when it landed
  inShot, inSpeed, inTop   the shot that came at you, off the other bat
  bx, bz               where that ball bounced on your half
  since                seconds from that bounce to your bat
  rise                 r when you took the ball still rising, f when it was falling
  cls                  the kind of ball that came at you, four letters: spin (t topspin, n little, b backspin),
                       side (B your backhand side, M middle, F your forehand side), depth of the bounce (s short,
                       h half-long, l long), pace (f 10 m/s or more, s slower); - where the log does not say
"""


def _rows(build, name):
    try:
        with open(os.path.join(build, name + '.json'), encoding='utf-8') as f:
            return json.load(f)['rows']
    except (FileNotFoundError, KeyError, ValueError):
        return []


def _columns(rows, first):
    seen = dict.fromkeys(k for r in rows for k in r)
    return [k for k in first if k in seen] + [k for k in seen if k not in first]


def tables(build):
    """{'matches' | 'points' | 'shots': (columns, rows)} from a workspace's built data."""
    matches = [{k: v for k, v in r.items() if k not in LEAVE} for r in _rows(build, 'matches')]
    points = [{k: v for k, v in r.items() if k not in LEAVE} for r in _rows(build, 'points')]
    shots = []
    for row in _rows(build, 'shots'):
        for one in (row.get('s') or '').split(';'):
            a = one.split(',')
            if len(a) < 3:
                continue
            game, _, point = a[0].partition('.')
            r = {'match': row['key'], 'game': int(game), 'point': int(point)}
            for f, v in zip(SHOT_FIELDS, a[1:]):
                if v == '':
                    r[f] = None
                elif f in SCALE:
                    r[f] = int(v) / SCALE[f]
                elif f in WHOLE:
                    r[f] = int(v)
                else:
                    r[f] = v
            for f in SHOT_FIELDS[len(a) - 1:]:
                r[f] = None
            shots.append(r)
    return {'matches': (_columns(matches, FIRST), matches),
            'points': (_columns(points, ['key', 'match', 'game', 'point', 'served', 'hits', 'won', 'ending', 'youBefore', 'aiBefore']), points),
            'shots': (['match', 'game', 'point'] + SHOT_FIELDS, shots)}


def write(build, out_dir, fmt='csv'):
    """Write the three tables and columns.txt into out_dir. Returns {'dir', 'files': [names], 'rows': {table: how many}}."""
    if fmt not in FORMATS:
        raise ValueError(f'format must be one of {", ".join(FORMATS)}')
    got = tables(build)
    if not got['matches'][1]:
        raise ValueError('there is no match data to export yet')
    os.makedirs(out_dir, exist_ok=True)
    files = []
    for name, (cols, rows) in got.items():
        path = os.path.join(out_dir, f'{name}.{fmt}')
        if fmt == 'csv':
            with open(path, 'w', encoding='utf-8', newline='') as f:
                w = csv.writer(f)
                w.writerow(cols)
                w.writerows([['' if r.get(c) is None else r[c] for c in cols] for r in rows])
        else:
            with open(path, 'w', encoding='utf-8', newline='\n') as f:
                json.dump(rows, f, ensure_ascii=False, separators=(',', ':'))
        files.append(os.path.basename(path))
    with open(os.path.join(out_dir, 'columns.txt'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(COLUMNS)
    return {'dir': os.path.abspath(out_dir), 'files': files + ['columns.txt'], 'rows': {k: len(v[1]) for k, v in got.items()}}
