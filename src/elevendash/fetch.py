"""Copy Eleven game logs into a workspace: over Wi-Fi from the game's File Sharing, or from files copied another way.

File Sharing is started inside Eleven (Settings > Network Settings > File Sharing) and shows the Quest's address. Only
two read requests are ever sent to it: /getListing and /downloadFile. Nothing is uploaded to the Quest or deleted.
"""
import json
import os
import re
import shutil
import socket
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

LOG_NAME = re.compile(r'^ALL-\d{2}\.\d{2}\.\d{4}\.\d{1,2}\.\d{2}\.\d{2}\.(AM|PM)\.log\Z')    # \Z: no newline after it
DEFAULT_PORT = 8090


MAX_LOG = 200 << 20             # the largest log taken from the headset (a long day of play is a few MB)
MAX_LISTING = 16 << 20         # the largest list of files read from it


class QuestUnreachable(Exception):
    pass


class PortError(ValueError):
    """An address whose number after the colon cannot be a port."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """File Sharing answers where it was asked: a reply that points elsewhere is not followed."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, 'a redirect, not followed', headers, fp)


_open = urllib.request.build_opener(_NoRedirect).open


def _listing(url, timeout=10):
    with _open(url, timeout=timeout) as r:
        raw = r.read(MAX_LISTING + 1)
    if len(raw) > MAX_LISTING:
        raise ValueError('the list of files is too large')
    return json.loads(raw.decode('utf-8'))['output']


_LABEL = re.compile(r'(?!-)[A-Za-z0-9-]{1,63}(?<!-)')


def _is_name(name):
    """Four numbers 0 to 255 with dots, a name with a dot in it (quest.local), or localhost."""
    if re.fullmatch(r'[\d.]+', name):
        parts = name.split('.')
        return len(parts) == 4 and all(p.isdigit() and len(p) <= 3 and int(p) <= 255 for p in parts)
    if name.lower() == 'localhost':
        return True
    labels = name.split('.')
    return len(labels) > 1 and all(_LABEL.fullmatch(x) for x in labels)


def normalize_host(host):
    """'192.168.1.20', '192.168.1.20:8090' or 'http://192.168.1.20:8090/' -> '192.168.1.20:8090'. Full-width digits,
    colons and stops, as a Chinese keyboard types them, count as the plain ones."""
    shown = str(host).strip()
    h = unicodedata.normalize('NFKC', shown).replace('\u3002', '.').strip()
    h = re.sub(r'^https?://', '', h, flags=re.I).strip('/')
    m = re.fullmatch(r'([A-Za-z0-9.\-]+)(?::(\d{1,5}))?', h)
    if not m or not _is_name(m.group(1)):
        raise ValueError(f'"{shown}" is not an address. The headset shows one like 192.168.1.20:8090: four numbers with dots, '
                         'then a colon and a number.')
    if m.group(2) is not None and not 0 < int(m.group(2)) < 65536:
        raise PortError(f'"{shown}" has {m.group(2)} after the colon, and that cannot be the number File Sharing shows. '
                        'It is a number from 1 to 65535, such as 8090.')
    return f'{m.group(1)}:{int(m.group(2))}' if m.group(2) else f'{m.group(1)}:{DEFAULT_PORT}'


def check(host, timeout=5):
    """The connection to the headset, step by step, for the app's welcome screen: is this an address, does anything
    answer there, is it Eleven's File Sharing, are there game logs. Reads the list of logs only (the first of the two
    requests from_quest sends). Returns {ok, host, logs, steps: [{step, ok}]}, stopping at the first step that fails."""
    out = {'ok': False, 'host': '', 'logs': 0, 'steps': []}

    def step(name, ok):
        out['steps'].append({'step': name, 'ok': bool(ok)})
        return ok

    try:
        h = normalize_host(str(host or ''))
    except ValueError as e:
        if isinstance(e, PortError):
            out['why'] = 'port'
        step('address', False)
        return out
    out['host'] = h
    name, _, port = h.partition(':')
    step('address', True)
    try:
        socket.create_connection((name, int(port)), timeout=timeout).close()
    except (OSError, OverflowError, ValueError):
        step('reach', False)
        return out
    step('reach', True)
    try:
        listing = _listing(f'http://{h}/getListing?path=logs')
        if not isinstance(listing, list):
            raise ValueError('not a listing')
    except (urllib.error.URLError, OSError, ValueError, KeyError, TypeError):
        step('sharing', False)
        return out
    step('sharing', True)
    out['logs'] = sum(1 for f in listing if isinstance(f, dict) and f.get('type') == 'file' and LOG_NAME.match(str(f.get('name', ''))))
    out['ok'] = bool(step('logs', out['logs'] > 0))
    return out


