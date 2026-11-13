"""Two languages for the dashboard: English as written, and Traditional Chinese from web/zh-Hant.json.

The word list has three parts, each keyed by the English:
  page    sentences of the page template. fill() writes each one twice, <span data-l="en"> and <span data-l="zh">,
          and the page's language switch shows one. A value the page draws inside a sentence is {1}, {2}, ... in
          the key, in the order it appears, so the Chinese can put it where Chinese word order wants it.
  script  words the page's scripts write, looked up with ER.tr(key, ...values); {0}, {1} take the values.
  data    sentences the builder writes (T below), with {name} for values. Rows carry each one twice: field, and
          field_zh in Chinese.

    python -m elevendash.i18n check     lists English with no Chinese yet, Chinese no longer used, and
                                        Chinese that lost or gained a value
"""
import ast
import json
import os
import re
import sys
from html.parser import HTMLParser

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(HERE, 'web')
CATALOG = os.path.join(WEB, 'zh-Hant.json')
SECTIONS = ('page', 'script', 'data')
_cat = None


def catalog():
    global _cat
    if _cat is None:
        try:
            with open(CATALOG, encoding='utf-8') as f:
                _cat = json.load(f)
        except FileNotFoundError:
            _cat = {}
        for s in SECTIONS:
            _cat.setdefault(s, {})
    return _cat


# ---------------- the builder's sentences ----------------
class Bi:
    """A piece of text in English and Chinese."""
    __slots__ = ('en', 'zh')

    def __init__(self, en, zh=None):
        self.en, self.zh = en, (en if zh is None else zh)

    def __add__(self, o):
        o = bi(o)
        return Bi(self.en + o.en, self.zh + o.zh)

    def __radd__(self, o):
        o = bi(o)
        return Bi(o.en + self.en, o.zh + self.zh)

    def __bool__(self):
        return bool(self.en)

    def map(self, en, zh=None):
        return Bi(en(self.en), (zh or en)(self.zh))

    def __repr__(self):
        return f'Bi({self.en!r}, {self.zh!r})'


def bi(v):
    return v if isinstance(v, Bi) else Bi(str(v))


MISSING = set()


def T(template, **kw):
    """One sentence in both languages. template is the English with {name} for values (a value may be a Bi); the
    Chinese is the word list's data entry for the same template, or the English while it has none."""
    zh_t = catalog()['data'].get(template)
    if zh_t is None:
        MISSING.add(template)
        zh_t = template
    en = template.format(**{k: (v.en if isinstance(v, Bi) else v) for k, v in kw.items()})
    zh = zh_t.format(**{k: (v.zh if isinstance(v, Bi) else v) for k, v in kw.items()})
    return Bi(en, zh)


def W(word):
    """A word or label on its own, in both languages."""
    return T(word)


def listing(xs, zh_sep=None):
    """'a, b and c', and in Chinese 'a、b和c' (or every item joined by zh_sep, for clauses)."""
    xs = [bi(x) for x in xs]
    if len(xs) == 1:
        return xs[0]
    zh = (zh_sep.join(x.zh for x in xs) if zh_sep else '、'.join(x.zh for x in xs[:-1]) + '和' + xs[-1].zh)
    return Bi(', '.join(x.en for x in xs[:-1]) + ' and ' + xs[-1].en, zh)


def join(sep, xs, zh_sep=None):
    xs = [bi(x) for x in xs]
    return Bi(sep.join(x.en for x in xs), (sep if zh_sep is None else zh_sep).join(x.zh for x in xs))


def put(row, field, value):
    """Set a row's field, and field_zh when the value is text in both languages."""
    if isinstance(value, Bi):
        row[field], row[field + '_zh'] = value.en, value.zh
    else:
        row[field] = value
    return row


# ---------------- the page ----------------
VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'source', 'track', 'wbr'}
INLINE = {'b', 'span', 'i', 'a', 'em', 'strong', 'small', 'code', 'abbr', 'sup', 'sub'}
WORD = re.compile(r'[A-Za-z]')


class _El:
    __slots__ = ('tag', 'start', 'kids', 'end')

    def __init__(self, tag, start, end=''):
        self.tag, self.start, self.kids, self.end = tag, start, [], end

    def html(self):
        return self.start + ''.join(k if isinstance(k, str) else k.html() for k in self.kids) + self.end

    def text(self):
        return ''.join(k if isinstance(k, str) else k.text() for k in self.kids)

    def attr(self, name):
        m = re.search(r'\s' + re.escape(name) + r'(?:="([^"]*)"|(?=[\s>/]))', self.start)
        return None if m is None else (m.group(1) or '')


