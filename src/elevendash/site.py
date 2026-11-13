"""Write the dashboard as one self-contained HTML file: the page, the data, the chart library and the look are all
inside it, so it needs no server and no network. Open it in a browser, send it to someone, or put it on any static host.

The file holds match data only: no game logs, no account tokens. With videos it also holds the links to your
(unlisted) YouTube uploads; leave them out with videos=False when you share it more widely.
"""
import json
import os
import re

from .page import LANGS, THEMES, WEB, color_tokens, fill

TITLE = 'Eleven vs AI Report'
FOOT_ZH = '「Eleven 對 AI 報告」'
VIDEO_FIELDS = ('video', 'videoT')


def _read(name):
    with open(os.path.join(WEB, name), encoding='utf-8') as f:
        return f.read()


def tokens_css(look):
    """Colour tokens for the file's own frame: dark, or light when the page's switch says so (data-theme on <html>).
    The page carries the same two looks on its outer element (page.theme_css)."""
    block = lambda t: ';'.join(f'{k}:{x}' for k, x in color_tokens(t).items())
    return (f':root{{{block(look["dark"])};color-scheme:dark}}\n'
            f':root[data-theme="light"]{{{block(look["light"])};color-scheme:light}}\n')


def load_data(build_dir, videos=True):
    data = {}
    for name in sorted(os.listdir(build_dir)):
        if name.endswith('.json') and not name.startswith('report_pdf'):   # the report_pdf sources belong to a hosted dashboard
            with open(os.path.join(build_dir, name), encoding='utf-8') as f:
                data[name[:-5]] = json.load(f)['rows']
    if not data:
        raise FileNotFoundError(f'no data in {build_dir}: run "elevendash build" first')
    if not videos:
        data['videos'] = []
        for rows in data.values():
            for r in rows:
                if isinstance(r, dict):
                    for k in VIDEO_FIELDS:
                        r.pop(k, None)
    return data


def _json_block(obj):
    # '<' is written as < so no text in the data can end the script block early
    return json.dumps(obj, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c')


def main_level(data):
    """The level the page opens on: your main level (most points in your last five sessions), else your latest session's."""
    main = next((r for r in data.get('findings') or [] if r.get('key') == 'main'), None)
    if main and main.get('level') is not None:
        return main['level']
    sessions = data.get('sessions') or []
    return sessions[-1]['level'] if sessions else 100


def render(build_dir, videos=True, title=TITLE, theme='dark', lang='en'):
    """The whole dashboard as one HTML string. theme and lang are what it opens with; its switches change them."""
    page = fill()
    scripts = re.findall(r'<script>(.*?)</script>', page, flags=re.S)
    markup = re.sub(r'<script>.*?</script>', '', page, flags=re.S).replace('<meta name="dash-one-writer">', '')
    data = load_data(build_dir, videos)
    look = json.loads(_read('look.json'))
    level = main_level(data)
    conf = {'params': {'level': level, 'match': '', 'session': '', 'theme': theme if theme in THEMES else 'dark',
                       'lang': lang if lang in LANGS else 'en'},
            'colors': len(look['light']['charts'])}
    d3 = _read('d3.min.js').replace('</script', '<\\/script')
    parts = [
        '<!doctype html>',
        '<html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">',
        f'<title>{title}</title>',
        '<meta name="generator" content="elevendash">',
        '<style>', tokens_css(look), _read('site.css'), '</style>',
        '</head><body>',
        '<div id="dash-root">', markup, '</div>',
        f'<p class="ed-foot"><span data-l="en">Saved from the {title}, made with elevendash from Eleven Table Tennis game logs.</span>'
        f'<span data-l="zh" lang="zh-Hant">由 elevendash 根據 Eleven Table Tennis 遊戲記錄製作的{FOOT_ZH}。</span></p>',
        f'<script type="application/json" id="ed-data">{_json_block(data)}</script>',
        f'<script type="application/json" id="ed-conf">{_json_block(conf)}</script>',
        f'<script>{d3}</script>',
        f'<script>{_read("runtime.js")}</script>',
    ]
    # each page script in its own function scope, as a dashboard host runs them
    parts += [f'<script>(function(){{\n{s}\n}})();</script>' for s in scripts]
    parts.append('<script>window.__elevendash.start();</script>')
    parts.append('</body></html>\n')
    return '\n'.join(parts)


def build_site(build_dir, out_file, videos=True, title=TITLE, theme='dark', lang='en'):
    html = render(build_dir, videos, title, theme, lang)
    os.makedirs(os.path.dirname(os.path.abspath(out_file)), exist_ok=True)
    tmp = out_file + '.tmp'
    with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
        f.write(html)
    os.replace(tmp, out_file)
    return out_file
