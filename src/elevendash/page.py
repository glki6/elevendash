"""Fill the dashboard page template: the metric tables are written out here so the template stays readable.

The filled page is plain HTML with `data-draw` elements and scripts that ask a host object, `dash`, for data and
parameters. site.py supplies that host for the standalone file; a hosted dashboard can supply its own.
"""
import json
import os

from .i18n import bilingual, script_words
from .metrics import SUMS

WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'web')
THEMES = ('dark', 'light')       # the page opens dark; its switch changes to light
LANGS = ('en', 'zh')             # English, and Traditional Chinese (i18n.py)


def look():
    with open(os.path.join(WEB, 'look.json'), encoding='utf-8') as f:
        return json.load(f)


def color_tokens(t):
    """The host's colour tokens for one theme of the look (look.json's light or dark)."""
    v = {'--color-bg': t['ground'], '--color-panel': t['card'], '--color-fg': t['text'], '--color-fg-muted': t['muted'],
         '--color-border-line': t['border'], '--color-ok': t['good'], '--color-warn': t['warning'], '--color-bad': t['bad']}
    v.update({f'--chart-{i}': c for i, c in enumerate(t['charts'])})
    return v


# Tokens a host works out from the colours. They are declared again with the page's own theme, since a custom property
# that refers to another is worked out where it is declared.
DERIVED = ('--cds-chart-muted:var(--color-fg-muted);--cds-chart-grid:color-mix(in oklab,var(--color-fg) 9%,var(--color-panel));'
           '--cds-chart-axis:color-mix(in oklab,var(--color-fg) 24%,var(--color-panel));--cds-chart-reference:var(--color-fg-muted);'
           '--cds-text-secondary:var(--color-fg-muted);--cds-surface-popover:var(--color-panel);--cds-border:var(--color-border-line)')


def theme_css():
    """The page's own light and dark looks, on its outer element, so it shows the theme its switch picked whatever the
    host's theme is."""
    lk = look()
    out = []
    for name in THEMES:
        v = ';'.join(f'{k}:{x}' for k, x in color_tokens(lk[name]).items())
        shadow = '0 4px 14px rgba(0,0,0,.45)' if name == 'dark' else '0 4px 14px rgba(0,0,0,.18)'
        out.append(f'.er-page.er-{name}{{{v};{DERIVED};--cds-shadow-popover:{shadow};color-scheme:{name}}}')
    return '\n'.join(out)

GROUPS = [
    ('Speed and spin', [
        ('serveSpeed', 'Average serve speed (m/s)', 'n1'), ('serveTop', 'Average serve topspin (r/s)', 'n1'),
        ('serveBack', 'Average serve backspin (r/s)', 'n1'), ('rallySpeed', 'Average rally speed (m/s)', 'n1'),
        ('rallyTop', 'Average rally topspin (r/s)', 'n1'), ('rallyBack', 'Average rally backspin (r/s)', 'n1')]),
    ('Landing the ball', [
        ('serveSuccess', 'Serves that landed', 'pct'), ('returnSuccess', 'Returns that landed', 'pct'),
        ('openUpAttempt', 'Open-up attempts (share of rally shots)', 'pct'), ('openUpSuccess', 'Open-ups that landed', 'pct')]),
    ('Winning points', [
        ('wonAsServer', 'Points won as server', 'pct'), ('wonAsReturner', 'Points won as returner', 'pct'),
        ('serveScore', 'Serve score rate: the serve was the last shot in a point won', 'pct'), ('returnScore', 'Return score rate: the return was the last shot in a point won', 'pct'),
        ('thirdBallScore', 'Third-ball score rate: the third ball was the last shot in a point won', 'pct')]),
    ('Share of points won, by the winning shot', [
        ('wonByServe', 'Serve', 'pct'), ('wonByReturn', 'Return', 'pct'), ('wonByThird', 'Third ball', 'pct'),
        ('wonByFourth', 'Fourth ball', 'pct'), ('wonByLater', 'Later shot', 'pct'),
        ('wonByOppServiceError', "Opponent's service fault", 'pct')]),
]

