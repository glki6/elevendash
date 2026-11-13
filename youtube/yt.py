"""YouTube uploads for the Eleven pipeline, through Google's official API libraries.

Every video is uploaded UNLISTED. That is the person's standing rule (2026-11-12): there is no switch for it here,
and an upload that does not come back unlisted is reported as a failure.

    yt.py auth                      one-time sign-in in the browser; saves a token on this PC
    yt.py whoami                    which channel the saved token uploads to
    yt.py upload FILE --title T [--description D | --description-file F] [--kind full|highlights|test] [--session S]
    yt.py status VIDEO_ID           how YouTube is getting on with a video (processing, privacy)

Run it with the environment beside it:  youtube\\.venv\\Scripts\\python.exe -I youtube\\yt.py ...

The Google client file and the saved token live outside the project, in %USERPROFILE%\\.eleven-youtube, so they
never travel with the code. videos.json in the workspace is the record of what was uploaded; it holds no secrets.
"""
import argparse
import ctypes
import datetime
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
HOME = os.path.join(os.path.expanduser('~'), '.eleven-youtube')
CLIENT = os.path.join(HOME, 'client_secret.json')
TOKEN = os.path.join(HOME, 'token.json')
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'src'))
from elevendash import workspace      # noqa: E402


def ledger_path():
    """videos.json in the elevendash workspace (the current folder, --dir is not taken here, or ELEVENDASH_HOME)."""
    try:
        return workspace.find().videos
    except workspace.NotAWorkspace as e:
        fail(str(e))


# upload, and read back our own videos to confirm them. Nothing here can edit or delete anything on the channel.
SCOPES = ['https://www.googleapis.com/auth/youtube.upload', 'https://www.googleapis.com/auth/youtube.readonly']
PRIVACY = 'unlisted'
SPORTS = '17'
CHUNK = 32 * 1024 * 1024


def fail(msg, code=1):
    print('ERROR: ' + msg, file=sys.stderr)
    sys.exit(code)


def low_priority():
    """Other jobs run on this PC: uploads take the lowest CPU priority."""
    if os.name == 'nt':
        try:
            k = ctypes.windll.kernel32
            k.SetPriorityClass(k.GetCurrentProcess(), 0x40)      # IDLE_PRIORITY_CLASS
        except Exception:
            pass


def save_token(creds):
    os.makedirs(HOME, exist_ok=True)
    with open(TOKEN, 'w', encoding='utf-8') as f:
        f.write(creds.to_json())


def auth(_args):
    from google_auth_oauthlib.flow import InstalledAppFlow
    if not os.path.exists(CLIENT):
        fail(f'No Google client file at {CLIENT}. Download the OAuth client (type "Desktop app") from the Google Cloud '
             'console as JSON and save it there under that name.')
    flow = InstalledAppFlow.from_client_secrets_file(CLIENT, SCOPES)
    print('Opening the browser for the Google sign-in. Pick the account that owns the YouTube channel and approve.')
    creds = flow.run_local_server(port=0, open_browser=True, access_type='offline', prompt='consent', timeout_seconds=900,
                                  authorization_prompt_message='If no browser opened, visit: {url}',
                                  success_message='Signed in. You can close this tab and go back to Claude.')
    if not creds.refresh_token:
        fail('Google gave no long-lived token. Remove this app at myaccount.google.com/permissions and run auth again.')
    save_token(creds)
    print('Token saved.')
    whoami(None)


def service():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    if not os.path.exists(TOKEN):
        fail('Not signed in yet: run "yt.py auth" first.', 2)
    creds = Credentials.from_authorized_user_file(TOKEN, SCOPES)
    if not creds.valid:
        try:
            creds.refresh(Request())
        except Exception as e:      # revoked, or expired after 7 days because the app is still in "Testing"
            fail(f'The saved sign-in no longer works ({type(e).__name__}). Run "yt.py auth" again. If this happens every '
                 'week, the app is still set to Testing in the Google Cloud console: set it to In production.', 2)
        save_token(creds)
    return build('youtube', 'v3', credentials=creds, cache_discovery=False)


def whoami(_args):
    r = service().channels().list(part='snippet', mine=True).execute()
    items = r.get('items', [])
    if not items:
        fail('The signed-in Google account has no YouTube channel.')
    for c in items:
        print(f"Channel: {c['snippet']['title']}  (https://www.youtube.com/channel/{c['id']})")


def ledger():
    if not os.path.exists(ledger_path()):
        return []
    with open(ledger_path(), encoding='utf-8') as f:
        return json.load(f)


def record(row):
    rows = ledger()
    rows.append(row)
    tmp = ledger_path() + '.tmp'
    with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    os.replace(tmp, ledger_path())


def replace_older(new):
    """A newer upload of the same kind for the same session takes the place of the older ones.

    The older rows stay in videos.json with kind 'replaced', which keeps them off the dashboard. The videos themselves
    stay on YouTube: this program has no right to delete anything there. Returns the rows it changed."""
    rows, old = ledger(), []
    for r in rows:
        if r['id'] != new['id'] and new.get('session') and r.get('kind') == new['kind'] and r.get('session') == new['session']:
            r.update(kind='replaced', was=new['kind'], replaced_by=new['id'])
            old.append(r)
    if old:
        tmp = ledger_path() + '.tmp'
        with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
            json.dump(rows, f, ensure_ascii=False, indent=1)
        os.replace(tmp, ledger_path())
    return old


