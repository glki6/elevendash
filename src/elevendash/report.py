"""The text report of the last session: results, the written notes, the change against your earlier average, and
win rates for the session and all time."""
import json
import os

LEVEL_NAMES = {100: 'Legendary'}


def level_name(level):
    return LEVEL_NAMES.get(level, f'level {level}')


def _rows(build_dir, name):
    with open(os.path.join(build_dir, name + '.json'), encoding='utf-8') as f:
        return json.load(f)['rows']


def _of(a, b, rate):
    return f'{a} of {b} ({rate:.1f}%)' if b else 'none'


def session_report(build_dir):
    """The report as a list of lines."""
    summary = {r['key']: r for r in _rows(build_dir, 'summary')}
    sessions, notes, matches = _rows(build_dir, 'sessions'), _rows(build_dir, 'session_notes'), _rows(build_dir, 'matches')
    out = []
    if not sessions:
        return ['No matches against the AI in these logs yet.']
    s = sessions[-1]
    lvl = level_name(s['level'])
    out.append(f"SESSION {s['n']}: {s['date']} {s['start'][:5]} to {s['end'][:5]}, AI at {lvl}")
    out.append(f"  Matches won  {_of(s['wins'], s['matches'], s['matchRate'])}")
    out.append(f"  Games won    {_of(s['gamesWon'], s['games'], s['gameRate'])}")
    out.append(f"  Points won   {_of(s['pointsWonN'], s['points'], s['pointRate'])}")
    for m in matches:
        if m.get('session') == s['key']:
            out.append(f"    {m['sessionMatch']:>2}. {m['start'][:5]}  {m['result']:<4} {m['gamesWon']}-{m['gamesLost']}  ({m['score']})")
    out.append('  Notes')
    for n in notes:
        if n['session'] == s['key']:
            out.append(f"    - {n['text']}")
    if s.get('basePoints'):
        out.append(f"  Against your level-{s['level']} average before this session ({s['baseMatches']} matches)")
        for f, label in (('pointRate', 'Points won'), ('servePointRate', 'Points won on your serve'),
                         ('returnPointRate', "Points won on the AI's serve"), ('servesLanded', 'Serves that landed'),
                         ('returnsLanded', 'Returns that landed'), ('rallyLanded', 'Rally shots that landed')):
            d = s['d_' + f]
            if d is None:
                continue
            out.append(f"    {label:<30} {s[f]:5.1f}%   before {s['base_' + f]:5.1f}%   {'+' if d >= 0 else ''}{d:.1f} pts")
    out.append('')
    out.append('ALL TIME')
    for key, label in (('all', 'All AI matches'), (f"L{s['level']}", f'At {lvl}'), ('online', 'Online')):
        r = summary.get(key)
        if r:
            out.append(f"  {label:<16} matches {_of(r['wins'], r['matches'], r['matchRate'])}, "
                       f"games {_of(r['gamesWon'], r['games'], r['gameRate'])}")
    return out