WVL = [('matches', 'Matches', 'int'), ('pointRate', 'Points won', 'pct'), ('servePointRate', 'Points won on your serve', 'pct'),
       ('returnPointRate', "Points won on the AI's serve", 'pct'), ('servesLanded', 'Serves that landed', 'pct'),
       ('returnsLanded', 'Returns that landed', 'pct'), ('rallyLanded', 'Rally shots that landed', 'pct'),
       ('rallySpeed', 'Rally speed (m/s)', 'n1'), ('rallyLength', 'Shots per point', 'n1')]


def td(ds, k, f, fmt):
    if ds == 'pick':        # worked out on the page from the matches picked (the pv drawing)
        return f'<td data-draw="pv" data-source="match_sums" data-f="{f}" data-fmt="{fmt}"></td>'
    return f'<td data-draw="v" data-ds="{ds}" data-k="{k}" data-f="{f}" data-fmt="{fmt}"></td>'


def metric_rows(cols):
    """One small table per metric group; cols is [(column heading, dataset, key template, field prefix)].
    Dataset 'pick' is the matches picked: prefix you_ or ai_ for the two players, ref_ for your other matches."""
    out = []
    for title, rows in GROUPS:
        head = ''.join(f'<th>{h}</th>' for h, _, _, _ in cols)
        lines = [f'      <div class="er-tablewrap"><table class="er-t"><thead><tr><th>{title}</th>{head}</tr></thead><tbody>']
        for key, label, fmt in rows:
            cells = ''.join(td(ds, k, pre + key, fmt) for _, ds, k, pre in cols)
            lines.append(f'        <tr><th>{label}</th>{cells}</tr>')
        lines.append('      </tbody></table></div>')
        out.append('\n'.join(lines))
    return '\n'.join(out)


def fill(collect=None, strict=False):
    """The page as HTML: the template with its tables written in, and every sentence in English and Chinese.
    collect, a set, gathers the English sentences (for the word list check); strict fails on one without Chinese."""
    with open(os.path.join(WEB, 'index.template.html'), encoding='utf-8') as f:
        html = f.read()
    html = html.replace('{{I18N_SCRIPT}}', script_words())
    html = html.replace('{{METRIC_SUMS}}', json.dumps(SUMS, separators=(',', ':')))
    wvl = '\n'.join(f'      <tr><th>{label}</th>{td("won_vs_lost", "{L}|Won", f, fmt)}{td("won_vs_lost", "{L}|Lost", f, fmt)}</tr>'
                    for f, label, fmt in WVL)
    html = html.replace('{{WVL_ROWS}}', wvl)
    html = html.replace('{{THEME_CSS}}', theme_css())
    html = html.replace('{{METRICS_LEVEL}}', metric_rows([('You', 'levels', '{L}', 'you_'), ('AI', 'levels', '{L}', 'ai_')]))
    # the match's other side: the AI, or a player online (the shown word follows the match picked)
    them = ''.join(f'<span data-showif data-ds="matches" data-k="{{M}}" data-f="vs" data-eq="{eq}"{" hidden" if eq != "AI" else ""}>{w}</span>'
                   for eq, w in (('AI', 'AI'), ('Online', 'Opponent')))
    html = html.replace('{{METRICS_MATCH}}', metric_rows([('You', 'matches', '{M}', 'you_'), (them, 'matches', '{M}', 'ai_'),
                                                          ('Level avg', 'levels', '{ML}', 'you_')]))
    html = html.replace('{{METRICS_PICK}}', metric_rows([('You', 'pick', '', 'you_'), ('AI', 'pick', '', 'ai_'),
                                                         ('Your other matches', 'pick', '', 'ref_')]))
    assert '{{' not in html, 'unfilled placeholder in the page template'
    html, _ = bilingual(html, collect, strict)
    return html
