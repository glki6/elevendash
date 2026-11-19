"""One file holding a whole workspace, to move it to another computer.

A backup is a zip of what cannot be made again: the game logs, your notes, journal and goals (notes.json), the video
record (videos.json) and the settings. The built data and the dashboard are left out; restoring builds them again.

The logs hold your Eleven and Meta account tokens, so a backup is as private as the workspace itself: keep it on your
own drives, and never send or post it. To show someone your matches, send the dashboard file (elevendash site, or
elevendash share for some matches only).

Restoring takes only the names a backup may hold, each to its own place, so a file made to look like a backup cannot
write anywhere else. It goes into a workspace that holds no game logs yet.
"""
import datetime
import json
import os
import shutil
import zipfile

from . import __version__, workspace
from .fetch import LOG_NAME

MARK = 'elevendash-backup.json'                 # says what the file is
FILES = ('notes.json', 'videos.json')           # kept as they are
SETTINGS = ('version', 'quest', 'hand', 'theme', 'lang', 'sample')      # of elevendash.json; the rest belongs to one computer
MAX_FILE = 1 << 30                              # the largest log taken out of a backup
MAX_TOTAL = 16 << 30


def _logs(ws):
    return sorted(n for n in os.listdir(ws.logs) if LOG_NAME.match(n)) if os.path.isdir(ws.logs) else []


def make(ws, out=None):
    """Write the backup of a workspace. Returns (path, {'logs': how many, 'bytes': its size})."""
    names = _logs(ws)
    if not names:
        raise ValueError('there are no game logs to back up yet')
    now = datetime.datetime.now()
    out = os.path.abspath(out or os.path.join(ws.root, 'backups', f'elevendash-backup-{now:%Y-%m-%d-%H%M}.zip'))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    part = out + '.part'
    try:
        with zipfile.ZipFile(part, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            z.writestr(MARK, json.dumps({'app': 'elevendash', 'version': __version__, 'made': now.isoformat(timespec='seconds'),
                                         'logs': len(names)}, indent=1))
            c = ws.config()
            z.writestr(workspace.CONFIG, json.dumps({k: c[k] for k in SETTINGS if k in c}, indent=1))
            for name in FILES:
                path = os.path.join(ws.root, name)
                if os.path.isfile(path):
                    z.write(path, name)
            for name in names:
                z.write(os.path.join(ws.logs, name), 'logs/' + name)
        os.replace(part, out)
    finally:
        if os.path.exists(part):
            os.remove(part)
    return out, {'logs': len(names), 'bytes': os.path.getsize(out)}


def restore(path, root, say=print):
    """Unpack a backup into the workspace at root (made if it is not there), which must hold no game logs yet.
    Returns {'logs': how many, 'notes': whether notes came with it}."""
    try:
        return _restore(path, root, say)
    except zipfile.BadZipFile:
        raise ValueError('that backup is damaged and could not be read')


def _restore(path, root, say):
    if not zipfile.is_zipfile(path):
        raise ValueError('that is not an elevendash backup (not a zip file)')
    with zipfile.ZipFile(path) as z:
        infos = {i.filename: i for i in z.infolist() if not i.is_dir()}
        try:
            mark = json.loads(z.read(infos[MARK]).decode('utf-8')) if infos[MARK].file_size < 65536 else {}
        except (KeyError, ValueError):
            mark = {}
        if not isinstance(mark, dict) or mark.get('app') != 'elevendash':
            raise ValueError('that is not an elevendash backup')
        logs = [n for n in infos if n.startswith('logs/') and LOG_NAME.match(n[5:])]
        if not logs:
            raise ValueError('that backup holds no game logs')
        take = logs + [n for n in FILES if n in infos]
        if any(infos[n].file_size > MAX_FILE for n in take) or sum(infos[n].file_size for n in take) > MAX_TOTAL:
            raise ValueError('that backup is larger than any workspace should be')
        ws = workspace.init(root)
        if _logs(ws):
            raise ValueError(f'{ws.root} already holds game logs. Restore into a new or empty folder, so two sets of matches never mix.')
        settings = {}
        if workspace.CONFIG in infos and infos[workspace.CONFIG].file_size < 65536:
            try:
                c = json.loads(z.read(infos[workspace.CONFIG]).decode('utf-8'))
                settings = {k: c[k] for k in SETTINGS if isinstance(c, dict) and isinstance(c.get(k), (str, int, bool))}
            except ValueError:
                pass
        for n in take:
            dest = os.path.join(ws.logs, n[5:]) if n.startswith('logs/') else os.path.join(ws.root, n)
            with z.open(infos[n]) as src, open(dest + '.part', 'wb') as out:
                shutil.copyfileobj(src, out, 1 << 20)
            os.replace(dest + '.part', dest)
        if settings:
            ws.set(**settings)
    say(f'  Restored {len(logs)} log file(s) into {ws.root}' + (f', made by elevendash {mark["version"]}' if mark.get('version') else ''))
    return {'logs': len(logs), 'notes': 'notes.json' in take}
