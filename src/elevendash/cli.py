"""elevendash: match analysis and a shareable dashboard from Eleven Table Tennis (Quest) game logs.

  elevendash init [DIR] [--quest HOST]   make a workspace: a private folder for your logs and results
  elevendash fetch [--quest HOST]        copy new logs from the Quest over Wi-Fi (Eleven's File Sharing)
  elevendash import PATH [PATH ...]      copy logs you got another way (USB cable, a file manager)
  elevendash build                       turn the logs into match data
  elevendash report                      print your last session: results, notes, win rates
  elevendash site [--out FILE]           write the dashboard as one HTML file you can open, send or host
  elevendash pdf [--out FILE]            print the dashboard to a PDF (needs Chrome, Edge or Chromium)
  elevendash app [--shortcut]            the dashboard in your browser, with a button that imports new logs
  elevendash update [--offline]          fetch, build, report and site in one go: the usual after-session step
  elevendash config [KEY=VALUE ...]      show or change settings: hand (auto, right, left), theme (dark, light),
                                         lang (en, zh: Traditional Chinese)
  elevendash backup [--out FILE]         one file with your logs, notes and settings, to move to another computer
  elevendash restore FILE [DIR]          unpack a backup into a new workspace and build it
  elevendash export [--format csv|json]  matches, points and shots as tables for other tools (match data only)
  elevendash share --last N | --from DATE [--to DATE] | --match KEY
                                         a dashboard file of some matches only, to send to a coach
  elevendash demo [DIR]                  try it without a Quest: a workspace of made-up matches and its dashboard
  elevendash redact LOG OUT              a copy of a log without account, people or location data, to show someone

Every command works on the workspace in the current folder, or the one named by --dir or ELEVENDASH_HOME.
Game logs contain your Eleven and Meta account tokens: keep the workspace private, share only the dashboard file.
"""
import argparse
import contextlib
import datetime
import io
import json
import os
import runpy
import sys
import tempfile

from . import __version__, fetch, report, workspace
from .page import LANGS, THEMES
from .site import build_site


def lower_priority():
    """Run as a background job, so the computer stays responsive while a long build runs."""
    if os.name == 'nt':
        try:
            import ctypes
            k = ctypes.windll.kernel32
            k.SetPriorityClass(k.GetCurrentProcess(), 0x40)      # IDLE_PRIORITY_CLASS
        except Exception:
            pass
    else:
        try:
            os.nice(19)
        except (AttributeError, OSError):
            pass


def log_count(ws):
    return len([n for n in os.listdir(ws.logs) if fetch.LOG_NAME.match(n)]) if os.path.isdir(ws.logs) else 0


def do_fetch(ws, quest=None, say=print):
    host = quest or ws.config().get('quest')
    if not host:
        say('No Quest address yet. Start File Sharing in Eleven (Settings > Network Settings > File Sharing) and run '
            '"elevendash fetch --quest <the address it shows>". Or copy logs in with "elevendash import".')
        return None
    host = fetch.normalize_host(host)
    if quest:
        ws.set(quest=host)
    say(f'Checking the Quest at {host} ...')
    got = fetch.from_quest(host, ws.logs, say)
    say(f'  {len(got)} log file(s) copied.' if got else '  No new logs on the Quest.')
    return got


