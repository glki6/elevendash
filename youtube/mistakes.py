r"""Cut a session's "misses to work on" reel from its full recording and upload it to YouTube (unlisted).

    mistakes.py FILE [--seconds 100] [--dry-run] [--no-upload] [--again]

FILE is a recording that session_video.py has already uploaded, after a rebuild (refresh.py) that took in its
matches: the reel is planned from the dashboard's shot list (build/shots.json), the same one the shot explorer shows.

Every shot of yours against the AI is grouped by the ball that came at you, exactly as in the shot explorer: a return
by the serve's spin, side and depth; a rally shot by the ball's spin, side and pace. The kinds of ball you missed (or
never reached) most often in this session come first, most misses first. For each kind the reel shows a few of the
misses back to back, spread over the session, and then the same ball on occasions when your shot landed, so the two
can be compared. A caption says which ball it is, how often you missed it in the session, and how each miss ended.

Each clip starts just before your previous shot (or at the toss) and runs until the ball is dead. The cut itself is
the highlight reel's: decoded and encoded on the graphics card at idle priority, the recording only read.
Run it with the environment beside it:  youtube\.venv\Scripts\python.exe -I youtube\mistakes.py FILE
"""
import argparse
import datetime
import json
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import highlights as hl     # noqa: E402  (the cutter, the clock and the workspace)
import yt                   # noqa: E402
from elevendash import extract as ett_extract     # noqa: E402

GROUPS, MISSES, MADE = 4, 4, 2      # kinds of ball in the reel; misses and landed shots shown for each
MIN_MISSES = 3                      # a kind of ball needs this many misses in the session to get in
BEFORE, AFTER_MISS, AFTER_MADE = 0.9, 1.3, 1.4      # seconds before your previous shot; after the point; after your shot
SHOT_FIELDS = ['at', 'n', 'role', 'shot', 'ok', 'miss', 'speed', 'top', 'win', 'cx', 'cy', 'inShot', 'inSpeed', 'inTop',
               'bx', 'bz', 'since', 'rise', 'cls']
SPIN = {'t': 'topspin', 'n': 'little spin', 'b': 'backspin'}
SIDE = {'B': 'your backhand side', 'M': 'the middle', 'F': 'your forehand side'}
DEPTH = {'s': 'short', 'h': 'half-long', 'l': 'long'}
HOW = {'n': 'into the net', 'l': 'long', 'w': 'wide', 'o': 'missed', 'u': 'missed', 'x': 'not reached'}


def group_of(r):
    """The kind of ball a shot record answers, as the shot explorer groups it; None for serves and unplaced balls."""
    c = r['cls']
    if r['role'] == 'S' or len(c) != 4 or c[1] == '-':
        return None
    if r['role'] == 'R':
        return None if c[2] == '-' else ('R', c[0], c[1], c[2])
    return ('A', c[0], c[1], c[3])


def label(g):
    role, spin, side, last = g
    if role == 'R':
        return f"Returning a {DEPTH[last]} {'no-spin' if spin == 'n' else SPIN[spin]} serve to {SIDE[side]}"
    ball = {'t': 'topspin', 'b': 'backspin', 'n': 'ball with little spin'}[spin]
    return f"{'Fast' if last == 'f' else 'Slower'} {ball} to {SIDE[side]}"


def shot_rows(build):
    """Match key -> the dashboard's shot records for it (dicts with the fields of SHOT_FIELDS)."""
    try:
        with open(os.path.join(build, 'shots.json'), encoding='utf-8') as f:
            rows = json.load(f)['rows']
    except (OSError, ValueError, KeyError):
        return {}
    return {r['key']: [dict(zip(SHOT_FIELDS, s.split(','))) for s in r['s'].split(';') if s] for r in rows}


