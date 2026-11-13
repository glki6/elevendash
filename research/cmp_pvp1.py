import json, math, statistics as st, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hits_from_log import hits
mine = hits(sys.argv[1])
m = json.load(open(os.path.join(os.environ.get('ELEVENDASH_HOME') or os.getcwd(), '11hero-match-pvp1.json')))
hero = [c for s in m['sets'] for p in s['points'] for c in p['contacts'] if c['contactType'] == 'Hit' and not c['playerIsHome']]
print(len(mine), len(hero))
ds = [abs(a['speed'] - b['velSqrt']) for a, b in zip(mine, hero)]; dw = [abs(a['spin'] - b['rrateSqrt']) for a, b in zip(mine, hero)]
print('speed diff max %.4f mean %.4f' % (max(ds), st.mean(ds)), ' spin diff max %.3f mean %.3f' % (max(dw), st.mean(dw)))
def topbot(h, sign):
    vx, vy, vz = h['vel']; wx, wy, wz = [x / 360 for x in h['rrate']]
    n = math.hypot(vx, vz); ax, az = (vz / n, -vx / n)
    return sign * (wx * ax + wz * az)
for sign in (1, -1):
    d = [abs(topbot(a, sign) - b['bmSpinTopBottom']) for a, b in zip(mine, hero)]
    print('topbot sign', sign, 'max diff %.2f mean %.2f' % (max(d), st.mean(d)))
for a, b in list(zip(mine, hero))[:6]:
    print(round(a['speed'], 2), round(b['velSqrt'], 2), round(a['spin'], 1), round(b['rrateSqrt'], 1), round(topbot(a, 1), 1), round(topbot(a, -1), 1), round(b['bmSpinTopBottom'], 1), b['shotType'])
