import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))
from elevendash import extract, redact, sample  # noqa: E402

# made-up values in the shapes real logs use: plain JSON, JSON inside a JSON string, numbers, lists
# (the place has five decimals: the generated logs' own numbers have four, so none of them can be the same number)
FAKE = '\n'.join([
    '[01/05/2026 18:00:00][100,7] [Auth] {"AuthToken":"tok-AAAA1111","PlatformAccessToken":"FAKEPLATFORMTOKEN99"}',
    '[01/05/2026 18:00:01][200,14] [Account] {"PlatformUserId":123456789012,"Username":"sample.player","DeviceId":"dev-0099xyz"}',
    '[01/05/2026 18:00:02][300,21] [Geo] {"Latitude":"51.50722","Longitude":"-0.12765","CountryCode":"GB","LocalIP":"10.1.2.3"}',
    '[01/05/2026 18:00:03][400,28] [Online] "{\\"HomeUserId\\":\\"777888999000\\",\\"PlayerNames\\":[\\"rival.one\\",\\"sample.player\\"]}"',
    '[01/05/2026 18:00:04][500,36] [Chat] sample.player joined the room hosted at 203.0.113.9',
    '[01/05/2026 18:00:05][600,43] [UserCommunication] voice packet',
    '\tsomething about voice',
    '[01/05/2026 18:00:06][700,50] [Settings] Paddle settings loaded: {"paddleHand":"Right"}',
])
SECRETS = ('tok-AAAA1111', 'FAKEPLATFORMTOKEN99', '123456789012', 'sample.player', 'dev-0099xyz', '51.50722', '-0.12765',
           '10.1.2.3', '777888999000', 'rival.one', '203.0.113.9', 'voice')


class Redact(unittest.TestCase):
    def test_fields_mentions_and_blocks(self):
        out, n = redact.redact(FAKE)
        for s in SECRETS:
            self.assertNotIn(s, out)
        self.assertEqual(n['left'], 0)
        self.assertGreaterEqual(n['fields'], 11)
        self.assertGreaterEqual(n['mentions'], 1)          # the name in the chat line, outside any field
        self.assertEqual(n['dropped'], 2)                   # the UserCommunication entry and its continuation line
        self.assertIn('"paddleHand":"Right"', out)
        self.assertIn('\\"HomeUserId\\":\\"REDACTED\\"', out)   # escaped JSON stays escaped JSON

    def test_match_data_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            name = sample.write_logs(d)[0]
            src = os.path.join(d, name)
            with open(src, 'a', encoding='utf-8') as f:
                f.write(FAKE + '\n')
            dst = os.path.join(d, 'redacted.log')
            n = redact.redact_file(src, dst)
            self.assertEqual(n['left'], 0)
            self.assertEqual(extract.extract_log(src)[0]['games'], extract.extract_log(dst)[0]['games'])
            with self.assertRaises(ValueError):
                redact.redact_file(src, src)


if __name__ == '__main__':
    unittest.main()
