"""The words for matches against people.

The dashboard was written for matches against the AI, and says so all over: "the AI's serve", "at level 100". Its
online side shows the same sums over your online matches, so every sentence that names the AI or an AI level has a
second wording, made here from the first: your opponent for the AI, and "online" where the AI side says a level.
The builder writes its sentences with it (i18n.T, in the online pass), the page carries both wordings of each of its
own sentences (i18n.bilingual), and the page's scripts get a list of theirs (script_words).

Three steps, each on the English and on the Chinese:
  PHRASES   a phrase that needs its own wording, replaced wherever it stands (a whole sentence is a phrase too)
  the rule  what is left: the AI becomes your opponent
  KEEP      sentences that stay as they are: the drills that send you to practise against the AI, and words about a
            level that is not the AI's

    python -m elevendash.voice check     lists what still names the AI or a level afterwards, and phrases nothing uses
    python -m elevendash.voice list      every sentence that changes, before and after, to read through
"""
import re
import sys

# In a wording for people that has to name the AI itself: the rule below leaves this alone, and pair() writes it out.
AI = chr(1)

# (English, for people, Chinese, for people). Where one phrase holds another, the longer is replaced first.
PHRASES = [
    # ---- whole labels
    ('Eleven vs AI Report', 'Eleven Online Report', 'Eleven 對 AI 報告', 'Eleven 線上對戰報告'),
    ('Breakdown by AI level', 'Breakdown by opponent rating', '按 AI 等級細分', '按對手積分細分'),
    ('By AI level', 'By opponent rating', '按 AI 等級', '按對手積分'),
    ('All AI matches', 'All online matches', '所有對 AI 的比賽', '所有線上比賽'),
    ('All at this level', 'All online', '此等級全部', '線上全部'),
    ('All at level {0}', 'All online', '等級 {0} 全部', '線上全部'),
    ('All your matches at this level', 'All your online matches', '此等級的全部比賽', '你全部的線上比賽'),
    ('11hero metrics at this level', '11hero metrics online', '此等級的 11hero 指標', '線上比賽的 11hero 指標'),
    ('Level avg is your average over every match at the same AI level.', 'Online avg is your average over every online match.',
     '等級平均是你在同一 AI 等級所有比賽的平均。', '線上平均是你所有線上比賽的平均。'),
    ('Level avg', 'Online avg', '等級平均', '線上平均'),
    ('AI level {0}', 'Online', 'AI 等級 {0}', '線上'),
    ('Level {0} (legendary), {1} matches', 'Online, {1} matches', '等級 {0}（傳奇），{1} 場比賽', '線上，{1} 場比賽'),
    ('Level {0}, {1} matches', 'Online, {1} matches', '等級 {0}，{1} 場比賽', '線上，{1} 場比賽'),
    ('Level {0} has {1} matches so far: not enough for a run of {2}.', 'You have {1} online matches so far: not enough for a run of {2}.',
     '等級 {0} 目前只有 {1} 場比賽：不足以計算 {2} 場的成績。', '目前只有 {1} 場線上比賽：不足以計算 {2} 場的成績。'),
    ('Level {0}: all {1} of your matches.', 'Online: all {1} of your matches.', '等級 {0}：你全部 {1} 場比賽。', '線上：你全部 {1} 場比賽。'),
    ('Level {0}: your {1} matches from {2} on.', 'Online: your {1} matches from {2} on.',
     '等級 {0}：你自 {2} 起的 {1} 場比賽。', '線上：你自 {2} 起的 {1} 場比賽。'),
    ('Level {lv}', 'Online', '等級 {lv}', '線上'),
    ('level {lv}', 'online', '等級 {lv}', '線上'),
    ('level {0}', 'online', '等級 {0}', '線上'),
    ('At this level', 'Online', '此等級', '線上'),
    # ---- sessions
    ('A session is a run of AI matches', 'A session is a run of online matches', '一節是一連串對 AI 的比賽', '一節是一連串線上比賽'),
    ('· level {5}', '· online', '· 等級 {5}', '· 線上'),
    ('up from {before} at level {lv} before', 'up from {before} online before', '比之前在等級 {lv} 的 {before} 上升', '比之前線上比賽的 {before} 上升'),
    ('down from {before} at level {lv} before', 'down from {before} online before', '比之前在等級 {lv} 的 {before} 下降', '比之前線上比賽的 {before} 下降'),
    ('your earlier level-{lv} average', 'your earlier online average', '你之前在等級 {lv} 的平均', '你之前線上比賽的平均'),
    ('Your first session at level {lv} in the logs', 'Your first online session in the logs',
     '這是紀錄中你在等級 {lv} 的第一節', '這是紀錄中你的第一節線上比賽'),
    ('Your first session at level {0} in the logs', 'Your first online session in the logs',
     '這是紀錄中你在等級 {0} 的第一節', '這是紀錄中你的第一節線上比賽'),
    ('Your average over the {0} level-{1} matches', 'Your average over the {0} online matches',
     '本節之前 {0} 場等級 {1} 比賽', '本節之前 {0} 場線上比賽'),
    ('all your earlier points at the same AI level', 'all your earlier online points',
     '你在同一 AI 等級所有更早的分數', '你所有更早的線上分數'),
    # ---- the top of the page and the findings
    ('From all {1} level-{2} matches, {3} to {4}.', 'From all {1} online matches, {3} to {4}.',
     '根據 {3} 至 {4} 期間全部 {1} 場等級 {2} 的比賽。', '根據 {3} 至 {4} 期間全部 {1} 場線上比賽。'),
    ('Over {1} matches at this level.', 'Over {1} online matches.', '根據此等級的 {1} 場比賽。', '根據 {1} 場線上比賽。'),
    ('Not enough matches at this level yet.', 'Not enough online matches yet.', '此等級的比賽還不夠多。', '線上比賽還不夠多。'),
    ('The opening line, the second scoreboard and What decides your points cover your main level: the AI level with the most '
     'points in your last five sessions.', 'The opening line and What decides your points cover all your online matches.',
     '開頭一句、第二個記分板和「你的得失分關鍵」都針對你的主要等級：即你最近五節中打過最多分的 AI 等級。',
     '開頭一句和「你的得失分關鍵」涵蓋你所有的線上比賽。'),
    ('Lets are left out. Online matches are not in the AI totals: the switch at the top of the page shows them.',
     f'Lets are left out. Matches against the {AI} are not in these totals: the switch at the top of the page shows them.',
     '擦網重發不計。線上比賽不計入對 AI 的總數：用頁面頂部的切換鍵可以查看。',
     f'擦網重發不計。對 {AI} 的比賽不計入這些總數：用頁面頂部的切換鍵可以查看。'),
    ("The AI level is the game's difficulty setting; 100 is legendary. On days you changed level, the progress chart labels "
     "the day with the higher one.",
     "Ratings are the game's own. Both players' ratings are read from the log as each online match starts, and the change "
     "after a ranked match is the one the game gave. The share of matches the ratings expect you to win follows the usual "
     "rating formula: half against an equal rating, about 64 in 100 against a player rated 100 points below you.",
     'AI 等級是遊戲的難度設定；100 是傳奇。在你轉換過等級的日子，進度圖以較高的等級標示。',
     '積分是遊戲本身的積分。每場線上比賽開始時，雙方的積分都從紀錄讀取；排名賽後的變化就是遊戲給出的變化。'
     '積分預期你贏得的比賽比例按一般的積分公式計算：對積分相同的對手是一半，對積分比你低 100 分的對手約為 100 場中的 64 場。'),
    # ---- the plan
    ('built for the AI level you played most in your last five sessions', 'built from your online matches',
     '針對你最近五節最常打的 AI 等級', '根據你的線上比賽建立'),
    ('Now is your latest sessions at that level', 'Now is your latest online sessions', '「現在」是你在該等級最近幾節的合計', '「現在」是你最近幾節線上比賽的合計'),
    ('the same number in the matches you won at that level', 'the same number in the online matches you won',
     '你在該等級贏球場次中的同一數字', '你贏下的線上比賽中的同一數字'),
    ('over all your points at that level', 'over all your online points', '在該等級所有分數中', '在所有線上分數中'),
    ('that the AI plays the same way', 'that your opponents play the same way', '而且 AI 的打法不變', '而且對手的打法不變'),
    ('after each earlier session at that level', 'after each earlier online session', '按該等級較早每一節結束時的情況', '按較早每一節線上比賽結束時的情況'),
    ('since is every session at that level played after that one', 'since is every online session played after that one',
     '「之後」是其後在該等級打的所有節', '「之後」是其後打的所有線上節'),
    ('Never on the plan at level {0}', 'Never on the online plan', '在等級 {0} 從未列入計劃', '在線上計劃中從未列入'),
    ('No matches won at this level yet', 'No online matches won yet', '此等級還沒有贏過比賽', '還沒有贏過線上比賽'),
    ('{0}: line chart by session at level {1}', '{0}: line chart by online session', '{0}：等級 {1} 的每節折線圖', '{0}：線上每節折線圖'),
    # ---- the shot explorer and matches you pick
    ('is worked out for the level of the training plan', 'is worked out over your online matches',
     '是按訓練計畫的等級計算的', '是按你的線上比賽計算的'),
    ('your other AI matches at the same levels', 'your other online matches', '你在相同等級的其他 AI 比賽', '你的其他線上比賽'),
    ('any of your AI matches', 'any of your online matches', '任選你對 AI 的比賽', '任選你的線上比賽'),
    ('Only matches at the same AI level as the ones you picked are used.', 'Only your online matches are used.',
     '只使用與你所選比賽相同 AI 等級的比賽。', '只使用你的線上比賽。'),
    ('The tick is your one other AI match at level {1}.', 'The tick is your one other online match.',
     '刻度是你在等級 {1} 的另外一場 AI 比賽。', '刻度是你另外一場線上比賽。'),
    ('The tick is your other {0} AI matches at level {1}.', 'The tick is your other {0} online matches.',
     '刻度是你在等級 {1} 的其他 {0} 場 AI 比賽。', '刻度是你其他 {0} 場線上比賽。'),
    ('You have no other AI matches at level {0} to set these against.', 'You have no other online matches to set these against.',
     '你在等級 {0} 沒有其他 AI 比賽可以比較。', '你沒有其他線上比賽可以比較。'),
    ('All {0} matches at this level: {1}.', 'All {0} online matches: {1}.', '此等級全部 {0} 場比賽：{1}。', '全部 {0} 場線上比賽：{1}。'),
    ('At level {0} over {1}', 'Online over {1}', '等級 {0}，{1}', '線上，{1}'),
    # ---- progress, form and stamina
    ('on each day you played the AI. The strip along the top is the AI level.', 'on each day you played online.',
     '每天對 AI 時你贏得的分數和局數比例。頂部的色帶是 AI 等級。', '每天線上比賽時你贏得的分數和局數比例。'),
    ('each day against the AI, with the AI level in a strip above', 'each day online', '你每天對 AI 的得分和贏局比例折線圖，上方色帶是 AI 等級',
     '你每天線上比賽的得分和贏局比例折線圖'),
    ('your latest matches at one AI level', 'your latest online matches', '你在某個 AI 等級最近幾場比賽的成績', '你最近幾場線上比賽的成績'),
    ('take your matches at one AI level in the order you played them', 'take your online matches in the order you played them',
     '取你在某個 AI 等級的比賽', '取你的線上比賽'),
    ('uses sessions with three or more matches at one level, and sets each match against the others of that session and level',
     'uses sessions with three or more matches, and sets each match against the others of that session',
     '只用同一等級有三場或以上比賽的節，把每場比賽與該節同等級的其他比賽相比', '只用有三場或以上比賽的節，把每場比賽與該節的其他比賽相比'),
    ('the other matches of the same session at the same level', 'the other matches of the same session',
     '與同一節、同一等級的其他比賽相比', '與同一節的其他比賽相比'),
    ('your last {0} matches at level {1}', 'your last {0} online matches', '你在等級 {1} 最近 {0} 場比賽', '你最近 {0} 場線上比賽'),
    ('Your last {0} matches at level {1}', 'Your last {0} online matches', '你在等級 {1} 最近 {0} 場比賽', '你最近 {0} 場線上比賽'),
    ('matches {0} to {1} at level {2}', 'online matches {0} to {1}', '等級 {2} 的第 {0} 至 {1} 場', '線上第 {0} 至 {1} 場'),
    # ---- the top of the page
    ('At {1} you have won', 'Online you have won', '在{1}，你', '線上比賽中，你'),
    ('In your last session, on', 'In your last online session, on', '上一節（', '上一節線上比賽（'),
    ('On the last day you played,', 'On the last day you played online,', '你最後打球的那天（', '你最後打線上比賽的那天（'),
    ('What decides your points at {1}', 'What decides your points online', '你在{1}的得失分關鍵', '你在線上比賽的得失分關鍵'),
    # ---- serves, returns and the breakdown
    ('Too few serves at this level.', 'Too few serves online.', '此等級的發球太少。', '線上的發球太少。'),
    ('Share of all points at this level', 'Share of all online points', '佔此等級所有分數的比例', '佔所有線上分數的比例'),
    ('{0} of all points at this level', '{0} of all online points', '佔此等級所有分數的 {0}', '佔所有線上分數的 {0}'),
    ('over every point at this level', 'over every online point', '涵蓋此等級的每一分', '涵蓋線上比賽的每一分'),
    ('The line is your average for the level.', 'The line is your online average.', '直線是你在該等級的平均。', '直線是你的線上平均。'),
    # ---- "its", where it means the AI: a person is "they"
    ('of its rally shots', 'of their rally shots', '佔它對打擊球', '佔對手對打擊球'),
    ('When its serve', 'When their serve', '它的發球落在', '對手的發球落在'),
    ('Against its serves', 'Against their serves', '面對它的弱旋發球', '面對對手的弱旋發球'),
    ('on its topspin serves', 'on their topspin serves', '面對它的上旋發球', '面對對手的上旋發球'),
    ('on its other serves', 'on their other serves', '它的其他發球', '對手的其他發球'),
    ('of its serves', 'of their serves', '它的發球中有', '對手的發球中有'),
    ('its backspin serves', 'their backspin serves', '它的下旋發球', '對手的下旋發球'),
    ('its serves with little spin', 'their serves with little spin', '它的弱旋發球', '對手的弱旋發球'),
    ('its topspin serves', 'their topspin serves', '它的上旋發球', '對手的上旋發球'),
    ('misses its next shot', 'misses their next shot', None, None),
    ('its serves on yours', 'their serves on yours', None, None),
]

