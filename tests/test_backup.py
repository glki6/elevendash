"""Backup and restore (one file holding a workspace) and the export of match data as tables."""
import contextlib
import csv
import io
import json
import os
import re
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))
from elevendash import backup, cli, export, sample, workspace  # noqa: E402


class Backup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.ws = workspace.init(os.path.join(cls.tmp.name, 'ws'), '192.168.1.20:8090')
        cls.names = sample.write_logs(cls.ws.logs)
        cls.ws.set(phone=True, phone_key='secret-of-this-computer', phone_port=8737, theme='light')
        with open(os.path.join(cls.ws.root, 'notes.json'), 'w', encoding='utf-8') as f:
            json.dump({'journal|2026-01-29|drill|k1': {'text': 'Multiball', 'at': ''}}, f)
        with contextlib.redirect_stdout(io.StringIO()):
            cli.do_build(cls.ws)
        cls.file, cls.n = backup.make(cls.ws)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_what_a_backup_holds(self):
        self.assertEqual(self.n['logs'], len(self.names))
        with zipfile.ZipFile(self.file) as z:
            names = set(z.namelist())
            self.assertEqual(names, {backup.MARK, 'elevendash.json', 'notes.json'} | {'logs/' + n for n in self.names})
            c = json.loads(z.read('elevendash.json'))
        # the settings that travel, and nothing that belongs to one computer
        self.assertEqual(c, {'version': 1, 'quest': '192.168.1.20:8090', 'theme': 'light'})

    def test_restore_gives_the_same_workspace(self):
        root = os.path.join(self.tmp.name, 'restored')
        got = backup.restore(self.file, root, say=lambda *a: None)
        self.assertEqual(got, {'logs': len(self.names), 'notes': True})
        ws = workspace.find(root)
        for n in self.names:
            with open(os.path.join(self.ws.logs, n), 'rb') as a, open(os.path.join(ws.logs, n), 'rb') as b:
                self.assertEqual(a.read(), b.read(), n)
        self.assertEqual(ws.config().get('quest'), '192.168.1.20:8090')
        self.assertNotIn('phone_key', ws.config())
        with open(os.path.join(root, 'notes.json'), encoding='utf-8') as f:
            self.assertIn('journal|2026-01-29|drill|k1', json.load(f))
        with self.assertRaises(ValueError):         # never on top of logs that are already there
            backup.restore(self.file, root, say=lambda *a: None)

    def test_only_a_backup_and_only_its_own_names(self):
        junk = os.path.join(self.tmp.name, 'junk.zip')
        with open(junk, 'wb') as f:
            f.write(b'PK not really')
        with self.assertRaises(ValueError):
            backup.restore(junk, os.path.join(self.tmp.name, 'a'))
        with zipfile.ZipFile(junk, 'w') as z:
            z.writestr('logs/' + self.names[0], 'x')
        with self.assertRaises(ValueError):         # a zip, but nothing says it is a backup
            backup.restore(junk, os.path.join(self.tmp.name, 'a'))
        # a file made to look like a backup cannot write outside the workspace, or anything but logs and notes
        root = os.path.join(self.tmp.name, 'careful')
        with zipfile.ZipFile(junk, 'w') as z:
            z.writestr(backup.MARK, json.dumps({'app': 'elevendash'}))
            z.writestr('logs/' + self.names[0], 'a log')
            z.writestr('../escaped.log', 'x')
            z.writestr('logs/../../' + self.names[1], 'x')
            z.writestr('logs/sub/' + self.names[1], 'x')
            z.writestr('build/matches.json', 'x')
            z.writestr('site/index.html', 'x')
            z.writestr('elevendash.json', json.dumps({'quest': '10.0.0.9:8090', 'phone': True, 'phone_key': 'theirs', 'hand': ['x']}))
        backup.restore(junk, root, say=lambda *a: None)
        found = sorted(os.path.relpath(os.path.join(d, f), root).replace(os.sep, '/') for d, _, fs in os.walk(root) for f in fs)
        self.assertEqual(found, ['elevendash.json', 'logs/' + self.names[0]])
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, 'escaped.log')))
        self.assertEqual(workspace.find(root).config(), {'version': 1, 'quest': '10.0.0.9:8090'})

    def test_command_line(self):
        out = io.StringIO()
        dest = os.path.join(self.tmp.name, 'cli.zip')
        with contextlib.redirect_stdout(out):
            self.assertEqual(cli.main(['--dir', self.ws.root, 'backup', '--out', dest]), 0)
        self.assertIn('account tokens', out.getvalue())
        self.assertTrue(zipfile.is_zipfile(dest))
        new = os.path.join(self.tmp.name, 'cli-restored')
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(['restore', dest, new]), 0)
        self.assertTrue(os.path.isfile(os.path.join(new, 'site', 'index.html')))


