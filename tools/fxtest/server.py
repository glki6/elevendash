"""Serve the harness folder and collect test results posted by the page.  server.py DIR PORT OUT"""
import http.server
import sys

root, port, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]


class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=root, **k)

    def do_POST(self):
        n = int(self.headers.get('Content-Length') or 0)
        body = self.rfile.read(n)
        with open(out, 'ab') as f:
            f.write(body + b'\n')
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def log_message(self, *a):
        pass


http.server.ThreadingHTTPServer(('127.0.0.1', port), H).serve_forever()