# Left as they are. The drills send you to the AI or the ball machine to practise, whoever you play your matches
# against; "the level of the matches you won" is a standard you reached, not an AI level; and a few labels are only
# ever shown for a match against the AI.
KEEP = {
    "Have slow balls fed to you (the ball machine, or the AI at a low level) and play every one as a firm topspin stroke: "
    "not a push, not a smash. Sets of 20, counting the ones that land. Once 15 land, have the feed moved around.",
    "Rally at a steady, firm pace with the ball machine, or with the AI at a level you beat comfortably, and count shots "
    "in a row, starting again at every miss. Aim for runs of 10 before you go back to matches.",
    'At the level of your matches won',
    'Close to the level of your matches won',
    'Every item is at the level of the matches you won. Time to move the targets.',
    'At or close to the level of the matches you won. Nothing to drill here; keep doing it.',
    'Match against the AI, level {0}',
    'Session {0} against the AI, level {1}',
    'AI matches',
    '{name} (level {lv})',
    '{1}, level {2}',
    'AI level',
    'Level',
    'Angle off your bat, degrees above level',
}

_EN = [(re.compile(r"\bThe AI's"), "Your opponent's"), (re.compile(r"\bthe AI's"), "your opponent's"),
       (re.compile(r'\bThe AI\b'), 'Your opponent'), (re.compile(r'\bthe AI\b'), 'your opponent'),
       (re.compile(r'\ban AI\b'), "an opponent's"), (re.compile(r"^AI\b"), 'Opponent'), (re.compile(r'\bAI\b'), 'opponent')]
