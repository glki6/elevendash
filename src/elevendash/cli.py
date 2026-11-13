"""elevendash: match analysis and a shareable dashboard from Eleven Table Tennis (Quest) game logs.

  elevendash init [DIR] [--quest HOST]   make a workspace: a private folder for your logs and results
  elevendash fetch [--quest HOST]        copy new logs from the Quest over Wi-Fi (Eleven's File Sharing)
  elevendash import PATH [PATH ...]      copy logs you got another way (USB cable, a file manager)
  elevendash build                       turn the logs into match data
  elevendash report                      print your last session: results, notes, win rates
  elevendash site [--out FILE]           write the dashboard as one HTML file you can open, send or host
  elevendash pdf [--out FILE]            print the dashboard to a PDF (needs Chrome, Edge or Chromium)
  elevendash update [--offline]          fetch, build, report and site in one go: the usual after-session step
  elevendash config [KEY=VALUE ...]      show or change settings: hand (auto, right, left), theme (dark, light),
                                         lang (en, zh: Traditional Chinese)
  elevendash demo [DIR]                  try it without a Quest: a workspace of made-up matches and its dashboard
  elevendash redact LOG OUT              a copy of a log without account, people or location data, to show someone

Every command works on the workspace in the current folder, or the one named by --dir or ELEVENDASH_HOME.
Game logs contain your Eleven and Meta account tokens: keep the workspace private, share only the dashboard file.
"""
import argparse
import contextlib
import io
import os
import runpy
import sys

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


def do_build(ws, verbose=False, say=print):
    n = log_count(ws)
    if not n:
        raise SystemExit(f'No game logs in {ws.logs} yet. Run "elevendash fetch" or "elevendash import" first.')
    say(f'Building match data from {n} log file(s) ...')
    argv = sys.argv
    sys.argv = ['elevendash.builddata', ws.logs, ws.build, ws.videos, ws.config().get('hand', 'auto')]
    try:
        sink = contextlib.nullcontext() if verbose else contextlib.redirect_stdout(io.StringIO())
        with sink:
            runpy.run_module('elevendash.builddata', run_name='__main__', alter_sys=False)
    finally:
        sys.argv = argv
    say(f'  Data in {ws.build}')


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
    say(f'Demo workspace: {ws.root} ({len(names)} made-up sessions against the AI)')
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
    p = sub.add_parser('update', help='fetch, build, report and site in one go')
    p.add_argument('--offline', action='store_true', help='do not contact the Quest; rebuild from the logs you have')
    p.add_argument('--quest', help="the Quest's File Sharing address (remembered for next time)")
    p.add_argument('--no-videos', action='store_true', help='leave out the links to your YouTube uploads')
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
    if a.cmd == 'redact':
        return do_redact(a.log, a.out)
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
