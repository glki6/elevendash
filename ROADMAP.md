# Roadmap

elevendash already answers **what am I doing wrong?** The next round is about **what should I do differently?** and
then **did doing it differently make me better?**

Everything here is worked out from what the logs hold: every ball contact, with position, speed, spin and time, plus
the score. Each item says what it would show, where it goes on the page, and what it needs from the data. Items are in
the order they are planned. Nothing here is a promise of a date.

## Next: what to do differently

1. **After you attack.** Not just whether your fast loop or fast drive landed, but what happened next: won outright,
   came back and you won the point anyway, or came back and you lost it. Split by the ball you attacked and by whether
   your next shot landed, so it shows whether your openers are backed by your follow-ups. A card in the Shot explorer
   that follows its filters. Needs only the shots the page already holds, plus who won each point.
2. **Patterns that win points.** The first shots of a point as one pattern: your serve, where the return went, your
   third ball; and on the AI's serve, its serve, your return, its third ball, your fourth. Ranked by how often they
   come up and the points they win against your average, each opening its points in the replay. Only patterns with 30
   or more points are ranked.
3. **Where your rally shots land.** The serve map, for every other shot: where your shots landed on the far half, and
   the points won from each part of the table (deep or short, wide or middle, cross or down the line). Split by
   stroke and by the ball you played. Needs the landing spot of each of your shots added to the shot records; the
   replay track already has it.
4. **Your speed and spin sweet spot.** For the balls the Shot explorer's filters pick: how often you land, and win the
   point, at each speed you hit them, and a speed by spin map of the shots you landed and missed. Also landing rate
   by when you met the ball: rising or falling, and how soon after the bounce. Answers "how hard should I hit this
   ball?" with your own numbers rather than one fixed speed.
5. **Then and now.** Pick two stretches of matches (say the month before you started winning and the month after)
   and see which measures moved most, at the same AI level and with the mix of balls you faced held the same, so a
   change in what the AI sent you does not pass for a change in you. Built on Matches you pick. Quick picks for
   "this week against the four before".
6. **A skill over time.** For the balls the Shot explorer's filters pick (returning fast topspin, say), your landing
   rate month by month with its likely range, apart from your match results.
7. **What works for you.** A short page of your best serves, your best stroke against each kind of ball and your best
   patterns, rebuilt after every import from items 1 to 4. Comes after them.

## Then: did it work

8. **Training journal.** Dated entries the logs cannot know: a drill, a game setting, new equipment, a change of
   technique. Kept on your computer like match notes, never in a shared file. Each entry is marked on the Progress
   and Form charts, with a before-and-since comparison built like item 5.
9. **Session goals.** Pick up to three measurable targets before you play (returns landed, points won on your serve, a
   kind of ball from the Shot explorer). After the import, the session report and session card say how each went.
10. **Side-by-side replay.** A shot you landed and one you missed against a similar ball, in two 3D replays that play
    in step from the moment the ball reaches you.
11. **Training plan history.** When each item joined the plan, whether it left it, and whether it came back.

## Smaller additions

- **Personal records.** Longest rally won, fastest shot that landed, longest run of matches won, best session.
- **Your floor, not just your average.** In Form: your weaker matches (the lower quarter of your match results) over
  time, to show whether your bad days are getting better.

## The app

- **Import report.** After an import, the app lists any log that looks misread and why. Today only the command line
  prints these.
- **Backup and restore.** One file holding the whole workspace, to move to a new computer. The logs inside it hold
  your account tokens, so the app says so and the file stays on your own drives.
- **Export.** Matches, points and shots as CSV or JSON for other tools. Match data only: no log lines, tokens or
  account details.
- **Share some matches.** A dashboard file built from only the matches you pick, for a coach, instead of your whole
  history.
- **First-run guide.** A step-by-step check of the headset connection in the welcome screen: File Sharing on, address
  reachable, logs found.

## After the features: a new layout

The page has grown one section at a time, split into "Latest" and "All-time analysis", and Breakdown by AI level holds
six different kinds of analysis. Once the items above have landed, the page is reorganised around the questions a
player asks. New features are built into today's page first and move with everything else, so the reorganisation is
done once, with every piece in hand.

### Sections

