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


if __name__ == '__main__':
    unittest.main()
