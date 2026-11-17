"""elevendash app: your dashboard in your own browser, with an Import button.

`elevendash app` starts a small web server on this computer only (127.0.0.1) and opens the dashboard in your default
browser. A bar above the dashboard imports new logs: from the Quest over Wi-Fi (the same two read-only requests as
`elevendash fetch`), or from log files you pick. Then it rebuilds the data and the page reloads with your new session.
Nothing is hosted anywhere and nothing leaves this computer, except those reads from your own Quest.

The server answers only this computer, only pages it served itself (a per-run key in the page; requests from other
websites are refused), and stops on its own a while after the last dashboard tab is closed. Starting it again while it
runs just opens the browser on the running one. Match notes are kept in the workspace (notes.json), not in the browser.
"""
import datetime
import http.server
import json
import os
import secrets
import shutil
import socketserver
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser

from . import __version__, cli, fetch, report, workspace
from .page import LANGS, THEMES
from .site import TITLE, tokens_css
from .page import look as read_look

PORT = 8737                    # the usual port, so the address (and what the browser keeps for it) stays the same
IDLE_EXIT = 20 * 60            # seconds without a request from an open page before the server stops
MAX_LOG = 200 << 20            # the largest log file an upload may carry
MAX_NOTES = 4 << 20
STATE = '.app.json'            # in the workspace: the port of the running app, so a second start finds it
NOTES = 'notes.json'
INCOMING = '.incoming'         # uploaded logs wait here until the import job copies them in
APP_NAME = 'Eleven Dashboard'
SETTINGS = {'hand': ('auto', 'right', 'left'), 'theme': THEMES, 'lang': LANGS}


def default_home():
    """Where the app keeps its data when no workspace is named: Documents/elevendash, else ~/elevendash."""
    docs = os.path.join(os.path.expanduser('~'), 'Documents')
    return os.path.join(docs if os.path.isdir(docs) else os.path.expanduser('~'), 'elevendash')


def pick_workspace(explicit=None):
    """The workspace named by --dir (made if new), else ELEVENDASH_HOME or the current folder when either is one,
    else the default folder (made if new). The app never needs a terminal, so it never stops for want of a folder."""
    if explicit:
        return workspace.init(explicit)
    for root in (os.environ.get('ELEVENDASH_HOME'), os.getcwd()):
        if root and os.path.isfile(os.path.join(root, workspace.CONFIG)):
            return workspace.Workspace(root)
    return workspace.init(os.environ.get('ELEVENDASH_HOME') or default_home())


def lower_priority():
    """The server stays responsive while the build thread runs at the lowest priority (lower_build_thread)."""
    if os.name == 'nt':
        try:
            import ctypes
            k = ctypes.windll.kernel32
            k.SetPriorityClass(k.GetCurrentProcess(), 0x4000)      # BELOW_NORMAL_PRIORITY_CLASS
        except Exception:
            pass
    else:
        try:
            os.nice(10)
        except (AttributeError, OSError):
            pass


def lower_build_thread():
    if os.name == 'nt':
        try:
            import ctypes
            k = ctypes.windll.kernel32
            k.SetThreadPriority(k.GetCurrentThread(), -15)          # THREAD_PRIORITY_IDLE
        except Exception:
            pass


class Job:
    """The one import or rebuild that may run at a time, and what it said."""

    def __init__(self):
        self.lock = threading.Lock()
        self.busy = False
        self.kind = ''
        self.lines = []
        self.result = None          # {ok, code, changed, headline, message}
        self.seq = 0                # counts finished jobs, so a page sees that one ended

    def say(self, line=''):
        with self.lock:
            self.lines.append(str(line))
            del self.lines[:-200]

    def view(self):
        with self.lock:
            return {'busy': self.busy, 'kind': self.kind, 'lines': self.lines[-40:], 'result': self.result, 'seq': self.seq}