def candidates(row, logs, build):
    """Every shot of yours against the AI in the recording that has a group and fits in the video, with its clip window.

    Returns (candidates, match keys the shot list does not have)."""
    out, missing = [], []
    shots, known = shot_rows(build), hl.dashboard_matches()
    for s in row['sync']:
        for mi, m in enumerate(mm for mm in ett_extract.extract_log(os.path.join(logs, s['log'])) if mm['games'] and mm.get('end')):
            if not m['ai']:
                continue
            mid = f"{m['date']} {m['start']}"
            if mid not in shots:
                missing.append(mid)
                continue
            session, number = known.get(mid, (None, None))
            mine = 0 if m['you'] == 'A' else 1
            to_video = lambda t: t - s['lag'] + row.get('audio_start', 0)
            for r in shots[mid]:
                g = group_of(r)
                gi, pi = (int(x) - 1 for x in r['at'].split('.'))
                p = m['games'][gi]['points'][pi]
                if g is None or p.get('t0') is None or p.get('t1') is None:
                    continue
                at = {h['n']: h['gt'] for h in p['hits'] if h.get('gt') is not None}
                n, ok = int(r['n']), r['ok'] == '1'
                if (n not in at and r['shot'] != 'X') or n - 1 not in at:
                    continue
                a = at[n - 2] - BEFORE if n - 2 in at else p['t0'] - hl.LEAD
                b = min(at[n] + AFTER_MADE, p['t1'] + AFTER_MISS) if ok else p['t1'] + AFTER_MISS
                a, b = to_video(max(a, p['t0'] - hl.LEAD)), to_video(b)
                if a < 0 or b > row['duration'] or b - a < 1.5:
                    continue
                out.append({'key': f'{mid}|{gi + 1}|{pi + 1}|{n}', 'match': mid, 'session': session, 'matchNo': number or mi + 1,
                            'game': gi + 1, 'you': p['score'][mine], 'ai': p['score'][1 - mine], 'group': g, 'ok': ok,
                            'miss': r['miss'], 'a': a, 'b': b})
    return out, missing


