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
                 'empty': {'text': '   '}, 'junk': 5}
        self.assertEqual(self.call('PUT', '/api/notes', notes)[0], 200)
        got = self.call('GET', '/api/notes')[1]
        self.assertEqual(list(got), ['2026-01-29 15:00:00'])
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
        for path in ('/api/phone', '/api/folder', '/api/shortcut', '/api/quit'):
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