def do_build(ws, verbose=False, say=print, only=None, out=None):
    """Build the workspace's data. With only (match keys) and out (a folder), build those matches alone into that
    folder, with no video links, and leave the workspace's own data as it is (do_share)."""
    n = log_count(ws)
    if not n:
        raise SystemExit(f'No game logs in {ws.logs} yet. Run "elevendash fetch" or "elevendash import" first.')
    say(f'Building match data from {n} log file(s) ...')
    from . import health, i18n
    build = out or ws.build
    videos = ws.videos if only is None else os.path.join(build, 'no-videos.json')       # a file that is not there

    def run(side, **given):
        """One pass of the builder: 'ai' writes every match and the sums against the AI, 'people' the online sums."""
        argv = sys.argv
        sys.argv = ['elevendash.builddata', ws.logs, build, videos, ws.config().get('hand', 'auto'), side]
        try:
            sink = contextlib.nullcontext() if verbose else contextlib.redirect_stdout(io.StringIO())
            with sink:
                return runpy.run_module('elevendash.builddata', init_globals=given, run_name='__main__', alter_sys=False)
        finally:
            sys.argv = argv
            i18n.set_voice(None)

    def drop_online():
        for name in os.listdir(build):
            if name.endswith('_h.json'):
                os.remove(os.path.join(build, name))

    made = run('ai', **({} if only is None else {'ONLY': set(only)}))
    if any(not m['ai'] for m, *_ in made['M']):
        try:        # the online side is built from the same matches; if it fails, the rest of the dashboard stands
            run('people', PARSED=(made['M'], made['PROBLEMS']))
        except Exception as e:
            drop_online()
            say(f'  The online side could not be built ({type(e).__name__}: {e}). Everything else is unaffected; '
                'please report this at https://github.com/glki6/elevendash/issues.')
    else:
        drop_online()
    if only is not None:
        return {}
    say(f'  Data in {ws.build}')
    for line in health.advice(made.get('PROBLEMS')):
        say(line)
    return made.get('PROBLEMS') or {}       # {log name: what looks misread in it}; the app lists these after an import


def match_rows(ws):
    """The workspace's matches as built: [{key, date, session, ...}], oldest first."""
    try:
        with open(os.path.join(ws.build, 'matches.json'), encoding='utf-8') as f:
            return json.load(f)['rows']
    except (OSError, ValueError, KeyError):
        raise SystemExit('No match data yet. Run "elevendash build" first.')


def do_share(ws, keys, out=None, say=print, theme=None, lang=None):
    """A dashboard file built from some matches only, to send to a coach instead of the whole history. It is built
    as if those were all the matches there are: nothing of the others is in the file, and no video links.
    Returns (the file, how many matches)."""
    want = set(keys)
    keys = [r['key'] for r in match_rows(ws) if r['key'] in want]
    if not keys:
        raise SystemExit('None of those matches are in your data. Pick matches from the dashboard, or see "elevendash share --help".')
    n = len(keys)
    stamp = datetime.datetime.now().strftime('%Y-%m-%d-%H%M')
    out = os.path.abspath(out or os.path.join(ws.root, 'share', f'elevendash-{n}-match{"" if n == 1 else "es"}-{stamp}.html'))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    c = ws.config()
    with tempfile.TemporaryDirectory(dir=ws.root, prefix='.share-') as tmp:         # beside the data, never in the system's temp folder
        try:
            do_build(ws, say=lambda *a: None, only=keys, out=tmp)
            build_site(tmp, out, videos=False, theme=theme or c.get('theme', 'dark'), lang=lang or c.get('lang', 'en'))
        except SystemExit:
            raise
        except Exception as e:
            raise SystemExit(f'A dashboard of only {"that match" if n == 1 else f"those {n} matches"} could not be built '
                             f'({type(e).__name__}: {e}). Try a few more matches, and please report this at '
                             'https://github.com/glki6/elevendash/issues.')
    say(f'Shared dashboard: {out} ({n} match{"" if n == 1 else "es"}, {os.path.getsize(out) // 1024:,} KB).')
    say('  It holds those matches only, as match data: no logs, tokens, account details, names or video links.')
    return out, n


def share_keys(ws, last=None, since=None, until=None, matches=()):
    """The matches an "elevendash share" command names: the last N sessions, a stretch of dates, and single matches."""
    rows = match_rows(ws)
    keys = set(matches)
    if last:
        sessions = sorted({r['session'] for r in rows})[-last:]
        keys |= {r['key'] for r in rows if r['session'] in sessions}
    if since or until:
        keys |= {r['key'] for r in rows if (since or '') <= r['date'] <= (until or '9999')}
    return [r['key'] for r in rows if r['key'] in keys]