# Chinese sets no space between its own words, but one around a Latin word: the spaces go with the word
_ZH = re.compile(r'(?<=[^\x00-\x7f]) ?AI ?(?=[^\x00-\x7f])|^AI ?(?=[^\x00-\x7f])|(?<=[^\x00-\x7f]) ?AI$|\bAI\b')


_BY_LENGTH = sorted(PHRASES, key=lambda ph: -len(ph[0]))


def pair(key, zh=None):
    """A sentence for the online side: (English, Chinese) from its English, which is also its key, and its Chinese."""
    en, zh = _pair(key, zh)
    return en.replace(AI, 'AI'), zh.replace(AI, 'AI')


def _pair(key, zh=None):
    zh = key if zh is None else zh
    if key in KEEP:
        return key, zh
    en = key
    for old, new, old_zh, new_zh in _BY_LENGTH:
        if old in en:
            en = en.replace(old, new)
            if old_zh and old_zh in zh:
                zh = zh.replace(old_zh, new_zh)
    for pat, new in _EN:
        en = pat.sub(new, en)
    return en, _ZH.sub('對手', zh)


def en(key):
    return pair(key)[0]


LEFT_EN = re.compile(r'\bAI\b|[Ll]evel')
LEFT_ZH = re.compile(r'AI|等級')


