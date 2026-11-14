# elevendash

Match analysis for **Eleven Table Tennis** on Meta Quest, from the game's own log files.

[![The top of the dashboard: matches won and lost at your main AI level and over every AI match, then the report on the last session.](pages/img/overview.png)](https://glki6.github.io/elevendash/demo/)

*The pictures on this page are of the [demo](https://glki6.github.io/elevendash/demo/), built from made-up matches.*

It copies the logs off your
headset over Wi-Fi, works out every match, game, point and shot, and writes a dashboard you can open in any browser:
win rates by session and AI level, a session report, a point-by-point replay of every match drawn from the ball
contacts (from above, or in 3D with a slow-motion replay of the shot that decided the point and its spin), serve and return breakdowns, a shot explorer that finds any of your shots by the ball that came at you and lists the kinds of ball you miss most and shows how your misses differ from the shots you land, rolling win rates with the range chance allows and how you play from the first match of a session to the last, your numbers over any matches you pick set against your other matches, a
picture of any match to send or post, your own notes on any match, and a training plan ranked by how many points each
item is worth.

No account, no server, no AI service: everything runs on your computer with plain Python, and the dashboard is a
single HTML file that works offline. Send it to a coach or a friend, or put it on any static host. Notes you write on
matches are kept in the browser you wrote them in, never in the file, so they stay behind when you send it.

elevendash is built for matches against the AI. Matches against people online have a side of their own, with
ratings: it should work, but it is close to untested on real matches
(see [Against the AI, and against people online](#against-the-ai-and-against-people-online)).

> elevendash is inspired by [11hero](https://11hero.com). Its match metrics follow 11hero's definitions and were
> checked against it on a real match (see `research/CALIBRATION.md`). It is an independent project, not affiliated
> with or endorsed by For Fun Labs, Meta or 11hero.

## What it looks like

### Session report

![A session of eight matches: five won and three lost, written notes, a chip for every match, and each number set against the average before it.](pages/img/session.png)

Written from the logs after every session: what you won, what changed, and each number against your average at the same AI level before it.

### Point by point

![A table seen from above with the paths of a 16-shot rally, bars for every point of two games, and a shot list with type, speed and spin.](pages/img/replay.png)

Every point of a match as a bar. Click one to play it back from the ball contacts, with the type, speed and spin of each shot.

### 3D replay

![The table drawn in 3D with the ball in flight over the net, its path so far, and a ball in the corner turning with the spin of the shot.](pages/img/replay-3d.png)

The same point in 3D, with the spin of the ball shown in the corner. "Deciding shot" replays the last shot in slow motion with the camera following the ball.

### Match card

![A card for one match: the result, a bar for every point, six numbers, how the points ended and you against the AI.](pages/img/card.png)

A picture of any match to send or post. It has no names, links or videos in it.

### Training plan

![Training plan items, each with a drill, what it is worth in points a match, and a chart of the number against its target.](pages/img/plan.png)

What to practise next, ranked by how many points a match each item is worth, with a drill, a target taken from the matches you won, and the trend.

### Shot explorer

![A ranked list of the kinds of ball missed most, each with a bar for the miss rate against the usual rate.](pages/img/shots.png)

The kinds of ball you miss most, each one click away from its replays, and a filter that finds any shot by the ball that came at you.

### Form and stamina

![A line of matches won over the last 10 matches, with a band for the range chance allows.](pages/img/form.png)

Rolling win rates with the range chance allows, so a lucky week does not look like progress, and how you play from the first match of a session to the last.

### Serves and returns

![Points won by the side the serve comes to and by the length of the return, then a bar for each kind of serve showing how its points ended.](pages/img/serves.png)

Where points on each serve end: by the side, spin and depth of the serve, for the AI's serves and your own.

### Online matches and ratings

![A line of your rating after each online match with a dot for every opponent's rating, three written notes, and a table of results against lower, equal and higher rated opponents.](pages/img/online.png)

A switch at the top turns the whole dashboard from your matches against the AI to your matches against people online. The online side adds your rating match by match, and your results set against what the ratings alone expect.

## Try it without a Quest

```
pip install -e .                  (see Install below)
elevendash demo
```

This writes `elevendash-demo/`: seven sessions of made-up matches, four against the AI and three online, built into a dashboard at
`elevendash-demo/site/index.html`. The logs are generated (`src/elevendash/sample.py`) and hold no account data.
The same demo is online at https://glki6.github.io/elevendash/demo/.

## Against the AI, and against people online

elevendash is built for matches against the AI, and nearly all of its testing is on them. Against the AI, the game
logs every ball contact by both players, so everything on the dashboard works: the replay, rally and serve analysis,
the 11hero metrics for both sides, the match card and the training plan.

Matches against people online are the dashboard's second side. A switch at the top of the page turns all of it from
your AI matches to your online ones: the same session report, training plan, shot explorer and breakdowns, added up
over your online matches and worded for an opponent. The two sides are added up apart, so neither changes the other's
totals. The log holds your own shots as ball contacts and your opponent's as the messages their game sends. It also
holds both players' ratings as each match starts and what a ranked match is worth, so the online side adds your rating
match by match and your results against lower, equal and higher rated opponents, set against what the ratings alone
expect. No opponent's name appears anywhere.

The online side should work, but treat it as untested. It is built and checked on generated matches, and on one real
online match, where every hit of both players and their metrics matched 11hero's. One match cannot show what a
season of online play looks like, so expect rough edges, and please report them (see `CONTRIBUTING.md`). The misses
reel and the session videos are still made for sessions against the AI only.

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

`site/index.html` is self-contained (about 5 MB for a few hundred matches; the data in it is compressed, and a browser
from 2023 or later unpacks it as it opens): send it as a file, or upload it to any
static host (GitHub Pages, Netlify, Cloudflare Pages). A view's level, session and match are kept in the address after
`#`, so a link can open a particular match. In the browser, Save as PDF prints it.

If you upload session videos (below), the dashboard links to them. `--no-videos` leaves those links out.

The dashboard opens dark and in English; switches at the top change the look (dark or light) and the language
(English or Traditional Chinese), and the address remembers the choice. `?theme=light` or `?lang=zh` on the file's
address, or `elevendash config theme=light lang=zh`, changes what it opens with. The PDF follows the same settings.

## Optional: session videos on YouTube

`youtube/` uploads a session's headset recording, an automatic highlight reel and a reel of the balls you missed most
(a few of the misses, then the same ball landed) to your own YouTube channel, always as unlisted, and lines the
recording up with the log by the sound of the ball, so every point on the dashboard gets a "watch" link. It needs `pip install -e ".[youtube]"`, ffmpeg on the PATH, and your own Google Cloud OAuth client
(Desktop app, YouTube Data API v3). See the top of `youtube/yt.py`. The reel's captions use a Windows font for now.

## How it works

| Path | What it is |
|---|---|
| `src/elevendash/extract.py` | Log to matches, games, points, ball contacts (bat, table, net, floor) |
| `src/elevendash/health.py` | Warns after a build when a log does not read as expected, as after a game update that changes the log format |
| `src/elevendash/metrics.py` | Per-player match metrics with 11hero's definitions |
| `src/elevendash/builddata.py` | All dashboard datasets, including the written session notes and the training plan, by fixed rules |
| `src/elevendash/web/` | The dashboard page (`index.template.html`), its small runtime, look and the d3 chart library |
| `src/elevendash/i18n.py`, `web/zh-Hant.json` | The two languages: the page's text, chart labels and written notes, keyed by the English |
| `src/elevendash/voice.py` | The wording for matches against people: every sentence that names the AI or an AI level, reworded by rule |
| `src/elevendash/site.py`, `pdf.py` | The single-file dashboard and its PDF |
| `src/elevendash/fetch.py`, `cli.py`, `workspace.py` | Getting logs, the command line, where your data lives |
| `src/elevendash/sample.py`, `redact.py` | Generated logs for the demo and tests; redacted copies of real logs |
| `tests/` | `python -m unittest discover -s tests` |
| `youtube/` | Optional video uploads and highlight reels |
| `integrations/claude_dashboard/` | Keeps a hosted copy of the dashboard on claude.ai in step with a workspace (optional) |
| `research/` | Calibration against 11hero |
| `tools/pagetest/` | Opens a built dashboard in headless Chrome and Firefox and checks that it works: `python tools/pagetest/run.py site/index.html` |
| `tools/prepush/`, `tools/hooks/` | A check, run by git before every push, that nothing private from your workspace is about to be published |
| `tools/fxtest/` | Scroll tests in a private headless Firefox |

Coordinates are your view: your half of the table is z < 0 and +x is your right. Which side is your backhand comes
from the paddle hand the game records in the log (`elevendash config hand=left` or `hand=right` overrides it).

To change a Chinese wording, edit `web/zh-Hant.json`. After changing any English text, run
`python -I -c "import sys; sys.path.insert(0, 'src'); from elevendash import i18n; i18n.check()"` from the repository:
it lists text with no Chinese yet, entries nothing uses any more, and placeholders that do not match.

## Status

Early, and so far tested on one player's logs (Quest 3S, AI levels 75 to 100, a few hundred matches), plus generated
logs. The dashboard opens on your main level (the AI level with the most points in your last five sessions), and its
findings are written from your numbers by fixed rules in `builddata.py`. Online play: see "Against the AI, and against
people online" above. Left-handed play is handled but has only been tested by forcing `hand=left` on right-handed logs. Logs
from other headsets, game versions and online matches are welcome (redacted): see `CONTRIBUTING.md`.

## Backstory

I had never played table tennis before Eleven. I got into the game, wanted to get better at it, and wanted to know
what was losing me points instead of guessing. [11hero](https://11hero.com) showed me what match analysis for Eleven
can look like, and elevendash is inspired by it: the same kind of numbers, worked out on my own computer from the
game's logs, for the matches I play most, which are against the AI. I play with a SolidSlime paddle adapter, made by
the same people behind 11hero.

I am one player with one headset, so this is built around how I play. If it helps you improve too, or it gets
something wrong on your logs, I would like to hear about it.

## Licence

MIT, see `LICENSE`. The bundled D3 chart library is under the ISC licence; see `THIRD_PARTY_NOTICES.md`.