| Section | The question | What goes in it |
|---|---|---|
| **Overview** | How am I doing? | Main level and recent form at a glance, the three findings worth the most points (each linking to its detail), the last session in one line, the top training plan item. Readable in under a minute. |
| **Match review** | What happened? | **Sessions**: session report, comparison, session card, videos and reels. **Matches**: match explorer, services, rally shots, notes, match card, 11hero metrics. **Replay**: point by point, 2D and 3D, Deciding shot, landing call, side-by-side replay. |
| **Progress** | Am I getting better? | **Results**: progress by day, rolling results, online rating. **Skills**: a skill over time. **Compare**: then and now, matches you pick, matches won and lost. **Consistency**: your floor, through a session. **Records**. |
| **Tactics** | What wins me points? | How points end (and length of point), serves and returns (and where serves land), after you attack, patterns that win points, where your rally shots land. |
| **Shot analysis** | How well am I hitting the ball? | Rally shots by type and 11hero metrics, the Shot explorer as it is, speed, spin and timing. |
| **Coaching** | What should I work on? | Training plan (weaknesses), what works for you (strengths, the plan's mirror), goals and journal, training plan history. |
| **About these numbers** | | How it's worked out: definitions, methods and what the logs cannot tell. |

Tactics and Shot analysis stay apart on purpose: landing 90% of your drives is execution; finding that drives down the
line win more points than drives across the table is tactics.

### What moves where

| Today | New home |
|---|---|
| Overview | Overview, redone |
| Session report | Match review › Sessions |
| Match explorer, with Point by point | Match review › Matches and Replay |
| Training plan | Coaching |
| Shot explorer | Shot analysis |
| Matches you pick | Progress › Compare |
| Progress by day | Progress › Results |
| Form and stamina | Rolling results to Progress › Results, through a session to Progress › Consistency |
| What decides points | Its top findings on the Overview, the rest in Tactics |
| Serves and returns | Tactics |
| Breakdown by AI level | Split up: how points end and length of point to Tactics, where serves land to Tactics › Serves, matches won and lost to Progress › Compare, rally shots by type and 11hero metrics to Shot analysis, rating charts to Progress › Results |
| How it's worked out | About these numbers |

### Rules for the new layout

- **AI level is a filter, not a section.** One bar at the top says what you are looking at: AI or online, which
  level, and how many matches and points that is. A card that has to look at other data says so on the card. A period
  filter appears only where the numbers are worked out on the page (Shot explorer, Compare, Tactics cards built from
  shots), not on figures fixed at import.
- **The conclusion first.** Each card leads with its finding and a number. Charts, tables and the method sit behind
  "In full" and "How to read this", as they do now.
- **Every finding opens its evidence.** A pattern, a group of misses or a finding opens its points in the one replay,
  with Back to return to where you were. Picking a match in a session opens it in Matches, and picking a point keeps
  the match picked.
- **One look for comparisons.** You and the AI, landed and missed, won and lost, now and before, each with the same
  colours and the same tick-for-the-baseline everywhere.
- **Still one page.** The sidebar groups the sections and keeps today's open-and-close behaviour; everything stays on
  one scrolling page that works offline as a single file.
- **The PDF keeps its own order.** The printed report stays a linear report, it does not have to follow the
  interactive layout.
- **Settings stay in the app.** Import, import warnings, backup, export, phone and startup live in the app's bar and
  Settings, not in the dashboard; import warnings show right after the import that caused them. Theme and language
  stay on the page.
- **Unchanged:** local first, the single-file dashboard and PDF, AI and online kept apart, English and Traditional
  Chinese.

## Already there

- **Which stroke to play against a kind of ball:** "Your strokes against these balls" in Find shots.
- **What goes with a miss:** "Your misses against the ones you landed" in Find shots, including when you met the ball.
- **Whether a training plan item has moved:** each item's number since it joined the plan.
- **Several players:** each player has their own workspace folder (`--dir`).

## Not planned

- **Pressure points and comebacks.** Tested on a few thousand points at one level: once each match's own win rate is
  taken into account, the score made no difference. Worth testing again when there are more players' logs.
- **Whether you are ready for the next AI level.** The likely range in Form already shows where your results sit; a
  verdict about a level you have not played would be a guess.
- **Saved lists of points to replay.** Not planned for now.
- **Bat angle, swing, footwork, body position, reaction time, forehand or backhand.** The logs hold the ball, not the
  player. Forehand and backhand were checked: the side of contact gives a likely wing only for wide balls.

Ideas and logs from other headsets are welcome: see `CONTRIBUTING.md`.
