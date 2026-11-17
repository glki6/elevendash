"""elevendash app: your dashboard in your own browser, with an Import button.

`elevendash app` starts a small web server on this computer only (127.0.0.1) and opens the dashboard in your default
browser. A bar above the dashboard imports new logs: from the Quest over Wi-Fi (the same two read-only requests as
`elevendash fetch`), or from log files you pick. Then it rebuilds the data and the page reloads with your new session.
Nothing is hosted anywhere and nothing leaves this computer, except those reads from your own Quest.

The server answers only this computer, only pages it served itself (a per-run key in the page; requests from other
websites are refused), and stops on its own a while after the last dashboard tab is closed. Starting it again while it
runs just opens the browser on the running one. Match notes are kept in the workspace (notes.json), not in the browser.

With the phone link on (Settings › Phone), a second server listens on this computer's Tailscale address and asks for
the phone key on every request; see "the phone, over Tailscale" below.
"""
import datetime
import http.server
import ipaddress
import json
import os
import secrets
import shutil
import socket
import socketserver
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser

from . import __version__, cli, fetch, qr, report, workspace
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
        self.phone_server = None
        self.phone_where = {}
        self.phone_port = 0
        self.phone_error = ''
        self.phone_lock = threading.Lock()
        self.phone_trying = False
        self.stopping = False

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
    def status(self, remote=False):
        c = self.ws.config()
        v = self.job.view()
        v.update({'quest': c.get('quest', ''), 'last_import': c.get('last_import', ''), 'logs': cli.log_count(self.ws),
                  'built': self.built(), 'settings': {k: c.get(k, SETTINGS[k][0]) for k in SETTINGS},
                  'version': __version__, 'remote': remote, 'phone': bool(self.phone_server)})
        if not remote:            # where things are on the computer is the computer's business
            v.update({'home': self.ws.root, 'shortcut': os.name == 'nt'})
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
        self.start_phone()
        if self.open_browser:
            threading.Timer(0.3, lambda: webbrowser.open(self.url())).start()
        try:
            self.server.serve_forever(poll_interval=0.5)
        finally:
            self.stopping = True
            self.stop_phone()
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
            # with the phone link on, the app stays up: the phone may ask at any time
            if self.idle_exit and not self.job.busy and not self.phone_server and time.monotonic() - self.seen > self.idle_exit:
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return

    # ---- the phone, over Tailscale ------------------------------------------------------------------------------
    # With the phone link on, a second server listens on this computer's Tailscale address only, so only devices
    # signed in to the same tailnet reach it, over Tailscale's encrypted connection. Each request must also carry
    # the phone key: in the link (?k=, which the QR code holds) or in the cookie the first visit leaves.
    def phone_key(self):
        c = self.ws.config()
        if not c.get('phone_key'):
            self.ws.set(phone_key=secrets.token_urlsafe(16))
            c = self.ws.config()
        return c['phone_key']

    def phone_url(self):
        if not self.phone_server:
            return ''
        host = self.phone_where.get('name') or self.phone_where['ip']
        return f'http://{host}:{self.phone_port}/?k={self.phone_key()}'

    def phone_hosts(self):
        w = self.phone_where or {}
        return {f'{h}:{self.phone_port}'.lower() for h in (w.get('ip'), w.get('name')) if h}

    def start_phone(self):
        """Listen on the Tailscale address when the phone link is on. Tailscale may come up after this app (at login,
        say), so it keeps trying every half minute until it can."""
        with self.phone_lock:
            if self.phone_server or not self.ws.config().get('phone') or self.phone_trying:
                return
            self.phone_trying = True
        threading.Thread(target=self._phone_loop, daemon=True, name='elevendash-phone').start()

    def _phone_loop(self):
        try:
            while self.ws.config().get('phone') and not self.phone_server and not self.stopping:
                where = tailscale()
                if where:
                    try:
                        self._bind_phone(where)
                        return
                    except OSError as e:
                        self.phone_error = f'could not listen on {where["ip"]}: {e}'
                else:
                    self.phone_error = 'Tailscale is not running on this computer'
                for _ in range(30):
                    if self.stopping or not self.ws.config().get('phone'):
                        return
                    time.sleep(1)
        finally:
            self.phone_trying = False

    def _bind_phone(self, where):
        handler = type('PhoneHandler', (Handler,), {'app': self, 'remote': True})
        want = int(self.ws.config().get('phone_port') or PORT)
        try:
            srv = Server((where['ip'], want), handler)
        except OSError:
            srv = Server((where['ip'], 0), handler)
        self.phone_where, self.phone_port, self.phone_error = where, srv.server_address[1], ''
        self.phone_key()
        if self.ws.config().get('phone_port') != self.phone_port:
            self.ws.set(phone_port=self.phone_port)
        self.phone_server = srv
        threading.Thread(target=srv.serve_forever, kwargs={'poll_interval': 0.5}, daemon=True).start()

    def stop_phone(self):
        srv, self.phone_server = self.phone_server, None
        if srv:
            srv.shutdown()
            srv.server_close()

    def set_phone(self, body):
        """Turn the phone link on or off, make a new key (the old link stops working), start with Windows or not."""
        if 'on' in body:
            self.ws.set(phone=bool(body['on']))
            if body['on']:
                self.start_phone()
                for _ in range(40):                 # give it a moment, so the answer can carry the link
                    if self.phone_server or self.phone_error:
                        break
                    time.sleep(0.1)
            else:
                self.stop_phone()
        if body.get('new_key'):
            self.ws.set(phone_key=secrets.token_urlsafe(16))
        if 'startup' in body:
            set_startup(self.ws.root, bool(body['startup']))
        return self.phone_view()

    def phone_view(self):
        url = self.phone_url()
        return {'on': bool(self.ws.config().get('phone')), 'url': url, 'qr': qr.svg(url) if url else '',
                'listening': bool(self.phone_server), 'error': '' if self.phone_server else self.phone_error,
                'startup': startup_exists(), 'startup_possible': os.name == 'nt'}


