"""Exploratory stats for takeaways. python -I analyze.py <logs-dir> [level]"""
import glob, os, sys
from collections import Counter, defaultdict
from statistics import mean
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))
from elevendash.extract import extract_log
logs, lvl = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 100
P = []  # (match, point)
M = []
for f in sorted(glob.glob(os.path.join(logs, 'ALL-*.log'))):
    for m in extract_log(f):
        if m['ai'] and m['difficulty'] == lvl and m['games'] and m.get('end'):
            M.append(m)
            for g in m['games']:
                for p in g['points']:
                    P.append((m, p))
pct = lambda a, b: f'{100*a/b:.0f}% ({a}/{b})' if b else '-'
print('matches', len(M), 'points', len(P))
won = [p for m, p in P if p['winner'] == 'A']
print('points won', pct(len(won), len(P)))
sv = [p for m, p in P if p['server'] == 'A']; rv = [p for m, p in P if p['server'] == 'B']
print('won on own serve', pct(sum(p['winner']=='A' for p in sv), len(sv)), ' on AI serve', pct(sum(p['winner']=='A' for p in rv), len(rv)))
# how points end
def ending(p):
    h = p['hits']
    if not h: return 'no hit (toss/fault)'
    last = h[-1]
    who = 'you' if last['side'] == 'A' else 'AI'
    if last['ok']:
        return f'{who} hit a winner (other side missed)'
    return f'{who} missed' + (' serve' if last['serve'] else ' return' if last['n'] == 2 else '')
lost = [p for m, p in P if p['winner'] == 'B']
print('\nHOW YOU LOSE POINTS'); [print(' ', k, pct(v, len(lost))) for k, v in Counter(map(ending, lost)).most_common()]
print('HOW YOU WIN POINTS'); [print(' ', k, pct(v, len(won))) for k, v in Counter(map(ending, won)).most_common()]
# rally length buckets
print('\nWIN RATE BY RALLY LENGTH (hits)')
b = defaultdict(list)
for m, p in P:
    n = len(p['hits']); k = '1' if n <= 1 else '2' if n == 2 else '3' if n == 3 else '4' if n==4 else '5-6' if n <= 6 else '7-9' if n <= 9 else '10+'
    b[k].append(p['winner'] == 'A')
for k in ['1','2','3','4','5-6','7-9','10+']:
    print(' ', k, pct(sum(b[k]), len(b[k])))
# serves by spin type
def stype(h): return 'topspin' if h['top'] > 20 else 'backspin' if h['top'] < -20 else 'little spin'
for who, side in (('YOUR', 'A'), ("AI's", 'B')):
    print(f'\n{who} SERVES by spin: share, lands, server wins point, avg speed')
    ss = [(p, p['hits'][0]) for m, p in P if p['hits'] and p['hits'][0]['side'] == side]
    g = defaultdict(list)
    for p, h in ss: g[stype(h)].append((p, h))
    for k, v in g.items():
        print(f'  {k:12s} {pct(len(v), len(ss)):>18s} lands {pct(sum(h["ok"] for p,h in v), len(v)):>16s} wins {pct(sum(p["winner"]==side for p,h in v), len(v)):>16s} speed {mean(h["speed"] for p,h in v):.1f} spin {mean(h["spin"] for p,h in v):.0f}')
# serve placement: depth of first bounce on receiver side (z from net), width
print('\nSERVE PLACEMENT (receiver-side bounce, from server view)')
for who, side in (('you', 'A'), ('AI', 'B')):
    s = 1 if side == 'A' else -1
    g = defaultdict(list)
    for m, p in P:
        if not p['hits'] or p['hits'][0]['side'] != side or not p['hits'][0]['ok']: continue
        ob = next((x for x in p['bounces'] if x['side'] != side), None)
        if not ob: continue
        z = ob['pos'][2] * s; x = ob['pos'][0] * s
        depth = 'short' if z < 0.5 else 'mid' if z < 1.0 else 'long'
        width = 'left' if x < -0.25 else 'right' if x > 0.25 else 'middle'
        g[depth].append(p['winner'] == side); g[width].append(p['winner'] == side)
    for k in ['short', 'mid', 'long', 'left', 'middle', 'right']:
        print(f'  {who} {k:7s} share {len(g[k])}  server wins {pct(sum(g[k]), len(g[k]))}')
# return quality vs AI serve types
print('\nYOUR RETURN vs AI serve spin: return lands / you win point')
g = defaultdict(list)
for m, p in P:
    h = p['hits']
    if len(h) >= 2 and h[0]['side'] == 'B' and h[0]['ok']:
        g[stype(h[0])].append((h[1]['ok'], p['winner'] == 'A'))
for k, v in g.items(): print(f'  {k:12s} n={len(v)} lands {pct(sum(a for a,_ in v), len(v))} win {pct(sum(b for _,b in v), len(v))}')
# shot types
print('\nSHOTS (rally) share / success / avg speed')
for who, side in (('you', 'A'), ('AI', 'B')):
    hs = [h for m, p in P for h in p['hits'] if h['side'] == side and not h['serve']]
    c = Counter(h['shot'] for h in hs)
    for k, v in c.most_common():
        xs = [h for h in hs if h['shot'] == k]
        print(f'  {who:3s} {k:9s} {pct(v, len(hs)):>18s} lands {pct(sum(h["ok"] for h in xs), v):>18s} speed {mean(h["speed"] for h in xs):.1f} winners {sum(h["win"] for h in xs)}')
# won vs lost matches
print('\nWON vs LOST MATCHES (your numbers)')
def mstats(m):
    pts = [p for g in m['games'] for p in g['points']]
    mine = [h for p in pts for h in p['hits'] if h['side'] == 'A']
    rally = [h for h in mine if not h['serve']]
    ret = [h for h in mine if h['n'] == 2]
    serv = [p for p in pts if p['server'] == 'A']
    return dict(points=sum(p['winner']=='A' for p in pts)/len(pts), rallyspeed=mean(h['speed'] for h in rally) if rally else 0,
                rallyok=mean(h['ok'] for h in rally) if rally else 0, retok=mean(h['ok'] for h in ret) if ret else 0,
                servewin=mean(p['winner']=='A' for p in serv) if serv else 0, rallylen=mean(len(p['hits']) for p in pts),
                push=mean(h['shot'] in ('Push','Chop') for h in rally) if rally else 0, loops=mean(h['shot'] in ('SlowLoop','FastLoop') for h in rally) if rally else 0)
res = lambda m: sum(g['score'][0] > g['score'][1] for g in m['games']) > sum(g['score'][1] > g['score'][0] for g in m['games'])
W = [mstats(m) for m in M if res(m)]; L = [mstats(m) for m in M if not res(m)]
print('  won', len(W), 'lost', len(L))
for k in W[0]: print(f'  {k:10s} won {mean(x[k] for x in W):.3f}  lost {mean(x[k] for x in L):.3f}')