def from_quest(host, logs_dir, say=print):
    """Copy logs that are new, or have grown, from the Quest into logs_dir. Returns the names copied."""
    base = f'http://{normalize_host(host)}'
    try:
        listing = _listing(f'{base}/getListing?path=logs')
        if not isinstance(listing, list):
            raise ValueError('not a listing')
    except (urllib.error.URLError, OSError, ValueError, KeyError, TypeError) as e:
        raise QuestUnreachable(f'Quest not reached at {host} ({e}). Open Eleven and start File Sharing '
                               '(Settings > Network Settings > File Sharing), on the same network as this computer.')
    os.makedirs(logs_dir, exist_ok=True)
    got = []
    for f in listing:
        if not isinstance(f, dict):
            continue
        name = str(f.get('name', ''))
        try:
            size = int(f.get('size') or 0)
        except (TypeError, ValueError):
            continue
        if f.get('type') != 'file' or not LOG_NAME.match(name):   # the name is checked, so it cannot point elsewhere
            continue
        if size > MAX_LOG:
            say(f'  {name}: {size:,} bytes, larger than any game log; skipped')
            continue
        dest = os.path.join(logs_dir, name)
        have = os.path.getsize(dest) if os.path.exists(dest) else -1
        if have >= size:
            if have > size:
                say(f'  kept the larger local copy of {name} ({have:,} bytes here, {size:,} on the Quest)')
            continue
        part = dest + '.part'
        url = f'{base}/downloadFile?path=' + urllib.parse.quote('logs/' + name)
        n, too_big = 0, False
        try:
            with _open(url, timeout=180) as r, open(part, 'wb') as out:
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    n += len(chunk)
                    if n > MAX_LOG:
                        too_big = True
                        break
                    out.write(chunk)
        except (urllib.error.URLError, OSError) as e:     # this one log failed (or pointed elsewhere): the rest go on
            if os.path.exists(part):
                os.remove(part)
            say(f'  {name}: not copied ({getattr(e, "reason", None) or e})')
            continue
        if too_big:
            os.remove(part)
            say(f'  {name}: more than {MAX_LOG >> 20} MB came, larger than any game log; discarded')
            continue
        if n < size:   # cut short; the log of a game still running may grow, never shrink
            os.remove(part)
            say(f'  {name}: got {n:,} of {size:,} bytes, discarded')
            continue
        os.replace(part, dest)
        got.append(name)
        say(f'  {"updated" if have >= 0 else "new"}: {name} ({n:,} bytes)')
    return got


def from_files(paths, logs_dir, say=print):
    """Copy ALL-*.log files, or the ones in the given folders, into logs_dir: new ones and ones that have grown."""
    files = []
    for p in paths:
        if os.path.isdir(p):
            files += [os.path.join(p, n) for n in sorted(os.listdir(p))]
        else:
            files.append(p)
    os.makedirs(logs_dir, exist_ok=True)
    got, skipped = [], 0
    for f in files:
        name = os.path.basename(f)
        if not os.path.isfile(f) or not LOG_NAME.match(name):
            skipped += 1
            continue
        dest = os.path.join(logs_dir, name)
        if os.path.abspath(f) == os.path.abspath(dest):
            continue
        size, have = os.path.getsize(f), os.path.getsize(dest) if os.path.exists(dest) else -1
        if have >= size:
            continue
        shutil.copyfile(f, dest + '.part')
        os.replace(dest + '.part', dest)
        got.append(name)
        say(f'  {"updated" if have >= 0 else "new"}: {name} ({size:,} bytes)')
    if skipped:
        say(f'  {skipped} file(s) skipped: not named like a game log (ALL-MM.DD.YYYY.h.mm.ss.AM.log)')
    return got