def tailscale():
    """This computer's Tailscale address and name ({'ip', 'name'}), or None when Tailscale is not up."""
    exe = shutil.which('tailscale')
    if not exe:
        for p in (r'C:\Program Files\Tailscale\tailscale.exe', '/Applications/Tailscale.app/Contents/MacOS/Tailscale'):
            if os.path.isfile(p):
                exe = p
                break
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    if exe:
        try:
            r = subprocess.run([exe, 'status', '--json'], capture_output=True, text=True, timeout=10, creationflags=flags)
            me = json.loads(r.stdout).get('Self') or {}
            ips = [ip for ip in me.get('TailscaleIPs') or [] if is_tailscale_ip(ip)]
            if ips and me.get('Online', True):
                return {'ip': ips[0], 'name': (me.get('DNSName') or '').rstrip('.').lower()}
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    try:       # no command line to ask: an address of this computer in Tailscale's range
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            if is_tailscale_ip(info[4][0]):
                return {'ip': info[4][0], 'name': ''}
    except OSError:
        pass
    return None


def is_tailscale_ip(ip):
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return a.version == 4 and a in ipaddress.ip_network('100.64.0.0/10')


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = False


class Handler(http.server.BaseHTTPRequestHandler):
    app = None
    remote = False              # True on the phone server (the Tailscale address)
    server_version = 'elevendash'
    sys_version = ''
    COOKIE = 'ed_phone'

    def log_message(self, *args):
        pass

    # Only this computer, and only pages this server served: the Host must be ours (no other name pointed at
    # 127.0.0.1), and every /api call must carry the page's key, which no other website can read. On the phone
    # server: the Host must be this computer's Tailscale address or name, and every request must carry the phone key.
    def _hosts(self):
        if self.remote:
            return self.app.phone_hosts()
        return {f'127.0.0.1:{self.app.port}', f'localhost:{self.app.port}'}

    def _host_ok(self):
        return (self.headers.get('Host') or '').lower() in self._hosts()

    def _query_key(self):
        return urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get('k', [''])[0]

    def _cookie_key(self):
        for part in (self.headers.get('Cookie') or '').split(';'):
            name, _, value = part.strip().partition('=')
            if name == self.COOKIE:
                return value
        return ''

    def _phone_ok(self):
        key = self.app.phone_key()
        return any(k and secrets.compare_digest(k, key) for k in (self._query_key(), self._cookie_key()))

    def _api_ok(self):
        if not secrets.compare_digest(self.headers.get('X-Elevendash', ''), self.app.token):
            return False
        origin = self.headers.get('Origin')
        return origin is None or origin.lower() in {'http://' + h for h in self._hosts()}

    def _send(self, code, body, ctype='application/json; charset=utf-8', cookie=None):
        data = body if isinstance(body, bytes) else (json.dumps(body, ensure_ascii=False) if not isinstance(body, str) else body).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        if cookie:
            self.send_header('Set-Cookie', f'{self.COOKIE}={cookie}; Path=/; Max-Age=31536000; HttpOnly; SameSite=Strict')
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
        if self.remote and not self._phone_ok():
            if path.startswith('/api/'):
                return self._send(403, {'error': 'phone key'})
            return self._send(403, OLD_LINK, 'text/html; charset=utf-8')
        if path == '/api/hello' and not self.remote:      # no key: lets a second start find this one
            return self._send(200, {'app': 'elevendash', 'root': self.app.ws.root})
        if path.startswith('/api/'):
            if not self._api_ok():
                return self._send(403, {'error': 'key'})
            self.app.seen = time.monotonic()
            return self._api(path)
        if self.command in ('GET', 'HEAD') and path in ('/', '/index.html'):
            self.app.seen = time.monotonic()
            cookie = self.app.phone_key() if self.remote and self._query_key() else None
            return self._send(200, self.app.page(), 'text/html; charset=utf-8', cookie=cookie)
        if path == '/favicon.ico':
            return self._send(204, b'')
        return self._send(404, {'error': 'not found'})

    def _api(self, path):
        app, m = self.app, self.command
        try:
            if path == '/api/status' and m == 'GET':
                return self._send(200, app.status(self.remote))
            if path == '/api/import' and m == 'POST':
                kind = self._body(4096).get('source', 'quest')
                if kind not in ('quest', 'files', 'rebuild'):
                    raise ValueError('source must be quest, files or rebuild')
                started = app.start_job(kind)
                return self._send(202 if started else 409, app.status(self.remote))
            if path == '/api/upload' and m == 'POST':
                name = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get('name', [''])[0]
                app.receive_log(name, self.rfile, int(self.headers.get('Content-Length') or 0))
                return self._send(200, {'ok': True})
            if path == '/api/settings' and m == 'POST':
                job = app.save_settings(self._body(4096))
                return self._send(200, dict(app.status(self.remote), started=job))
            if path == '/api/notes' and m == 'GET':
                return self._send(200, app.read_notes())
            if path == '/api/notes' and m == 'PUT':
                app.write_notes(self._body(MAX_NOTES))
                return self._send(200, {'ok': True})
            if path in ('/api/shortcut', '/api/folder', '/api/phone') and self.remote:
                return self._send(403, {'error': 'only on the computer itself'})
            if path == '/api/shortcut' and m == 'POST':
                return self._send(200, {'made': make_shortcuts(app.ws.root)})
            if path == '/api/folder' and m == 'POST':
                open_folder(app.ws.root)
                return self._send(200, {'ok': True})
            if path == '/api/phone' and m == 'GET':
                return self._send(200, app.phone_view())
            if path == '/api/phone' and m == 'POST':
                return self._send(200, app.set_phone(self._body(4096)))
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


