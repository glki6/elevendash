"""Extract paddle hits (post-hit position, velocity, spin) from an Eleven log, inside running matches.
Each '[Physics-BallCollisions]Dynamic Collision...' block = one paddle contact; side by table half (z<0 -> A, z>0 -> B)."""
import re, sys, math
vec = lambda s: tuple(float(x) for x in s.split(','))
post = re.compile(r'postCollisionState:\{pos:\(([^)]*)\),vel:\(([^)]*)\),rRate:\(([^)]*)\)')
def hits(path):
    out, running, pending = [], False, False
    for line in open(path, encoding='utf-8', errors='replace'):
        if '[matchRunning] from [False] to [True]' in line: running = True
        elif '[matchRunning] from [True] to [False]' in line: running = False
        elif 'Dynamic Collision...' in line: pending = True
        elif pending and 'postCollisionState:' in line:
            pending = False
            m = post.search(line)
            if running and m:
                p, v, w = vec(m[1]), vec(m[2]), vec(m[3])
                out.append({'t': line[12:20], 'side': 'A' if p[2] < 0 else 'B', 'pos': p, 'vel': v, 'rrate': w,
                            'speed': math.hypot(*v), 'spin': math.hypot(*w) / 360})
    return out
if __name__ == '__main__':
    H = hits(sys.argv[1]); print(len(H), 'hits', sum(h['side']=='A' for h in H), 'A', sum(h['side']=='B' for h in H), 'B')
