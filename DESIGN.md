# Design spec for the new layout

This is the design spec for the reorganisation described in `ROADMAP.md` ("After the features: a new layout"),
built in v1.0.0. It records what the page is for, what an audit of v0.19.0 found, the rules the layout has to
meet, which outside advice was taken and which was left out, and the layout that was chosen.

## What the page is for

One player, after a session or between sessions, on a desktop browser or a phone, asking one of six questions:
how am I doing, what happened, am I getting better, what wins me points, how well am I hitting the ball, what should I
work on. They come to read an answer and then check the evidence behind it. It is a working tool and a report, not a
showcase: familiar controls, restraint, and exact numbers matter more than expression.

## Audit of v0.19.0

Measured on a well-used workspace, with every "In full" and "How to read this" closed.

| | Desktop (1440 x 900) | Phone (375 x 812) |
|---|---|---|
| Page length | about 29 screens | about 53 screens |
| Longest section | Shot explorer, 7.7 screens | Shot explorer, 12 screens |

- 11 sections, 33 sidebar links, about 70 cards.
- The AI level is one setting for the whole page, but its picker is repeated in seven places, and Find shots has a
  level filter of its own.
- 20 tab groups, 17 dropdowns, 64 open-and-close blocks (28 "How to read this", 19 "In full").
- On a phone about 800 controls are on the page at once, and nearly all are under 44 px tall.

What is hard today:

1. **Finding a card.** The order is the order things were built in. Rally shots by type and the 11hero metrics appear
   twice (per match and per level); serve analysis is split between Serves and returns and Breakdown by AI level.
2. **Knowing what you are looking at.** The level picker that governs a card is often screens away from it, in
   another section's heading.
3. **Getting the answer.** The Overview states the record, then the page moves straight into detail. The findings that
   are worth the most points sit two thirds of the way down.
4. **Getting back.** A finding that opens the replay moves the page; Back returns, but only one step.
5. **Length on a phone.** The sidebar becomes a menu, and after that the page is one 53-screen scroll.

What works and stays: the finding-first cards with the detail behind "In full"; "How to read this" on every chart;
the one replay that every list of points opens; both themes; both languages; the PDF; the page test.

## Principles, in order

Where two pull against each other, the earlier one wins.

### 1. Information architecture

- Six areas, one per question, plus About these numbers. Every card lives in exactly one area. A number may be
  repeated on the Overview; a card may not.
- Each area is ordered the same way: scope and controls, then the answer in three to five numbers, then the main
  trend or problem view, then breakdowns, then the detail table.
- Tactics and Shot analysis stay apart: what you choose to play, and how well you play it.
- At most nine cards are open in view at once. More than that sit closed to their finding, or in another part.

### 2. Readability

- A card leads with its finding as a sentence and one number. The answer of an area is readable in a few seconds
  without hovering over anything.
- Running text is 60 to 75 characters wide in English; Chinese text is set at the same box width, so it runs shorter.
- One type scale with a ratio of about 1.2, fixed sizes (no fluid type), system fonts only, because the file has to
  work offline. Numbers are tabular and right-aligned in tables.
- A tooltip never holds the only copy of a number.

### 3. Useful density

- Width adds columns (one, two, then four); no half-empty card in a row.
- Tables are allowed to be dense; prose is not. A table wider than its card scrolls inside the card, never the page.
- Empty and thin data say so in words ("12 shots so far; 30 are needed"), never as a chart of two points.

### 4. Analytical accuracy

- Every number is worked out exactly as today. The reorganisation moves cards; it does not change a formula.
- One scope bar says what the page is about: AI or online, which level, how many matches and points, and the dates.
  A card that looks at other data says so on the card. A period filter appears only where numbers are worked out on
  the page.
- Each headline number has one baseline, named beside it. A rate over a small base shows the count, greyed, not a
  bare percentage.
- Bars start at zero. Rate axes step in 5 or 10 points. Missing values are gaps and read "–".

### 5. Discoverability

- Every finding opens its evidence: its points in the one replay, with Back to where you were, however many steps.
- The area, the part of it, the level and the picked match or session are kept in the address after `#`, so reload,
  Back and a shared link all restore the view.
- Everything works from the keyboard, with a visible focus ring. Single-key shortcuts are off while typing.
- Touch targets are at least 44 px on a phone and 24 px elsewhere.

### 6. Consistency

- One look for each comparison, everywhere: you and the AI, landed and missed, won and lost, now and before. The
  thing being compared against is always the quieter one (a tick, grey, or dashed), and never told apart by colour
  alone.
- A category keeps its colour across every chart. Series colours are checked with a colour-blindness validator
  against both themes' surfaces before they ship.
- The same control looks and behaves the same in every card: level, period, show more, sort.
- Motion only shows a change of state, is over in about a quarter of a second (a bar may take half a second to
  fill), and respects the reduced-motion setting.

## Fixed

- One self-contained HTML file that works offline; plain HTML and JavaScript with the bundled D3; no new runtime
  dependency.
- English and Traditional Chinese throughout, dark and light themes, AI and online kept apart.
- The look starts from the current blue theme (the colours in `look.json`). A new layout may refine it, not replace
  it with another palette.
- The PDF keeps its own linear order with everything open and every value printed. Nothing in it depends on hover,
  on a tab, or on the address.
- Import, backup, export, sharing and the phone link stay with the app, not the page: behind a gear button in the
  page's bar when the app serves it, and absent from the file you send to someone.

## Taken from outside, and left out