class Export(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.ws = workspace.init(os.path.join(cls.tmp.name, 'ws'))
        sample.write_logs(cls.ws.logs)
        with contextlib.redirect_stdout(io.StringIO()):
            cli.do_build(cls.ws)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def rows(self, name):
        with open(os.path.join(self.ws.build, name + '.json'), encoding='utf-8') as f:
            return json.load(f)['rows']

    def test_fields_are_the_builders(self):
        src = os.path.join(os.path.dirname(os.path.abspath(export.__file__)), 'builddata.py')
        with open(src, encoding='utf-8') as f:
            m = re.search(r'^SHOT_FIELDS = (\[[^\]]+\])', f.read(), re.M)
        self.assertEqual(export.SHOT_FIELDS, json.loads(m.group(1).replace("'", '"')))

    def test_tables(self):
        out = os.path.join(self.tmp.name, 'csv')
        got = export.write(self.ws.build, out, 'csv')
        self.assertEqual(got['rows']['matches'], len(self.rows('matches')))
        self.assertEqual(got['rows']['points'], len(self.rows('points')))
        self.assertEqual(got['rows']['shots'], sum(r['n'] for r in self.rows('shots')))
        with open(os.path.join(out, 'shots.csv'), encoding='utf-8', newline='') as f:
            shots = list(csv.DictReader(f))
        self.assertEqual(len(shots), got['rows']['shots'])
        keys = {r['key'] for r in self.rows('matches')}
        self.assertTrue(all(r['match'] in keys and r['shot'] in 'SDLFPCX' and r['role'] in 'SRA' for r in shots))
        fast = [float(r['speed']) for r in shots if r['speed']]
        self.assertTrue(0 < max(fast) < 40, max(fast))          # metres a second, not tenths
        with open(os.path.join(out, 'matches.csv'), encoding='utf-8', newline='') as f:
            head = next(csv.reader(f))
        self.assertEqual(head[:3], ['key', 'date', 'start'])
        self.assertFalse({'video', 'videoT'} & set(head))
        # match data only: nothing of the log's account lines
        for name in got['files']:
            with open(os.path.join(out, name), encoding='utf-8') as f:
                text = f.read()
            for word in ('AuthToken', 'PlatformAccessToken', 'UserName', 'Bearer'):
                self.assertNotIn(word, text, name)
        j = export.write(self.ws.build, os.path.join(self.tmp.name, 'json'), 'json')
        with open(os.path.join(j['dir'], 'points.json'), encoding='utf-8') as f:
            self.assertEqual(len(json.load(f)), got['rows']['points'])
        with self.assertRaises(ValueError):
            export.write(self.ws.build, out, 'xml')

    def test_command_line(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cli.main(['--dir', self.ws.root, 'export', '--format', 'json']), 0)
        self.assertIn('Match data only', out.getvalue())
        self.assertTrue(os.path.isfile(os.path.join(self.ws.root, 'export', 'shots.json')))


if __name__ == '__main__':
    unittest.main()
