"""Take account, people and location data out of a game log, so a copy can be shown to someone (a bug report, 11hero).

Eleven's logs hold your Eleven and Meta account tokens, platform user ids and names, the names and ids of people you
played online, your location and country, network addresses and the headset's device id. redact() replaces the value
of every field it knows to be one of those with REDACTED, then any of those values that turn up anywhere else in the
text, and any IPv4 address. It also drops the UserCommunication blocks, as 11hero does before an upload. What elevendash
reads (ball contacts, scores, settings) stays, so a redacted log still builds the same match data.

A game update can add fields this list does not know yet: read the result before you share it.
"""
import re

# Field names whose values identify you, other people, where you are, or your accounts and devices
FIELDS = (
    # account secrets
    'AuthToken', 'PlatformAccessToken', 'Token', 'AccessToken', 'SessionToken', 'RefreshToken', 'ReplayToken',
    'ShareCode', 'ArchiveKey',
    # account and player ids, yours and other people's
    'UserId', 'userId', 'PlatformUserId', 'PlatformId', 'OldPlatformId', 'NewPlatformId', 'HomeUserId', 'AwayUserId',
    'HostId', 'OwnerId', 'PlayerIds', 'EditorId', 'MatchId', 'userConnectionId', 'RelayConnectionId',
    # names, yours and other people's
    'Username', 'UserName', 'userName', 'PlatformUserName', 'PlatformPublicName', 'CensoredUserName', 'censoredName',
    'PlayerNames',
    # where you are and how you connect
    'Latitude', 'Longitude', 'CountryCode', 'LocalIP', 'ServerIP', 'CustomServerIP', 'Address', 'DeviceId',
    # fields with scrambled names whose values the game keeps to itself
    'JUCIDK', 'PIPUOJ', 'RUIDAS',
)
MARK = 'REDACTED'
# a field as JSON, or as JSON inside a JSON string (quotes escaped): "Key": "value" | number | [list]
FIELD = re.compile(r'(\\?"(?:' + '|'.join(FIELDS) + r')\\?"\s*:\s*)'
                   r'(\\?"(?:[^"\\]|\\(?!"))*\\?"|-?\d[\d.eE+-]*|\[[^\]]*\])')
IPV4 = re.compile(r'(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])')
HEAD = re.compile(r'^\[.*\]\[.*,.*\]')          # the first line of a log entry: [date time][ms,frame]
QUOTED = re.compile(r'\\?"((?:[^"\\]|\\(?!"))*)\\?"')
# words elevendash reads; a value that is one of them is only removed from its own field, never from the whole text
KEEP = {'toss', 'table', 'floor', 'paddle', 'player', 'match', 'score', 'settings', 'right', 'left', 'true', 'false',
        'null', 'none', MARK.lower()}


def _values(raw):
    """The values held by one matched field value: the string, each string in a list, or a long number."""
    if raw.startswith('['):
        return [v for v in QUOTED.findall(raw)] + re.findall(r'(?<![\w.])\d{6,}(?![\w.])', raw)
    if raw.lstrip('-')[:1].isdigit():
        return [raw] if len(re.sub(r'\D', '', raw)) >= 6 else []
    return QUOTED.findall(raw)


def _pattern(v):
    """How a found value is looked for in the rest of the text: a number only where it stands alone, not as digits
    inside a longer number (a time, a coordinate)."""
    if v.lstrip('-').replace('.', '').isdigit():
        return re.compile(r'(?<![\d.])' + re.escape(v) + r'(?![\d.])')
    return re.compile(re.escape(v))


def _worth(v):
    return len(v) >= 5 and v.lower() not in KEEP and v != MARK


def redact(text):
    """Returns (redacted text, counts). counts: fields, mentions (the same values found elsewhere), addresses, lines
    dropped, and left (values still in the text afterwards: should be 0)."""
    found = set()

    def field(m):
        raw = m.group(2)
        found.update(v for v in _values(raw) if v)
        q = '\\"' if raw.startswith('\\"') else '"'
        return m.group(1) + q + MARK + q

    text, fields = FIELD.subn(field, text)
    mentions = 0
    for v in sorted(filter(_worth, found), key=len, reverse=True):
        text, n = _pattern(v).subn(MARK, text)
        mentions += n
    text, addresses = IPV4.subn('0.0.0.0', text)
    out, skip, dropped = [], False, 0
    for line in text.split('\n'):
        if HEAD.match(line):
            skip = 'UserCommunication' in line
        if skip:
            dropped += 1
        else:
            out.append(line)
    text = '\n'.join(out)
    left = sum(1 for v in filter(_worth, found) if _pattern(v).search(text))
    return text, {'fields': fields, 'mentions': mentions, 'addresses': addresses, 'dropped': dropped, 'left': left}


def redact_file(src, dst):
    """Write a redacted copy of the log src to dst (never over src). Returns the counts from redact()."""
    import os
    if os.path.abspath(src) == os.path.abspath(dst):
        raise ValueError('write the redacted copy to a new file, not over the log')
    with open(src, encoding='utf-8', errors='surrogateescape', newline='') as f:
        text = f.read()
    text, counts = redact(text)
    with open(dst, 'w', encoding='utf-8', errors='surrogateescape', newline='') as f:
        f.write(text)
    return counts
