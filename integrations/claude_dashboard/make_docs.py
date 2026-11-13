"""Write one JSON file per store document of the Claude dashboard (a claude.ai Data artifact) for an elevendash
workspace: the filled page, the parameters, the look, and one source per dataset pointing at its uploaded asset.

Usage, from the workspace: python -I <repo>/integrations/claude_dashboard/make_docs.py <out-dir> <utc-iso-now>
Keep <out-dir> between runs (claude/store): writes.json then says which documents changed and need writing.
Asset ids come from claude/published.json, kept by refresh.py record after each upload.
"""
import json, os, sys

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
               'One row per point: every ball contact from the serve on, as kind,x,z,y,t joined by semicolons, in your view (your half is z below 0, +x your right), in cm and hundredths of a second. Kinds: h bat, b table, n net, o anything else (nearly always the floor), x an estimated last stretch. A bat contact adds who (y or a), speed in 0.1 m/s, topspin (+) or backspin (-) in r/s, the shot letter and 1 if it landed.'),
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


def body(d):
    return {k: v for k, v in d.items() if k not in ('edit', 'updated')}


def doc(collection, doc_id, data):
    """Write one store document. `changed` is False when it matches the file left by the previous run, timestamps aside."""
    path = os.path.join(out, f'{collection.replace("/", "_")}__{doc_id}.json')
    old = json.load(open(path, encoding='utf-8')) if os.path.exists(path) else None
    changed = old is None or body(old) != body(data)
    if changed:
        json.dump(data, open(path, 'w', encoding='utf-8'), ensure_ascii=False)
    writes.append({'op': 'set', 'collection': collection, 'doc_id': doc_id, 'file_path': path, 'changed': changed})


doc('dash', 'meta', {'title': 'Eleven vs AI Report'})
find_rows = json.load(open(os.path.join(ws.build, 'findings.json'), encoding='utf-8'))['rows']
main = next((r for r in find_rows if r['key'] == 'main'), None)
doc('dash', 'params', {'level': main['level'] if main else 100, 'match': '', 'session': '', 'theme': 'dark', 'lang': 'en'})
for ds, (blob, title, desc) in BLOBS.items():
    doc('datasets', ds, {'title': title, 'description': desc + ' Made from the Quest game logs by elevendash (src/elevendash/builddata.py).',
                         'source': {'kind': 'file', 'url': f'/_blob/{blob}', 'name': f'{ds}.json', 'format': 'json'},
                         'updated': upd, 'fixed': True, 'edit': edit})
doc('files', 'index.html', {'text': html, 'edit': edit})
# The look (colours for light and dark) is the same file the standalone dashboard uses.
doc('dash', 'look', json.load(open(os.path.join(WEB, 'look.json'), encoding='utf-8')))
json.dump(writes, open(os.path.join(out, 'writes.json'), 'w'), indent=1)
print(len(writes), 'docs; page', len(html.encode()) // 1024, 'KB')
print('changed:', ' '.join(f"{w['collection']}/{w['doc_id']}" for w in writes if w['changed']) or 'none')