class _Tree(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.root = _El('', '')
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        e = _El(tag, self.get_starttag_text())
        self.stack[-1].kids.append(e)
        if tag not in VOID:
            self.stack.append(e)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].kids.append(_El(tag, self.get_starttag_text()))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                self.stack[i].end = f'</{tag}>'
                del self.stack[i:]
                return
        raise ValueError(f'</{tag}> closes nothing')

    def handle_data(self, data):
        self.stack[-1].kids.append(data)

    def handle_entityref(self, name):
        self.stack[-1].kids.append(f'&{name};')

    def handle_charref(self, name):
        self.stack[-1].kids.append(f'&#{name};')

    def handle_comment(self, data):
        self.stack[-1].kids.append(f'<!--{data}-->')

    def handle_decl(self, decl):
        self.stack[-1].kids.append(f'<!{decl}>')


def _parse(markup):
    t = _Tree()
    t.feed(markup)
    t.close()
    if len(t.stack) != 1:
        raise ValueError(f'<{t.stack[-1].tag}> is never closed')
    if t.root.html() != markup:
        raise ValueError('the page markup does not read back the same: write it as plain, closed HTML')
    return t.root


INLINE_CODE = INLINE | {'code'}


def _atom(k):
    """A child that sits inside a sentence as a value: an inline element with no id or condition, and no words of its
    own, or words that stay as they are (translate="no", such as a command)."""
    return (isinstance(k, _El) and k.tag in INLINE_CODE and k.attr('id') is None and k.attr('data-showif') is None
            and (k.attr('translate') == 'no' or not WORD.search(k.text())))


def _drawn(k):
    return 'data-draw' in k.html()


def _key(run):
    out, n = [], 0
    for k in run:
        if isinstance(k, str):
            out.append(k)
        else:
            n += 1
            out.append('{%d}' % n)
    return re.sub(r'\s+', ' ', ''.join(out)).strip()


class _Page:
    def __init__(self, zh, collect=None):
        self.zh, self.collect, self.missing = zh, collect, set()

    def word(self, en):
        if self.collect is not None:
            self.collect.add(en)
        zh = self.zh.get(en)
        if zh is None:
            self.missing.add(en)
        return zh

    def unit(self, run):
        """A sentence: its words, and the values drawn inside it."""
        i, j = 0, len(run)
        while i < j and ((isinstance(run[i], str) and not run[i].strip()) or (not isinstance(run[i], str) and not _drawn(run[i]))):
            i += 1
        while j > i and ((isinstance(run[j - 1], str) and not run[j - 1].strip()) or (not isinstance(run[j - 1], str) and not _drawn(run[j - 1]))):
            j -= 1
        core = run[i:j]
        if not any(isinstance(k, str) and WORD.search(k) for k in core):
            return run
        lead = re.match(r'\s*', core[0]).group() if isinstance(core[0], str) else ''
        tail = re.search(r'\s*$', core[-1]).group() if isinstance(core[-1], str) else ''
        key = _key(core)
        zh = self.word(key)
        if zh is None or zh == key:
            return run
        atoms = [k for k in core if not isinstance(k, str)]
        en_html = ''.join(k if isinstance(k, str) else k.html() for k in core)
        en_html = en_html[len(lead):len(en_html) - len(tail)] if tail else en_html[len(lead):]
        zh_html = re.sub(r'\{(\d+)\}', lambda m: atoms[int(m.group(1)) - 1].html(), zh)
        out = f'{lead}<span data-l="en">{en_html}</span><span data-l="zh" lang="zh-Hant">{zh_html}</span>{tail}'
        return run[:i] + [out] + run[j:]

    def attrs(self, e):
        label = e.attr('aria-label')
        if label and WORD.search(label) and 'data-aria-zh' not in e.start:
            zh = self.word(label)
            if zh and zh != label:
                esc = zh.replace('&', '&amp;').replace('"', '&quot;')
                e.start = re.sub(r'(\s*/?>)$', lambda m: f' data-aria-en="{label}" data-aria-zh="{esc}"' + m.group(1), e.start, count=1)

    def walk(self, e):
        if e.tag:
            self.attrs(e)
        if e.attr('translate') == 'no' or e.tag in ('svg', 'script', 'style'):
            return
        out, run = [], []
        for k in e.kids + [None]:
            if k is not None and (isinstance(k, str) or _atom(k)):
                run.append(k)
                continue
            if run:
                out += self.unit(run)
                run = []
            if k is not None:
                self.walk(k)
                out.append(k)
        e.kids = out


SPLIT = re.compile(r'(<style>.*?</style>|<script>.*?</script>)', re.S)


