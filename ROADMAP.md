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
