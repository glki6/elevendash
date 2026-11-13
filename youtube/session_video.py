r"""Upload a session's full recording to YouTube (unlisted) and work out where every point is in it.

    session_video.py FILE [--dry-run] [--again]

The recording is uploaded untouched. What makes it useful is the timing: the Eleven log gives every ball contact a
time on the app's own clock, and the recording carries the sound of those contacts. Sliding one against the other
finds the offset between "seconds since the app started" and "seconds into the video" to a few milliseconds, so the
dashboard can link straight to any point. The offset is saved with the video in videos.json:

    video seconds = app seconds - lag + audio_start

A weak match between sound and log stops the upload, because wrong links are worse than no links.
Run it with the environment beside it:  youtube\.venv\Scripts\python.exe -I youtube\session_video.py FILE
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import tempfile

import numpy as np

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
SR, HOP = 16000, 32                 # audio at 16 kHz, loudness in 2 ms steps
MIN_Z, MIN_EVENTS = 12.0, 40        # how clearly the sound must match the log before anything is uploaded
IDLE = 0x00000040 if os.name == 'nt' else 0
LOG_NAME = re.compile(r'^ALL-(\d{2})\.(\d{2})\.(\d{4})\.(\d{1,2})\.(\d{2})\.(\d{2})\.(AM|PM)\.log$')
FILE_TIME = re.compile(r'(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})')
MONTHS = 'Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split()


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=IDLE)


def probe(path):
    r = run(['ffprobe', '-v', 'error', '-print_format', 'json', '-show_format', '-show_streams', path])
    if r.returncode:
        yt.fail(f'ffprobe could not read {path}: {r.stderr.strip()[:300]}')
    d = json.loads(r.stdout)
    audio = next((s for s in d['streams'] if s.get('codec_type') == 'audio'), None)
    if not audio:
        yt.fail('The recording has no sound, so it cannot be lined up with the log.')
    return float(d['format']['duration']), float(audio.get('start_time') or 0)


def recording_start(path, duration):
    """(when the recording began by the PC's or headset's clock, how far off that may be in seconds)."""
    m = FILE_TIME.search(os.path.basename(path))
    if m:
        return datetime.datetime(*map(int, m.groups())), 6.0
    return datetime.datetime.fromtimestamp(os.path.getmtime(path)) - datetime.timedelta(seconds=duration), 20.0


def log_opened(name):
    m = LOG_NAME.match(name)
    if not m:
        return None
    mo, d, y, h, mi, s, ap = m.groups()
    h = int(h) % 12 + (12 if ap == 'PM' else 0)
    return datetime.datetime(int(y), int(mo), int(d), h, int(mi), int(s))


def onsets(path):
    """How sharply the sound gets louder, every 2 ms: ball contacts are short, bright clicks."""
    fd, raw = tempfile.mkstemp(suffix='.raw')
    os.close(fd)
    try:
        r = run(['ffmpeg', '-v', 'error', '-y', '-i', path, '-vn', '-ac', '1', '-ar', str(SR), '-f', 's16le', raw])
        if r.returncode:
            yt.fail(f'ffmpeg could not read the sound: {r.stderr.strip()[:300]}')
        a = np.fromfile(raw, dtype=np.int16).astype(np.float32) / 32768
    finally:
        os.remove(raw)
    hp = np.diff(a, prepend=a[0])
    n = len(hp) // HOP
    le = np.log(np.sqrt((hp[:n * HOP].reshape(n, HOP) ** 2).mean(axis=1) + 1e-12) + 1e-5)
    return np.maximum(0, le - np.concatenate([[le[0]] * 3, le[:-3]]))      # rise over 6 ms


def best_lag(on, times, guess, slack):
    """Slide the log's contact times along the sound; returns (lag, how far the best stands out, contacts inside)."""
    ts = np.asarray(times)
    lags = np.arange(guess - slack, guess + slack, 0.002)
    score = np.empty(len(lags))
    for j, d in enumerate(lags):
        i = np.round((ts - d) * SR / HOP).astype(int)
        i = i[(i >= 0) & (i < len(on))]
        score[j] = on[i].sum() / max(1, len(i))
    k = int(score.argmax())
    med = np.median(score)
    z = (score[k] - med) / (np.median(np.abs(score - med)) + 1e-9)
    inside = int(((ts - lags[k] >= 0) & (ts - lags[k] < len(on) * HOP / SR)).sum())
    return round(float(lags[k]), 3), round(float(z), 1), inside


def clock(sec):
    sec = int(sec)
    return f'{sec // 3600}:{sec % 3600 // 60:02d}:{sec % 60:02d}' if sec >= 3600 else f'{sec // 60}:{sec % 60:02d}'


def result(m):
    """('Won' or 'Lost', your games, their games, the game scores from your side) for one extracted match."""
    you = 0 if m['you'] == 'A' else 1
    games = [(g['score'][you], g['score'][1 - you]) for g in m['games']]
    won, lost = sum(a > b for a, b in games), sum(b > a for a, b in games)
    return ('Won' if won > lost else 'Lost'), won, lost, ', '.join(f'{a}–{b}' for a, b in games)