def sentences():
    """Every sentence of the dashboard as (section, English, Chinese): the page's, its scripts' and the builder's."""
    from . import i18n
    cat = i18n.catalog()
    found = {'page': i18n.page_keys(), 'script': i18n.script_keys() | set(cat['script']), 'data': i18n.data_keys()}
    return [(sect, k, cat[sect].get(k, k)) for sect in i18n.SECTIONS for k in sorted(found[sect])]


def check(out=sys.stdout):
    bad, used = 0, set()
    for sect, key, zh in sentences():
        p_en, p_zh = _pair(key, zh)
        used.update(i for i, ph in enumerate(PHRASES) if ph[0] in key)
        if key not in KEEP and (LEFT_EN.search(p_en) or LEFT_ZH.search(p_zh)):
            bad += 1
            print(f'{sect}: still names the AI or a level\n  {p_en}\n  {p_zh}', file=out)
        if key not in KEEP and p_en != key and p_zh == zh and zh != key:      # the Chinese may name the AI where the English does not
            bad += 1
            print(f'{sect}: changed in English only\n  {key}\n  {p_en}\n  {zh}\n  {p_zh}', file=out)
    for i, ph in enumerate(PHRASES):
        if i not in used:
            bad += 1
            print(f'phrase in no sentence: {ph[0]}', file=out)
    keys = {k for _, k, _ in sentences()}
    for k in sorted(KEEP - keys):
        bad += 1
        print(f'kept sentence that is gone: {k}', file=out)
    print(f'voice: {bad} to fix', file=out)
    return bad


def listing(out=sys.stdout):
    for sect, key, zh in sentences():
        p_en, p_zh = pair(key, zh)
        if (p_en, p_zh) != (key, zh):
            print(f'[{sect}]\n  {key}\n  {p_en}\n  {zh}\n  {p_zh}', file=out)


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except (AttributeError, ValueError):
        pass
    if sys.argv[1:] == ['list']:
        listing()
    else:
        sys.exit(1 if check() else 0)
