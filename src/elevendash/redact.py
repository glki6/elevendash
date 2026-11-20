"""Take account, people and location data out of a game log, so a copy can be shown to someone (a bug report, 11hero).

Eleven's logs hold your Eleven and Meta account tokens, platform user ids and names, the names and ids of people you
played online, your location and country, network addresses and the headset's device id.

By default redact() keeps only what elevendash reads: the ball contacts, scores, match starts and ends, the AI level
and your paddle hand. The online server messages it reads are rewritten to the numbers it uses (both ratings and what
the match is worth), with each player id replaced by a stand-in number, the same one all through the file. Every
other line is left out. A redacted copy builds the same match data as the log, and has nothing else in it.

With full=True (`elevendash redact --full`) every line stays, for a problem with lines elevendash does not read yet.
Then the value of every field known to hold one of those kinds of data becomes REDACTED, then any of those values
that turn up anywhere else in the text, then tokens in links and headers, e-mail and network addresses. The
UserCommunication blocks are dropped, as 11hero does before an upload. A game update can add fields this does not
know: read a full copy before you share it.

Both ways, the values found are looked for again at the end: `left` counts the ones still in the text (should be 0).
"""
import re

# Field names whose values identify you, other people, where you are, or your accounts and devices (any case)
FIELDS = (
    # account secrets
    'AuthToken', 'PlatformAccessToken', 'Token', 'AccessToken', 'SessionToken', 'RefreshToken', 'ReplayToken', 'IdToken',
    'access_token', 'refresh_token', 'id_token', 'auth_token', 'session_token', 'ShareCode', 'ArchiveKey', 'Password',
    'Secret', 'ApiKey', 'api_key',
    # account and player ids, yours and other people's
    'UserId', 'user_id', 'PlatformUserId', 'PlatformId', 'OldPlatformId', 'NewPlatformId', 'HomeUserId', 'AwayUserId',
    'HostId', 'OwnerId', 'PlayerIds', 'EditorId', 'MatchId', 'userConnectionId', 'RelayConnectionId', 'OculusId',
    'oculus_id', 'MetaId', 'AccountId', 'account_id',
    # names and contact, yours and other people's
    'Username', 'user_name', 'PlatformUserName', 'PlatformPublicName', 'CensoredUserName', 'censoredName',
    'PlayerNames', 'DisplayName', 'display_name', 'Email', 'EmailAddress', 'e_mail', 'Phone',
    # where you are and how you connect
    'Latitude', 'Longitude', 'CountryCode', 'Country', 'City', 'Region', 'PostalCode', 'ZipCode', 'TimeZone',
    'LocalIP', 'ServerIP', 'CustomServerIP', 'IPAddress', 'Address', 'MacAddress',
    # the headset
    'DeviceId', 'device_id', 'SerialNumber', 'serial_number', 'HardwareId',
    # fields with scrambled names whose values the game keeps to itself
    'JUCIDK', 'PIPUOJ', 'RUIDAS',
)
MARK = 'REDACTED'
_KEYS = '|'.join(FIELDS)
# A value: a string as plain JSON, or as JSON inside a JSON string (quotes escaped, and an escaped quote inside it
# written \\\"), a number, a list, or an object without objects inside.
_PLAIN = r'"(?:[^"\\]|\\.)*"'
_ESC = r'\\"(?:\\\\\\.|[^"\\]|\\(?!"))*\\"'
FIELD = re.compile(r'((?<![\w])\\?"(?:' + _KEYS + r')\\?"\s*:\s*)'
                   r'(' + _ESC + '|' + _PLAIN + r'|-?\d[\d.eE+-]*|\[[^\]]*\]|\{[^{}]*\})', re.I)
# key=value and key: value outside JSON (a URL's query, a header, a printed setting)
PAIR = re.compile(r'(?<![\w"])((?:' + _KEYS + r')\s*[=:]\s*)(?!\s*["\[{\\])([^\s,;&"\'<>)\]}]+)', re.I)
BEARER = re.compile(r'(?i)(\bBearer\s+)[\w.~+/=-]{8,}')
JWT = re.compile(r'\beyJ[\w-]{4,}\.[\w-]{4,}\.[\w-]{4,}')
EMAIL = re.compile(r'[\w.+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+')
IPV4 = re.compile(r'(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])')
IPV6 = re.compile(r'(?<![\w:.])(?:(?:[0-9a-f]{1,4}:){7}[0-9a-f]{1,4}'
                  r'|(?=[0-9a-f:]*[0-9a-f])(?:[0-9a-f]{1,4}(?::[0-9a-f]{1,4})*)?::(?:[0-9a-f]{1,4}(?::[0-9a-f]{1,4})*)?)'
                  r'(?![\w:])', re.I)