class App:
    def __init__(self, ws, port=PORT, idle_exit=IDLE_EXIT, open_browser=True):
        self.ws = ws
        self.port = port
        self.idle_exit = idle_exit
        self.open_browser = open_browser
        self.token = secrets.token_urlsafe(24)
        self.job = Job()
        self.seen = time.monotonic()
        self.server = None
        self.page_cache = (None, None)       # (mtime, html)

    # ---- jobs -------------------------------------------------------------------------------------------------
    def start_job(self, kind, **kw):
        with self.job.lock:
            if self.job.busy:
                return False
            self.job.busy, self.job.kind, self.job.lines, self.job.result = True, kind, [], None
        threading.Thread(target=self._run, args=(kind, kw), daemon=True, name='elevendash-job').start()
        return True

    def _run(self, kind, kw):
        lower_build_thread()
        say = self.job.say
        result = {'ok': True, 'code': 'done', 'changed': False, 'headline': [], 'message': ''}
        try:
            if kind == 'quest':
                result.update(self._import_quest(say))
            elif kind == 'files':
                result.update(self._import_files(say))
            elif kind == 'rebuild':
                self._rebuild(say)
                result['changed'] = True
            elif kind == 'site':
                cli.do_site(self.ws, say=say)
                result['changed'] = True
        except fetch.QuestUnreachable as e:
            result.update(ok=False, code='unreachable', message=str(e))
        except SystemExit as e:                         # the CLI's own "nothing to build" and the like
            result.update(ok=False, code='error', message=str(e))
        except Exception as e:
            result.update(ok=False, code='error', message=f'{type(e).__name__}: {e}')
        if result['ok'] and result['changed']:
            result['headline'] = self.headline()
        if result['message']:
            say(result['message'])
        with self.job.lock:
            self.job.busy = False
            self.job.result = result
            self.job.seq += 1

    def _rebuild(self, say):
        cli.do_build(self.ws, say=say)
        cli.do_site(self.ws, say=say)

    def _after_copy(self, got, say):
        if got:
            self.ws.set(last_import=datetime.datetime.now().isoformat(timespec='seconds'))
        if got or (cli.log_count(self.ws) and not self.built()):
            self._rebuild(say)
            return {'changed': True, 'new': len(got)}
        return {'changed': False, 'new': 0, 'code': 'nothing'}

    def _import_quest(self, say):
        got = cli.do_fetch(self.ws, None, say)
        if got is None:
            return {'ok': False, 'code': 'need_quest', 'message': 'No Quest address yet.'}
        return self._after_copy(got, say)

    def _import_files(self, say):
        inbox = os.path.join(self.ws.root, INCOMING)
        try:
            got = fetch.from_files([inbox], self.ws.logs, say) if os.path.isdir(inbox) else []
        finally:
            shutil.rmtree(inbox, ignore_errors=True)
        return self._after_copy(got, say)

    def built(self):
        return os.path.isfile(self.site_file())

    def site_file(self):
        return os.path.join(self.ws.site, 'index.html')

    def headline(self):
        """The first lines of the session report: which session, and the matches, games and points won."""
        try:
            lines = list(report.session_report(self.ws.build))
        except Exception:
            return []
        out = []
        for line in lines:
            if line.startswith('SESSION') or (out and line.strip().startswith(('Matches won', 'Games won', 'Points won'))):
                out.append(' '.join(line.split()))
            elif out and len(out) >= 4:
                break
        return out

    # ---- state ------------------------------------------------------------------------------------------------
    def status(self):
        c = self.ws.config()
        v = self.job.view()
        v.update({'quest': c.get('quest', ''), 'last_import': c.get('last_import', ''), 'logs': cli.log_count(self.ws),
                  'built': self.built(), 'home': self.ws.root, 'settings': {k: c.get(k, SETTINGS[k][0]) for k in SETTINGS},
                  'shortcut': os.name == 'nt', 'version': __version__})
        return v

    def save_settings(self, body):
        new = {}
        if 'quest' in body:
            q = str(body['quest'] or '').strip()
            new['quest'] = fetch.normalize_host(q) if q else ''
        for k, choices in SETTINGS.items():
            if k in body:
                if body[k] not in choices:
                    raise ValueError(f'{k} must be one of {", ".join(choices)}')
                new[k] = body[k]
        before = self.ws.config()
        self.ws.set(**new)
        job = None
        if self.built() and 'hand' in new and new['hand'] != before.get('hand', 'auto'):
            job = 'rebuild'
        elif self.built() and any(k in new and new[k] != before.get(k, SETTINGS[k][0]) for k in ('theme', 'lang')):
            job = 'site'
        if job:
            self.start_job(job)
        return job

    def read_notes(self):
        try:
            with open(os.path.join(self.ws.root, NOTES), encoding='utf-8') as f:
                v = json.load(f)
            return v if isinstance(v, dict) else {}
        except (FileNotFoundError, ValueError):
            return {}

    def write_notes(self, notes):
        if not isinstance(notes, dict):
            raise ValueError('notes must be an object')
        clean = {}
        for k, v in notes.items():
            if isinstance(k, str) and isinstance(v, dict) and isinstance(v.get('text'), str) and v['text'].strip():
                clean[k[:200]] = {'text': v['text'][:2000], 'at': str(v.get('at', ''))[:40]}
        path = os.path.join(self.ws.root, NOTES)
        with open(path + '.tmp', 'w', encoding='utf-8', newline='\n') as f:
            json.dump(clean, f, ensure_ascii=False, indent=1)
            f.write('\n')
        os.replace(path + '.tmp', path)

    def receive_log(self, name, stream, length):
        if not fetch.LOG_NAME.match(name or ''):
            raise ValueError(f'not a game log name: {name!r} (game logs are named like ALL-11.17.2026.3.31.58.PM.log)')
        if length <= 0 or length > MAX_LOG:
            raise ValueError('empty or too large')
        inbox = os.path.join(self.ws.root, INCOMING)
        os.makedirs(inbox, exist_ok=True)
        dest = os.path.join(inbox, name)
        left = length
        with open(dest + '.part', 'wb') as out:
            while left:
                chunk = stream.read(min(left, 1 << 20))
                if not chunk:
                    break
                out.write(chunk)
                left -= len(chunk)
        if left:
            os.remove(dest + '.part')
            raise ValueError('upload cut short')
        os.replace(dest + '.part', dest)

    # ---- pages ------------------------------------------------------------------------------------------------
    def page(self):
        """The dashboard with the app bar on top, or the welcome page while there is no data yet."""
        if not self.built():
            return welcome_page(self.token)
        path = self.site_file()
        mtime = os.path.getmtime(path)
        if self.page_cache[0] != mtime:
            with open(path, encoding='utf-8') as f:
                self.page_cache = (mtime, f.read())
        return inject(self.page_cache[1], self.token)

    # ---- running ----------------------------------------------------------------------------------------------
    def url(self):
        return f'http://127.0.0.1:{self.port}/'

    def bind(self):
        handler = type('Handler', (Handler,), {'app': self})
        try:
            self.server = Server(('127.0.0.1', self.port), handler)
        except OSError:
            self.server = Server(('127.0.0.1', 0), handler)        # the usual port is taken: any free one
        self.port = self.server.server_address[1]
        return self

    def serve(self):
        if self.server is None:
            self.bind()
        state = os.path.join(self.ws.root, STATE)
        with open(state, 'w', encoding='utf-8') as f:
            json.dump({'port': self.port, 'pid': os.getpid()}, f)
        threading.Thread(target=self._watch_idle, daemon=True).start()
        if self.open_browser:
            threading.Timer(0.3, lambda: webbrowser.open(self.url())).start()
        try:
            self.server.serve_forever(poll_interval=0.5)
        finally:
            self.server.server_close()
            try:
                with open(state, encoding='utf-8') as f:
                    if json.load(f).get('pid') == os.getpid():
                        os.remove(state)
            except (OSError, ValueError):
                pass

    def _watch_idle(self):
        while True:
            time.sleep(15)
            if self.idle_exit and not self.job.busy and time.monotonic() - self.seen > self.idle_exit:
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = False


