"""The text report of the last session: results, the written notes, the change against your earlier average, and
win rates for the session and all time. The last session is the latest one of either side: against the AI, or
against people online (the datasets ending in _h), where it also says what the session did to your rating."""
import json
import os

LEVEL_NAMES = {100: 'Legendary'}


def level_name(level):
    return LEVEL_NAMES.get(level, f'level {level}')


def _rows(build_dir, name):
    try:
        with open(os.path.join(build_dir, name + '.json'), encoding='utf-8') as f:
            return json.load(f)['rows']
    except FileNotFoundError:           # a build from before the online side, or with no online matches
        return []


def _of(a, b, rate):
    return f'{a} of {b} ({rate:.1f}%)' if b else 'none'


def _signed(v):
    return f'{v:+d}'.replace('-', '−')


def _side(build_dir, tail):
    """One side's datasets: tail '' for the AI, '_h' for people online."""
    return {'online': bool(tail), 'summary': {r['key']: r for r in _rows(build_dir, 'summary' + tail)},
            'sessions': _rows(build_dir, 'sessions' + tail), 'notes': _rows(build_dir, 'session_notes' + tail)}


def _totals(label, r):
    return (f"  {label:<16} matches {_of(r['wins'], r['matches'], r['matchRate'])}, "
            f"games {_of(r['gamesWon'], r['games'], r['gameRate'])}")


def session_report(build_dir):
    """The report as a list of lines."""
    ai, people = _side(build_dir, ''), _side(build_dir, '_h')
    played = [x for x in (ai, people) if x['sessions']]
    if not played:
        return ['No matches in these logs yet.']
    side = max(played, key=lambda x: x['sessions'][-1]['key'])      # a session's key is its date and starting time
    online = side['online']
    s = side['sessions'][-1]
    lvl = level_name(s['level'])
    them = "your opponent's" if online else "the AI's"
    out = [f"SESSION {s['n']}: {s['date']} {s['start'][:5]} to {s['end'][:5]}, " + ('online' if online else f'AI at {lvl}')]
    out.append(f"  Matches won  {_of(s['wins'], s['matches'], s['matchRate'])}")
    out.append(f"  Games won    {_of(s['gamesWon'], s['games'], s['gameRate'])}")
    out.append(f"  Points won   {_of(s['pointsWonN'], s['points'], s['pointRate'])}")
    if s.get('rankedMatches'):
        out.append(f"  Rating       {s['ratingStart']} to {s['ratingEnd']} ({_signed(s['ratingChange'])}) over "
                   f"{s['rankedMatches']} ranked match{'es' if s['rankedMatches'] > 1 else ''}")
    for m in _rows(build_dir, 'matches'):
        if m.get('session') == s['key'] and (m['vs'] != 'AI') == online:
            rated = f"  rated {m['rOpp']}" if m.get('rOpp') else ''
            out.append(f"    {m['sessionMatch']:>2}. {m['start'][:5]}  {m['result']:<4} {m['gamesWon']}-{m['gamesLost']}  ({m['score']}){rated}")
    out.append('  Notes')
    for n in side['notes']:
        if n['session'] == s['key']:
            out.append(f"    - {n['text']}")
    if s.get('basePoints'):
        before = 'online' if online else f"level-{s['level']}"
        out.append(f"  Against your {before} average before this session ({s['baseMatches']} matches)")
        for f, label in (('pointRate', 'Points won'), ('servePointRate', 'Points won on your serve'),
                         ('returnPointRate', f'Points won on {them} serve'), ('servesLanded', 'Serves that landed'),
                         ('returnsLanded', 'Returns that landed'), ('rallyLanded', 'Rally shots that landed')):
            d = s['d_' + f]
            if d is None:
                continue
            out.append(f"    {label:<36} {s[f]:5.1f}%   before {s['base_' + f]:5.1f}%   {'+' if d >= 0 else ''}{d:.1f} pts")
    out.append('')
    out.append('ALL TIME')
    every = people['summary'].get('all') or ai['summary'].get('online')      # the online totals, from either build
    lines = []
    if 'all' in ai['summary']:
        lines.append(_totals('All AI matches', ai['summary']['all']))
        at = ai['sessions'][-1]['level'] if ai['sessions'] else None
        if f'L{at}' in ai['summary']:
            lines.append(_totals(f'At {level_name(at)}', ai['summary'][f'L{at}']))
    if every:
        one = _totals('Online', every)
        if every.get('rating') is not None:
            one += f", rating {every['rating']} ({_signed(every['ratingChange'])} since your first rated match in the logs)"
        lines = [one] + lines if online else lines + [one]
    return out + lines
