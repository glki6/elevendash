"""Signs that a log was not read properly.

elevendash reads the game's debug log, which the game is free to change with any update. A changed line usually does
not stop the build: matches go missing, or their numbers come out quietly wrong. So every build checks each log for
what a misread looks like and says so. The limits sit far from anything in the logs checked so far (35 logs, 544
matches: none is reported), so a warning means the log is unlike those, not that a number moved a little.

check_log(path, matches) returns the problems of one log as short sentences; nothing here raises or stops a build.
Each sentence is English and carries the same sentence in Traditional Chinese (.zh), which the app shows.
"""

# Lines the reader depends on, counted in the raw log.
SCORE = 'updating gameScore side'
CONTACT = 'MyCollision:'
AFTER_HIT = 'postCollisionState:'
OPPONENT = 'from opponent: pos:'

ISSUES = 'https://github.com/glki6/elevendash/issues'


class Note(str):
    """A problem as an English sentence, with the same sentence in Traditional Chinese on .zh."""
    zh = ''


def note(en, zh):
    n = Note(en)
    n.zh = zh
    return n


def pairs(problems):
    """{log name: [sentences]} as plain data for the app: {log name: [{'en': ..., 'zh': ...}]}."""
    return {name: [{'en': str(x), 'zh': getattr(x, 'zh', '') or str(x)} for x in found] for name, found in (problems or {}).items() if found}


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
            found.append(note(f'no match was found, though it holds {n[SCORE]} score lines and {n[CONTACT]} ball contacts',
                              f'找不到任何比賽，但裡面有 {n[SCORE]} 行比分和 {n[CONTACT]} 次擊球'))
        return found
    games = [g for m in matches for g in m['games']]
    points = [p for g in games for p in g['points']]
    hits = sum(len(p['hits']) for p in points)
    if not points:
        if n[CONTACT] >= 200:
            found.append(note(f'{len(matches)} matches were found but no points, though it holds {n[CONTACT]} ball contacts',
                              f'找到 {len(matches)} 場比賽，但沒有任何一分，雖然裡面有 {n[CONTACT]} 次擊球'))
        return found
    bare = sum(1 for p in points if not p['hits'])
    if len(points) >= 20 and bare > 0.2 * len(points):
        found.append(note(f'{bare} of {len(points)} points have no shots', f'{len(points)} 分之中有 {bare} 分沒有任何擊球'))
    if hits >= 50 and n[AFTER_HIT] < 0.3 * hits:
        found.append(note(f'the ball\'s state after a hit is missing for most shots ({n[AFTER_HIT]} for {hits} shots): speed and spin '
                          'would be measured as the ball arrived, not as it left the bat',
                          f'大部分擊球缺少擊球後的球況（{hits} 板只有 {n[AFTER_HIT]} 筆）：球速和旋轉會按來球而不是離拍時計算'))
    # every game but a match's last ran to its end, so one that did not has lost points
    short = sum(1 for m in matches for g in m['games'][:-1] if not _finished(g))
    if short >= 2:
        found.append(note(f'{short} games stop short of a finished score, so some of their points were not read',
                          f'{short} 局沒有打到完整的比分，所以其中有些分沒有讀到'))
    lost = sum(1 for m in matches if not m['ai'])
    if lost and not n[OPPONENT]:
        found.append(note(f'{lost} matches are neither against the AI nor online, so their opponent was not recognised',
                          f'{lost} 場比賽既不是對 AI 也不是線上對戰，所以認不出對手'))
    if any(m['ai'] and m['difficulty'] is None for m in matches):
        found.append(note('matches against the AI have no level', '對 AI 的比賽沒有等級'))
    if any(not m.get('date') for m in matches):
        found.append(note('matches have no date', '比賽沒有日期'))
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
