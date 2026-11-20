"""A report to paste into a bug report: what elevendash and the computer are, and how the logs read, with nothing private.

It holds no log lines, account details, tokens, names, ids, addresses, paths or dates, and none of the scores: only
versions, counts, sizes, which settings are set, and the problems the log check finds. Each log is named by its place
in the list (log 3 of 39), not by its file name, which is the time the game was started.
"""
import glob
import json
import os
import platform
import sys
import traceback

from . import __version__, health
from .extract import extract_log
from .fetch import LOG_NAME

HEAD = ('elevendash diagnostic report',
        'Read it before you share it. It holds no log lines, account details, tokens, names, ids, addresses, paths or '
        'dates, and none of your scores: only versions, counts, sizes and the problems found in reading your logs.')
SAFE = {'hand': ('auto', 'left', 'right'), 'theme': ('dark', 'light'), 'lang': ('en', 'zh')}


def _mb(n):
    return f'{n / 1048576:.1f} MB'


def _where(e):
    """Where in elevendash's own code an error was raised (file:line), never its message, which may quote a log."""
    frames = [f for f in traceback.extract_tb(e.__traceback__) if 'elevendash' in f.filename.replace('\\', '/')]
    f = frames[-1] if frames else None
    return f'{type(e).__name__} at {os.path.basename(f.filename)}:{f.lineno}' if f else type(e).__name__


def settings(ws):
    try:
        c = ws.config()
    except (OSError, ValueError):
        return ['  elevendash.json could not be read']
    if not isinstance(c, dict):
        return ['  elevendash.json is not a set of settings']
    out = []
    for k in sorted(c):
        v = c[k]
        if k in SAFE:
            out.append(f'  {k}: {v if v in SAFE[k] else "an unexpected value"}')
        elif k == 'quest':
            out.append('  quest: set' if v else '  quest: not set')
        elif isinstance(v, bool):
            out.append(f'  {k}: {"on" if v else "off"}')
        else:
            out.append(f'  {k}: {"set" if v not in (None, "", [], {}) else "not set"}')
    return out or ['  none set']


def make(ws, read=True):
    """The report as text. read=False skips reading every log (quick, for a workspace with a very long history)."""
    out = list(HEAD) + ['']
    frozen = getattr(sys, 'frozen', False)
    out.append(f'elevendash {__version__} ({"the Windows app" if frozen else "the Python package"})')
    out.append(f'Python {platform.python_version()}, {platform.system()} {platform.release()} '
               f'({platform.version()}, {platform.machine()})')
    docs = os.path.join(os.path.expanduser('~'), 'Documents')
    inside = os.path.normcase(os.path.abspath(ws.root)).startswith(os.path.normcase(os.path.abspath(docs)) + os.sep)
    out.append(f'Workspace: {"in your Documents folder" if inside else "a folder elsewhere"} (its path is not shown)')
    out.append('')

    files = sorted(glob.glob(os.path.join(ws.logs, '*'))) if os.path.isdir(ws.logs) else []
    logs = [p for p in files if os.path.isfile(p) and LOG_NAME.match(os.path.basename(p))]
    other = [p for p in files if p not in logs and not p.endswith('.part')]
    sizes = [os.path.getsize(p) for p in logs]
    out.append(f'Game logs: {len(logs)}' + (f', {_mb(sum(sizes))} in all, the largest {_mb(max(sizes))}' if sizes else ''))
    if other:
        out.append(f'  {len(other)} other file(s) in logs/, not read (not named like a game log)')
    if read and logs:
        found = {'matches': 0, 'ai': 0, 'online': 0, 'stopped': 0, 'points': 0, 'shots': 0, 'left': 0, 'right': 0}
        problems = []
        for i, p in enumerate(logs, 1):
            try:
                ms = extract_log(p)
            except Exception as e:      # noqa: BLE001 - any failure is what the report is for
                problems.append(f'  log {i} of {len(logs)} ({_mb(sizes[i - 1])}): could not be read: {_where(e)}')
                continue
            for m in ms:
                pts = [pt for g in m['games'] for pt in g['points']]
                found['matches'] += 1
                found['ai' if m.get('ai') else 'online'] += 1
                found['stopped'] += bool(not m.get('end') or not m['games'] or not health._finished(m['games'][-1]))
                found['points'] += len(pts)
                found['shots'] += sum(len(pt['hits']) for pt in pts)
                if m.get('hand') in ('left', 'right'):
                    found[m['hand']] += 1
            for s in health.check_log(p, ms):
                problems.append(f'  log {i} of {len(logs)} ({_mb(sizes[i - 1])}): {s}')
        out.append(f"  read: {found['matches']} matches ({found['ai']} against the AI, {found['online']} not), "
                   f"{found['stopped']} of them stopped before the end; {found['points']:,} points, {found['shots']:,} shots")
        out.append(f"  paddle hand in the logs: right in {found['right']} matches, left in {found['left']}, "
                   f"not said in {found['matches'] - found['right'] - found['left']}")
        out += ['Problems found in reading the logs:'] + problems if problems else ['No problems found in reading the logs.']
    out.append('')

    data = sorted(glob.glob(os.path.join(ws.build, '*.json'))) if os.path.isdir(ws.build) else []
    out.append(f'Match data: {len(data)} file(s)' if data else 'Match data: not built yet')
    for name in ('matches', 'matches_h'):
        try:
            with open(os.path.join(ws.build, name + '.json'), encoding='utf-8') as f:
                n = len(json.load(f)['rows'])
            out.append(f'  {name}: {n} rows')
        except (OSError, ValueError, KeyError, TypeError):
            pass
    page = os.path.join(ws.site, 'index.html')
    out.append(f'Dashboard file: {_mb(os.path.getsize(page))}' if os.path.exists(page) else 'Dashboard file: not written yet')
    out.append(f'Video links: {"a videos.json is there" if os.path.exists(ws.videos) else "none"}')
    out.append('')
    out.append('Settings (values are shown only for hand, theme and lang):')
    out += settings(ws)
    return '\n'.join(out) + '\n'


def write(ws, read=True):
    """Write the report into diagnose/ in the workspace. Returns (path, text)."""
    text = make(ws, read)
    folder = os.path.join(ws.root, 'diagnose')
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, 'elevendash-diagnose.txt')
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)
    return path, text