def do_report(ws, say=print):
    if not os.path.exists(os.path.join(ws.build, 'sessions.json')):
        raise SystemExit('No match data yet. Run "elevendash build" first.')
    for line in report.session_report(ws.build):
        say(line)


def do_site(ws, out=None, videos=True, say=print, theme=None, lang=None):
    out = out or os.path.join(ws.site, 'index.html')
    c = ws.config()
    build_site(ws.build, out, videos=videos, theme=theme or c.get('theme', 'dark'), lang=lang or c.get('lang', 'en'))
    say(f'Dashboard: {out} ({os.path.getsize(out) // 1024:,} KB). Open it in a browser; it works offline.')
    return out


SETTINGS = {
    'hand': (('auto', 'right', 'left'), 'the hand you hold the paddle in; auto reads it from the game logs'),
    'theme': (THEMES, 'how the dashboard and PDF open; the page has a switch for the other'),
    'lang': (LANGS, 'the language the dashboard and PDF open in: en, or zh for Traditional Chinese'),
}


def do_config(ws, pairs, say=print):
    """Show the settings, or set KEY=VALUE pairs. A changed hand takes effect at the next build."""
    new = {}
    for pair in pairs:
        key, _, value = pair.partition('=')
        if key not in SETTINGS or value not in SETTINGS[key][0]:
            choices = '; '.join(f'{k}={"|".join(v[0])}' for k, v in SETTINGS.items())
            say(f'elevendash config: {pair!r} is not a setting. Settings: {choices}')
            return 2
        new[key] = value
    if new:
        ws.set(**new)
    c = ws.config()
    for key, (choices, text) in SETTINGS.items():
        say(f'{key} = {c.get(key, choices[0])}    ({text})')
    if 'hand' in new:
        say('Run "elevendash build" for the new hand to reach the data.')
    return 0


def do_demo(path, say=print):
    """A workspace of generated logs (src/elevendash/sample.py), built and drawn: the whole tool without a Quest."""
    from . import sample
    ws = workspace.init(path)
    if log_count(ws):
        say(f'{ws.logs} already holds game logs. Pick a new or empty folder for the demo, so made-up matches never mix '
            'with real ones.')
        return 2
    ws.set(sample=True)
    names = sample.write_logs(ws.logs)
    say(f'Demo workspace: {ws.root} ({len(names)} made-up sessions: {len(sample.SESSIONS)} against the AI, {len(sample.ONLINE)} online)')
    do_build(ws, say=say)
    say('')
    do_report(ws, say=say)
    say('')
    do_site(ws, say=say)
    return 0