class Handler(http.server.BaseHTTPRequestHandler):
    app = None
    server_version = 'elevendash'
    sys_version = ''

    def log_message(self, *args):
        pass

    # Only this computer, and only pages this server served: the Host must be ours (no other name pointed at
    # 127.0.0.1), and every /api call must carry the page's key, which no other website can read.
    def _host_ok(self):
        host = (self.headers.get('Host') or '').lower()
        return host in (f'127.0.0.1:{self.app.port}', f'localhost:{self.app.port}')

    def _api_ok(self):
        if not secrets.compare_digest(self.headers.get('X-Elevendash', ''), self.app.token):
            return False
        origin = self.headers.get('Origin')
        return origin in (None, f'http://127.0.0.1:{self.app.port}', f'http://localhost:{self.app.port}')

    def _send(self, code, body, ctype='application/json; charset=utf-8'):
        data = body if isinstance(body, bytes) else (json.dumps(body, ensure_ascii=False) if not isinstance(body, str) else body).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Frame-Options', 'DENY')                      # no other page may frame the app's buttons
        self.send_header('Content-Security-Policy', "frame-ancestors 'none'")
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(data)

    def _body(self, limit):
        n = int(self.headers.get('Content-Length') or 0)
        if n > limit:
            raise ValueError('too large')
        raw = self.rfile.read(n) if n else b''
        return json.loads(raw.decode('utf-8')) if raw else {}

    def _route(self):
        if not self._host_ok():
            return self._send(403, {'error': 'host'})
        path = urllib.parse.urlsplit(self.path).path
        if path == '/api/hello':                 # no key: lets a second start find this one
            return self._send(200, {'app': 'elevendash', 'root': self.app.ws.root})
        if path.startswith('/api/'):
            if not self._api_ok():
                return self._send(403, {'error': 'key'})
            self.app.seen = time.monotonic()
            return self._api(path)
        if self.command in ('GET', 'HEAD') and path in ('/', '/index.html'):
            self.app.seen = time.monotonic()
            return self._send(200, self.app.page(), 'text/html; charset=utf-8')
        if path == '/favicon.ico':
            return self._send(204, b'')
        return self._send(404, {'error': 'not found'})

    def _api(self, path):
        app, m = self.app, self.command
        try:
            if path == '/api/status' and m == 'GET':
                return self._send(200, app.status())
            if path == '/api/import' and m == 'POST':
                kind = self._body(4096).get('source', 'quest')
                if kind not in ('quest', 'files', 'rebuild'):
                    raise ValueError('source must be quest, files or rebuild')
                started = app.start_job(kind)
                return self._send(202 if started else 409, app.status())
            if path == '/api/upload' and m == 'POST':
                name = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get('name', [''])[0]
                app.receive_log(name, self.rfile, int(self.headers.get('Content-Length') or 0))
                return self._send(200, {'ok': True})
            if path == '/api/settings' and m == 'POST':
                job = app.save_settings(self._body(4096))
                return self._send(200, dict(app.status(), started=job))
            if path == '/api/notes' and m == 'GET':
                return self._send(200, app.read_notes())
            if path == '/api/notes' and m == 'PUT':
                app.write_notes(self._body(MAX_NOTES))
                return self._send(200, {'ok': True})
            if path == '/api/shortcut' and m == 'POST':
                return self._send(200, {'made': make_shortcuts(app.ws.root)})
            if path == '/api/folder' and m == 'POST':
                open_folder(app.ws.root)
                return self._send(200, {'ok': True})
            return self._send(404, {'error': 'not found'})
        except (ValueError, OSError, RuntimeError) as e:
            return self._send(400, {'error': str(e)})

    def do_GET(self):
        self._route()

    def do_HEAD(self):
        self._route()

    def do_POST(self):
        self._route()

    def do_PUT(self):
        self._route()