Read as reference only: the web interface guidelines from Vercel Labs, three dashboard and data-visualisation skill
repositories (MMS-21/agent-skills, abdiraimov-otabek/dashboard-design-skill, SvaraNova/skills), and how Intervals.icu,
Strava, TrainingPeaks, Linear and TradingView lay out dense data. Nothing from them is installed or run.

Taken: overview first and detail on demand; the fixed order of an area; one scope and one comparison per view;
state in the address; a pinned summary above the sub-views of one match or session; a shared, lockable cursor across
stacked time charts; direct labels for five series or fewer; targets, focus and reduced motion; numbers through one
formatter per language.

Left out, and why:

- Marketing-page advice (heroes, calls to action, title case): this is a tool.
- "No sentences on a dashboard, no insight cards": the coaching text is the point of this page. The rule is kept for
  tables and charts, which carry no commentary of their own.
- Anything that needs a server or a framework: one request per card, server-side downsampling, retry buttons, React
  and Tailwind specifics.
- A wall of charts the reader arranges: it brings the long page back, and its arrangement could only live in one
  browser's storage.
- Sideways-scrolling tab rows on a phone: a phone gets a short fixed bar or a menu.

## The layout: six areas

Three concepts were drawn on the six areas and the rules above, and reviewed on real data:

- **A. One page, in order.** Still one scrolling page, grouped by question, every card closed to its finding. Ruled
  out: it is still the longest of the three.
- **B. Six areas, one on screen at a time.** Chosen.
- **C. Workbench.** A list of findings beside the picked card, arrow keys and a jump-to box. Not built: the biggest
  rebuild, and it reads less like a report.

### As built

- **The bar.** Its first row holds the name, the six areas and the theme and language switches. Its second row is the
  scope: AI or online, the AI level, and how many matches and points that is, with their dates. On a wide screen the
  bar stays at the top while the page scrolls. Under 800 px the six areas move to a bar along the foot of the screen,
  each at least 44 px tall, and the top bar scrolls away with the page. That foot bar steps aside while you scroll
  down and comes back when you scroll up, reach the end, or open an area.
- **An area** opens with one line on what is in it as its heading, and its parts as one row of buttons: "All" and
  one for
  each part. A part is a filter: it shows the blocks that belong to it and nothing else. A block may belong to two
  parts (the match picker belongs to Matches and to Replay).
- **The Overview** opens on how the last session went, as its heading. It answers in one screen: the sentence, the scoreboard, recent form, the top of the training plan and
  the first three findings. Each of these opens its full card in its own area.
- **Where the cards went.** Match review: sessions, matches, replay. Progress: results (by day, rolling results,
  online rating), compare (matches won and lost, matches you pick, then and now), consistency (your floor, through a
  session), records. Tactics: how points end (the findings, how points are won and lost, length of point), serves
  and returns (with where serves land), patterns. Shot analysis: where misses pile up, Find shots, strokes (rally
  shots by type, 11hero metrics). Coaching: training plan, what works for you, training journal.
- **The address** holds the area and the part (`#area=tactics&part=serves`) beside the level and the picked match.
  A change of area or part is a step the browser's Back undoes.
- **The finder.** "Jump to" lists the headings of the area on screen, as they stand with the part shown, and
  takes you to one. It sits at the right of the scope row on a wide screen and as a button at the foot of a phone,
  opposite the way back. Headings a drawing writes from the data (a finding, a plan item) are not listed: they
  sit under a heading that is.
- **Motion.** An area rises into place when it comes on screen, with its bars filling; the line under the area's
  tab slides to the next tab; the replay's window, the menus, the Back button and anything unfolded ease in. Each
  shows a change of state, and none of it runs for a reader who asked for less motion, or in the PDF.
- **The replay comes to you.** A point opened from a list in another area (Find shots, patterns, records) plays in
  a window over the page, not in Match review: the replay's own card is moved into the window, on a larger table,
  with the same controls. Closing it puts the card back and leaves the page at the list, so the next point is one
  click away. The window can also open the point in Match review, where the rest of its match is.
- **The way back.** A jump from a card that changes the area or the part, or moves the page by more than a
  screen, leaves a Back button at the foot of the screen (above the areas on a phone), one step for each jump
  taken. Picking an area yourself clears it.
- **The app's controls** (import, settings, your data, the phone link) open as a panel under a gear button at the
  right of the bar, beside the theme and language buttons. A dot on the gear says there is something to read, and
  what an import found shows as a short note under it.
- **A link to a card** anywhere on the page brings the card's area with it, and its part when the part on screen
  leaves it out. This is how a finding opens its points in the replay and how Back to the card returns.
- **What is off is still drawn.** An area or part that is not on screen stays laid out at its own width, out of the
  flow and out of sight (`.er-off`), so every chart keeps its size and changing area needs no redraw. Nothing is added
  to or taken from the page by the script: it only marks what is on.
- **The look is unchanged.** Colours, type and cards are the ones of v0.19.0 (`look.json`). The new parts (bar, area
  heading, part buttons) are built from the controls the page already had.
- **The PDF** shows every area in turn, each starting a page, with the bar's name and scope at the top and no
  buttons.

### Not done yet

- The level picker inside Find shots is still its own filter, as before.
- Cards are in their areas but have not each been rewritten to lead with one number; they keep the form they had.
- No keyboard shortcut moves between areas, and the finder covers one area at a time, not the whole page.
- The six questions the areas answer are the plan behind the page, not its headings: as headings they read as
  odd. The area's name is not the heading either: it is already on the tab above, so the heading is a line saying
  what is in the area (on the Overview, the last session's result). The name is kept for a screen reader, and
  shows as the title in the PDF, which has no tabs.
