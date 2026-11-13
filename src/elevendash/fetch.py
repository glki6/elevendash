"""Copy Eleven game logs into a workspace: over Wi-Fi from the game's File Sharing, or from files copied another way.

File Sharing is started inside Eleven (Settings > Network Settings > File Sharing) and shows the Quest's address. Only
two read requests are ever sent to it: /getListing and /downloadFile. Nothing is uploaded to the Quest or deleted.
"""
import json
import os
import re
import shutil
import urllib.error
import urllib.parse
import urllib.request

LOG_NAME = re.compile(r'^ALL-\d{2}\.\d{2}\.\d{4}\.\d{1,2}\.\d{2}\.\d{2}\.(AM|PM)\.log$')
DEFAULT_PORT = 8090


class QuestUnreachable(Exception):
    pass


def normalize_host(host):
    """'192.168.1.20', '192.168.1.20:8090' or 'http://192.168.1.20:8090/' -> '192.168.1.20:8090'."""
    h = host.strip()
    h = re.sub(r'^https?://', '', h).strip('/')
    if not re.fullmatch(r'[A-Za-z0-9.\-]+(:\d{1,5})?', h):
        raise ValueError(f'not a host or host:port: {host!r}')
    return h if ':' in h else f'{h}:{DEFAULT_PORT}'


def from_quest(host, logs_dir, say=print):
    """Copy logs that are new, or have grown, from the Quest into logs_dir. Returns the names copied."""
    base = f'http://{normalize_host(host)}'
    try:
        with urllib.request.urlopen(f'{base}/getListing?path=logs', timeout=10) as r:
            listing = json.load(r)['output']
    except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
        raise QuestUnreachable(f'Quest not reached at {host} ({e}). Open Eleven and start File Sharing '
                               '(Settings > Network Settings > File Sharing), on the same network as this computer.')
    os.makedirs(logs_dir, exist_ok=True)
    got = []
    for f in listing:
        name, size = str(f.get('name', '')), int(f.get('size') or 0)
        if f.get('type') != 'file' or not LOG_NAME.match(name):   # the name is checked, so it cannot point elsewhere
            continue
        dest = os.path.join(logs_dir, name)
        have = os.path.getsize(dest) if os.path.exists(dest) else -1
        if have >= size:
            if have > size:
                say(f'  kept the larger local copy of {name} ({have:,} bytes here, {size:,} on the Quest)')
            continue
        part = dest + '.part'
        url = f'{base}/downloadFile?path=' + urllib.parse.quote('logs/' + name)
        with urllib.request.urlopen(url, timeout=180) as r, open(part, 'wb') as out:
            shutil.copyfileobj(r, out, 1 << 20)
        n = os.path.getsize(part)
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
