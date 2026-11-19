// Checks a built dashboard in a real browser. run.py adds this to a copy of site/index.html and reads the result
// the page posts to /log. It knows nothing about the matches in the file, so it runs on the demo and on your own.
(() => {
  const errs = [];
  window.addEventListener('error', (e) => errs.push(String(e.message)));
  window.addEventListener('unhandledrejection', (e) => errs.push('rejection: ' + String(e.reason)));
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const q = (s) => document.querySelector(s);
  const qa = (s) => [...document.querySelectorAll(s)];
  const until = async (fn, ms = 15000) => {
    const end = performance.now() + ms;
    for (;;) {
      let v = null;
      try {
        v = fn();
      } catch (e) {
        v = null;
      }
      if (v) return v;
      if (performance.now() > end) return null;
      await wait(40);
    }
  };
  const checks = [];
  const check = (name, ok, detail) => checks.push({name, ok: !!ok, detail: detail == null ? '' : String(detail)});
  const root = document.documentElement;
  const lazy = () => qa('script[data-lazy]');
  const unpacked = () => lazy().filter((s) => s.textContent === '').length;
  const shown = () => q('#replay-select') && q('#replay-select').value;

  const run = async () => {
    // 1. the page draws, with no script errors
    const drawn = await until(() => root.dataset.edDrawn, 30000);
    check('the page draws', drawn === '0', 'data-ed-drawn=' + drawn + ' ' + (window.__errors || []).join(' | '));
    if (drawn !== '0') return;
    const ER = window.ER;

    // 2. every section holds something, and nothing says it failed to load
    for (const id of ['session', 'match', 'plan', 'shots', 'pick', 'progress', 'form', 'findings', 'serve', 'by-level']) {
      const s = q('#' + id);
      check('section ' + id, s && s.textContent.trim().length > 40, s ? s.textContent.trim().length + ' characters' : 'not in the page');
    }
    check('nothing failed to load', qa('.er-fail').length === 0, qa('.er-fail').length);
    // a style that sets display must not bring back what the page has hidden
    const showing = () => qa('.er-page [hidden]').filter((e) => e.getClientRects().length);
    check('nothing hidden shows', showing().length === 0, showing().slice(0, 3).map((e) => e.className || e.id || e.tagName).join(', '));

    // 3. point replays: only the month of the match on screen is unpacked, and its court draws
    const months = lazy().length;
    check('the court draws', await until(() => q('#chart-replay svg')));
    check('a point is on the table', await until(shown), shown());
    if (months) check('only one month of replays is unpacked', unpacked() === 1, unpacked() + ' of ' + months);

    // 4. shot explorer: each kind of ball's two buttons pick exactly its balls
    q('#shots').scrollIntoView();
    await until(() => qa('.er-sxlist tbody tr').length);
    let groups = 0;
    const wrong = [];
    for (const scope of ['recent', 'all']) {
      const b = q(`#sx-scope [data-scope="${scope}"]`);
      if (!b) continue;
      b.click();
      await wait(120);
      const gs = ER.shots.groups();
      const lis = qa('.er-sxgroups > li');
      if (lis.length !== gs.length) wrong.push(scope + ': ' + lis.length + ' rows for ' + gs.length + ' kinds');
      for (let i = 0; i < Math.min(gs.length, lis.length); i++) {
        lis[i].querySelectorAll('button')[0].click();
        await wait(40);
        const c = ER.shots.chosen();
        const failed = c.base.filter((r) => !r.ok).length;
        const a = c.base.length === gs[i].n && failed === gs[i].failed && c.list.length === failed && c.list.every((r) => !r.ok);
        lis[i].querySelectorAll('button')[1].click();
        await wait(40);
        const c2 = ER.shots.chosen();
        const ok = a && c2.list.length === gs[i].n - gs[i].failed && c2.list.every((r) => r.ok);
        groups += 1;
        if (!ok) wrong.push(scope + ' ' + (i + 1));
      }
    }
    check('shot explorer: kinds of ball match their filters', wrong.length === 0, groups + ' checked' + (wrong.length ? '; wrong: ' + wrong.join(', ') : ''));
    q('#sx-clear').click();
    await wait(120);

    // 4b. after you attack: the lines add up, and a line lists exactly its attacks
    {
      const s0 = ER.shots.chosen(), c = ER.shots.attackSum(s0);
      const sums = c.out + c.backWon + c.backLost + c.miss === c.n && c.ok + c.nmiss + c.nx === c.back && c.n === s0.attacks.length;
      const fair = s0.attacks.every((a) => a.r.role !== 'S' && a.r.speed >= 10 && 'DLF'.includes(a.r.shot))
        && new Set(s0.attacks.map((a) => a.r.pt)).size === c.n;
      check('after you attack: the lines add up', sums && fair, c.n + ' points');
      const bars = qa('[data-draw="sx-attack"] .er-sxpick');
      if (c.n >= 5) {
        const k = ['out', 'backWon', 'backLost', 'miss'].findIndex((x) => c[x] > 0);
        const kind = ['out', 'backWon', 'backLost', 'miss'][k];
        bars[k].click();
        await wait(80);
        const l = ER.shots.chosen().list;
        const listed = bars.length === 4 && l.length === c[kind] && !q('#sx-only-wrap').hidden && ER.shots.state.only === kind;
        q('#sx-only-clear').click();
        await wait(80);
        const back = ER.shots.chosen().list.length === s0.base.length && q('#sx-only-wrap').hidden;
        check('after you attack: a line lists its attacks, and back', listed && back, kind + ' ' + c[kind]);
      } else {
        check('after you attack: a line lists its attacks, and back', q('#sx-attack-wrap').hidden, 'too few attacks: hidden');
      }
    }

    // 4c. patterns that win points: every pattern holds its points, a row lists them, and the way back leads to the card
    {
      let bad = '', rowsSeen = 0, opened = false;
      for (const who of ['serve', 'recv']) {
        for (const steps of who === 'serve' ? [2, 3] : [2, 3, 4]) {
          q(`#pat-who [data-who="${who}"]`).click();
          q(`#pat-steps [data-steps="${steps}"]`).click();
          await wait(60);
          const s = ER.shots.patterns();
          const fair = s.who === who && s.steps === steps && s.n <= s.served && s.won <= s.n
            && s.rows.every((c) => c.n >= 10 && c.pts.length === c.n && c.pts.filter((o) => o.pt.won).length === c.won
              && c.key.split('|').length === steps && c.pts.every((o) => (o.pt.served === 'You') === (who === 'serve')))
            && s.ranked.every((c) => c.n >= 30) && s.rows.reduce((a, c) => a + c.n, 0) <= s.n;
          const trs = qa('.er-pat tbody tr');
          if (!fair || trs.length !== Math.min(10, s.rows.length)) bad += ` ${who}${steps}`;
          rowsSeen += s.rows.length;
          if (trs.length && !opened) {
            trs[0].click();
            await wait(80);
            const first = ER.shots.patterns().rows.find((c) => c.key === ER.shots.patState.open);
            const listed = first && !q('#pat-points-wrap').hidden && qa('[data-draw="pat-points"] tr').length === Math.min(25, first.n);
            q('#pat-close').click();
            await wait(60);
            if (!listed || !q('#pat-points-wrap').hidden) bad += ` list:${who}${steps}`;
            opened = true;
          }
        }
      }
      check('patterns: each holds its points, and a row lists them', !bad, rowsSeen + ' patterns' + (bad ? '; wrong:' + bad : ''));
    }

    // 5. open a shot of another match from the list (of another month, when there is one): the match changes, its
    //    replays are unpacked, and the point asked for is the one on the table
    const list = ER.shots.chosen().list;
    const here = ER.matchKey();
    const other = list.find((r) => ER.replayId(r.m.key) !== ER.replayId(here)) || list.find((r) => r.m.key !== here);
    if (other) {
      const far = ER.replayId(other.m.key) !== ER.replayId(here);
      const before = unpacked();
      const idx = list.indexOf(other);
      const rows = qa('.er-sxlist tbody tr');
      if (idx < rows.length && rows[idx].querySelector('button')) rows[idx].querySelector('button').click();
      else ER.set({match: other.m.key}, null, {after: () => ER.replay.show(other.pt.key, other.n, true)});
      const got = await until(() => ER.matchKey() === other.m.key && shown() === other.pt.key && q('#chart-replay svg'), 10000);
      check('a shot opens its point in the replay' + (far ? ' (another month)' : ''), got, 'on the table: ' + (shown() === other.pt.key));
      check('the way back to the shot explorer shows', await until(() => q('#replay-back') && !q('#replay-back').hidden, 3000));
      if (far) check('the other month is unpacked when asked for', unpacked() === before + 1, unpacked() + ' of ' + months);
      await wait(300);
      if (q('#replay-play-stop') && !q('#replay-play-stop').hidden) q('#replay-play').click();
    } else {
      check('a shot opens its point in the replay', true, 'skipped: one match only');
    }

    // 6. the 3D replay, and back
    q('#replay-view [data-view="3d"]').click();
    const three = await until(() => q('#chart-replay svg.er-r3d'), 5000);
    check('the 3D replay draws', three);
    if (three) {
      const d = qa('#chart-replay svg path').map((p) => p.getAttribute('d') || '');
      check('the 3D replay has no broken paths', d.length > 5 && !d.some((s) => /NaN|Infinity|undefined/.test(s)), d.length + ' paths');
    }
    q('#replay-view [data-view="2d"]').click();
    check('back to the 2D replay', await until(() => q('#chart-replay svg') && !q('#chart-replay svg.er-r3d'), 5000));

    // 7. Chinese, and back: the page's own words (both languages are in the file, one is shown) and the drawn ones
    const cjk = (el) => /[一-鿿]/.test(el.innerText);
    const words = () => [q('#shots h2'), q('[data-draw="sx-summary"]')];
    q('#pref-lang').click();
    const zh = await until(() => root.lang === 'zh-Hant' && words().every(cjk), 5000);
    check('the page switches to Chinese', zh, words().map((e) => e.innerText.slice(0, 20)).join(' / '));
    await wait(700);
    q('#pref-lang').click();
    check('and back to English', await until(() => root.lang === 'en' && !words().some(cjk), 5000),
      root.lang + ' ' + words().map((e) => e.innerText.slice(0, 20)).join(' / '));
    await wait(200);

    // 8. the online side, when the file has matches on both sides: the switch shows it, in its own words
    const side = q('#side');
    if (side && !side.hidden) {
      const page = q('.er-page');
      q('[data-side="people"]').click();
      const on = await until(() => page.classList.contains('er-people') && q('#chart-rating svg path') && qa('[data-draw="rating-bands"] tr').length, 8000);
      check('the switch shows the online side', on, 'rating rows: ' + qa('[data-draw="rating-bands"] tr').length);
      await wait(500);
      const ms = ER.rows('matches') || [];
      check('online: only online matches are listed', ms.length > 0 && ms.every((r) => r.vs === 'Online') && ER.matchRow() && ER.matchRow().vs === 'Online', ms.length);
      for (const id of ['session', 'match', 'plan', 'shots', 'pick', 'progress', 'form', 'findings', 'serve', 'by-level']) {
        const s = q('#' + id);
        if (!(s && s.textContent.trim().length > 40)) check('online: section ' + id, false, s ? s.textContent.trim().length + ' characters' : 'not in the page');
      }
      check('online: nothing failed to load', qa('.er-fail').length === 0, qa('.er-fail').length);
      check('online: nothing hidden shows', showing().length === 0, showing().slice(0, 3).map((e) => e.className || e.id || e.tagName).join(', '));
      // what may still name the AI or a level: the way back, the drills against the AI, and a standard you reached
      const kept = ['AI matches', 'the AI at a low level', 'the AI at a level you beat', 'level of the matches you won', 'level of your matches won', 'above level',
        'Matches against the AI are not in these totals'];
      qa('details').forEach((d) => {
        d.open = true;
      });
      await wait(400);
      let text = page.innerText;
      kept.forEach((k) => {
        text = text.split(k).join('');
      });
      const left = text.match(/.{0,30}(\bAI\b|[Ll]evel|999).{0,30}/g) || [];
      check('online: no sentence names the AI or a level', left.length === 0, left.slice(0, 3).join(' | '));
      q('#pref-lang').click();
      const zhOn = await until(() => root.lang === 'zh-Hant' && cjk(q('#rating-run h3')) && cjk(q('[data-draw="rating-notes"]')), 5000);
      check('online: the page switches to Chinese', zhOn);
      await wait(500);
      q('#pref-lang').click();
      await until(() => root.lang === 'en', 5000);
      await wait(300);
      q('[data-side="ai"]').click();
      const back = await until(() => !page.classList.contains('er-people') && ER.matchRow() && ER.matchRow().vs === 'AI', 8000);
      check('and back to the AI side', back);
      await wait(300);
    }

    // 9. nothing went wrong on the way
    check('no drawing errors', (window.__errors || []).length === 0, (window.__errors || []).join(' | '));
    check('no script errors', errs.length === 0, errs.join(' | '));
  };

  const start = () => run()
    .catch((e) => check('the test itself', false, String((e && e.stack) || e)))
    .then(() => fetch('/log', {method: 'POST', body: JSON.stringify({step: 'done', ua: navigator.userAgent, checks})}));
  if (document.readyState === 'complete') start();
  else window.addEventListener('load', start);
})();
