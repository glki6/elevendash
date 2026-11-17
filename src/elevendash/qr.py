"""A QR code as SVG, for the app's phone link: byte mode, error correction level M, versions 1 to 10 (up to 213
bytes), plain Python. It follows ISO/IEC 18004 the way Project Nayuki's reference QR Code generator (MIT) lays it out.
"""

# versions 1..10 at level M: error correction codewords per block, and number of blocks
ECC_PER_BLOCK = [None, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26]
BLOCKS = [None, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5]
FORMAT_M = 0                     # the two format bits for level M
MAX_VERSION = 10


def _gf_mul(x, y):
    z = 0
    for i in reversed(range(8)):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z


def _rs_divisor(degree):
    result = [0] * (degree - 1) + [1]
    root = 1
    for _ in range(degree):
        for j in range(len(result)):
            result[j] = _gf_mul(result[j], root)
            if j + 1 < len(result):
                result[j] ^= result[j + 1]
        root = _gf_mul(root, 0x02)
    return result


def _rs_remainder(data, divisor):
    result = [0] * len(divisor)
    for b in data:
        factor = b ^ result.pop(0)
        result.append(0)
        for i, coef in enumerate(divisor):
            result[i] ^= _gf_mul(coef, factor)
    return result


def _raw_modules(ver):
    n = (16 * ver + 128) * ver + 64
    if ver >= 2:
        k = ver // 7 + 2
        n -= (25 * k - 10) * k - 55
        if ver >= 7:
            n -= 36
    return n


def _data_codewords(ver):
    return _raw_modules(ver) // 8 - ECC_PER_BLOCK[ver] * BLOCKS[ver]