def read_status(yt, vid):
    r = yt.videos().list(part='status,processingDetails,contentDetails', id=vid).execute()
    items = r.get('items', [])
    return items[0] if items else None


def already(path):
    """The videos.json row for a file uploaded before (same name and size), or None."""
    name, size = os.path.basename(path), os.path.getsize(path)
    return next((r for r in ledger() if r.get('file') == name and r.get('bytes') == size), None)


def check_text(title, desc):
    if len(title) > 100:
        fail('YouTube titles are at most 100 characters.')
    if len(desc.encode('utf-8')) > 5000:
        fail('YouTube descriptions are at most 5,000 bytes.')
    if '<' in title + desc or '>' in title + desc:
        fail('YouTube does not allow < or > in a title or description.')


def upload_file(path, title, desc='', kind='full', session=None, again=False, extra=None):
    """Upload one file as unlisted, record it in videos.json (with any `extra` fields) and return that row."""
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        fail(f'No such file: {path}')
    size = os.path.getsize(path)
    name = os.path.basename(path)
    if not again:
        r = already(path)
        if r:
            fail(f"Already uploaded as {r['url']} on {r['at']}. Pass --again to upload it a second time.", 3)
    check_text(title, desc)
    body = {
        'snippet': {'title': title, 'description': desc, 'categoryId': SPORTS},
        'status': {'privacyStatus': PRIVACY, 'selfDeclaredMadeForKids': False, 'embeddable': True},
    }
    low_priority()
    yt = service()
    media = MediaFileUpload(path, chunksize=CHUNK, resumable=True)
    req = yt.videos().insert(part='snippet,status', body=body, media_body=media, notifySubscribers=False)
    print(f'Uploading {name} ({size / 1e6:,.1f} MB) as {PRIVACY} ...', flush=True)
    resp, tries, last = None, 0, -1
    while resp is None:
        try:
            status, resp = req.next_chunk(num_retries=3)
            tries = 0
            if status:
                pct = int(status.progress() * 100)
                if pct >= last + 5:
                    last = pct
                    print(f'  {pct}%', flush=True)
        except HttpError as e:
            if e.resp.status not in (500, 502, 503, 504):
                fail(f'YouTube refused the upload: HTTP {e.resp.status} {e.reason}')
            tries += 1
        except (OSError, TimeoutError):
            tries += 1
        if tries:
            if tries > 8:
                fail('The upload kept failing; nothing was recorded. Run the same command again to retry.')
            wait = min(120, 2 ** tries)
            print(f'  connection trouble, trying again in {wait}s', flush=True)
            time.sleep(wait)
    vid = resp['id']
    url = f'https://youtu.be/{vid}'
    got = (resp.get('status') or {}).get('privacyStatus')
    seen = read_status(yt, vid)
    if seen:
        got = seen['status'].get('privacyStatus', got)
    row = {'id': vid, 'url': url, 'kind': kind, 'session': session, 'title': title, 'file': name, 'bytes': size,
           'privacy': got, 'at': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}
    row.update(extra or {})
    record(row)
    print(f'Uploaded: {url}')
    print(f'Privacy as YouTube reports it: {got}')
    if got != PRIVACY:
        fail(f'The video is {got}, not {PRIVACY}. It is recorded in videos.json; check it in YouTube Studio.', 4)
    return row


def upload(a):
    desc = a.description or ''
    if a.description_file:
        with open(a.description_file, encoding='utf-8') as f:
            desc = f.read()
    upload_file(a.file, a.title, desc, a.kind, a.session, a.again)


def status(a):
    v = read_status(service(), a.video_id)
    if not v:
        fail('No such video on the signed-in channel.')
    s = v['status']
    print(f"Upload: {s.get('uploadStatus')}   Privacy: {s.get('privacyStatus')}   Made for kids: {s.get('madeForKids')}")
    if s.get('failureReason') or s.get('rejectionReason'):
        print(f"Problem: {s.get('failureReason') or s.get('rejectionReason')}")
    p = v.get('processingDetails') or {}
    if p:
        print(f"Processing: {p.get('processingStatus')}")
    d = (v.get('contentDetails') or {}).get('duration')
    if d:
        print(f'Duration: {d}')


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('auth').set_defaults(fn=auth)
    sub.add_parser('whoami').set_defaults(fn=whoami)
    up = sub.add_parser('upload')
    up.add_argument('file')
    up.add_argument('--title', required=True)
    up.add_argument('--description')
    up.add_argument('--description-file')
    up.add_argument('--kind', choices=['full', 'highlights', 'test'], default='full')
    up.add_argument('--session', help='session key this video belongs to, for the dashboard links')
    up.add_argument('--again', action='store_true', help='upload even if this file is already in videos.json')
    up.set_defaults(fn=upload)
    st = sub.add_parser('status')
    st.add_argument('video_id')
    st.set_defaults(fn=status)
    for out in (sys.stdout, sys.stderr):        # titles carry · and –, which the Windows console code page lacks
        if hasattr(out, 'reconfigure'):
            out.reconfigure(encoding='utf-8', errors='replace')
    a = ap.parse_args()
    a.fn(a)


if __name__ == '__main__':
    main()