# ---- the bar above the dashboard ------------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))


def _web(name):
    with open(os.path.join(_HERE, 'web', name), encoding='utf-8') as f:
        return f.read()


def app_parts(token):
    """The bar's style, markup and script. The first script runs before the page's own, so the page finds
    window.__elevendashApp (its notes go to the workspace through it)."""
    conf = json.dumps({'token': token}).replace('<', '\\u003c')
    head = (f'<style>{_web("app.css")}</style>'
            f'<script>window.__elevendashApp={{conf:{conf}}};\n{_web("app-head.js")}</script>')
    return head, _web('app.html'), f'<script>{_web("app.js")}</script>'


def inject(html, token):
    head, bar, script = app_parts(token)
    html = html.replace('</head>', head + '</head>', 1)
    html = html.replace('<div id="dash-root">', bar + '<div id="dash-root">', 1)
    return html.replace('</body>', script + '</body>', 1)


def welcome_page(token):
    head, bar, script = app_parts(token)
    look = read_look()
    return ('<!doctype html><html lang="en" data-theme="dark"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{APP_NAME}</title><style>{tokens_css(look)}body{{margin:0;background:var(--color-bg);color:var(--color-fg);'
            'font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,"Microsoft JhengHei","PingFang TC",sans-serif}</style>'
            f'{head}</head><body class="ed-welcome-page">{bar}{_web("welcome.html")}'
            '<script>document.documentElement.lang=(navigator.language||"").toLowerCase().startsWith("zh")?"zh-Hant":"en";</script>'
            f'{script}</body></html>')


