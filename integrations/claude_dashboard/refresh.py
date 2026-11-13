r"""Keep a Claude dashboard (a claude.ai Data artifact) in step with an elevendash workspace.

This is one person's hosted copy of the dashboard; elevendash itself does not need it. Run it from the workspace:

  python -I <repo>/integrations/claude_dashboard/refresh.py [--offline] [--quest HOST]
        fetch new logs, rebuild, print the session report, write site/index.html, print the PDF, and list the data
        files that differ from what the dashboard holds
  python -I <repo>/integrations/claude_dashboard/refresh.py record <dataset>=<asset id> ...
        after uploading: remember the new asset ids, print the replaced ones to delete
  python -I <repo>/integrations/claude_dashboard/make_docs.py <workspace>/claude/store <utc now>
        then write the store documents it lists as changed

Uploads come from build/<dataset>.json, and from claude/report_pdf*.json for the PDFs (one per look and language).
The asset ids are kept in claude/published.json in the workspace.
"""
import argparse
import base64
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, 'src'))
from elevendash import cli, fetch, workspace      # noqa: E402
from elevendash.pdf import make_pdf               # noqa: E402
from elevendash.site import render                # noqa: E402


def sha_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha(path):
    with open(path, 'rb') as f:
        return sha_bytes(f.read())


# One PDF per look and language. The page's Save as PDF button hands over the one matching what is on screen.
PDFS = {'report_pdf': ('dark', 'en'), 'report_pdf_light': ('light', 'en'),
        'report_pdf_zh': ('dark', 'zh'), 'report_pdf_zh_light': ('light', 'zh')}


class Claude:
    def __init__(self, ws, reports=None):
        self.ws = ws
        self.dir = os.path.join(ws.root, 'claude')
        self.published = os.path.join(self.dir, 'published.json')
        self.pdf_wraps = {ds: os.path.join(self.dir, f'{ds}.json') for ds in PDFS}
        # where the PDFs go: --reports, else the workspace's claude_reports setting, else reports\ in the workspace
        self.reports = reports or ws.config().get('claude_reports') or os.path.join(ws.root, 'reports')

    def load_published(self):
        if not os.path.exists(self.published):
            return {}
        with open(self.published, encoding='utf-8') as f:
            return json.load(f)

    def files(self):
        """dataset name -> the file that is uploaded for it."""
        out = {f[:-5]: os.path.join(self.ws.build, f) for f in sorted(os.listdir(self.ws.build)) if f.endswith('.json')}
        for ds, wrap in self.pdf_wraps.items():
            if os.path.exists(wrap):
                out[ds] = wrap
        return out

    def changed(self):
        pub = self.load_published()
        return [n for n, p in self.files().items() if pub.get(n, {}).get('sha256') != sha(p)]

    def pdf(self):
        """Print the report to reports\\ in each look and language and wrap each as its report_pdf data file, skipping
        any whose page has not changed. Returns the paths."""
        with open(os.path.join(self.ws.build, 'summary.json'), encoding='utf-8') as f:
            last = json.load(f)['rows'][0]['to']
        paths = []
        for ds, (theme, lang) in PDFS.items():
            wrap = self.pdf_wraps[ds]
            mark = sha_bytes(render(self.ws.build, theme=theme, lang=lang).encode('utf-8'))
            tag = ''.join(f'-{x}' for x in (lang, theme) if x not in ('en', 'dark'))
            name = f'Eleven-vs-AI-Report-{last}{tag}.pdf'
            path = os.path.join(self.reports, name)
            paths.append(path)
            if os.path.exists(wrap) and os.path.exists(path):
                with open(wrap, encoding='utf-8') as f:
                    if json.load(f)['rows'][0].get('mark') == mark:
                        continue
            make_pdf(self.ws.build, path, theme=theme, lang=lang)
            with open(path, 'rb') as f:
                data = f.read()
            row = {'key': 'pdf', 'name': name, 'dataTo': last, 'theme': theme, 'lang': lang, 'bytes': len(data),
                   'mark': mark, 'base64': base64.b64encode(data).decode()}
            meta = [{'label': 'Made by', 'value': 'elevendash printing the dashboard page with headless Chrome (src/elevendash/pdf.py)'}]
            os.makedirs(self.dir, exist_ok=True)
            with open(wrap, 'w', encoding='utf-8') as f:
                json.dump({'rows': [row], 'meta': meta}, f, separators=(',', ':'))
        return paths

    def record(self, pairs):
        pub, old, files = self.load_published(), [], self.files()
        now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        for pair in pairs:
            name, _, blob = pair.partition('=')
            if not re.fullmatch(r'[0-9a-f]{32}', blob) or name not in files:
                sys.exit(f'bad entry: {pair}')
            if pub.get(name, {}).get('blob') not in (None, blob):
                old.append(pub[name]['blob'])
            pub[name] = {'blob': blob, 'sha256': sha(files[name]), 'at': now}
        os.makedirs(self.dir, exist_ok=True)
        with open(self.published, 'w', encoding='utf-8') as f:
            json.dump(pub, f, indent=1)
        print('recorded', len(pairs), 'asset ids')
        print('replaced assets to delete:', ' '.join(old) if old else 'none')
        left = self.changed()
        print('still to upload:', ' '.join(left) if left else 'nothing')


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('command', nargs='?', default='run', choices=['run', 'record'])
    ap.add_argument('pairs', nargs='*', help='for record: dataset=<asset id>')
    ap.add_argument('--dir', help='the workspace (default: ELEVENDASH_HOME, else the current folder)')
    ap.add_argument('--quest', help="the Quest's File Sharing address (default: the one saved in the workspace)")
    ap.add_argument('--offline', action='store_true', help='do not contact the Quest')
    ap.add_argument('--reports', help='where the PDFs go (default: the claude_reports setting in elevendash.json, '
                                      'else reports in the workspace)')
    a = ap.parse_args()
    cli.lower_priority()
    try:
        ws = workspace.find(a.dir)
    except workspace.NotAWorkspace as e:
        sys.exit(str(e))
    c = Claude(ws, a.reports)
    if a.command == 'record':
        return c.record(a.pairs)
    if a.offline:
        print('Offline: using the logs already in the workspace.')
    else:
        try:
            cli.do_fetch(ws, a.quest)
        except fetch.QuestUnreachable as e:
            print(e)
    cli.do_build(ws)
    site = cli.do_site(ws)
    try:
        saved = c.pdf()
    except Exception as e:      # the PDFs are an extra: never let them stop the update
        saved = []
        print(f'PDF not made: {e}')
    print()
    cli.do_report(ws)
    if saved:
        print('\nPDF\n' + '\n'.join(f'  {p} ({os.path.getsize(p) // 1024} KB)' for p in saved))
    print(f'\nSTANDALONE DASHBOARD\n  {site}')
    todo = c.changed()
    print('\nCLAUDE DASHBOARD')
    if todo:
        print(f'  {len(todo)} data file(s) differ from what is published: ' + ' '.join(todo))
        print(f'  Upload from {ws.build} (the report_pdf files from {c.dir})')
    else:
        print('  Nothing to publish: every data file matches what is on the dashboard.')


if __name__ == '__main__':
    main()
