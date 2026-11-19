"""The app (elevendash app): its guard against other websites, importing logs from files, notes and settings.
Runs a real server on a free port with generated logs; no browser and no Quest needed."""
import http.client
import json
import os
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

from elevendash import app, sample, workspace  # noqa: E402


class AppServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.src = os.path.join(cls.tmp.name, 'from-headset')
        os.makedirs(cls.src)
        cls.names = sample.write_logs(cls.src)
        cls.ws = workspace.init(os.path.join(cls.tmp.name, 'ws'))
        cls.app = app.App(cls.ws, port=0, idle_exit=0, open_browser=False).bind()
        cls.port = cls.app.port
        cls.thread = threading.Thread(target=cls.app.serve, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.app.server.shutdown()
        cls.thread.join(10)
        cls.tmp.cleanup()

    def call(self, method, path, body=None, key=True, host=None, headers=None, raw=None):
        c = http.client.HTTPConnection('127.0.0.1', self.port, timeout=60)
        h = {'Host': host or f'127.0.0.1:{self.port}'}
        if key:
            h['X-Elevendash'] = self.app.token
        if body is not None:
            raw = json.dumps(body).encode('utf-8')
            h['Content-Type'] = 'application/json'
        h.update(headers or {})
        c.request(method, path, body=raw, headers=h)
        r = c.getresponse()
        data = r.read()
        c.close()
        try:
            return r.status, json.loads(data.decode('utf-8'))
        except ValueError:
            return r.status, data.decode('utf-8')

    def wait(self):
        for _ in range(600):
            code, s = self.call('GET', '/api/status')
            if not s['busy']:
                return s
            time.sleep(0.5)
        self.fail('the job did not finish')

    def upload(self, name):
        with open(os.path.join(self.src, name), 'rb') as f:
            return self.call('POST', '/api/upload?name=' + name, raw=f.read())

    def test_1_guard(self):
        self.assertEqual(self.call('GET', '/api/hello', key=False)[0], 200)
        self.assertEqual(self.call('GET', '/api/status', key=False)[0], 403)
        self.assertEqual(self.call('GET', '/api/status', headers={'X-Elevendash': 'wrong'}, key=False)[0], 403)
        self.assertEqual(self.call('GET', '/', host='attacker.example:%d' % self.port)[0], 403)
        self.assertEqual(self.call('GET', '/api/status', headers={'Origin': 'https://attacker.example'})[0], 403)
        code, s = self.call('GET', '/api/status')
        self.assertEqual(code, 200)
        self.assertFalse(s['built'])
        self.assertEqual(s['logs'], 0)

    def test_2_welcome(self):
        code, html = self.call('GET', '/', key=False)
        self.assertEqual(code, 200)
        self.assertIn('ed-welcome', html)
        self.assertIn(self.app.token, html)        # the page carries its key; other sites cannot read it

    def test_3_no_quest(self):
        code, s = self.call('POST', '/api/import', {'source': 'quest'})
        self.assertEqual(code, 202)
        s = self.wait()
        self.assertEqual(s['result']['code'], 'need_quest')

    def test_4_bad_names(self):
        code, s = self.call('POST', '/api/upload?name=..%5Cevil.log', raw=b'x')
        self.assertEqual(code, 400)
        code, s = self.call('POST', '/api/upload?name=notes.txt', raw=b'x')
        self.assertEqual(code, 400)
        self.assertEqual(self.call('POST', '/api/import', {'source': 'elsewhere'})[0], 400)

    def test_5_import_files(self):
        for name in self.names:
            self.assertEqual(self.upload(name)[0], 200)
        self.assertEqual(self.call('POST', '/api/import', {'source': 'files'})[0], 202)
        s = self.wait()
        self.assertTrue(s['result']['ok'], s['lines'])
        self.assertTrue(s['result']['changed'])
        self.assertEqual(s['result']['new'], len(self.names))
        self.assertTrue(s['result']['headline'][0].startswith('SESSION'))
        self.assertTrue(s['built'])
        self.assertEqual(s['logs'], len(self.names))
        self.assertFalse(os.path.exists(os.path.join(self.ws.root, app.INCOMING)))
        code, html = self.call('GET', '/', key=False)
        self.assertIn('id="ed-app"', html)
        self.assertIn('id="dash-root"', html)
        self.assertLess(html.index('__elevendashApp'), html.index('window.__elevendash.start()'))
        # the same files again: nothing new, nothing rebuilt
        self.upload(self.names[0])
        self.call('POST', '/api/import', {'source': 'files'})
        s = self.wait()
        self.assertEqual(s['result']['code'], 'nothing')

    def test_6_notes(self):
        self.assertEqual(self.call('GET', '/api/notes')[1], {})
        notes = {'2026-01-29 15:00:00': {'text': 'Long backhand returns', 'at': '2026-01-29T16:00:00'},
                 'empty': {'text': '   '}, 'junk': 5,
                 'journal|2026-01-29|equipment|k1': {'text': 'New rubber', 'at': '2026-01-29T16:05:00'}}      # a journal entry
        self.assertEqual(self.call('PUT', '/api/notes', notes)[0], 200)
        got = self.call('GET', '/api/notes')[1]
        self.assertEqual(list(got), ['2026-01-29 15:00:00', 'journal|2026-01-29|equipment|k1'])
        self.assertEqual(got['journal|2026-01-29|equipment|k1']['text'], 'New rubber')
        self.assertEqual(got['2026-01-29 15:00:00']['text'], 'Long backhand returns')
        self.assertTrue(os.path.isfile(os.path.join(self.ws.root, app.NOTES)))

    def test_7_settings(self):
        self.assertEqual(self.call('POST', '/api/settings', {'hand': 'both'})[0], 400)
        self.assertEqual(self.call('POST', '/api/settings', {'quest': 'not a host!'})[0], 400)
        code, s = self.call('POST', '/api/settings', {'quest': 'http://192.168.1.20/'})
        self.assertEqual(code, 200)
        self.assertEqual(s['quest'], '192.168.1.20:8090')
        self.assertIsNone(s['started'])

    def test_8_second_start_finds_the_first(self):
        self.assertEqual(app.running_port(self.ws), self.port)

    def test_9a_check_the_headset(self):
        """The welcome screen's check stops at the first step that fails, and passes against a File Sharing stand-in."""
        import http.server
        steps = lambda r: [(x['step'], x['ok']) for x in r['steps']]
        code, r = self.call('POST', '/api/check', {'quest': 'not an address!'})
        self.assertEqual((code, r['ok'], steps(r)), (200, False, [('address', False)]))
        with __import__('socket').socket() as free:        # a port nothing listens on
            free.bind(('127.0.0.1', 0))
            closed = free.getsockname()[1]
        r = self.call('POST', '/api/check', {'quest': f'127.0.0.1:{closed}'})[1]
        self.assertEqual(steps(r), [('address', True), ('reach', False)])
        # this app answers, but it is not File Sharing
        r = self.call('POST', '/api/check', {'quest': f'127.0.0.1:{self.port}'})[1]
        self.assertEqual(steps(r)[-1], ('sharing', False))
        seen = []

        class Sharing(http.server.BaseHTTPRequestHandler):
            files = []

            def do_GET(self):
                seen.append(self.path)
                body = json.dumps({'output': self.files}).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        srv = http.server.HTTPServer(('127.0.0.1', 0), Sharing)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            host = f'127.0.0.1:{srv.server_address[1]}'
            r = self.call('POST', '/api/check', {'quest': 'http://' + host + '/'})[1]
            self.assertEqual((r['ok'], r['host'], steps(r)[-1]), (False, host, ('logs', False)))
            Sharing.files = [{'name': self.names[0], 'type': 'file', 'size': 5}, {'name': 'notes.txt', 'type': 'file', 'size': 5},
                             {'name': 'ALL-old', 'type': 'dir'}]
            r = self.call('POST', '/api/check', {'quest': host})[1]
            self.assertEqual((r['ok'], r['logs'], len(r['steps'])), (True, 1, 4))
            self.assertEqual(set(seen), {'/getListing?path=logs'})      # the list of logs is all it asks the headset for
        finally:
            srv.shutdown()
            srv.server_close()

    def test_9b_import_report(self):
        """A log that reads oddly is listed after the build, in both languages, and the list outlives a restart."""
        s = self.call('GET', '/api/status')[1]
        self.assertEqual(s['report']['problems'], {})
        path = os.path.join(self.ws.logs, self.names[0])
        with open(path, encoding='utf-8') as f:
            text = f.read()
        with open(path, 'w', encoding='utf-8') as f:
            f.write(text.replace('postCollisionState:', 'stateAfter:'))
        self.assertEqual(self.call('POST', '/api/import', {'source': 'rebuild'})[0], 202)
        s = self.wait()
        self.assertTrue(s['result']['ok'], s['lines'])
        found = s['report']['problems']
        self.assertEqual(list(found), [self.names[0]])
        self.assertIn('after a hit is missing', found[self.names[0]][0]['en'])
        self.assertIn('擊球後', found[self.names[0]][0]['zh'])
        self.assertEqual(app.App(self.ws, port=0, open_browser=False).report, s['report'])

    def test_9c_backup_and_export(self):
        code, r = self.call('POST', '/api/backup')
        self.assertEqual((code, r['logs']), (200, len(self.names)))
        self.assertEqual(os.path.dirname(r['file']), os.path.join(self.ws.root, 'backups'))
        self.assertEqual(os.path.getsize(r['file']), r['bytes'])
        self.assertEqual(self.call('POST', '/api/export', {'format': 'xml'})[0], 400)
        code, r = self.call('POST', '/api/export', {'format': 'csv'})
        self.assertEqual((code, r['dir']), (200, os.path.join(self.ws.root, 'export')))
        self.assertEqual(sorted(r['files']), ['columns.txt', 'matches.csv', 'points.csv', 'shots.csv'])
        self.assertTrue(all(os.path.isfile(os.path.join(r['dir'], n)) for n in r['files']))
        # a backup goes into an empty workspace only
        with open(self.call('POST', '/api/backup')[1]['file'], 'rb') as f:
            self.assertEqual(self.call('POST', '/api/restore', raw=f.read())[0], 400)


class Restore(unittest.TestCase):
    """A new computer: the welcome screen takes a backup, and the dashboard is there."""

    def test_restore(self):
        from elevendash import backup
        with tempfile.TemporaryDirectory() as tmp:
            old = workspace.init(os.path.join(tmp, 'old'), '192.168.1.20:8090')
            names = sample.write_logs(old.logs)
            old.set(phone=True, phone_key='not for another computer', hand='left')
            with open(os.path.join(old.root, app.NOTES), 'w', encoding='utf-8') as f:
                json.dump({'2026-01-29 15:00:00': {'text': 'Long backhand returns', 'at': ''}}, f)
            path, n = backup.make(old)
            new = workspace.init(os.path.join(tmp, 'new'))
            a = app.App(new, port=0, idle_exit=0, open_browser=False).bind()
            t = threading.Thread(target=a.serve, daemon=True)
            t.start()
            try:
                def call(method, url, raw=None):
                    c = http.client.HTTPConnection('127.0.0.1', a.port, timeout=120)
                    c.request(method, url, body=raw, headers={'Host': f'127.0.0.1:{a.port}', 'X-Elevendash': a.token})
                    r = c.getresponse()
                    out = r.status, json.loads(r.read().decode('utf-8'))
                    c.close()
                    return out
                self.assertEqual(call('POST', '/api/restore', b'not a zip')[0], 202)        # taken, then refused by the job
                for _ in range(100):
                    s = call('GET', '/api/status')[1]
                    if not s['busy']:
                        break
                    time.sleep(0.2)
                self.assertFalse(s['result']['ok'])
                self.assertIn('not an elevendash backup', s['result']['message'])
                self.assertFalse(os.path.exists(os.path.join(new.root, app.RESTORE)))
                with open(path, 'rb') as f:
                    self.assertEqual(call('POST', '/api/restore', f.read())[0], 202)
                for _ in range(600):
                    s = call('GET', '/api/status')[1]
                    if not s['busy']:
                        break
                    time.sleep(0.5)
                self.assertTrue(s['result']['ok'], s['lines'])
                self.assertEqual((s['result']['new'], s['logs'], s['built'], s['quest']), (len(names), len(names), True, '192.168.1.20:8090'))
                c = new.config()
                self.assertEqual(c.get('hand'), 'left')
                self.assertNotIn('phone_key', c)
                self.assertNotIn('phone', c)
                self.assertIn('2026-01-29 15:00:00', a.read_notes())
            finally:
                a.server.shutdown()
                t.join(10)


class Phone(unittest.TestCase):
    """The phone server, bound here to 127.0.0.1 in place of a Tailscale address: it needs the phone key."""
    NAME = 'pc.example.ts.net'

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.ws = workspace.init(os.path.join(cls.tmp.name, 'ws'))
        cls.app = app.App(cls.ws, port=0, idle_exit=0, open_browser=False).bind()
        cls.thread = threading.Thread(target=cls.app.serve, daemon=True)
        cls.thread.start()
        cls.app._bind_phone({'ip': '127.0.0.1', 'name': cls.NAME})
        cls.pport = cls.app.phone_port

    @classmethod
    def tearDownClass(cls):
        cls.app.server.shutdown()
        cls.thread.join(10)
        cls.tmp.cleanup()

    def call(self, method, path, port=None, host=None, token=True, cookie=None):
        port = port or self.pport
        c = http.client.HTTPConnection('127.0.0.1', port, timeout=30)
        h = {'Host': host or (f'{self.NAME}:{port}' if port == self.pport else f'127.0.0.1:{port}')}
        if token:
            h['X-Elevendash'] = self.app.token
        if cookie:
            h['Cookie'] = f'other=1; ed_phone={cookie}'
        body = None
        if isinstance(path, tuple):
            path, data = path
            body = json.dumps(data).encode('utf-8')
        c.request(method, path, body=body, headers=h)
        r = c.getresponse()
        data = r.read().decode('utf-8')
        c.close()
        return r.status, r.getheader('Set-Cookie') or '', data

    def test_1_key_needed(self):
        code, _, html = self.call('GET', '/')
        self.assertEqual(code, 403)
        self.assertIn('new key', html)
        self.assertNotIn(self.app.token, html)
        self.assertEqual(self.call('GET', '/api/status')[0], 403)
        self.assertEqual(self.call('GET', '/api/status', cookie='wrong')[0], 403)
        self.assertEqual(self.call('GET', '/?k=' + self.app.phone_key(), host='evil.example:%d' % self.pport)[0], 403)

    def test_2_link_sets_cookie(self):
        key = self.app.phone_key()
        code, cookie, html = self.call('GET', '/?k=' + key)
        self.assertEqual(code, 200)
        self.assertIn('ed_phone=' + key, cookie)
        self.assertIn('HttpOnly', cookie)
        self.assertIn('SameSite=Strict', cookie)
        code, _, body = self.call('GET', '/api/status', cookie=key)
        self.assertEqual(code, 200)
        s = json.loads(body)
        self.assertTrue(s['remote'])
        self.assertNotIn('home', s)                         # where the data lives stays on the computer
        for path in ('/api/phone', '/api/folder', '/api/shortcut', '/api/quit', '/api/backup', '/api/restore', '/api/export', '/api/share'):
            self.assertEqual(self.call('POST', path, cookie=key)[0], 403, path)
        self.assertEqual(self.call('GET', '/api/phone', cookie=key)[0], 403)

    def test_3_computer_side(self):
        code, _, body = self.call('GET', '/api/phone', port=self.app.port)
        self.assertEqual(code, 200)
        v = json.loads(body)
        self.assertTrue(v['listening'])
        self.assertTrue(v['url'].startswith(f'http://127.0.0.1:{self.pport}/?k='))     # the address: browsers force https on ts.net
        self.assertTrue(v['qr'].startswith('<svg'))
        s = json.loads(self.call('GET', '/api/status', port=self.app.port)[2])
        self.assertFalse(s['remote'])
        self.assertIn('home', s)

    def test_4_new_key_ends_old_link(self):
        old = self.app.phone_key()
        code, _, body = self.call('POST', ('/api/phone', {'new_key': True}), port=self.app.port)
        self.assertEqual(code, 200)
        self.assertNotIn(old, json.loads(body)['url'])
        self.assertEqual(self.call('GET', '/api/status', cookie=old)[0], 403)
        self.assertEqual(self.call('GET', '/api/status', cookie=self.app.phone_key())[0], 200)

    def test_5_quit(self):
        self.assertEqual(self.call('POST', '/api/quit', port=self.app.port)[0], 200)
        self.thread.join(10)
        self.assertFalse(self.thread.is_alive())
        self.assertIsNone(self.app.phone_server)            # the phone server stops with it
        self.assertFalse(os.path.exists(os.path.join(self.ws.root, app.STATE)))


class Bits(unittest.TestCase):
    def test_command(self):
        exe, args = app.launch_command('C:/somewhere')
        self.assertTrue(os.path.isabs(exe))
        self.assertEqual(args[-3:], ['--dir', 'C:/somewhere', 'app'])
        self.assertEqual(app.launch_command('C:/somewhere', ('--no-browser',))[1][-4:], ['--dir', 'C:/somewhere', 'app', '--no-browser'])

    def test_tailscale_range(self):
        self.assertTrue(app.is_tailscale_ip('100.98.1.2'))
        self.assertTrue(app.is_tailscale_ip('100.64.0.1'))
        self.assertFalse(app.is_tailscale_ip('100.128.0.1'))
        self.assertFalse(app.is_tailscale_ip('192.168.1.20'))
        self.assertFalse(app.is_tailscale_ip('fd7a:115c:a1e0::1'))
        self.assertFalse(app.is_tailscale_ip('nonsense'))

    def test_qr(self):
        # checked against the qrcode library (byte mode, level M, the same mask): 288 codes, none differing
        import hashlib
        from elevendash import qr
        m = qr.matrix('http://pc.example.ts.net:8737/?k=abcdefghijklmnopqrstuv', mask=3)
        self.assertEqual(len(m), 33)
        bits = ''.join('1' if c else '0' for row in m for c in row)
        self.assertEqual(hashlib.sha256(bits.encode()).hexdigest(), 'f2ffe8113b7bcc5ae889916474d14fd4bf0167d25386fccd70c83129a8b95e2d')
        self.assertTrue(qr.svg('x').startswith('<svg'))
        with self.assertRaises(ValueError):
            qr.matrix('x' * 300)


if __name__ == '__main__':
    unittest.main()
