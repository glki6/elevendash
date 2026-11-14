r"""Cut a session's highlight reel from its full recording and upload it to YouTube (unlisted).

    highlights.py FILE [--seconds 90] [--dry-run] [--no-upload] [--again]

FILE is a recording that session_video.py has already uploaded: its row in videos.json holds the offset between the
game log's clock and the video, which is what lets the points be cut without anyone watching the footage.

The points are picked from the log alone. Each point gets a score: two for every shot in the rally, one for every
m/s over 10 on your winning shot, a bonus for a point won at game point or late in a close game, and a larger one
for the point that won a match. Points you won need three shots or more; one or two long rallies you lost get in
too, so the reel is not only winners. The best are taken until the reel is about --seconds long, then put back in
the order they were played, each with a caption saying where in the session it was. One rally fades into the next
over FADE seconds; rallies played back to back stay one unbroken stretch.

The cut is made on the graphics card (decode and encode) at idle priority; the recording itself is only read.
Run it with the environment beside it:  youtube\.venv\Scripts\python.exe -I youtube\highlights.py FILE
"""
import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, 'src'))
sys.path.insert(0, HERE)
from elevendash import extract as ett_extract     # noqa: E402
from elevendash import workspace                  # noqa: E402
import yt               # noqa: E402

try:
    WS = workspace.find()
except workspace.NotAWorkspace as _e:
    sys.exit(str(_e))

LOGS = WS.logs
BUILD = WS.build
REELS = os.path.join(WS.root, 'reels')
FONT = r'C:\Windows\Fonts\seguisb.ttf'
LEAD, TAIL = 1.5, 1.6               # seconds kept before the toss and after the last contact
FADE = 0.4                          # seconds one rally and the next overlap in a crossfade
FPS = 60
MIN_WON_SHOTS, MIN_LOST_SHOTS, MAX_LOST = 3, 6, 2
MIN_CLIPS = 3
IDLE = 0x00000040 if os.name == 'nt' else 0
MONTHS = 'Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split()


def clock(sec):
    sec = int(sec)
    return f'{sec // 60}:{sec % 60:02d}'


def dashboard_matches():
    """Match key -> (session key, number within the session) as the dashboard has them, from the last rebuild."""
    try:
        with open(os.path.join(BUILD, 'matches.json'), encoding='utf-8') as f:
            return {r['key']: (r.get('session'), r.get('sessionMatch')) for r in json.load(f)['rows']}
    except (OSError, ValueError, KeyError):
        return {}


def candidates(row):
    """Every point of the recording that may go in the reel, scored."""
    out = []
    known = dashboard_matches()
    for s in row['sync']:
        # a game the log never scored was left unfinished (a match restarted after a point, say): the dashboard leaves
        # those out, and so does the reel
        ms = [dict(m, games=[g for g in m['games'] if 'score' in g])
              for m in ett_extract.extract_log(os.path.join(LOGS, s['log']))]
        ms = [m for m in ms if m['games']]
        for mi, m in enumerate(ms):
            you = m['you']
            mid = f"{m['date']} {m['start']}"
            session, number = known.get(mid, (None, None))
            last_game = len(m['games']) - 1
            mine = 0 if you == 'A' else 1
            match_won = sum(g['score'][mine] > g['score'][1 - mine] for g in m['games']) * 2 > len(m['games']) and 'end' in m
            for gi, g in enumerate(m['games']):
                for pi, p in enumerate(g['points']):
                    if p.get('t0') is None or not p['hits']:
                        continue
                    a = p['t0'] - s['lag'] + row.get('audio_start', 0) - LEAD
                    b = p['t1'] - s['lag'] + row.get('audio_start', 0) + TAIL
                    if a < 0 or b > row['duration']:
                        continue
                    won = p['winner'] == you
                    shots = len(p['hits'])
                    sc = (p['score'][mine], p['score'][1 - mine])
                    if shots < (MIN_WON_SHOTS if won else MIN_LOST_SHOTS):
                        continue
                    score = 2.0 * shots
                    if won:
                        win = next((h for h in p['hits'] if h['win'] and h['side'] == you), None)
                        if win:
                            score += max(0.0, win['speed'] - 10)
                        if match_won and gi == last_game and pi == len(g['points']) - 1:
                            score += 5                       # the point that won the match
                        elif sc[0] >= 10 and sc[0] > sc[1]:
                            score += 3                       # won at game point
                        elif min(sc) >= 9:
                            score += 2                       # late in a close game
                    else:
                        score -= 4
                    out.append({'key': f'{mid}|{gi + 1}|{pi + 1}', 'match': mid, 'session': session,
                                'matchNo': number or mi + 1, 'game': gi + 1, 'you': sc[0], 'ai': sc[1], 'ai_match': m['ai'],
                                'won': won, 'shots': shots, 'score': round(score, 1), 'a': a, 'b': b})
    return out


