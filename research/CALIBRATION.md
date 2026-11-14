# Matching 11hero's numbers from raw Eleven logs

Reference: one ranked online quick match from November 2026, the logging player on table side B, won 2–0 (11–8,
12–10). 11hero's full data for it was saved locally as `11hero-match-pvp1.json` (from the page's embedded data). That
file holds another player's data, so it is not in the repository; `cmp_pvp1.py` and `metrics.py` compare against it
when it is present.

## Exact matches (59 of the logging player's hits, compared one by one)
- **Speed** = |post-hit velocity| from the `[Physics-BallCollisions]Dynamic Collision...` block's `postCollisionState vel`. Max difference 0.0000 m/s.
- **Spin** (11hero "r/s" = revolutions per second) = |rRate| / 360 (the log's rRate is in degrees/s). Max difference 0.000.
- **Top/back spin component** (`bmSpinTopBottom`) = rRate/360 projected onto the horizontal axis perpendicular to the ball's
  horizontal travel: axis = (vz, 0, −vx)/|(vx, vz)|. Max difference 0.00.
- **Side**: contact z < 0 → table side A, z > 0 → side B. Against the AI the player is side A; online it can be either
  (the log's `MoveUserIntoPosition(TableSideX)` says which).

## Metric definitions (all reproduce 11hero's values for both players)
- Average serve / rally speed = mean speed of serves / non-serve hits.
- Average serve / rally top spin = mean top/back component over hits with component > +20 r/s; back spin = mean over hits < −20 r/s (0 if none).
- Serve success rate = share of serves that land.

## Shot types: 78/78 rally shots match with this rule
- top/back component < 0 → **Push** if contact |z| < 1.35 m (over the table), else **Chop**
- else total spin ≥ 50 r/s → **FastLoop** if speed ≥ 10.5 m/s, else **SlowLoop**
- else **Drive**

**Open-up** = an attacking shot (drive or loop) hit against a ball that had backspin (the previous shot's component < 0). That rule fits all 6 flagged shots.

## Online: the opponent's hits
- The log has collision blocks only for the logging player's own hits (59 of 118). Each of the opponent's hits arrives
  as `[MPMatch]Received ball hit from opponent: pos:(…) vel:(…) rrate:(…)` and each of their tosses as
  `[MPMatch]Received ball toss from opponent: …`. vel and rrate are the ball's state just after the hit, so speed, spin
  and the top/back component come out as 11hero's (max difference 0.0000 over the opponent's 59 hits).
- Not every such message is a shot. Left out: a ball at rest at (0,-10,0) sent between points; a hit before the point's
  toss (the opponent touching the ball between points, or a serve that arrives after the point was already given); the
  same message logged twice. The bounces after an opponent's hit are the local game's, timed from the message's arrival.
- On the reference match: all 118 hits in the same order, with the same serve, landed, winning-shot, open-up and shot
  type, and the same server on every point. The opponent's 21 metrics and 16 of the logging player's equal 11hero's.
  The other five (shares of points won by the winning shot) differ because 11hero adds an empty 42nd point, won by the
  logging player; scored on the same 41 points, all 42 metrics agree.

## Limits
- Against the AI both sides are local: one day's log held 2,156 hits (1,155 the player's, 1,001 the AI's).
- One online match is a small sample, both for the 20 r/s and 1.35 m cut-offs (which fit it exactly) and for the
  handling of the opponent's messages above.