OLD_LINK = ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,'
            'initial-scale=1"><title>Eleven Dashboard</title></head><body style="font:16px/1.5 system-ui,sans-serif;'
            'background:#0b1018;color:#eef1f5;padding:24px;max-width:36em">'
            '<h1 style="font-size:22px">This link needs a new key</h1><p>Open Eleven Dashboard on your computer, then '
            '<b>Settings › Phone</b>, and scan the code there again.</p>'
            '<p lang="zh-Hant">請在電腦上開啟 Eleven 儀表板，前往<b>設定 › 手機</b>，再掃描一次那裡的條碼。</p></body></html>')


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
def launch_command(root, extra=()):
    """What a shortcut runs: the packaged app itself, or this Python without a console window."""
    if getattr(sys, 'frozen', False):
        return sys.executable, ['--dir', root, 'app', *extra]
    exe = sys.executable
    if os.name == 'nt':
        w = os.path.join(os.path.dirname(exe), 'pythonw.exe')
        exe = w if os.path.isfile(w) else exe
    return exe, ['-m', 'elevendash', '--dir', root, 'app', *extra]


def _startup_link():
    if os.name != 'nt':
        return None
    base = os.path.join(os.environ.get('APPDATA', ''), 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup')
    return os.path.join(base, APP_NAME + '.lnk')


def startup_exists():
    p = _startup_link()
    return bool(p and os.path.isfile(p))


def set_startup(root, on):
    """Start the app (without a browser tab) when you sign in to Windows, so the phone link works all day."""
    p = _startup_link()
    if not p:
        raise RuntimeError('starting with the computer is set up on Windows only')
    if on:
        make_shortcuts(root, places=('Startup',), extra=('--no-browser',))
    elif os.path.isfile(p):
        os.remove(p)


def make_shortcuts(root, places=('Programs', 'Desktop'), extra=()):
    """A Start menu and a desktop shortcut named Eleven Dashboard (Windows). Returns the paths made."""
    if os.name != 'nt':
        raise RuntimeError('shortcuts are made on Windows only; elsewhere run "elevendash app"')
    exe, args = launch_command(root, extra)
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
