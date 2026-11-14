"""Write one JSON file per store document of the Claude dashboard (a claude.ai Data artifact) for an elevendash
workspace: the filled page, the parameters, the look, and one source per dataset pointing at its uploaded asset.

Usage, from the workspace: python -I <repo>/integrations/claude_dashboard/make_docs.py <out-dir> <utc-iso-now>
Keep <out-dir> between runs (claude/store): writes.json then says which documents changed and need writing.
Asset ids come from claude/published.json, kept by refresh.py record after each upload.
"""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), 'src'))
from elevendash import workspace           # noqa: E402
from elevendash.page import WEB, fill      # noqa: E402

out, now = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
ws = workspace.find()
html = fill()

edit = {'via': 'claude', 'at': now}
upd = {'at': now, 'by': 'Claude'}
PUBLISHED = json.load(open(os.path.join(ws.root, 'claude', 'published.json'), encoding='utf-8'))
TITLES = {
    'summary': ('Win rates by scope',
                'Matches, games and points won over all AI matches, each AI level, the last two sessions, the last day played and online play.'),
    'sessions': ('Every session',
                 'One row per session: matches, games and points won, serve, return and rally rates, and the same rates over all earlier points at that AI level.'),
    'session_notes': ('Session notes',
                      'The written lines of each session report: the result, what moved furthest from your earlier average, and the longest point.'),
    'plan': ('Training plan',
             'One row per thing to practise at the AI level you play now, ranked by the points a match it is worth: your recent number, the target from matches you won, the evidence and a drill.'),
    'plan_trend': ('Training plan by session',
                   'Each plan item\'s number in every session at that level, with how many tries it covers.'),
    'serve_flow': ('Where serve points end',
                   'For each AI level and each kind of serve (side, spin, depth), yours and the AI\'s: the share of points that ended at each stage, from the serve to the later rally.'),
    'serve_types': ('Serve types',
                    'Side, spin and depth together, for the AI\'s serves and yours: how many, speed, the return, the third ball and points won.'),
    'serve_next': ('The shot after the serve',
                   'Your return by pace and by where it lands; the AI\'s return of your serve by pace and by where it lands, with your third ball.'),
    'serve_notes': ('Serve and return notes',
                    'Sentences about serves and returns at each AI level, written by the same code that builds the data.'),
    'replay': ('Point replays',
               'One row per point: every ball contact from the serve on, as kind,x,z,y,t joined by semicolons, in your view (your half is z below 0, +x your right), in cm and thousandths of a second. Kinds: h bat, b table, n net, o anything else (nearly always the floor), x an estimated last stretch. A bat contact adds who (y or a), speed in 0.1 m/s, topspin (+) or backspin (-) in r/s, the shot letter and 1 if it landed. Every logged contact then ends with the velocity of the ball as it arrived (x, y up, z, in 0.1 m/s), and a bat contact with its velocity and its spin (axis times r/s) just after the hit; a triple the log lacks is empty.'),
    'shots': ('Every shot of yours',
              'One row per match, for the shot explorer: every shot you hit and every ball that landed on your half untouched, in s, joined by semicolons. Each is at (game.point), n (place in the point), role (S serve, R return, A rally shot), shot letter (X not reached), 1 if it landed, how it missed (n net, l long, w wide, x not reached, o other, u not known), speed in 0.1 m/s, topspin (+) or backspin (-) in r/s, 1 if it won the point, where you met the ball (x and height, cm), then the ball that came: shot letter, speed in 0.1 m/s and spin off the bat, where it bounced on your half (x, z in cm), thousandths of a second from that bounce to your bat, r or f if it was rising or falling, and its class: spin (t, n, b), side (B backhand, M middle, F forehand), depth (s, h, l) and speed (f fast, s slower).'),
    'shot_groups': ('Where your misses pile up',
                    'At the level of the training plan, the kinds of ball you miss or do not reach more often than usual: returns by the serve (side, spin, depth) and rally shots by the ball that came (spin, side, fast or slower). One row per kind and period (recent sessions, or all matches at the level), with its balls, how many failed and how (net, long, wide, not reached), your usual rate for that kind of shot, and the points a match it costs beyond that rate. At most eight per period, each with 30 balls or more.'),
    'form': ('Rolling results',
             'One row per AI match, in order at its level (i). For the last 10, 20 and 50 matches at that level up to it: the share of matches won (m10, m20, m50) and of points won (p10, p20, p50), each with the range the true share sits in 9 times in 10 (lo, hi). Empty until the level has that many matches.'),
    'session_shape': ('From the first match of a session to the last',
                      'One row per place in a session (match 1, match 2, matches 3 to 5 and so on): the points won there, the rate of the other matches of the same session and level (rest), the gap in percentage points with the range chance allows 9 times in 10 (lo, hi), and move (1 clearly better, -1 clearly worse, 0 within chance). Sessions with three or more matches at one level.'),
    'form_notes': ('Warm-up and tiring',
                   'One or two sentences written by fixed rules from session_shape: how your first match of a session compares with the rest of it, and how the matches from the eleventh on compare with the first ten.'),
    'findings': ('What decides your points',
                 'Your main level (the AI level with the most points in your last five sessions) and up to six findings there, each a headline, a sentence and two bars, written by fixed rules from the numbers.'),
    'days': ('Daily results against the AI',
             'One row per day: AI level, matches, games and points won, and serve, return and rally rates.'),
    'levels': ('11hero metrics by AI level',
               'Every 11hero match metric for you and the AI, over all points at each AI level.'),
    'insights': ('How points end, by AI level',
                 'How points were won and lost, points won by length of point, and results by serve spin, per AI level.'),
    'zones': ('Serve landing zones',
              'Points you won by where each serve first landed, seen from your end, per AI level.'),
    'won_vs_lost': ('Matches won vs lost',
                    'Your serve, return and rally numbers in matches you won and in matches you lost, per AI level.'),
    'matches': ('Every match',
                'One row per match: result, game scores and 11hero metrics for you and your opponent.'),
    'match_sums': ('Match totals',
                   'One row per match, in the same order as Every match: the counts and sums behind its rates (points, serves, returns, rally shots, how points ended) and behind each 11hero metric for you (you_) and your opponent (ai_), so the page can work out the numbers over any matches picked.'),
    'shot_mix': ('Rally shots by type',
                 'Shots, landing rate, speed, spin and winners by shot type, per match and per AI level.'),
    'serves': ('Every serve',
               'Speed, spin, where it first landed and who won the point, for each serve.'),
    'points': ('Every point',
               'Score before the point, server, number of shots and how the point ended.'),
    'videos': ('Session videos',
               'One row per YouTube upload (always unlisted): the full recording of a session and the session it belongs to.'),
    'report_pdf': ('This report as a PDF',
                   'One row holding the PDF that the Save as PDF button hands over in the dark look and English: the report as it stood at the last update.'),
    'report_pdf_light': ('This report as a PDF, light',
                         'The same PDF in the light look, in English.'),
    'report_pdf_zh': ('This report as a PDF, Chinese',
                      'The same PDF in Traditional Chinese, in the dark look.'),
    'report_pdf_zh_light': ('This report as a PDF, Chinese, light',
                            'The same PDF in Traditional Chinese, in the light look.'),
}
missing = [ds for ds in TITLES if ds not in PUBLISHED]
assert not missing, f'upload these first, then run refresh.py record: {missing}'
BLOBS = {ds: (PUBLISHED[ds]['blob'], t, d) for ds, (t, d) in TITLES.items()}
writes = []


