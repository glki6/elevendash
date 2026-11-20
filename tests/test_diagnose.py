"""The report for a bug report: what it says, and that nothing private gets into it."""
import contextlib
import io
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))
from elevendash import cli, diagnose, sample, workspace  # noqa: E402


class Diagnose(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = os.path.join(cls.tmp.name, 'private-folder-name')
        with contextlib.redirect_stdout(io.StringIO()):
            cli.main(['demo', root])
        cls.ws = workspace.find(root)
        cls.ws.set(quest='192.168.77.66:8090', phone_key='a-secret-phone-key-123', hand='left', theme='dark')
        with open(os.path.join(cls.ws.logs, 'notes.txt'), 'w') as f:
            f.write('x')
        cls.text = diagnose.make(cls.ws)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_says_what_is_there(self):
        logs = len(sample.SESSIONS) + len(sample.ONLINE)
        self.assertIn(f'Game logs: {logs}', self.text)
        self.assertIn('1 other file(s) in logs/', self.text)
        self.assertIn('No problems found in reading the logs.', self.text)
        self.assertIn('hand: left', self.text)
        self.assertIn('quest: set', self.text)
        self.assertIn('phone_key: set', self.text)
        self.assertIn('Match data:', self.text)

    def test_nothing_private(self):
        names = os.listdir(self.ws.logs)
        for secret in ['private-folder-name', self.tmp.name, '192.168.77', 'a-secret-phone-key', sample.ME, str(sample.MY_ID),
                       'rival.', '2026', *names, *(n[4:14] for n in names)]:
            self.assertNotIn(secret, self.text, secret)

    def test_a_log_that_breaks_the_reader(self):
        path = os.path.join(self.ws.logs, sorted(n for n in os.listdir(self.ws.logs) if n.startswith('ALL-'))[0])
        with open(path, encoding='utf-8') as f:
            keep = f.read()
        try:
            from elevendash import diagnose as d
            real = d.extract_log
            d.extract_log = lambda p: (_ for _ in ()).throw(ValueError('a quoted line with sample.player in it'))
            text = d.make(self.ws)
        finally:
            d.extract_log = real
            with open(path, 'w', encoding='utf-8', newline='\n') as f:
                f.write(keep)
        self.assertIn('could not be read: ValueError', text)
        self.assertNotIn('sample.player', text)

    def test_quick(self):
        self.assertNotIn('read:', diagnose.make(self.ws, read=False))


if __name__ == '__main__':
    unittest.main()
