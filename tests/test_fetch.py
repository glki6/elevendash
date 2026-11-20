import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))
from elevendash import fetch  # noqa: E402


class Hosts(unittest.TestCase):
    def test_forms(self):
        for given in ('192.168.1.20', '192.168.1.20:8090', 'http://192.168.1.20:8090/', ' 192.168.1.20 '):
            self.assertEqual(fetch.normalize_host(given), '192.168.1.20:8090')
        self.assertEqual(fetch.normalize_host('quest.local:9000'), 'quest.local:9000')

    def test_rejects_paths_and_junk(self):
        for bad in ('192.168.1.20/logs', 'a b', '', 'http://x:80/../y'):
            with self.assertRaises(ValueError):
                fetch.normalize_host(bad)


class Names(unittest.TestCase):
    def test_log_names(self):
        self.assertTrue(fetch.LOG_NAME.match('ALL-11.13.2026.3.25.33.PM.log'))
        self.assertTrue(fetch.LOG_NAME.match('ALL-01.05.2026.12.00.00.AM.log'))
        for bad in ('ALL-11.13.2026.3.25.33.PM.log.part', '../ALL-11.13.2026.3.25.33.PM.log', 'notes.txt', 'ALL-x.log'):
            self.assertFalse(fetch.LOG_NAME.match(bad), bad)

    def test_import_copies_only_logs(self):
        with tempfile.TemporaryDirectory() as src, tempfile.TemporaryDirectory() as dst:
            for name in ('ALL-01.05.2026.6.30.00.PM.log', 'other.txt'):
                with open(os.path.join(src, name), 'w') as f:
                    f.write('x\n')
            got = fetch.from_files([src], dst, say=lambda *a: None)
            self.assertEqual(got, ['ALL-01.05.2026.6.30.00.PM.log'])
            self.assertEqual(os.listdir(dst), ['ALL-01.05.2026.6.30.00.PM.log'])
            self.assertEqual(fetch.from_files([src], dst, say=lambda *a: None), [])     # nothing new the second time



class FromQuest(unittest.TestCase):
    """A stand-in for File Sharing that misbehaves: it points elsewhere, and sends more than any log."""

    def test_no_redirects_and_a_size_limit(self):
        import http.server
        import json
        import threading
        good, big, moved = 'ALL-01.05.2026.6.30.00.PM.log', 'ALL-01.06.2026.6.30.00.PM.log', 'ALL-01.07.2026.6.30.00.PM.log'
        seen = []

        class Sharing(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                seen.append(self.path)
                if self.path.startswith('/getListing'):
                    body = json.dumps({'output': [{'name': n, 'type': 'file', 'size': 3} for n in (good, big, moved)]})
                    return self.reply(body.encode())
                if moved in self.path:
                    self.send_response(302)
                    self.send_header('Location', 'http://127.0.0.1:9/elsewhere')
                    self.send_header('Content-Length', '0')
                    return self.end_headers()
                if big in self.path:
                    return self.reply(b'x' * (fetch.MAX_LOG + 10))
                return self.reply(b'ok\n')

            def reply(self, body):
                self.send_response(200)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                try:
                    self.wfile.write(body)
                except OSError:
                    pass

            def log_message(self, *a):
                pass

        srv = http.server.HTTPServer(('127.0.0.1', 0), Sharing)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        old = fetch.MAX_LOG
        fetch.MAX_LOG = 1 << 16          # a small limit, so the test sends little
        try:
            with tempfile.TemporaryDirectory() as dst:
                said = []
                got = fetch.from_quest(f'127.0.0.1:{srv.server_address[1]}', dst, say=said.append)
                self.assertEqual(got, [good])               # the others are skipped, and the import goes on
                self.assertEqual(sorted(os.listdir(dst)), [good])
                self.assertEqual(len(said), 3)              # one line for each: the copied log and the two skipped
                self.assertFalse(os.path.exists(os.path.join(dst, big)))
                self.assertFalse([n for n in os.listdir(dst) if n.endswith('.part')])
        finally:
            fetch.MAX_LOG = old
            srv.shutdown()
            srv.server_close()


if __name__ == '__main__':
    unittest.main()