MAX_DOC = 262144      # bytes: the most one store document (and one page file) may hold


def body(d):
    return {k: v for k, v in d.items() if k not in ('edit', 'updated')}


def split_scripts(page):
    """The page with each of its scripts moved to a file of its own (page-01.js, ...), which the host loads from the
    files collection in place of the <script src> tag, so index.html keeps under MAX_DOC. Each runs as before: in order,
    one at a time, and a fault in one stops only that one."""
    scripts = {}

    def take(m):
        name = f'page-{len(scripts) + 1:02d}.js'
        scripts[name] = m.group(1)
        return f'<script src="{name}"></script>'
    return re.sub(r'<script>(.*?)</script>', take, page, flags=re.S), scripts


def doc(collection, doc_id, data):
    """Write one store document. `changed` is False when it matches the file left by the previous run, timestamps aside."""
    size = len(json.dumps(data, ensure_ascii=False).encode())
    assert size <= MAX_DOC, f'{collection}/{doc_id} is {size} bytes; a store document holds {MAX_DOC} at most'
    path = os.path.join(out, f'{collection.replace("/", "_")}__{doc_id}.json')
    old = json.load(open(path, encoding='utf-8')) if os.path.exists(path) else None
    changed = old is None or body(old) != body(data)
    if changed:
        json.dump(data, open(path, 'w', encoding='utf-8'), ensure_ascii=False)
    writes.append({'op': 'set', 'collection': collection, 'doc_id': doc_id, 'file_path': path, 'changed': changed})


doc('dash', 'meta', {'title': 'Eleven vs AI Report'})
find_rows = json.load(open(os.path.join(ws.build, 'findings.json'), encoding='utf-8'))['rows']
main = next((r for r in find_rows if r['key'] == 'main'), None)
doc('dash', 'params', {'level': main['level'] if main else 100, 'match': '', 'session': '', 'pick': '', 'theme': 'dark', 'lang': 'en'})
for ds, (blob, title, desc) in BLOBS.items():
    doc('datasets', ds, {'title': title, 'description': desc + ' Made from the Quest game logs by elevendash (src/elevendash/builddata.py).',
                         'source': {'kind': 'file', 'url': f'/_blob/{blob}', 'name': f'{ds}.json', 'format': 'json'},
                         'updated': upd, 'fixed': True, 'edit': edit})
page, scripts = split_scripts(html)
doc('files', 'index.html', {'text': page, 'edit': edit})
for name, text in scripts.items():
    doc('files', name, {'text': text, 'edit': edit})
for fn in sorted(os.listdir(out)):     # script files an earlier, longer page had
    if fn.startswith('files__page-') and fn.endswith('.js.json') and fn[len('files__'):-len('.json')] not in scripts:
        writes.append({'op': 'delete', 'collection': 'files', 'doc_id': fn[len('files__'):-len('.json')],
                       'file_path': os.path.join(out, fn), 'changed': True})
# The look (colours for light and dark) is the same file the standalone dashboard uses.
doc('dash', 'look', json.load(open(os.path.join(WEB, 'look.json'), encoding='utf-8')))
json.dump(writes, open(os.path.join(out, 'writes.json'), 'w'), indent=1)
print(len(writes), 'docs; page', len(page.encode()) // 1024, 'KB and', len(scripts), 'script files', sum(len(t.encode()) for t in scripts.values()) // 1024, 'KB')
print('changed:', ' '.join(f"{w['collection']}/{w['doc_id']}" for w in writes if w['changed'] and w['op'] == 'set') or 'none')
gone = [f"{w['collection']}/{w['doc_id']}" for w in writes if w['op'] == 'delete']
if gone:
    print('delete:', ' '.join(gone), '(then remove their files from', out + ')')