def do_redact(src, dst, say=print):
    from .redact import redact_file
    try:
        n = redact_file(src, dst)
    except (OSError, ValueError) as e:
        say(f'elevendash redact: {e}')
        return 1
    say(f'Redacted copy: {dst}')
    say(f"  {n['fields']} fields cleared, {n['mentions']} more mentions of their values, {n['addresses']} network "
        f"addresses, {n['dropped']} lines of UserCommunication dropped.")
    if n['left']:
        say(f"  {n['left']} cleared value(s) still appear in the text: do not share this copy; please report it.")
        return 1
    say('  Read it before you share it: a game update can add fields elevendash does not know about yet.')
    return 0


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(prog='elevendash', description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--version', action='version', version=f'elevendash {__version__}')
    ap.add_argument('--dir', help='the workspace folder (default: ELEVENDASH_HOME, else the current folder)')
    ap.add_argument('--nice', action='store_true', help='run at the lowest CPU priority')
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('init', help='make a workspace')
    p.add_argument('path', nargs='?', default='.', help='the folder to use (default: the current folder)')
    p.add_argument('--quest', help="the Quest's File Sharing address, host or host:port")
    p = sub.add_parser('fetch', help='copy new logs from the Quest over Wi-Fi')
    p.add_argument('--quest', help="the Quest's File Sharing address (remembered for next time)")
    p = sub.add_parser('import', help='copy logs from files or folders')
    p.add_argument('paths', nargs='+')
    p = sub.add_parser('build', help='turn the logs into match data')
    p.add_argument('-v', '--verbose', action='store_true', help='list every data file written')
    sub.add_parser('report', help="print your last session's report")
    for name, text in (('site', 'write the dashboard as one HTML file'), ('pdf', 'print the dashboard to a PDF')):
        p = sub.add_parser(name, help=text)
        p.add_argument('--out', help='where to write it')
        p.add_argument('--no-videos', action='store_true', help='leave out the links to your YouTube uploads')
        p.add_argument('--theme', choices=THEMES, help='dark or light (default: the theme setting, else dark)')
        p.add_argument('--lang', choices=LANGS, help='en, or zh for Traditional Chinese (default: the lang setting, else en)')
    p = sub.add_parser('config', help='show or change settings')
    p.add_argument('pairs', nargs='*', metavar='KEY=VALUE', help='hand=auto|right|left, theme=dark|light, lang=en|zh')
    p = sub.add_parser('backup', help='write one file holding your logs, notes and settings')
    p.add_argument('--out', help='where to write it (default: backups/ in the workspace)')
    p = sub.add_parser('restore', help='unpack a backup into a new workspace and build it')
    p.add_argument('file', help='the backup (elevendash-backup-*.zip)')
    p.add_argument('path', nargs='?', help='the folder to restore into (default: --dir, ELEVENDASH_HOME, else the current folder)')
    p = sub.add_parser('export', help='write matches, points and shots as CSV or JSON')
    p.add_argument('--format', choices=('csv', 'json'), default='csv')
    p.add_argument('--out', help='the folder to write into (default: export/ in the workspace)')
    p = sub.add_parser('share', help='write a dashboard of some matches only, to send to a coach')
    p.add_argument('--last', type=int, metavar='N', help='the last N sessions')
    p.add_argument('--from', dest='since', metavar='DATE', help='matches from this day on (YYYY-MM-DD)')
    p.add_argument('--to', dest='until', metavar='DATE', help='matches up to this day (YYYY-MM-DD)')
    p.add_argument('--match', action='append', default=[], metavar='KEY', help='one match, by its start: "YYYY-MM-DD HH:MM:SS" (may repeat)')
    p.add_argument('--out', help='where to write it (default: share/ in the workspace)')
    p.add_argument('--theme', choices=THEMES)
    p.add_argument('--lang', choices=LANGS)
    p = sub.add_parser('update', help='fetch, build, report and site in one go')
    p.add_argument('--offline', action='store_true', help='do not contact the Quest; rebuild from the logs you have')
    p.add_argument('--quest', help="the Quest's File Sharing address (remembered for next time)")
    p.add_argument('--no-videos', action='store_true', help='leave out the links to your YouTube uploads')
    p = sub.add_parser('app', help='open the dashboard in your browser, with an Import button (runs until you close it)')
    p.add_argument('--port', type=int, default=None, help='the local port (default 8737, or any free one)')
    p.add_argument('--no-browser', action='store_true', help='start the app without opening a browser tab')
    p.add_argument('--shortcut', action='store_true', help='add Eleven Dashboard to the Start menu and the desktop (Windows), then stop')
    p = sub.add_parser('demo', help='make a workspace of made-up matches and build its dashboard (no Quest needed)')
    p.add_argument('path', nargs='?', default='elevendash-demo', help='a new or empty folder (default: elevendash-demo)')
    p = sub.add_parser('redact', help='write a copy of a log without account, people or location data')
    p.add_argument('log', help='the game log (ALL-*.log)')
    p.add_argument('out', help='where to write the redacted copy (a new file)')
    a = ap.parse_args(argv)
    if a.nice:
        lower_priority()

    if a.cmd == 'init':
        ws = workspace.init(a.path, fetch.normalize_host(a.quest) if a.quest else None)
        print(f'Workspace ready: {ws.root}')
        print('Next: "elevendash fetch --quest <address>" (Eleven > Settings > Network Settings > File Sharing), '
              'or "elevendash import <folder with ALL-*.log files>".')
        return 0
    if a.cmd == 'demo':
        return do_demo(a.path)
    if a.cmd == 'app':
        from . import app
        try:
            return app.run(a.dir, a.port or app.PORT, open_browser=not a.no_browser, shortcut=a.shortcut)
        except (OSError, RuntimeError, ValueError) as e:
            print(f'elevendash app: {e}', file=sys.stderr)
            return 1
    if a.cmd == 'redact':
        return do_redact(a.log, a.out)
    if a.cmd == 'restore':
        from . import backup
        try:
            backup.restore(a.file, a.path or a.dir or os.environ.get('ELEVENDASH_HOME') or os.getcwd())
            ws = workspace.find(a.path or a.dir)
            do_build(ws)
            do_site(ws)
        except (OSError, ValueError) as e:
            print(f'elevendash restore: {e}', file=sys.stderr)
            return 1
        return 0
    try:
        ws = workspace.find(a.dir)
    except workspace.NotAWorkspace as e:
        print(e, file=sys.stderr)
        return 2
    try:
        if a.cmd == 'fetch':
            return 0 if do_fetch(ws, a.quest) is not None else 1
        if a.cmd == 'import':
            got = fetch.from_files(a.paths, ws.logs)
            print(f'{len(got)} log file(s) copied into {ws.logs}.')
            return 0
        if a.cmd == 'build':
            do_build(ws, a.verbose)
            return 0
        if a.cmd == 'report':
            do_report(ws)
            return 0
        if a.cmd == 'site':
            do_site(ws, a.out, not a.no_videos, theme=a.theme, lang=a.lang)
            return 0
        if a.cmd == 'config':
            return do_config(ws, a.pairs)
        if a.cmd == 'backup':
            from . import backup
            path, n = backup.make(ws, a.out)
            print(f'Backup: {path} ({n["logs"]} log file(s), {n["bytes"] // 1024:,} KB)')
            print('It holds your game logs, and they hold your Eleven and Meta account tokens: keep it on your own drives,')
            print('and never send or post it. On the other computer: elevendash restore <this file> <a new folder>.')
            return 0
        if a.cmd == 'export':
            from . import export
            got = export.write(ws.build, a.out or os.path.join(ws.root, 'export'), a.format)
            print(f'Export: {got["dir"]} ({", ".join(got["files"])})')
            print('  ' + ', '.join(f'{n:,} {k}' for k, n in got['rows'].items()) + '. Match data only: no log lines, tokens or account details.')
            return 0
        if a.cmd == 'share':
            if not (a.last or a.since or a.until or a.match):
                print('elevendash share: say which matches: --last N (sessions), --from DATE [--to DATE], or --match KEY', file=sys.stderr)
                return 2
            do_share(ws, share_keys(ws, a.last, a.since, a.until, a.match), a.out, theme=a.theme, lang=a.lang)
            return 0
        if a.cmd == 'pdf':
            from .pdf import make_pdf
            out = a.out or os.path.join(ws.site, 'report.pdf')
            c = ws.config()
            make_pdf(ws.build, out, videos=not a.no_videos, theme=a.theme or c.get('theme', 'dark'), lang=a.lang or c.get('lang', 'en'))
            print(f'PDF: {out} ({os.path.getsize(out) // 1024:,} KB)')
            return 0
        if a.cmd == 'update':
            if a.offline:
                print('Offline: using the logs already in the workspace.')
            else:
                try:
                    do_fetch(ws, a.quest)
                except fetch.QuestUnreachable as e:
                    print(e)
                    print('Going on with the logs already in the workspace.')
            do_build(ws)
            print()
            do_report(ws)
            print()
            do_site(ws, None, not a.no_videos)
            return 0
    except fetch.QuestUnreachable as e:
        print(e, file=sys.stderr)
        return 1
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        print(f'elevendash: {e}', file=sys.stderr)
        return 1
    return 0
