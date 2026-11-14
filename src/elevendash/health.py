"""Signs that a log was not read properly.

elevendash reads the game's debug log, which the game is free to change with any update. A changed line usually does
not stop the build: matches go missing, or their numbers come out quietly wrong. So every build checks each log for
what a misread looks like and says so. The limits sit far from anything in the logs checked so far (35 logs, 544
matches: none is reported), so a warning means the log is unlike those, not that a number moved a little.

check_log(path, matches) returns the problems of one log as short sentences; nothing here raises or stops a build.
"""

# Lines the reader depends on, counted in the raw log.
SCORE = 'updating gameScore side'
CONTACT = 'MyCollision:'
AFTER_HIT = 'postCollisionState:'
OPPONENT = 'from opponent: pos:'

ISSUES = 'https://github.com/glki6/elevendash/issues'


def _finished(game):
    a = sum(p['winner'] == 'A' for p in game['points'])
    b = len(game['points']) - a
    return max(a, b) >= 11 and abs(a - b) >= 2


def check_log(path, matches):
    """What looks wrong in one log, given what extract_log made of it. An empty list for a log that reads as usual."""
    with open(path, encoding='utf-8', errors='replace') as f:
        text = f.read()
    n = {k: text.count(k) for k in (SCORE, CONTACT, AFTER_HIT, OPPONENT)}
    found = []
    if not matches:
        # a launch with no match played has neither; one of them alone means the match start was not recognised
        if n[SCORE] >= 20 or n[CONTACT] >= 200:
            found.append(f'no match was found, though it holds {n[SCORE]} score lines and {n[CONTACT]} ball contacts')
        return found
    games = [g for m in matches for g in m['games']]
    points = [p for g in games for p in g['points']]
    hits = sum(len(p['hits']) for p in points)
    if not points:
        if n[CONTACT] >= 200:
            found.append(f'{len(matches)} matches were found but no points, though it holds {n[CONTACT]} ball contacts')
        return found
    bare = sum(1 for p in points if not p['hits'])
    if len(points) >= 20 and bare > 0.2 * len(points):
        found.append(f'{bare} of {len(points)} points have no shots')
    if hits >= 50 and n[AFTER_HIT] < 0.3 * hits:
        found.append(f'the ball\'s state after a hit is missing for most shots ({n[AFTER_HIT]} for {hits} shots): speed and spin '
                     'would be measured as the ball arrived, not as it left the bat')
    # every game but a match's last ran to its end, so one that did not has lost points
    short = sum(1 for m in matches for g in m['games'][:-1] if not _finished(g))
    if short >= 2:
        found.append(f'{short} games stop short of a finished score, so some of their points were not read')
    lost = sum(1 for m in matches if not m['ai'])
    if lost and not n[OPPONENT]:
        found.append(f'{lost} matches are neither against the AI nor online, so their opponent was not recognised')
    if any(m['ai'] and m['difficulty'] is None for m in matches):
        found.append('matches against the AI have no level')
    if any(not m.get('date') for m in matches):
        found.append('matches have no date')
    return found


def advice(problems):
    """Lines to print under the problems found: {log name: [sentences]}."""
    if not problems:
        return []
    out = ['', 'Warning: some logs did not read as expected. A game update may have changed the log format, and numbers',
           'from these logs may be wrong or missing:']
    for name, found in problems.items():
        out += [f'  {name}: {s}' for s in found]
    out += [f'Please report it at {ISSUES} (with a redacted copy of one such log if you can: elevendash redact LOG OUT).']
    return out
