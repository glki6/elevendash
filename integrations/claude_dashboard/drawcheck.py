"""The Claude dashboard's one-writer check on stored HTML, done locally: every outermost data-draw element must be
stored empty (no child element; its text only dashes, dots, spaces or n/a), and no drawing may sit inside another.
usage: drawcheck.py <page.html | store files__index.html.json>"""
import json, re, sys
from html.parser import HTMLParser

NL = re.compile(r'^[\s–—−\-·.…]*$|^n/?a$', re.I)
VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}

path = sys.argv[1]
text = open(path, encoding='utf-8').read()
if path.endswith('.json'):
    doc = json.loads(text)
    strs = [v for v in (doc.values() if isinstance(doc, dict) else []) if isinstance(v, str)]
    text = max(strs, key=len)


class P(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []  # [tag, drawing record or None]
        self.draws, self.nested = [], []

    def owner(self):
        for _, d in reversed(self.stack):
            if d is not None:
                return d
        return None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        own = self.owner()
        if own is not None:
            own['kids'] += 1
            if 'data-draw' in a:
                self.nested.append(a['data-draw'])
        rec = None
        if 'data-draw' in a and own is None:
            rec = {'name': a['data-draw'], 'tag': tag, 'kids': 0, 'text': ''}
            self.draws.append(rec)
        if tag not in VOID:
            self.stack.append([tag, rec])

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID and self.stack and self.stack[-1][0] == tag:
            self.stack.pop()

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        own = self.owner()
        if own is not None:
            own['text'] += data


p = P()
p.feed(text)
bad = [d for d in p.draws if d['kids'] or not NL.match(d['text'].strip())]
print(f'{len(p.draws)} drawings; not empty: {len(bad)}; nested: {len(p.nested)}')
for d in bad:
    print(f"  not empty: <{d['tag']} data-draw={d['name']}> {d['kids']} child elements, text {d['text'].strip()[:60]!r}")
for n in p.nested:
    print(f'  nested: {n}')