def bilingual(html, collect=None, strict=False):
    """The page with every sentence in both languages, and the Chinese for its scripts. Text inside a
    translate="no" element is left as it is."""
    zh = catalog()['page']
    page = _Page(zh, collect)
    parts = SPLIT.split(html)
    for i in range(0, len(parts), 2):
        if parts[i].strip():
            root = _parse(parts[i])
            page.walk(root)
            parts[i] = root.html()
    if strict and page.missing:
        raise KeyError('no Chinese for: ' + '; '.join(sorted(page.missing)))
    return ''.join(parts), page.missing


def script_words():
    """The Chinese words the page's scripts look up (ER.tr), as a JSON object for the page."""
    return json.dumps(catalog()['script'], ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c')


# ---------------- check ----------------
JS_CALL = re.compile(r'ER\.(?:tr|trn|k)\(')
JS_STR = re.compile(r"""'((?:\\.|[^'\\])*)'|"((?:\\.|[^"\\])*)\"""")


def _js_unescape(s):
    return re.sub(r'\\(.)', r'\1', s)


def _first_arg(js, i):
    """The text of the first argument of the call whose '(' ends at i: up to the first comma or ')' at its own depth."""
    depth, j, quote = 0, i, None
    while j < len(js):
        ch = js[j]
        if quote:
            if ch == '\\':
                j += 1
            elif ch == quote:
                quote = None
        elif ch in '\'"`':
            quote = ch
        elif ch in '([{':
            depth += 1
        elif ch in ')]}':
            if depth == 0:
                break
            depth -= 1
        elif ch == ',' and depth == 0:
            break
        j += 1
    return js[i:j]


def _js_keys(js):
    """Every string in the first argument of ER.tr, ER.trn and ER.k: the word itself, or each word a condition picks."""
    keys = set()
    for m in JS_CALL.finditer(js):
        for a, b in JS_STR.findall(_first_arg(js, m.end())):
            keys.add(_js_unescape(a or b))
    return keys


def page_keys():
    from .page import fill
    keys = set()
    fill(collect=keys)
    return keys


def script_keys():
    from .page import fill
    html = fill(collect=set())
    keys = set()
    for block in re.findall(r'<script>(.*?)</script>', html, flags=re.S):
        keys |= _js_keys(block)
    return keys - JS_NOT_WORDS


# strings a condition compares against inside ER.tr(...), which are not shown themselves
JS_NOT_WORDS = {'full'}


def data_keys():
    """Every template the builder passes to T or W, read from its source."""
    keys = set()
    for name in ('builddata.py',):
        with open(os.path.join(HERE, name), encoding='utf-8') as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ('T', 'W') and node.args:
                # the template itself, or each one a condition picks
                todo = [node.args[0]]
                while todo:
                    c = todo.pop()
                    if isinstance(c, ast.IfExp):
                        todo += [c.body, c.orelse]
                    elif isinstance(c, ast.Constant) and isinstance(c.value, str):
                        keys.add(c.value)
    return keys


def _fields(s, sect):
    return sorted(set(re.findall(r'\{(\d+)\}' if sect != 'data' else r'\{(\w+)(?:[:!][^}]*)?\}', s)))


def check(out=sys.stdout):
    cat = catalog()
    found = {'page': page_keys(), 'script': script_keys(), 'data': data_keys()}
    bad = 0
    for sect in SECTIONS:
        have, want = cat[sect], found[sect]
        missing = sorted(want - set(have))
        unused = sorted(set(have) - want)
        wrong = sorted(k for k in want & set(have) if _fields(k, sect) != _fields(have[k], sect))
        bad += len(missing) + len(wrong)
        print(f'{sect}: {len(want)} in use, {len(missing)} without Chinese, {len(unused)} unused, {len(wrong)} with other values',
              file=out)
        for k in missing:
            print(f'  missing  {k}', file=out)
        for k in wrong:
            print(f'  values   {k}  ->  {have[k]}', file=out)
        for k in unused:
            print(f'  unused   {k}', file=out)
    return bad


def dump_missing(path):
    """Write the English with no Chinese yet, by section, to a JSON file to fill in."""
    cat = catalog()
    found = {'page': page_keys(), 'script': script_keys(), 'data': data_keys()}
    todo = {s: {k: '' for k in sorted(found[s] - set(cat[s]))} for s in SECTIONS}
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(todo, f, ensure_ascii=False, indent=1)
    return {s: len(v) for s, v in todo.items()}


if __name__ == '__main__':
    if len(sys.argv) > 2 and sys.argv[1] == 'todo':
        print(dump_missing(sys.argv[2]))
    else:
        sys.exit(1 if check() else 0)
