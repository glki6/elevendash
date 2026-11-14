"""Open a built dashboard in a real browser and check that it works (tools/pagetest/test.js has the checks).

usage: python tools/pagetest/run.py SITE_HTML [--browser chrome|firefox|all] [--timeout SECONDS]

  elevendash demo demo-workspace
  python tools/pagetest/run.py demo-workspace/site/index.html

It serves a copy of the file, with the test added, on 127.0.0.1, and opens it in headless Chrome (or Chromium, Edge)
and, with --browser all, Firefox. Each browser runs with a new, empty profile in a temporary folder that is removed
afterwards: your own browser, its profile and its windows are never touched. Set CHROME or FIREFOX to the program to
use if it is not found. Exits 1 if a check fails or a browser gives no result.
"""
import argparse
import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
WIN = os.name == 'nt'


def find(env, names, win_paths):
    if os.environ.get(env):
        return os.environ[env]
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    if WIN:
        for base in (os.environ.get('ProgramFiles'), os.environ.get('ProgramFiles(x86)'), os.environ.get('LocalAppData')):
            for rel in win_paths:
                p = os.path.join(base or '', rel)
                if os.path.exists(p):
                    return p
    elif sys.platform == 'darwin':
        for p in win_paths:
            if p.startswith('/') and os.path.exists(p):
                return p
    return None


def chrome():
    return find('CHROME', ('google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser', 'chrome', 'msedge'),
                (r'Google\Chrome\Application\chrome.exe', r'Microsoft\Edge\Application\msedge.exe',
                 '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'))


def firefox():
    return find('FIREFOX', ('firefox',), (r'Mozilla Firefox\firefox.exe', '/Applications/Firefox.app/Contents/MacOS/firefox'))


def serve(folder, results):
    class H(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=folder, **k)

        def do_POST(self):
            body = self.rfile.read(int(self.headers.get('Content-Length') or 0))
            try:
                results.append(json.loads(body.decode('utf-8')))
            except ValueError:
                pass
            self.send_response(204)
            self.end_headers()

        def end_headers(self):
            self.send_header('Cache-Control', 'no-store')
            super().end_headers()

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def stop(proc, profile):
    """End the test browser: the process we started and everything it started. On Windows a browser may hand over to
    another process, so anything whose command line names the throwaway profile goes too (nothing else can match it)."""
    if WIN:
        subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'], capture_output=True)
        ps = ("Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*" + profile.replace("'", "''") +
              "*' -and $_.Name -ne 'powershell.exe' } | ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop } catch {} }")
        subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', ps], capture_output=True)
    else:
        import signal
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        pass


def run_browser(name, exe, url, results, timeout):
    profile = tempfile.mkdtemp(prefix='elevendash-pagetest-')
    env = dict(os.environ)
    if name == 'chrome':
        args = [exe, '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check', '--disable-extensions',
                '--user-data-dir=' + profile, '--window-size=1200,900']
        if not WIN and (os.environ.get('CI') or (hasattr(os, 'geteuid') and os.geteuid() == 0)):
            args.append('--no-sandbox')          # a container has no user namespaces for Chrome's own sandbox
        args.append(url)
    else:
        with open(os.path.join(profile, 'user.js'), 'w', encoding='ascii') as f:
            f.write('user_pref("toolkit.startup.max_resumed_crashes", -1);\nuser_pref("browser.shell.checkDefaultBrowser", false);\n'
                    'user_pref("datareporting.policy.dataSubmissionEnabled", false);\nuser_pref("app.update.enabled", false);\n')
        env['MOZ_HEADLESS_WIDTH'], env['MOZ_HEADLESS_HEIGHT'] = '1200', '900'
        args = [exe, '--headless', '--no-remote', '--profile', profile, url]
    kw = {'creationflags': subprocess.IDLE_PRIORITY_CLASS} if WIN else {'start_new_session': True}
    had = len(results)
    proc = subprocess.Popen(args, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kw)
    try:
        end = time.time() + timeout
        while time.time() < end and len(results) == had:
            time.sleep(0.25)
    finally:
        stop(proc, profile)
        time.sleep(0.5)
        shutil.rmtree(profile, ignore_errors=True)
    return results[had] if len(results) > had else None


def main():
    ap = argparse.ArgumentParser(description='Check a built dashboard in a headless browser.')
    ap.add_argument('site', help='the dashboard file, e.g. site/index.html')
    ap.add_argument('--browser', choices=('chrome', 'firefox', 'all'), default='chrome')
    ap.add_argument('--timeout', type=int, default=120)
    a = ap.parse_args()
    with open(a.site, encoding='utf-8') as f:
        html = f.read()
    with open(os.path.join(HERE, 'test.js'), encoding='utf-8') as f:
        test = f.read()
    i = html.rfind('</body>')
    if i < 0:
        sys.exit(f'{a.site} does not look like a dashboard file')
    folder = tempfile.mkdtemp(prefix='elevendash-pagetest-site-')
    failed = 0
    try:
        with open(os.path.join(folder, 'index.html'), 'w', encoding='utf-8') as f:
            f.write(html[:i] + '<script>\n' + test + '\n</script>' + html[i:])
        results = []
        srv = serve(folder, results)
        url = f'http://127.0.0.1:{srv.server_address[1]}/index.html'
        todo = [('chrome', chrome())] if a.browser != 'firefox' else []
        if a.browser != 'chrome':
            todo.append(('firefox', firefox()))
        for name, exe in todo:
            if not exe:
                print(f'{name}: not found (set {name.upper()} to the program)')
                failed += 1
                continue
            r = run_browser(name, exe, url, results, a.timeout)
            if r is None:
                print(f'{name}: no result within {a.timeout} s')
                failed += 1
                continue
            bad = [c for c in r['checks'] if not c['ok']]
            print(f"{name}: {len(r['checks']) - len(bad)} of {len(r['checks'])} checks passed")
            for c in r['checks']:
                print(f"  {'ok  ' if c['ok'] else 'FAIL'} {c['name']}" + (f"  [{c['detail']}]" if c['detail'] and not c['ok'] or c['detail'].startswith('skipped') else ''))
            failed += len(bad)
        srv.shutdown()
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