def spread(items, k):
    """k of the items, evenly spread over their order (all of them when there are no more than k)."""
    if len(items) <= k:
        return list(items)
    return [items[round(i * (len(items) - 1) / (k - 1))] for i in range(k)] if k > 1 else [items[len(items) // 2]]


def plan(cands, seconds):
    """The reel: [{group, label, n, missed, clips}], most-missed kinds of ball first, no moment of the recording twice."""
    by = defaultdict(list)
    for c in cands:
        by[c['group']].append(c)
    order = sorted(by, key=lambda g: (-sum(not c['ok'] for c in by[g]), -len(by[g]), g))
    reel, taken, total = [], [], 0.0
    free = lambda c: all(c['b'] <= a or c['a'] >= b for a, b in taken)
    for g in order:
        cs = sorted(by[g], key=lambda c: c['a'])
        missed = [c for c in cs if not c['ok']]
        if len(reel) == GROUPS or len(missed) < MIN_MISSES:
            break
        clips = []
        for pool, k in ((missed, MISSES), ([c for c in cs if c['ok']], MADE)):
            for c in spread([c for c in pool if free(c)], k):
                if free(c) and total + c['b'] - c['a'] <= seconds + 4:
                    clips.append(c)
                    taken.append((c['a'], c['b']))
                    total += c['b'] - c['a']
        if sum(not c['ok'] for c in clips) < 2:
            for c in clips:
                taken.remove((c['a'], c['b']))
                total -= c['b'] - c['a']
            continue
        reel.append({'group': g, 'label': label(g), 'n': len(cs), 'missed': len(missed), 'clips': clips})
    return reel


def captions(reel):
    """Write each clip's caption and return the clips in reel order."""
    out = []
    for i, part in enumerate(reel):
        head = f"{i + 1} · {part['label']} · missed {part['missed']} of {part['n']}"
        misses = [c for c in part['clips'] if not c['ok']]
        for c in part['clips']:
            where = f"Match {c['matchNo']} · Game {c['game']} · {c['you']}–{c['ai']}"
            what = f"Miss {misses.index(c) + 1} of {len(misses)}: {HOW.get(c['miss'], 'missed')}" if not c['ok'] else 'The same ball, landed'
            c['caption'] = f'{head}\n{what} · {where}'
            out.append(c)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('file')
    ap.add_argument('--seconds', type=float, default=100, help='about how long the reel may be (default 100)')
    ap.add_argument('--dry-run', action='store_true', help='print the picked shots, cut and upload nothing')
    ap.add_argument('--no-upload', action='store_true', help='cut the reel and stop')
    ap.add_argument('--again', action='store_true', help='upload even if this reel is already in videos.json')
    for out in (sys.stdout, sys.stderr):
        if hasattr(out, 'reconfigure'):
            out.reconfigure(encoding='utf-8', errors='replace')
    a = ap.parse_args()
    src = os.path.abspath(a.file)
    if not os.path.isfile(src):
        yt.fail(f'No such file: {src}')
    row = yt.already(src)
    if not row or not row.get('sync'):
        yt.fail('This recording is not in videos.json with its timing yet. Run session_video.py on it first.')
    yt.low_priority()

    cands, missing = candidates(row, hl.LOGS, hl.BUILD)
    if missing:
        yt.fail(f'The dashboard data does not have {len(missing)} of this recording\'s matches yet. Run refresh.py first.')
    reel = plan(cands, a.seconds)
    if not reel:
        yt.fail(f'No kind of ball was missed {MIN_MISSES} times or more in this recording; no reel was made.')
    clips = captions(reel)
    parts, t = hl.stretches(clips)
    first = datetime.datetime.strptime(min(c['match'] for c in cands), '%Y-%m-%d %H:%M:%S')
    when = f'{first.day} {hl.MONTHS[first.month - 1]} {first.year}, {first:%H:%M}'
    session = next((c['session'] for c in cands if c['match'] == f'{first:%Y-%m-%d %H:%M:%S}'), None) or f'{first:%Y-%m-%d %H:%M:%S}'
    title = f'Misses to work on · Eleven Table Tennis vs AI · {when}'
    lines = []
    for i, part in enumerate(reel):
        lines.append(f"{hl.clock(part['clips'][0]['t'])} {i + 1}. {part['label']}: missed {part['missed']} of {part['n']} in the session")
    desc = '\n'.join(['The balls I missed most often in this session, picked from the game log: a few of the misses for each, '
                      'then the same ball on occasions when the shot landed.', '', *lines, '',
                      f"Full session: {row['url']}", '',
                      'Cut and uploaded automatically from the headset recording.'])
    yt.check_text(title, desc)
    print(f'{len(clips)} clips, {hl.clock(t)} ({t:.1f} s)\n\nTitle: {title}\n\n{desc}\n')
    for c in clips:
        print('  ' + c['caption'].replace('\n', '\n      ') + f"\n      recording {hl.clock(c['a'])} to {hl.clock(c['b'])}")
    if a.dry_run:
        return

    os.makedirs(hl.REELS, exist_ok=True)
    out = os.path.join(hl.REELS, f'mistakes-{first:%Y%m%d-%H%M}.mp4')
    print('\nCutting the reel on the graphics card ...', flush=True)
    hl.cut(src, parts, t, out)
    got = hl.checked_duration(out, t)
    print(f'Reel: {out} ({got:.1f} s, {os.path.getsize(out) / 1e6:.1f} MB)')
    if a.no_upload:
        return
    new = yt.upload_file(out, title, desc, 'mistakes', session, a.again,
                         {'duration': round(got, 3), 'source': row['id'], 'fade': hl.FADE,
                          'groups': [{'label': p['label'], 'missed': p['missed'], 'n': p['n']} for p in reel],
                          'clips': [{'key': c['key'], 't': round(c['t'], 2), 'd': round(c['b'] - c['a'], 2), 'ok': int(c['ok'])} for c in clips]})
    for old in yt.replace_older(new):
        print(f"The earlier reel for this session, {old['url']}, is no longer linked from the dashboard. It is still on "
              'YouTube: delete it in YouTube Studio if you do not want it.')


if __name__ == '__main__':
    main()
