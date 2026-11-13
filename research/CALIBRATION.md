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

## Limits
- Online logs only hold the logging player's own hits (59 of 118). 11hero gets the opponent's from data this parser
  doesn't read yet. Against the AI both sides are local: one day's log held 2,156 hits (1,155 the player's, 1,001 the AI's).
- One match is a small sample. The 20 r/s and 1.35 m cut-offs fit it exactly but may need checking against a second online match.