# ---- the desktop -------------------------------------------------------------------------------------------------
def launch_command(root):
    """What a shortcut runs: the packaged app itself, or this Python without a console window."""
    if getattr(sys, 'frozen', False):
        return sys.executable, ['--dir', root, 'app']
    exe = sys.executable
    if os.name == 'nt':
        w = os.path.join(os.path.dirname(exe), 'pythonw.exe')
        exe = w if os.path.isfile(w) else exe
    return exe, ['-m', 'elevendash', '--dir', root, 'app']


def make_shortcuts(root, places=('Programs', 'Desktop')):
    """A Start menu and a desktop shortcut named Eleven Dashboard (Windows). Returns the paths made."""
    if os.name != 'nt':
        raise RuntimeError('shortcuts are made on Windows only; elsewhere run "elevendash app"')
    exe, args = launch_command(root)
    env = dict(os.environ, ED_TARGET=exe, ED_ARGS=subprocess.list2cmdline(args), ED_DIR=root, ED_NAME=APP_NAME,
               ED_PLACES=','.join(places))
    script = ("$sh=New-Object -ComObject WScript.Shell;"
              "foreach($d in @($env:ED_PLACES.Split(',') | ForEach-Object {[Environment]::GetFolderPath($_)})){"
              "$p=Join-Path $d ($env:ED_NAME+'.lnk');$s=$sh.CreateShortcut($p);$s.TargetPath=$env:ED_TARGET;"
              "$s.Arguments=$env:ED_ARGS;$s.WorkingDirectory=$env:ED_DIR;"
              "$s.Description='Your Eleven Table Tennis dashboard';$s.Save();$p}")
    r = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', script], env=env, capture_output=True,
                       text=True, timeout=60, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if r.returncode:
        raise RuntimeError('could not make the shortcuts: ' + (r.stderr.strip().splitlines() or ['unknown error'])[-1])
    return [line.strip() for line in r.stdout.splitlines() if line.strip()]


def open_folder(path):
    if os.name == 'nt':
        os.startfile(path)
    elif sys.platform == 'darwin':
        subprocess.Popen(['open', path])
    else:
        subprocess.Popen(['xdg-open', path])


def running_port(ws):
    """The port of an app already serving this workspace, or None."""
    try:
        with open(os.path.join(ws.root, STATE), encoding='utf-8') as f:
            port = int(json.load(f)['port'])
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/hello', timeout=2) as r:
            v = json.load(r)
        return port if v.get('app') == 'elevendash' and os.path.normcase(v.get('root', '')) == os.path.normcase(ws.root) else None
    except Exception:
        return None


def run(explicit_dir=None, port=PORT, open_browser=True, shortcut=False, say=print):
    ws = pick_workspace(explicit_dir)
    if shortcut:
        for p in make_shortcuts(ws.root):
            say(f'Shortcut: {p}')
        return 0
    other = running_port(ws)
    if other:
        if open_browser:
            webbrowser.open(f'http://127.0.0.1:{other}/')
        say(f'{APP_NAME} is already running: http://127.0.0.1:{other}/')
        return 0
    lower_priority()
    app = App(ws, port, open_browser=open_browser).bind()
    say(f'{APP_NAME}: {app.url()} (this computer only), data in {ws.root}')
    say(f'It stops by itself {IDLE_EXIT // 60} minutes after the last dashboard tab is closed, or press Ctrl+C.')
    try:
        app.serve()
    except KeyboardInterrupt:
        pass
    return 0
