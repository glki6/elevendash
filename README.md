# elevendash

Match analysis for **Eleven Table Tennis** on Meta Quest, from the game's own log files. It copies the logs off your
headset over Wi-Fi, works out every match, game, point and shot, and writes a dashboard you can open in any browser:
win rates by session and AI level, a session report, a point-by-point replay of every match drawn from the ball
contacts, serve and return breakdowns, and a training plan ranked by how many points each item is worth.

No account, no server, no AI service: everything runs on your computer with plain Python, and the dashboard is a
single HTML file that works offline. Send it to a coach or a friend, or put it on any static host.

> elevendash is an independent project, not affiliated with or endorsed by For Fun Labs, Meta or 11hero. Its match
> metrics follow [11hero](https://11hero.com)'s definitions and were checked against it on a real match
> (see `research/CALIBRATION.md`).

## Try it without a Quest

```
pip install -e .                  (see Install below)
elevendash demo
```

This writes `elevendash-demo/`: four sessions of made-up matches against the AI, built into a dashboard at
`elevendash-demo/site/index.html`. The logs are generated (`src/elevendash/sample.py`) and hold no account data.
The same demo is online at https://glki6.github.io/elevendash/demo/.

## Made for matches against the AI

Against the AI, the game logs every ball contact by both players, so everything on the dashboard works: the replay,
rally and serve analysis, the 11hero metrics for both sides and the training plan. Online matches against people are
counted (who won, the scores), but for those the game logs only your own shots, so the shot-level analysis is
one-sided there. So far elevendash has seen just one online match; its metrics for your own shots matched 11hero's
exactly, and the rest of the online side is largely untested.

## Privacy first

Eleven's log files contain your **Eleven and Meta account tokens**, your platform user id and name, the names of people
you played online, and sometimes your location. elevendash keeps the logs in your workspace and never sends them
anywhere. The dashboard file holds match data only, never logs or tokens.

**Never share your `logs` folder or a raw log.** If you need to show one (for a bug report), make a redacted copy and
read it before you share it:

```
elevendash redact logs/ALL-01.05.2026.6.30.00.PM.log redacted.log
```

The only network requests elevendash makes are two read-only calls to your own Quest on your own network
(`/getListing` and `/downloadFile`). It never uploads to the headset or deletes anything there. See `SECURITY.md`.

## Install

Python 3.10 or newer. No other packages are needed for the dashboard.

```
git clone https://github.com/glki6/elevendash.git
cd elevendash
python -m venv .venv
.venv\Scripts\activate            (Windows)     or     source .venv/bin/activate     (macOS, Linux)
pip install -e .
```

## Use

```
elevendash init ~/eleven                      a private folder for your logs and results
cd ~/eleven
elevendash fetch --quest 192.168.1.20         the address Eleven shows under File Sharing (remembered after this)
elevendash update                             fetch, build, print the session report, write the dashboard
```

Then open `site/index.html`. After every session, `elevendash update` again.

To get the logs over Wi-Fi: in Eleven open **Settings > Network Settings > File Sharing** and start it; it shows an
address such as `192.168.1.20:8090`. The computer must be on the same network. The headset keeps only its most recent
launches, so fetch after each session; elevendash keeps a copy of every log it has seen.

No Wi-Fi sharing? Copy the `ALL-*.log` files off the headset any other way (USB cable, a file manager) and run
`elevendash import <folder>`.

| Command | What it does |
|---|---|
| `elevendash init [DIR] [--quest HOST]` | Make a workspace |
| `elevendash fetch [--quest HOST]` | Copy new logs from the Quest |
| `elevendash import PATH ...` | Copy logs from files or folders |
| `elevendash build` | Turn the logs into match data (`build/`, one JSON file per dataset) |
| `elevendash report` | Print the last session: results, notes, session and all-time win rates |
| `elevendash site [--out FILE] [--no-videos] [--theme dark\|light] [--lang en\|zh]` | Write the dashboard (`site/index.html`) |
| `elevendash pdf [--out FILE] [--theme dark\|light] [--lang en\|zh]` | Print the dashboard to a PDF (needs Chrome, Edge or Chromium) |
| `elevendash update [--offline]` | fetch + build + report + site |
| `elevendash config [hand=auto\|right\|left] [theme=dark\|light] [lang=en\|zh]` | Show or change the workspace settings |
| `elevendash demo [DIR]` | A workspace of made-up matches and its dashboard |
| `elevendash redact LOG OUT` | A copy of a log without account, people or location data |

Add `--nice` to any command to run it at the lowest CPU priority. Commands use the workspace in the current folder,
or `--dir`, or `ELEVENDASH_HOME`.

## Sharing the dashboard

`site/index.html` is self-contained (about 10 MB for a few hundred matches): send it as a file, or upload it to any
static host (GitHub Pages, Netlify, Cloudflare Pages). A view's level, session and match are kept in the address after
`#`, so a link can open a particular match. In the browser, Save as PDF prints it.

If you upload session videos (below), the dashboard links to them. `--no-videos` leaves those links out.

The dashboard opens dark and in English; switches at the top change the look (dark or light) and the language
(English or Traditional Chinese), and the address remembers the choice. `?theme=light` or `?lang=zh` on the file's
address, or `elevendash config theme=light lang=zh`, changes what it opens with. The PDF follows the same settings.

## Optional: session videos on YouTube

`youtube/` uploads a session's headset recording and an automatic highlight reel to your own YouTube channel, always
as unlisted, and lines the recording up with the log by the sound of the ball, so every point on the dashboard gets a
"watch" link. It needs `pip install -e ".[youtube]"`, ffmpeg on the PATH, and your own Google Cloud OAuth client
(Desktop app, YouTube Data API v3). See the top of `youtube/yt.py`. The reel's captions use a Windows font for now.

## How it works

| Path | What it is |
|---|---|
| `src/elevendash/extract.py` | Log to matches, games, points, ball contacts (bat, table, net, floor) |
| `src/elevendash/metrics.py` | Per-player match metrics with 11hero's definitions |
| `src/elevendash/builddata.py` | All dashboard datasets, including the written session notes and the training plan, by fixed rules |
| `src/elevendash/web/` | The dashboard page (`index.template.html`), its small runtime, look and the d3 chart library |
| `src/elevendash/i18n.py`, `web/zh-Hant.json` | The two languages: the page's text, chart labels and written notes, keyed by the English |
| `src/elevendash/site.py`, `pdf.py` | The single-file dashboard and its PDF |
| `src/elevendash/fetch.py`, `cli.py`, `workspace.py` | Getting logs, the command line, where your data lives |
| `src/elevendash/sample.py`, `redact.py` | Generated logs for the demo and tests; redacted copies of real logs |
| `tests/` | `python -m unittest discover -s tests` |
| `youtube/` | Optional video uploads and highlight reels |
| `integrations/claude_dashboard/` | Keeps a hosted copy of the dashboard on claude.ai in step with a workspace (optional) |
| `research/` | Calibration against 11hero |
| `tools/fxtest/` | Scroll tests in a private headless Firefox |

Coordinates are your view: your half of the table is z < 0 and +x is your right. Which side is your backhand comes
from the paddle hand the game records in the log (`elevendash config hand=left` or `hand=right` overrides it).

To change a Chinese wording, edit `web/zh-Hant.json`. After changing any English text, run
`python -I -c "import sys; sys.path.insert(0, 'src'); from elevendash import i18n; i18n.check()"` from the repository:
it lists text with no Chinese yet, entries nothing uses any more, and placeholders that do not match.

## Status

Early, and so far tested on one player's logs (Quest 3S, AI levels 75 to 100, a few hundred matches), plus generated
logs. The dashboard opens on your main level (the AI level with the most points in your last five sessions), and its
findings are written from your numbers by fixed rules in `builddata.py`. Online play: see "Made for matches against
the AI" above. Left-handed play is handled but has only been tested by forcing `hand=left` on right-handed logs. Logs
from other headsets, game versions and online matches are welcome (redacted): see `CONTRIBUTING.md`.

## Licence

MIT, see `LICENSE`. The bundled D3 chart library is under the ISC licence; see `THIRD_PARTY_NOTICES.md`.