def pick(cands, seconds):
    """The best-scoring points that fit in about `seconds`, in the order they were played."""
    chosen, total, lost = [], 0.0, 0
    for c in sorted(cands, key=lambda c: -c['score']):
        d = c['b'] - c['a']
        if total + d > seconds + 4 or (not c['won'] and lost >= MAX_LOST):
            continue
        chosen.append(c)
        total += d
        lost += not c['won']
    chosen.sort(key=lambda c: c['a'])
    for x, y in zip(chosen, chosen[1:]):         # two points played back to back: meet in the middle, repeat nothing
        if y['a'] < x['b']:
            x['b'] = y['a'] = (x['b'] + y['a']) / 2
    return chosen


def stretches(clips):
    """Group the clips into unbroken stretches of the recording and place each in the reel.

    Points played back to back are one stretch, so nothing fades into itself. Every stretch is a whole number of
    frames long, and each one after the first starts FADE seconds before the one before it ends. Sets each clip's
    time in the reel (`t`) and returns (stretches, length of the reel)."""
    out = []
    for c in clips:
        if out and abs(c['a'] - out[-1]['b']) < 0.01:
            out[-1]['b'] = c['b']
            out[-1]['clips'].append(c)
        else:
            out.append({'a': c['a'], 'b': c['b'], 'clips': [c]})
    t = 0.0
    for g in out:
        g['d'] = round((g['b'] - g['a']) * FPS) / FPS
        g['t'] = t
        for c in g['clips']:
            c['t'] = t + (c['a'] - g['a'])
        t += g['d'] - FADE
    return out, t + FADE


def cut(src, parts, total, out):
    """One pass: decode each stretch on the graphics card, caption it, crossfade into the next, encode on the card."""
    work = tempfile.mkdtemp(prefix='reel-')
    try:
        shutil.copyfile(FONT, os.path.join(work, 'font.ttf'))
        cmd = ['ffmpeg', '-hide_banner', '-v', 'error', '-y']
        graph = []
        for i, g in enumerate(parts):
            cmd += ['-hwaccel', 'd3d11va', '-ss', f"{g['a']:.3f}", '-t', f"{g['d'] + 0.5:.3f}", '-i', src]
            text = ''
            for k, c in enumerate(g['clips']):
                with open(os.path.join(work, f'c{i}_{k}.txt'), 'w', encoding='utf-8', newline='\n') as f:
                    f.write(c['caption'])
                a0 = c['a'] - g['a']
                b0 = g['clips'][k + 1]['a'] - g['a'] if k + 1 < len(g['clips']) else g['d'] + 1
                text += (f",drawtext=fontfile=font.ttf:textfile=c{i}_{k}.txt:expansion=none:x=48:y=44:fontsize=34:line_spacing=10:"
                         f"fontcolor=white:box=1:boxcolor=black@0.5:boxborderw=14:enable='between(t,{a0:.3f},{b0:.3f})'")
            graph.append(f"[{i}:v]fps={FPS},trim=duration={g['d']:.4f},setpts=PTS-STARTPTS,scale=1920:1080,setsar=1{text},"
                         f"format=yuv420p,settb=AVTB[v{i}]")
            graph.append(f"[{i}:a]aresample=48000,atrim=duration={g['d']:.4f},asetpts=PTS-STARTPTS[a{i}]")
        v, a = 'v0', 'a0'
        for i in range(1, len(parts)):
            graph.append(f"[{v}][v{i}]xfade=transition=fade:duration={FADE}:offset={parts[i]['t']:.4f}[x{i}]")
            graph.append(f'[{a}][a{i}]acrossfade=d={FADE}:c1=tri:c2=tri[y{i}]')
            v, a = f'x{i}', f'y{i}'
        end = max(0, total - 0.5)
        graph.append(f'[{v}]fade=t=in:d=0.3,fade=t=out:st={end:.3f}:d=0.5[v]')
        graph.append(f'[{a}]afade=t=in:d=0.3,afade=t=out:st={end:.3f}:d=0.5[a]')
        cmd += ['-filter_complex', ';'.join(graph), '-map', '[v]', '-map', '[a]', '-r', str(FPS),
                '-c:v', 'h264_amf', '-quality', 'quality', '-rc', 'cqp', '-qp_i', '22', '-qp_p', '24', '-qp_b', '26',
                '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', out]
        r = subprocess.run(cmd, cwd=work, capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=IDLE)
        if r.returncode or not os.path.exists(out):
            yt.fail('ffmpeg could not cut the reel: ' + r.stderr.strip()[-600:])
    finally:
        shutil.rmtree(work, ignore_errors=True)