def session_numbers():
    """Match key -> its number within its session, as the dashboard counts it (from the last rebuild, if there is one)."""
    try:
        with open(os.path.join(BUILD, 'matches.json'), encoding='utf-8') as f:
            return {r['key']: r.get('sessionMatch') for r in json.load(f)['rows']}
    except (OSError, ValueError, KeyError):
        return {}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('file')
    ap.add_argument('--dry-run', action='store_true', help='line the recording up and print the plan, upload nothing')
    ap.add_argument('--again', action='store_true', help='upload even if this file is already in videos.json')
    for out in (sys.stdout, sys.stderr):        # titles carry · and –, which the Windows console code page lacks
        if hasattr(out, 'reconfigure'):
            out.reconfigure(encoding='utf-8', errors='replace')
    a = ap.parse_args()
    path = os.path.abspath(a.file)
    if not os.path.isfile(path):
        yt.fail(f'No such file: {path}')
    if not a.again and not a.dry_run:
        r = yt.already(path)
        if r:
            yt.fail(f"Already uploaded as {r['url']} on {r['at']}. Pass --again to upload it a second time.", 3)
    yt.low_priority()
    duration, audio_start = probe(path)
    began, slack = recording_start(path, duration)
    ended = began + datetime.timedelta(seconds=duration)
    print(f'Recording: {os.path.basename(path)}, {clock(duration)} long, began about {began:%Y-%m-%d %H:%M:%S}')

    # Logs the app opened before the recording ended and not more than half a day earlier can hold its matches.
    names = sorted((n for n in os.listdir(LOGS) if LOG_NAME.match(n)), key=log_opened)
    near = [n for n in names if datetime.timedelta(0) <= ended - log_opened(n) <= datetime.timedelta(hours=12)]
    on = None
    sync, covered = [], []
    for name in near:
        ms = [m for m in ett_extract.extract_log(os.path.join(LOGS, name)) if m.get('t0') is not None and m['games']]
        if not ms:
            continue
        # wall clock of app second 0, from a match start (the log's wall clock is whole seconds: good to about 1 s)
        m0 = ms[0]
        origin = datetime.datetime.strptime(f"{m0['date']} {m0['start']}", '%Y-%m-%d %H:%M:%S') - datetime.timedelta(seconds=m0['t0'])
        guess = (began - origin).total_seconds()
        times = [t['gt'] for m in ms for g in m['games'] for p in g['points'] for t in p['track']
                 if t['k'] in ('hit', 'table') and t.get('gt')]
        if sum(0 <= t - guess < duration for t in times) < MIN_EVENTS:
            continue
        if on is None:
            print('Listening to the recording for ball contacts ...', flush=True)
            on = onsets(path)
        lag, z, inside = best_lag(on, times, guess, slack)
        print(f'  {name}: lag {lag:.3f} s, stands out by {z} (needs {MIN_Z}), {inside} contacts inside the recording')
        if z < MIN_Z or inside < MIN_EVENTS:
            continue
        sync.append({'log': name, 'lag': lag, 'z': z, 'events': inside})
        for m in ms:
            pts = [p for g in m['games'] for p in g['points'] if p.get('t0') is not None]
            t0 = m['t0'] - lag + audio_start
            if pts and t0 < duration and pts[-1]['t1'] - lag + audio_start > 0:
                covered.append((max(0.0, t0), m, name))
    if not sync:
        yt.fail('Could not line this recording up with any log (no log covers it, or the sound does not match). '
                'Nothing was uploaded.')
    covered.sort(key=lambda c: (c[1]['date'], c[1]['start']))

    nums = session_numbers()
    first = covered[0][1]
    day = datetime.datetime.strptime(first['date'], '%Y-%m-%d')
    n = len(covered)
    vs = 'vs AI' if all(m['ai'] for _, m, _ in covered) else ('online' if not any(m['ai'] for _, m, _ in covered) else 'vs AI and online')
    title = f"Eleven Table Tennis {vs} · {day.day} {MONTHS[day.month - 1]} {day.year}, {first['start'][:5]} · {n} match{'es' if n != 1 else ''}"
    lines, chapters = [], []
    for i, (t0, m, _) in enumerate(covered):
        key = f"{m['date']} {m['start']}"
        no = nums.get(key) or i + 1
        res, w, l, games = result(m)
        who = f"AI level {m['difficulty']}" if m['ai'] else 'online'
        chapters.append((t0, f'Match {no} · {who} · {res.lower()} {w}–{l}'))
        lines.append(f"Match {no} ({m['start'][:5]}, {who}): {res.lower()} {w}–{l} ({games})")
    # YouTube shows chapters only when the first is at 0:00, there are three or more, and each lasts 10 s or longer.
    if chapters[0][0] >= 10:
        chapters.insert(0, (0.0, 'Before the first match'))
    else:
        chapters[0] = (0.0, chapters[0][1])
    kept = [chapters[0]]
    for c in chapters[1:]:
        if int(c[0]) - int(kept[-1][0]) >= 10:
            kept.append(c)
    desc = '\n'.join([f'Full session recording, Eleven Table Tennis on Quest 3S, {day.day} {MONTHS[day.month - 1]} {day.year}.', '',
                      *lines, '', *(f'{clock(t)} {text}' for t, text in kept), '',
                      'Uploaded automatically from the headset recording; point times come from the game log.'])
    yt.check_text(title, desc)
    print('\nTitle: ' + title + '\n\n' + desc + '\n')
    extra = {'duration': round(duration, 3), 'audio_start': audio_start, 'sync': sync,
             'matches': [f"{m['date']} {m['start']}" for _, m, _ in covered]}
    if a.dry_run:
        print('Dry run: nothing uploaded. Would record: ' + json.dumps(extra, ensure_ascii=False))
        return
    yt.upload_file(path, title, desc, 'full', extra['matches'][0], a.again, extra)


if __name__ == '__main__':
    main()