HEAD = re.compile(r'^\[\d+/\d+/\d+ [\d:]+\](?:\[-?\d+,-?\d+\])?')     # a log entry's first line: [date time][ms,frame]
QUOTED = re.compile(r'\\?"((?:\\\\\\.|[^"\\]|\\(?!"))*)\\?"')
# words elevendash reads; a value that is one of them is only removed from its own field, never from the whole text
KEEP = {'toss', 'table', 'floor', 'paddle', 'player', 'match', 'score', 'settings', 'right', 'left', 'true', 'false',
        'null', 'none', 'ai', 'a', 'b', 'net', 'ball', 'balla', 'ballb', 'hit', 'hita', 'hitb', 'tossa', 'tossb',
        'tablea', 'tableb', 'tableside', 'continue', 'let', 'reset', 'round', 'side', 'position', 'velocity',
        'rotationrate', 'gametime', 'game', 'gamescore', 'updating', 'from', 'to', 'adding', 'local', 'response',
        'difficulty', 'chosen', 'next', 'against', 'single', 'starting', 'running', 'elo', 'online', 'ranked',
        'mymatch', 'mycollision', 'dynamic', 'collision', 'opponent', 'received', 'pos', 'vel', 'rrate', 'user', 'id',
        MARK.lower()}

# The entries elevendash reads (extract.py): an entry whose first line holds one of these is kept by default
READ = ('MyCollision:', 'from opponent: pos:', 'Dynamic Collision...', 'postCollisionState:', '"paddleHand":"',
        'Difficulty:', 'against AI', 'MoveUserIntoPosition(TableSide', 'Setting StrictServingRules from',
        '[matchRunning] from [', 'adding a round', 'Local Response:', 'updating gameScore side')
BLOCK_KEYS = ('pongGameCollisionType', 'position', 'velocity', 'rotationRate', 'gameTime', 'relativeSender')
# the online server messages: what extract.py takes from them
SELF = re.compile(r'"user":\{"Id":"(\d+)"')
SNAPSHOT = re.compile(r'"PlayerIds":\[([^\]]*)\],"PlayerELOs":\[([^\]]*)\]')
STAKES = ('HomeUserId', 'AwayUserId', 'winnerELODiffIfHomeWins', 'winnerELODiffIfAwayWins', 'loserELODiffIfHomeWins',
          'loserELODiffifAwayWins')
STAND_IN = 900000001        # the first stand-in player id (one that is in the log is skipped)


def _values(raw):
    """The values held by one matched field value: the string, each string in a list or object, or a long number."""
    if raw[:1] in '[{':
        return QUOTED.findall(raw) + re.findall(r'(?<![\w.])\d{6,}(?![\w.])', raw)
    if raw.lstrip('-')[:1].isdigit():
        return [raw] if len(re.sub(r'\D', '', raw)) >= 6 else []
    return [v.replace('\\\\\\"', '"').replace('\\"', '"') for v in QUOTED.findall(raw)]


def _pattern(v):
    """How a found value is looked for in the text: a number only where it stands alone, not as digits inside a
    longer number (a time, a coordinate); a short word only as a whole word."""
    if v.lstrip('-').replace('.', '').isdigit():
        return re.compile(r'(?<![\d.])' + re.escape(v) + r'(?![\d.])')
    if len(v) < 5:
        return re.compile(r'(?<![\w])' + re.escape(v) + r'(?![\w])')
    return re.compile(re.escape(v))


def _worth(v):
    """A value worth looking for elsewhere: a word of two letters or more that is not one elevendash reads, or a
    number of six digits or more (shorter numbers are everywhere: times, scores, coordinates)."""
    d = v.lstrip('-')
    if d.replace('.', '').isdigit():
        return d.isdigit() and len(d) >= 6
    return len(v) >= 2 and v.lower() not in KEEP and v != MARK


def _found(text):
    """Every value the known fields hold, in any form, anywhere in the text."""
    got = set()
    for m in FIELD.finditer(text):
        got.update(v for v in _values(m.group(2)) if v)
    for m in PAIR.finditer(text):
        got.add(m.group(2))
    return got


def _scrub(text, found):
    """The full way: fields, then their values anywhere, then links, headers, e-mail and network addresses."""
    n = {'fields': 0, 'mentions': 0, 'addresses': 0}

    def field(m):
        raw = m.group(2)
        q = '\\"' if raw.startswith('\\"') else '"'
        return m.group(1) + q + MARK + q

    text, n['fields'] = FIELD.subn(field, text)
    text, k = PAIR.subn(lambda m: m.group(1) + MARK, text)
    n['fields'] += k
    for v in sorted(filter(_worth, found), key=len, reverse=True):
        text, k = _pattern(v).subn(MARK, text)
        n['mentions'] += k
    for rx, to in ((BEARER, r'\g<1>' + MARK), (JWT, MARK), (EMAIL, MARK)):
        text, k = rx.subn(to, text)
        n['mentions'] += k
    text, k = IPV4.subn('0.0.0.0', text)
    n['addresses'] += k
    text, k = IPV6.subn('::', text)
    n['addresses'] += k
    return text, n


def _entries(lines):
    """The log as entries: a first line (with its date and time) and the lines that follow it, up to the next."""
    cur = None
    for line in lines:
        if HEAD.match(line):
            if cur:
                yield cur
            cur = [line]
        elif cur is not None:
            cur.append(line)
        else:
            yield [line]                    # before the first entry: on its own, never a first line
    if cur:
        yield cur


