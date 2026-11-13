"""Print the dashboard to a PDF with a Chromium-based browser (Chrome, Edge or Chromium), headless and with a
throwaway profile, so it never touches the profile you browse with.

The PDF shows the page as it opens (your main level, the last session, the last match) with every section expanded,
dark or light and in English or Chinese as asked.
"""
import os
import pathlib
import shutil
import subprocess
import tempfile

from .site import build_site

CANDIDATES = [
    r'C:\Program Files\Google\Chrome\Application\chrome.exe',
    r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
    r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
    r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
]
NAMES = ['google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser', 'microsoft-edge', 'msedge', 'chrome']


def find_browser():
    env = os.environ.get('ELEVENDASH_CHROME')
    if env and os.path.exists(env):
        return env
    for c in CANDIDATES:
        if os.path.exists(c):
            return c
    for n in NAMES:
        p = shutil.which(n)
        if p:
            return p
    return None


def make_pdf(build_dir, out_pdf, videos=True, theme='dark', lang='en'):
    browser = find_browser()
    if not browser:
        raise RuntimeError('no Chrome, Edge or Chromium found to print the PDF (set ELEVENDASH_CHROME to its path)')
    work = tempfile.mkdtemp(prefix='elevendash-pdf-')
    try:
        page = build_site(build_dir, os.path.join(work, 'index.html'), videos=videos, theme=theme, lang=lang)
        tmp_pdf = os.path.join(work, 'report.pdf')
        url = pathlib.Path(page).as_uri() + '?pdf=1'
        subprocess.run([browser, '--headless=new', '--disable-gpu', '--no-first-run', '--disable-extensions',
                        '--user-data-dir=' + os.path.join(work, 'profile'), '--window-size=1040,1471',
                        '--virtual-time-budget=8000', '--no-pdf-header-footer', '--print-to-pdf=' + tmp_pdf, url],
                       check=True, timeout=240, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if not os.path.exists(tmp_pdf) or os.path.getsize(tmp_pdf) < 20000:
            raise RuntimeError('the browser wrote no usable PDF')
        os.makedirs(os.path.dirname(os.path.abspath(out_pdf)), exist_ok=True)
        shutil.copyfile(tmp_pdf, out_pdf)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return out_pdf
