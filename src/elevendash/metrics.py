"""11hero-style match metrics for one player, from points in extract.py's shape.

Point: {'winner': 'A'|'B', 'server': 'A'|'B'|None, 'hits': [{'side','n','serve','ok','win','open','shot','speed','top'}], 'dist'}
Definitions reproduce 11hero's numbers (checked against its data for a real match, see CALIBRATION.md).
"""
from statistics import mean

SPIN_T = 20.0   # r/s threshold for counting a hit in the top / back spin averages


def _pct(a, b):
    return 100.0 * a / b if b else None


def _avg(xs):
    xs = list(xs)
    return mean(xs) if xs else None


def player_metrics(points, me):
    opp = 'B' if me == 'A' else 'A'
    hits = [h for p in points for h in p['hits']]
    mine = [h for h in hits if h['side'] == me]
    serves = [h for h in mine if h['serve']]
    rally = [h for h in mine if not h['serve']]
    served = [p for p in points if p['hits'] and p['hits'][0]['side'] == me]
    returns = [h for h in mine if h['n'] == 2]
    ret_pts = [p for p in points if len(p['hits']) >= 2 and p['hits'][1]['side'] == me]
    third = [h for h in mine if h['n'] == 3]
    won = [p for p in points if p['winner'] == me]

    def win_shot(p):
        w = [h for h in p['hits'] if h['win']]
        return w[-1] if w else None

    def won_by(n):
        return sum(1 for p in won if (w := win_shot(p)) and w['side'] == me and w['n'] == n)

    opp_service_err = sum(1 for p in won if p['hits'] and p['hits'][0]['side'] == opp and not p['hits'][0]['ok'])
    ou = [h for h in mine if h['open']]
    return {
        'serveSpeed': _avg(h['speed'] for h in serves),
        'serveTop': _avg(h['top'] for h in serves if h['top'] > SPIN_T),
        'serveBack': _avg(h['top'] for h in serves if h['top'] < -SPIN_T),
        'rallySpeed': _avg(h['speed'] for h in rally),
        'rallyTop': _avg(h['top'] for h in rally if h['top'] > SPIN_T),
        'rallyBack': _avg(h['top'] for h in rally if h['top'] < -SPIN_T),
        'serveScore': _pct(sum(1 for p in served if p['winner'] == me and (w := win_shot(p)) and w['n'] == 1), len(served)),
        'returnScore': _pct(sum(1 for h in returns if h['win']), len(returns)),
        'thirdBallScore': _pct(sum(1 for h in third if h['win']), len(third)),
        'wonAsServer': _pct(sum(1 for p in served if p['winner'] == me), len(served)),
        'wonAsReturner': _pct(sum(1 for p in ret_pts if p['winner'] == me), len(ret_pts)),
        'serveSuccess': _pct(sum(1 for h in serves if h['ok']), len(serves)),
        'returnSuccess': _pct(sum(1 for h in returns if h['ok']), len(returns)),
        'openUpAttempt': _pct(len(ou), len(rally)),
        'openUpSuccess': _pct(sum(1 for h in ou if h['ok']), len(ou)),
        'wonByOppServiceError': _pct(opp_service_err, len(won)),
        'wonByServe': _pct(won_by(1), len(won)),
        'wonByReturn': _pct(won_by(2), len(won)),
        'wonByThird': _pct(won_by(3), len(won)),
        'wonByFourth': _pct(won_by(4), len(won)),
        'wonByLater': _pct(sum(1 for p in won if (w := win_shot(p)) and w['side'] == me and w['n'] > 4), len(won)),
        'counts': {'points': len(points), 'won': len(won), 'served': len(served), 'serves': len(serves),
                   'returns': len(returns), 'hits': len(mine)},
    }


def match_metrics(points):
    # hits per point over all points. (11hero averages its own per-point field, which also counts a voided
    # point as -1: 2.79 vs 2.88 here for the reference match.)
    return {'rallyLength': _avg(len(p['hits']) for p in points),
            'ballDistance': sum(p.get('dist', 0) for p in points)}


def from_11hero(match):
    """Convert 11hero's match JSON into extract.py's point shape (home = A) for testing."""
    pts = []
    for s in match['sets']:
        for p in s['points']:
            hits = []
            for c in p['contacts']:
                if c['contactType'] != 'Hit':
                    continue
                hits.append({'side': 'A' if c['playerIsHome'] else 'B', 'n': c['rallyCount'], 'serve': c['isServe'],
                             'ok': c['isSuccess'], 'win': c['isWinningShot'], 'open': c['isOpenUpShot'],
                             'shot': c['shotType'], 'speed': c['velSqrt'], 'top': c['bmSpinTopBottom']})
            toss = next((c for c in p['contacts'] if c['contactType'] == 'Toss'), None)
            server = hits[0]['side'] if hits else (('A' if toss['playerIsHome'] else 'B') if toss else None)
            pts.append({'winner': 'A' if p['wonByHome'] else 'B', 'server': server, 'hits': hits})
    return pts


if __name__ == '__main__':
    import json, os, sys
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, '11hero-match-pvp1.json'), encoding='utf-8') as f:
        m = json.load(f)
    pts = from_11hero(m)
    key = {'serveSpeed': 'averageServeSpeed', 'serveTop': 'averageServeTopSpin', 'serveBack': 'averageServeBackSpin',
           'rallySpeed': 'averageRallySpeed', 'rallyTop': 'averageRallyTopSpin', 'rallyBack': 'averageRallyBackSpin',
           'serveScore': 'serveScoreRate', 'returnScore': 'serveReturnScoreRate', 'thirdBallScore': 'thirdBallScoreRate',
           'wonAsServer': 'pointsWonAsServerRate', 'wonAsReturner': 'pointsWonAsServeReturnerRate',
           'serveSuccess': 'serveSuccessRate', 'returnSuccess': 'serveReturnSuccessRate',
           'openUpAttempt': 'openUpAttemptRate', 'openUpSuccess': 'openUpSuccessRate',
           'wonByOppServiceError': 'pointsWonByOpponentServiceErrorInAllPointsWon',
           'wonByServe': 'pointsWonByServeInAllPointsWon', 'wonByReturn': 'pointsWonByServeReturnInAllPointsWon',
           'wonByThird': 'pointsWonByThirdBallInAllPointsWon', 'wonByFourth': 'pointsWonByFourthBallInAllPointsWon',
           'wonByLater': 'pointsWonByMoreThanFourthBallInAllPointsWon'}
    bad = 0
    for side, suf in (('A', 'Home'), ('B', 'Away')):
        mm = player_metrics(pts, side)
        for k, hk in key.items():
            mine, theirs = mm[k] or 0, m[hk + suf] or 0
            ok = abs(mine - theirs) < 0.01
            bad += not ok
            if not ok:
                print(f'MISMATCH {suf} {k}: mine {mine:.2f} 11hero {theirs:.2f}')
    print('rally length', match_metrics(pts)['rallyLength'], '11hero', m['averageRallyLength'])
    print('mismatches:', bad, 'of', 2 * len(key))