def checked_duration(path, expect):
    r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', path],
                       capture_output=True, text=True, creationflags=IDLE)
    got = float(r.stdout.strip() or 0)
    if abs(got - expect) > 1.0:
        yt.fail(f'The reel is {got:.1f} s long but should be {expect:.1f} s. Nothing was uploaded.')
    r = subprocess.run(['ffmpeg', '-v', 'error', '-hwaccel', 'd3d11va', '-i', path, '-f', 'null', '-'],
                       capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=IDLE)
    if r.returncode or r.stderr.strip():
        yt.fail('The reel does not play back cleanly: ' + r.stderr.strip()[-400:])
    return got


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('file')
    ap.add_argument('--seconds', type=float, default=90, help='about how long the reel should be (default 90)')
    ap.add_argument('--dry-run', action='store_true', help='print the picked points, cut and upload nothing')
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

    clips = pick(candidates(row), a.seconds)
    if len(clips) < MIN_CLIPS:
        yt.fail(f'Only {len(clips)} point(s) in this recording are worth a highlight; no reel was made.')
    for c in clips:
        c['caption'] = f"Match {c['matchNo']} · Game {c['game']} · {c['you']}–{c['ai']}"
    parts, t = stretches(clips)
    first = datetime.datetime.strptime(clips[0]['match'], '%Y-%m-%d %H:%M:%S')
    when = f'{first.day} {MONTHS[first.month - 1]} {first.year}, {first:%H:%M}'
    session = clips[0]['session'] or clips[0]['match']
    vs = 'vs AI' if all(c['ai_match'] for c in clips) else 'online'
    title = f'Highlights · Eleven Table Tennis {vs} · {when}'
    lines = [f"{clock(c['t'])} Match {c['matchNo']}, game {c['game']}, {c['you']}–{c['ai']}: {c['shots']} shots, "
             f"{'won' if c['won'] else 'lost'}" for c in clips]
    desc = '\n'.join([f'The best {len(clips)} points of the session, picked from the game log: longest rallies, fastest '
                      'winners and the points that mattered.', '', *lines, '',
                      f"Full session: {row['url']}", '',
                      'Cut and uploaded automatically from the headset recording.'])
    yt.check_text(title, desc)
    print(f'{len(clips)} points, {clock(t)} ({t:.1f} s)\n\nTitle: {title}\n\n{desc}\n')
    for c in clips:
        print(f"  score {c['score']:>5}  {c['caption']}  {c['shots']} shots {'won' if c['won'] else 'lost'}  "
              f"recording {clock(c['a'])} to {clock(c['b'])}")
    if a.dry_run:
        return

    os.makedirs(REELS, exist_ok=True)
    out = os.path.join(REELS, f'highlights-{first:%Y%m%d-%H%M}.mp4')
    print('\nCutting the reel on the graphics card ...', flush=True)
    cut(src, parts, t, out)
    got = checked_duration(out, t)
    print(f'Reel: {out} ({got:.1f} s, {os.path.getsize(out) / 1e6:.1f} MB)')
    if a.no_upload:
        return
    new = yt.upload_file(out, title, desc, 'highlights', session, a.again,
                         {'duration': round(got, 3), 'source': row['id'], 'fade': FADE,
                          'clips': [{'key': c['key'], 't': round(c['t'], 2), 'd': round(c['b'] - c['a'], 2)} for c in clips]})
    for old in yt.replace_older(new):
        print(f"The earlier reel for this session, {old['url']}, is no longer linked from the dashboard. It is still on "
              'YouTube: delete it in YouTube Studio if you do not want it.')


if __name__ == '__main__':
    main()
