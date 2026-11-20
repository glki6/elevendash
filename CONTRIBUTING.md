# Contributing

Thanks for helping. Bug reports, logs that parse wrongly (redacted), new analysis and translations are all welcome.

## Set up

```
git clone https://github.com/glki6/elevendash.git
cd elevendash
python -m venv .venv
.venv\Scripts\activate            (Windows)     or     source .venv/bin/activate     (macOS, Linux)
pip install -e .
python -m unittest discover -s tests
elevendash demo                   a dashboard of made-up matches in elevendash-demo/
```

No Quest is needed: `elevendash demo` and the tests use generated logs (`src/elevendash/sample.py`).

If you keep a workspace of your own logs next to the code, turn on the check that runs before every push:

```
git config core.hooksPath tools/hooks
```

It refuses a push that holds anything private from that workspace: values from your game logs (ids, names, tokens,
location), your Google client values and video ids if you use `youtube/`, anything that looks like a log, and any word
you list in `private-words.txt` (one word or regular expression a line: your name, an address; git ignores the file).
It reads the files to be committed and every file version in the commits being pushed, and prints file names only.
`python tools/prepush/check.py` runs it by hand.

## Ground rules

- **No real logs, ever**, in commits, issues or pull requests: they hold account tokens. Use the generated logs, or a
  copy made with `elevendash redact` that you have read through. For a bug report, `elevendash diagnose` (in the app,
  **Report for a bug…**) says most of what is needed and holds nothing private. Workspaces (`elevendash.json`, `logs/`, `build/`,
  `site/` …) are ignored by git; keep it that way.
- No other people's data: no screenshots or dashboards with real player names unless they agreed.
- The dashboard needs only the Python standard library. A new dependency needs a strong reason, and goes in an
  optional extra like `youtube`.
- Everything a player sees is in English and Traditional Chinese. After changing any English text (the page, chart
  labels, or the notes `builddata.py` writes), add its translation to `src/elevendash/web/zh-Hant.json` and run the
  check, which must print 0 everywhere:

  ```
  python -c "import sys; sys.path.insert(0, 'src'); from elevendash import i18n; i18n.check()"
  ```

  (The tests run it too.)
- The dashboard has a second side for matches against people online, which shows the same sentences reworded for an
  opponent (`src/elevendash/voice.py`). After adding a sentence that names the AI or an AI level, run this from the
  repository with `src` on `PYTHONPATH`; it must print `voice: 0 to fix`, and `list` in place of `check` shows every
  sentence in both wordings:

  ```
  python -X utf8 -m elevendash.voice check
  ```
- Page changes: try the dashboard in Firefox and in a Chromium browser, dark and light, English and Chinese, and at
  about 640 px wide. A click must never move the page. `python tools/pagetest/run.py SITE --browser all` opens a built
  dashboard in headless Chrome and Firefox, each with an empty throwaway profile, and checks that every section draws,
  the shot explorer's filters, the replay in 2D and 3D and both languages (the tests on GitHub run it on the demo in
  Chrome). `tools/fxtest/` runs scroll tests in a private headless Firefox.
- Keep the side colours: blue is the player, orange the AI or opponent. Green and red only mean better and worse.

## Pull requests

Small and focused is easiest to review. Say what changed for the player, and how you checked it.

By contributing you agree that your contribution is licensed under the MIT License (see `LICENSE`).
