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
    '[01/05/2026 18:00:06][700,50] [Settings] Paddle settings loaded: {"paddleHand":"Right","gripAngle":50}',
])
SECRETS = ('tok-AAAA1111', 'FAKEPLATFORMTOKEN99', '123456789012', 'sample.player', 'dev-0099xyz', '51.50722', '-0.12765',
           '10.1.2.3', '777888999000', 'rival.one', '203.0.113.9', 'voice')

# the shapes an independent review (2026-11-19) found the first version let through, all made up
MORE = '\n'.join([
    '[01/05/2026 18:01:00][800,57] [Account] {"UserName":"Bo","token":"tkn-ZZZZ5555","accessToken":"acc-YYYY4444"}',
    '[01/05/2026 18:01:01][900,64] [Account] Logged in as Bo',
    '[01/05/2026 18:01:02][1000,71] [Profile] {"DisplayName":"Shown Name","Email":"someone@example.com","oculusId":"oc-31337x"}',
    '[01/05/2026 18:01:03][1100,78] [Geo] {"City":"Springfield","Region":"Northshire","Address":{"Street":"1 Fake Lane","Zip":"99999"}}',
    '[01/05/2026 18:01:04][1200,85] [Device] {"SerialNumber":"SN-4455667788","refresh_token":"rfr-XXXX3333"}',
    '[01/05/2026 18:01:05][1300,92] [Net] GET https://api.example.com/v1/me?access_token=urltok-WWWW2222&x=1',
    '[01/05/2026 18:01:06][1400,99] [Net] Authorization: Bearer brr-VVVV1111abcd',
    '[01/05/2026 18:01:07][1500,106] [Net] jwt eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.c2lnbmF0dXJlLWZha2U',
    '[01/05/2026 18:01:08][1600,113] [Net] connected to fe80::1ff:fe23:4567:890a and 2001:db8:85a3:0:0:8a2e:370:7334',
    '[01/05/2026 18:01:09][1700,120] [Config] session_token=sess-UUUU0000 user_id=4242424242',
    '[01/05/2026 18:01:10][1800,127] [Account] {"UserName":"Quote\\"Tail"}',
])
MORE_SECRETS = ('tkn-ZZZZ5555', 'acc-YYYY4444', 'Bo', 'Shown Name', 'someone@example.com', 'oc-31337x', 'Springfield',
                'Northshire', '1 Fake Lane', 'SN-4455667788', 'rfr-XXXX3333', 'urltok-WWWW2222', 'brr-VVVV1111abcd',
                'eyJhbGciOiJIUzI1NiJ9', 'fe80::1ff', '2001:db8', 'sess-UUUU0000', '4242424242', 'Quote', 'Tail')


def present(secret, text):
    return redact._pattern(secret).search(text) is not None


class Redact(unittest.TestCase):
    def test_full_fields_mentions_and_blocks(self):
        out, n = redact.redact(FAKE, full=True)
        for s in SECRETS:
            self.assertNotIn(s, out)
        self.assertEqual(n['left'], 0)
        self.assertGreaterEqual(n['fields'], 11)
        self.assertGreaterEqual(n['mentions'], 1)          # the name in the chat line, outside any field
        self.assertEqual(n['dropped'], 2)                   # the UserCommunication entry and its continuation line
        self.assertIn('"paddleHand":"Right"', out)
        self.assertIn('\\"HomeUserId\\":\\"REDACTED\\"', out)   # escaped JSON stays escaped JSON

    def test_full_catches_the_shapes_the_review_found(self):
        out, n = redact.redact(FAKE + '\n' + MORE, full=True)
        for s in SECRETS + MORE_SECRETS:
            self.assertFalse(present(s, out), s)
        self.assertEqual(n['left'], 0)
        self.assertIn('18:01:08', out)                      # times are not network addresses

    def test_default_keeps_only_what_is_read(self):
        out, n = redact.redact(FAKE + '\n' + MORE)
        for s in SECRETS + MORE_SECRETS:
            self.assertFalse(present(s, out), s)
        self.assertEqual(n['left'], 0)
        self.assertEqual(out.strip().splitlines(), ['[01/05/2026 18:00:06][700,50] [Settings] Paddle settings loaded: {"paddleHand":"Right"}'])

    def test_match_data_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            names = sample.write_logs(d)
            for name in (names[0], names[-1]):              # one against the AI, one online (names, ids and ratings)
                src = os.path.join(d, name)
                with open(src, 'a', encoding='utf-8') as f:
                    f.write(FAKE + '\n' + MORE + '\n')
                for full in (False, True):
                    dst = os.path.join(d, f'redacted-{full}.log')
                    n = redact.redact_file(src, dst, full=full)
                    self.assertEqual(n['left'], 0)
                    a, b = extract.extract_log(src), extract.extract_log(dst)
                    self.assertEqual(len(a), len(b))
                    for x, y in zip(a, b):
                        self.assertEqual(x['games'], y['games'])
                        if not full:            # the full copy blanks the player ids, so the ratings go with them
                            self.assertEqual(x.get('rating'), y.get('rating'))
                    with open(dst, encoding='utf-8') as f:
                        text = f.read()
                    for s in ('sample.player', 'rival.', str(sample.MY_ID)):
                        self.assertNotIn(s, text)
            with self.assertRaises(ValueError):
                redact.redact_file(src, src)


if __name__ == '__main__':
    unittest.main()
