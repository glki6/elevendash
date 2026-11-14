"""Stop private data reaching a public repository. Run before every push (tools/hooks/pre-push does it for you).

It collects what must never be published from the workspace this repository sits in, and looks for it in what is
about to be pushed:

  - every identifying value in your game logs (account ids, names, tokens, location: the fields `elevendash redact`
    removes), read from logs/
  - your Google client and token values, if you use youtube/ (from ~/.eleven-youtube)
  - the ids of your uploaded videos (videos.json)
  - anything you list in private-words.txt, one word or regular expression a line (your name, an address, ...)

It reads the files git would commit, and every file version in the commits being pushed, with their messages and
authors. It prints file names and counts only, never a value, and exits 1 on any hit. With no workspace data next to
the code (someone else's clone) there is nothing to look for and it passes.

usage: python tools/prepush/check.py [--all | REF ...]      (default: what is in the index and in HEAD's history)
       python tools/prepush/check.py --hook                 (the pre-push hook: reads git's "local-ref local-sha
                                                             remote-ref remote-sha" lines from standard input)
"""
import glob
import json
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, 'src'))
from elevendash import redact  # noqa: E402

ZERO = '0' * 40
LOGLINE = re.compile(r'\[\d\d/\d\d/\d{4} \d\d:\d\d:\d\d\]\[')
# Generated logs for the demo and the tests look like logs on purpose.
LOG_OK = ('src/elevendash/sample.py', 'tests/')


def git(*args, text=True):
    r = subprocess.run(['git', *args], cwd=REPO, capture_output=True, check=True)
    return r.stdout.decode('utf-8', errors='replace') if text else r.stdout


def private():
    """(compiled patterns, what was collected) from the workspace. Values never leave this process."""
    counts = {}
    values = set()
    for log in glob.glob(os.path.join(REPO, 'logs', 'ALL-*.log')):
        with open(log, encoding='utf-8', errors='replace') as f:
            text = f.read()
        for m in redact.FIELD.finditer(text):
            values.update(v for v in redact._values(m.group(2)) if redact._worth(v))
    counts['log values'] = len(values)
    pats = [redact._pattern(v) for v in values]

    secrets = set()
    home = os.path.join(os.path.expanduser('~'), '.eleven-youtube')
    for name in ('client_secret.json', 'token.json'):
        p = os.path.join(home, name)
        if os.path.exists(p):
            try:
                with open(p, encoding='utf-8') as f:
                    d = json.load(f)
            except (OSError, ValueError):
                continue
            d = d.get('installed', d)
            secrets.update(d[k] for k in ('client_id', 'client_secret', 'token', 'refresh_token', 'project_id')
                           if isinstance(d.get(k), str) and len(d[k]) > 8)
    counts['Google values'] = len(secrets)

    videos = set()
    p = os.path.join(REPO, 'videos.json')
    if os.path.exists(p):
        try:
            with open(p, encoding='utf-8') as f:
                found = re.findall(r'"(?:id|videoId|video|url)"\s*:\s*"([^"]+)"', f.read())
        except OSError:
            found = []
        for v in found:
            v = v.rsplit('/', 1)[-1].rsplit('=', 1)[-1]
            if re.fullmatch(r'[A-Za-z0-9_-]{11}', v):
                videos.add(v)
    counts['video ids'] = len(videos)
    pats += [re.compile(re.escape(s)) for s in secrets | videos]

    words = 0
    p = os.path.join(REPO, 'private-words.txt')
    if os.path.exists(p):
        with open(p, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    pats.append(re.compile(line, re.I))
                    words += 1
    counts['private words'] = words
    return pats, counts


def look(text, path, pats):
    found = []
    n = sum(1 for p in pats if p.search(text))
    if n:
        found.append(f'{n} private value(s)')
    if LOGLINE.search(text) and not path.startswith(LOG_OK):
        found.append('lines that look like a game log')
    if path.lower().endswith('.log') or path.startswith('logs/') or '/logs/' in path:
        found.append('a log file')
    return found


def main(argv):
    hook = argv[:1] == ['--hook']
    argv = [a for a in argv if a != '--hook']
    ranges = []
    if hook:
        for line in sys.stdin.read().splitlines():
            parts = line.split()
            if len(parts) == 4 and parts[1] != ZERO:        # a deleted ref has nothing to check
                ranges.append([parts[1]] if parts[3] == ZERO else [parts[1], '^' + parts[3]])
    if not ranges:
        ranges = [['--all']] if argv == ['--all'] else [argv or ['HEAD']]
    pats, counts = private()
    hits = 0

    # 1. the files git would commit now
    files = [f for f in git('ls-files', '--cached', '-z').split('\0') if f]
    for name in files:
        try:
            with open(os.path.join(REPO, name), encoding='utf-8', errors='replace') as f:
                text = f.read()
        except OSError:
            continue
        found = look(text, name, pats)
        if found:
            hits += 1
            print(f'HIT {name}: ' + '; '.join(found))

    # 2. every file version in the commits being pushed, and their messages and authors
    blobs, commits = {}, 0
    for rng in ranges:
        for line in git('rev-list', '--objects', *rng).splitlines():
            sha, _, path = line.partition(' ')
            if path:
                blobs.setdefault(sha, path)
        commits += len(git('rev-list', *rng).split())
        msgs = git('log', '--format=%B%n%an %ae%n%cn %ce', *rng)
        n = sum(1 for p in pats if p.search(msgs))
        if n:
            hits += 1
            print(f'HIT commit messages or authors: {n} private value(s)')
    if blobs:
        kinds = subprocess.run(['git', 'cat-file', '--batch-check=%(objectname) %(objecttype)'], cwd=REPO,
                               input='\n'.join(blobs).encode(), capture_output=True, check=True).stdout.decode().split('\n')
        for line in kinds:
            sha, _, kind = line.partition(' ')
            if kind != 'blob':
                continue
            found = look(git('cat-file', 'blob', sha, text=False).decode('utf-8', errors='replace'), blobs[sha], pats)
            if found:
                hits += 1
                print(f'HIT {blobs[sha]} ({sha[:8]}, in the history): ' + '; '.join(found))

    what = ', '.join(f'{v} {k}' for k, v in counts.items())
    print(f'leak check: looked for {what}; {len(files)} files, {commits} commits, {len(blobs)} file versions; hits: {hits}')
    if hits:
        print('Nothing was pushed. Remove what is listed above (from the history too, if it says so) and try again.')
    return 1 if hits else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