def _codewords(data, ver):
    """The data with its mode, length, padding and error correction, interleaved into the final codewords."""
    bits = []

    def put(value, n):
        bits.extend((value >> i) & 1 for i in reversed(range(n)))

    put(0b0100, 4)
    put(len(data), 8 if ver <= 9 else 16)
    for b in data:
        put(b, 8)
    cap = _data_codewords(ver) * 8
    put(0, min(4, cap - len(bits)))
    put(0, -len(bits) % 8)
    pad = 0xEC
    while len(bits) < cap:
        put(pad, 8)
        pad ^= 0xEC ^ 0x11
    words = [int(''.join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]

    nblocks, ecc_len = BLOCKS[ver], ECC_PER_BLOCK[ver]
    raw = _raw_modules(ver) // 8
    nshort = nblocks - raw % nblocks
    short_len = raw // nblocks
    divisor = _rs_divisor(ecc_len)
    blocks, k = [], 0
    for i in range(nblocks):
        n = short_len - ecc_len + (0 if i < nshort else 1)
        dat = words[k:k + n]
        k += n
        ecc = _rs_remainder(dat, divisor)
        if i < nshort:
            dat.append(0)
        blocks.append(dat + ecc)
    out = []
    for i in range(len(blocks[0])):
        for j, blk in enumerate(blocks):
            if i != short_len - ecc_len or j >= nshort:
                out.append(blk[i])
    return out


class _Grid:
    def __init__(self, ver):
        self.ver = ver
        self.size = ver * 4 + 17
        self.dark = [[False] * self.size for _ in range(self.size)]
        self.fixed = [[False] * self.size for _ in range(self.size)]

    def set(self, x, y, dark):
        self.dark[y][x] = dark
        self.fixed[y][x] = True

    def patterns(self):
        s = self.size
        for i in range(s):
            self.set(6, i, i % 2 == 0)
            self.set(i, 6, i % 2 == 0)
        for cx, cy in ((3, 3), (s - 4, 3), (3, s - 4)):
            for dy in range(-4, 5):
                for dx in range(-4, 5):
                    x, y = cx + dx, cy + dy
                    if 0 <= x < s and 0 <= y < s:
                        self.set(x, y, max(abs(dx), abs(dy)) not in (2, 4))
        pos = self.alignment_positions()
        last = len(pos) - 1
        for i, a in enumerate(pos):
            for j, b in enumerate(pos):
                if (i, j) in ((0, 0), (0, last), (last, 0)):
                    continue
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        self.set(a + dx, b + dy, max(abs(dx), abs(dy)) != 1)
        self.format_bits(0)
        if self.ver >= 7:
            rem = self.ver
            for _ in range(12):
                rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
            bits = self.ver << 12 | rem
            for i in range(18):
                bit = (bits >> i) & 1 == 1
                a, b = s - 11 + i % 3, i // 3
                self.set(a, b, bit)
                self.set(b, a, bit)

    def alignment_positions(self):
        if self.ver == 1:
            return []
        n = self.ver // 7 + 2
        step = (self.ver * 8 + n * 3 + 5) // (n * 4 - 4) * 2
        return [6] + sorted(self.size - 7 - i * step for i in range(n - 1))

    def format_bits(self, mask):
        data = FORMAT_M << 3 | mask
        rem = data
        for _ in range(10):
            rem = (rem << 1) ^ ((rem >> 9) * 0x537)
        bits = (data << 10 | rem) ^ 0x5412
        bit = lambda i: (bits >> i) & 1 == 1
        s = self.size
        for i in range(6):
            self.set(8, i, bit(i))
        self.set(8, 7, bit(6))
        self.set(8, 8, bit(7))
        self.set(7, 8, bit(8))
        for i in range(9, 15):
            self.set(14 - i, 8, bit(i))
        for i in range(8):
            self.set(s - 1 - i, 8, bit(i))
        for i in range(8, 15):
            self.set(8, s - 15 + i, bit(i))
        self.set(8, s - 8, True)

    def place(self, words):
        s, i, total = self.size, 0, len(words) * 8
        right = s - 1
        while right >= 1:
            if right == 6:
                right = 5
            for vert in range(s):
                for j in range(2):
                    x = right - j
                    upward = ((right + 1) & 2) == 0
                    y = s - 1 - vert if upward else vert
                    if not self.fixed[y][x] and i < total:
                        self.dark[y][x] = (words[i >> 3] >> (7 - (i & 7))) & 1 == 1
                        i += 1
            right -= 2

    def apply_mask(self, mask):
        f = MASKS[mask]
        for y in range(self.size):
            for x in range(self.size):
                if not self.fixed[y][x] and f(x, y):
                    self.dark[y][x] = not self.dark[y][x]

    def penalty(self):
        s, m, score = self.size, self.dark, 0

        def lines():
            for y in range(s):
                yield m[y]
            for x in range(s):
                yield [m[y][x] for y in range(s)]

        for line in lines():
            run_color, run, hist = False, 0, [0] * 7
            for c in line:
                if c == run_color:
                    run += 1
                    if run == 5:
                        score += 3
                    elif run > 5:
                        score += 1
                else:
                    _add_history(run, hist, s)
                    if not run_color:
                        score += _finder_like(hist) * 40
                    run_color, run = c, 1
            if run_color:
                _add_history(run, hist, s)
                run = 0
            _add_history(run + s, hist, s)
            score += _finder_like(hist) * 40
        for y in range(s - 1):
            for x in range(s - 1):
                if m[y][x] == m[y][x + 1] == m[y + 1][x] == m[y + 1][x + 1]:
                    score += 3
        dark = sum(map(sum, m))
        total = s * s
        score += ((abs(dark * 20 - total * 10) + total - 1) // total - 1) * 10
        return score


def _add_history(run, hist, size):
    if hist[0] == 0:
        run += size
    hist.pop()
    hist.insert(0, run)


def _finder_like(h):
    n = h[1]
    core = n > 0 and h[2] == h[4] == h[5] == n and h[3] == n * 3
    return (1 if core and h[0] >= n * 4 and h[6] >= n else 0) + (1 if core and h[6] >= n * 4 and h[0] >= n else 0)


MASKS = [
    lambda x, y: (x + y) % 2 == 0,
    lambda x, y: y % 2 == 0,
    lambda x, y: x % 3 == 0,
    lambda x, y: (x + y) % 3 == 0,
    lambda x, y: (x // 3 + y // 2) % 2 == 0,
    lambda x, y: x * y % 2 + x * y % 3 == 0,
    lambda x, y: (x * y % 2 + x * y % 3) % 2 == 0,
    lambda x, y: ((x + y) % 2 + x * y % 3) % 2 == 0,
]


def matrix(text, mask=None):
    """The QR code for text as rows of booleans (True = dark), without the quiet zone. mask=None picks the best."""
    data = text.encode('utf-8') if isinstance(text, str) else bytes(text)
    for ver in range(1, MAX_VERSION + 1):
        if 4 + (8 if ver <= 9 else 16) + 8 * len(data) <= _data_codewords(ver) * 8:
            break
    else:
        raise ValueError(f'too long for a QR code here ({len(data)} bytes)')
    words = _codewords(data, ver)
    best = None
    for k in ([mask] if mask is not None else range(8)):
        g = _Grid(ver)
        g.patterns()
        g.place(words)
        g.apply_mask(k)
        g.format_bits(k)
        p = g.penalty() if mask is None else 0
        if best is None or p < best[0]:
            best = (p, g)
    return best[1].dark


def svg(text, quiet=4):
    """The QR code as an SVG image: dark modules on white, so it scans in a dark page too."""
    m = matrix(text)
    n = len(m) + 2 * quiet
    path = ''.join(f'M{x + quiet},{y + quiet}h1v1h-1z' for y, row in enumerate(m) for x, c in enumerate(row) if c)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {n} {n}" shape-rendering="crispEdges" '
            f'role="img" aria-label="QR code"><rect width="{n}" height="{n}" fill="#fff"/>'
            f'<path d="{path}" fill="#000"/></svg>')