def _online(head, line, ids, avoid):
    """A server message reduced to what extract.py reads from it, with stand-in player ids; None if nothing."""
    text = line.replace('\\', '')

    def sid(v):
        if v not in ids:
            k = STAND_IN + len(ids)
            while str(k) in avoid or str(k) in ids.values():
                k += 1
            ids[v] = str(k)
        return ids[v]

    parts = []
    m = SELF.search(text)
    if m:
        parts.append(f'"user":{{"Id":"{sid(m[1])}"}}')
    m = SNAPSHOT.search(text)
    if m:
        pids, elos = re.findall(r'\d+', m[1]), re.findall(r'-?\d+', m[2])
        if len(pids) == len(elos) == 2:
            parts.append(f'"PlayerIds":[{",".join(sid(p) for p in pids)}],"PlayerELOs":[{",".join(elos)}],'
                         f'"Ranked":"{"True" if chr(34) + "Ranked" + chr(34) + ":" + chr(34) + "True" in text else "False"}"')
    if '"winnerELODiffIfHomeWins"' in text:
        got = {k: re.search('"' + k + r'":"?(-?\d+)', text) for k in STAKES + ('Winner',)}
        if all(got.values()):
            vals = {k: (sid(v[1]) if k.endswith('UserId') else v[1]) for k, v in got.items()}
            parts.append(','.join(f'"{k}":"{v}"' for k, v in vals.items()))
    if not parts:
        return None
    return head + ' [elevendash: a server message, reduced to what elevendash reads; ELO] {' + ','.join(parts) + '}'


def redact(text, full=False):
    """Returns (redacted text, counts). counts: fields, mentions (the same values found elsewhere, and tokens, e-mail
    addresses), addresses (network), dropped (lines left out), and left (values still in the text afterwards: should
    be 0)."""
    crlf = '\r\n' in text       # a log can mix both line ends (a copy with lines added): work in one, write the other back
    nl = '\n'
    text = text.replace('\r\n', nl)
    lines = text.split(nl)
    found = _found(text)
    if full:
        out, skip, dropped = [], False, 0
        for line in lines:
            if HEAD.match(line):
                skip = 'UserCommunication' in line
            if skip:
                dropped += 1
            else:
                out.append(line)
        result, n = _scrub(nl.join(out), found)
        n['dropped'] = dropped
    else:
        out, ids, dropped, kept_online = [], {}, 0, set()
        # extract.py looks at every line, the ones inside a long message too (the game prints some JSON over many
        # lines, and some messages carry no date of their own): a line it takes something from is kept or rewritten
        # under the date and time of the entry it is in, which is what extract.py has in hand when it reads it
        for entry in _entries(lines):
            first = entry[0]
            h = HEAD.match(first)
            head = h.group(0) if h else ''
            collision = 'MyCollision:' in first
            for i, line in enumerate(entry):
                if 'ELO' in line:
                    reduced = _online(head, line, ids, found)
                    if reduced:
                        kept_online.add(len(out))
                        out.append(reduced)
                    else:
                        dropped += 1
                elif '"paddleHand":"' in line:
                    hand = line.split('"paddleHand":"')[1][:1].upper()
                    out.append(head + ' [Settings] Paddle settings loaded: {"paddleHand":"' + ('Left' if hand == 'L' else 'Right') + '"}')
                elif i == 0:
                    if h and any(k in line for k in READ):
                        out.append(line)
                    else:
                        dropped += 1
                else:
                    key, _, val = line.strip().partition(':')
                    if collision and line.startswith('\t') and key in BLOCK_KEYS:
                        if key == 'relativeSender':
                            val = ' Ball' + (val.strip()[-1:] if val.strip()[-1:] in ('A', 'B') else '')
                        out.append('\t' + key + ':' + val)
                    else:
                        dropped += 1
        # the reduced server messages are made only of numbers and stand-ins; everything else gets the full scrub too
        rest = [l for i, l in enumerate(out) if i not in kept_online]
        scrubbed, n = _scrub(nl.join(rest), found)
        it = iter(scrubbed.split(nl))
        result = nl.join(out[i] if i in kept_online else next(it) for i in range(len(out)))
        if out:
            result += nl
        n['dropped'] = dropped
    n['left'] = sum(1 for v in filter(_worth, found) if _pattern(v).search(result))
    n['kept'] = len(result.split(nl)) - (1 if result.endswith(nl) else 0)
    return (result.replace(nl, '\r\n') if crlf else result), n


def redact_file(src, dst, full=False):
    """Write a redacted copy of the log src to dst (never over src). Returns the counts from redact()."""
    import os
    if os.path.abspath(src) == os.path.abspath(dst):
        raise ValueError('write the redacted copy to a new file, not over the log')
    with open(src, encoding='utf-8', errors='surrogateescape', newline='') as f:
        text = f.read()
    text, counts = redact(text, full=full)
    with open(dst, 'w', encoding='utf-8', errors='surrogateescape', newline='') as f:
        f.write(text)
    return counts
