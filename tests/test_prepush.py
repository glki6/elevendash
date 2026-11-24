"""The pre-push leak check (tools/prepush/check.py): short values do not trip on a picture's pixels, while text
files, the text a picture carries and long values in a picture are still checked."""
import importlib.util
import os
import re
import struct
import unittest
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location('prepush_check', os.path.join(ROOT, 'tools', 'prepush', 'check.py'))
check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check)
redact = check.redact


def pats(*values):
    return [(redact._pattern(v), len(v) >= check.LONG) for v in values]


def chunk(kind, body):
    return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body))


def png(*chunks):
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', bytes(13)) + b''.join(chunks) + chunk(b'IEND', b'')


class PrepushTest(unittest.TestCase):
    def test_short_value_found_by_chance_in_a_picture_is_not_a_hit(self):
        path = os.path.join(ROOT, 'pages', 'img', 'shots.png')
        with open(path, 'rb') as f:
            data = f.read()
        text = data.decode('utf-8', errors='replace')
        # a three-letter "word" that turns up in the compressed pixels, the way a short name from the logs did
        word = next(m.group(0) for m in re.finditer(r'(?<!\w)[A-Za-z]{3}(?!\w)', text))
        self.assertTrue(redact._pattern(word).search(text))
        self.assertEqual(check.look(data, 'pages/img/shots.png', pats(word)), [])

    def test_long_value_in_a_picture_is_a_hit(self):
        data = png(chunk(b'IDAT', b'\x00\x13noise PlayerSecret42 noise\xff'))
        self.assertEqual(check.look(data, 'a.png', pats('PlayerSecret42')), ['1 private value(s)'])

    def test_short_value_in_a_pictures_text_is_a_hit(self):
        for meta in (chunk(b'tEXt', b'Author\0Ann'),
                     chunk(b'zTXt', b'Author\0\0' + zlib.compress(b'Ann')),
                     chunk(b'iTXt', b'Author\0\1\0en\0\0' + zlib.compress(b'Ann'))):
            data = png(meta, chunk(b'IDAT', b'\x00\x01'))
            self.assertEqual(check.look(data, 'a.png', pats('Ann')), ['1 private value(s)'], meta[4:8])

    def test_jpeg_and_webp_text_are_read(self):
        jpeg = b'\xff\xd8\xff\xfe' + struct.pack('>H', 2 + 5) + b'b Ann' + b'\xff\xda\x00\x02 Bob \xff\xd9'
        self.assertEqual(check.look(jpeg, 'a.jpg', pats('Ann')), ['1 private value(s)'])
        self.assertEqual(check.look(jpeg, 'a.jpg', pats('Bob')), [])
        body = b'x Ann x'
        webp = b'RIFF' + struct.pack('<I', 4 + 8 + len(body) + 1) + b'WEBP' + b'EXIF' + struct.pack('<I', len(body)) \
            + body + b'\0'
        self.assertEqual(check.look(webp, 'a.webp', pats('Ann')), ['1 private value(s)'])

    def test_short_value_in_a_text_file_is_still_a_hit(self):
        self.assertEqual(check.look(b'hello Ann, bye', 'notes.md', pats('Ann')), ['1 private value(s)'])

    def test_secret_shapes_are_still_found_in_a_picture(self):
        token = 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.c2lnbmF0dXJlMTIz'
        data = png(chunk(b'IDAT', b' ' + token.encode() + b' '))
        self.assertEqual(check.look(data, 'a.png', []), ['1 secret-shaped value(s) (a token or key)'])


if __name__ == '__main__':
    unittest.main()
