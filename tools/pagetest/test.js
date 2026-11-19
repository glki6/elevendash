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
  const SECTIONS = ['area-overview', 'ov-findings', 'session', 'match', 'progress', 'form', 'won-lost', 'pick', 'records-part', 'findings', 'points-end', 'serve',
    'shots', 'strokes', 'plan', 'works', 'journal-part'];
  // on screen: laid out, and not put out of sight with its area or its part
  const seen = (e) => !!e && e.getClientRects().length > 0 && getComputedStyle(e).visibility !== 'hidden' && e.getBoundingClientRect().height > 0;

  const run = async () => {
    // 1. the page draws, with no script errors
    const drawn = await until(() => root.dataset.edDrawn, 30000);
    check('the page draws', drawn === '0', 'data-ed-drawn=' + drawn + ' ' + (window.__errors || []).join(' | '));
    if (drawn !== '0') return;
    const ER = window.ER;

    // 2. every section holds something, and nothing says it failed to load
    for (const id of SECTIONS) {
      const s = q('#' + id);
      check('section ' + id, s && s.textContent.trim().length > 40, s ? s.textContent.trim().length + ' characters' : 'not in the page');
    }
    check('nothing failed to load', qa('.er-fail').length === 0, qa('.er-fail').length);
    // a style that sets display must not bring back what the page has hidden
    const showing = () => qa('.er-page [hidden]').filter((e) => e.getClientRects().length);
    check('nothing hidden shows', showing().length === 0, showing().slice(0, 3).map((e) => e.className || e.id || e.tagName).join(', '));

    // 2a. areas: the bar shows one area at a time and the address names it; a part shows only what belongs to it;
    //     a card brings its area and its part with it, and the browser's Back returns
    {
      const areas = qa('.er-area'), tabs = qa('.er-areatab');
      let bad = '';
      for (const t of tabs) {
        t.click();
        await wait(60);
        const on = areas.filter(seen), a = t.dataset.go;
        if (on.length !== 1 || on[0].dataset.area !== a || ER.area() !== a || t.getAttribute('aria-current') !== 'page') bad += ' ' + a;
        if (location.protocol !== 'file:' && (a === 'overview' ? location.hash.includes('area=') : !location.hash.includes('area=' + a))) bad += ' address:' + a;
        if (qa('.er-areatab[aria-current],.er-bottab[aria-current]').length !== 2) bad += ' marked:' + a;
      }
      check('areas: one on screen at a time, named in the address', tabs.length === 6 && areas.length === 6 && !bad, tabs.length + ' areas' + (bad ? '; wrong:' + bad : ''));
      bad = '';
      let parts = 0;
      for (const a of areas) {
        for (const b of [...a.querySelectorAll('button[data-part]')].filter((x) => x.dataset.part)) {
          ER.go({area: a.dataset.area, part: b.dataset.part});
          await wait(40);
          parts += 1;
          const tagged = [...a.querySelectorAll('[data-part]:not(button)')];
          const wrong = tagged.filter((e) => {
            const off = !e.dataset.part.split(' ').includes(b.dataset.part);
            return e.classList.contains('er-off') !== off || (off && seen(e));
          });
          if (wrong.length || !tagged.some(seen) || b.getAttribute('aria-pressed') !== 'true') bad += ` ${a.dataset.area}/${b.dataset.part}`;
        }
        ER.go({area: a.dataset.area, part: ''});
        await wait(40);
        if (a.querySelector('.er-off')) bad += ` ${a.dataset.area}/all`;
      }
      check('areas: a part shows what belongs to it', parts >= 15 && !bad, parts + ' parts' + (bad ? '; wrong:' + bad : ''));
      ER.go({area: 'overview', part: ''});
      await wait(40);
      ER.goto(q('#shots-find'));
      await wait(80);
      const there = ER.area() === 'shots' && seen(q('#shots-find')) && !seen(q('#area-overview'));
      history.back();
      const backed = await until(() => ER.area() === 'overview' && seen(q('#area-overview')) && !seen(q('#shots-find')), 3000);
      check('areas: a card brings its area, and Back returns', there && backed, ER.area());
      ER.go({area: 'shots', part: 'misses'});
      await wait(40);
      const hid = !seen(q('#shots-find'));
      ER.goto(q('#shots-find'));
      await wait(60);
      check('areas: a card brings its part', hid && ER.part() === 'explorer' && seen(q('#shots-find')), ER.part());
      const jump = q('#area-overview [data-jump="plan"]');
      ER.go({area: 'overview', part: ''});
      await wait(40);
      const steps = ER.trail();
      jump.click();
      await wait(80);
      check('areas: the Overview opens a card where it lives', ER.area() === 'coaching' && seen(q('#plan')), ER.area());
      // the jump leaves a way back, which returns to the Overview and then goes
      const way = !q('#back-btn').hidden && seen(q('#back-btn')) && q('#back-btn').textContent.length > 4;
      q('#back-btn').click();
      await wait(80);
      const back = ER.area() === 'overview' && seen(q('#area-overview')) && ER.trail() === steps;
      // picking an area yourself clears it
      q('.er-areatab[data-go="progress"]').click();
      await wait(60);
      check('areas: a jump leaves a way back', way && back && ER.trail() === 0 && q('#back-btn').hidden, ER.area() + ', steps back: ' + ER.trail());
      // the finder lists what is in the area on screen, follows the part, and takes you to a heading
      ER.go({area: 'progress', part: ''});
      await wait(120);
      const all = ER.finder.heads();
      ER.go({area: 'progress', part: 'records'});
      await wait(120);
      const some = ER.finder.heads();
      ER.go({area: 'tactics', part: ''});
      await wait(120);
      window.scrollTo(0, 0);
      q('#find .er-finderbtn').click();
      const items = qa('#find .er-findermenu button');
      const names = items.map((b) => b.textContent);
      const last = items[items.length - 1];
      const opened = !q('#find .er-findermenu').hidden && items.length >= 8 && names.every((s) => s && s === s.trim());
      if (last) last.click();
      const went = await until(() => window.scrollY > 600 && q('#find .er-findermenu').hidden, 3000);
      check('areas: the finder lists the area and jumps to a heading', all >= 8 && some < all && opened && !!went,
        all + ' headings, ' + some + ' in a part, ' + items.length + ' listed, at ' + Math.round(window.scrollY));
      window.scrollTo(0, 0);
      // motion: the area that comes on screen has settled within a second, and the line sits under its tab
      ER.go({area: 'coaching', part: ''});
      const moving = () => q('#area-coaching').getAnimations({subtree: true}).filter((x) => ['er-rise', 'er-sweep'].includes(x.animationName) && x.playState === 'running').length;
      const began = moving();
      await wait(1000);
      const line = q('.er-areas .er-ink'), tab = q('.er-areatab[aria-current=page]');
      const under = !tab.offsetWidth || (!!line && Math.abs(line.getBoundingClientRect().left - tab.getBoundingClientRect().left) < 2
        && Math.abs(line.getBoundingClientRect().width - tab.offsetWidth) < 2);
      const calmed = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      check('motion: an area rises into place and settles', (calmed || began > 0) && moving() === 0 && under && getComputedStyle(q('#area-coaching h1')).opacity === '1',
        began + ' moving at first, ' + moving() + ' after a second');
      // a title does not repeat the tab: the name is kept for a screen reader and the PDF, and a line of its own shows
      const titles = qa('.er-area h1');
      const kept = titles.every((h) => { const n = h.querySelector('.er-areaname'); return !!n && n.textContent.trim() && n.offsetWidth <= 1; });
      const said = titles.every((h) => { const s = h.querySelector('.er-areasay'); return !!s && s.textContent.trim().length > 12; });
      const led = q('#area-overview .er-areasay').textContent, titleLine = q('#area-coaching .er-areasay').innerText.trim();
      check('areas: a title says more than the tab above it', titles.length === 6 && kept && said && titleLine.length > 12 && led.replace(/[^0-9]/g, '').length >= 2,
        titles.length + ' titles, names kept ' + kept + ', lines ' + said);
      // the dock on a phone (the frame made narrow): at the foot of the screen, aside on the way down, back on the way up
      const shell = q('.er-shell'), bot = q('#bot');
      shell.style.maxWidth = '420px';
      ER.go({area: 'tactics', part: ''});
      await wait(400);
      const atFoot = () => Math.abs(bot.getBoundingClientRect().bottom - window.innerHeight) < 2;
      const aside = () => q('#page').classList.contains('er-dockoff');
      const docked = bot.offsetHeight > 40 && atFoot() && !aside();
      window.scrollTo(0, 900);
      const wentOff = await until(() => aside(), 2000);
      window.scrollTo(0, 700);
      const cameBack = await until(() => !aside(), 2000);
      await wait(400);
      const footAgain = atFoot() && getComputedStyle(bot).opacity === '1';
      window.scrollTo(0, 1300);
      await until(() => aside(), 2000);
      ER.go({area: 'coaching', part: ''});
      await wait(200);
      const fresh = !aside();
      shell.style.maxWidth = '';
      window.scrollTo(0, 0);
      await wait(300);
      check('areas: the phone dock stays at the foot, steps aside going down and returns going up', docked && !!wentOff && !!cameBack && footAgain && fresh,
        'docked ' + docked + ', aside ' + !!wentOff + ', back ' + !!cameBack + ', at the foot ' + footAgain + ', shown in a new area ' + fresh);
      ER.go({area: 'overview', part: ''});
      await wait(60);
    }

    // 2b. plan history: every item has a square for each session at the plan's level, as the plan stood after it
    {
      const hist = await until(() => ER.planHistory()), rows = qa('[data-draw="plan-history"] .er-phitem');
      const prog = ER.rows('plan_progress') || [];
      const square = hist && hist.length && rows.length === hist.length && hist.every((h, i) => h.cells.length === hist[0].cells.length
        && rows[i].querySelectorAll('.er-phstrip i').length === h.cells.length && rows[i].querySelectorAll('.er-phstrip i.s1').length === h.on
        && rows[i].querySelector('p').textContent.trim().length > 10);
      const agree = hist && hist.every((h) => {
        const g = prog.find((x) => x.key === h.r.key), first = h.runs[0];
        return g && g.states === h.cells.map((c) => c.state).join('') && (first ? g.ever === 1 && h.cells[first.from].session === g.session : g.ever === 0);
      });
      check('plan history: a square a session, as the plan stood', square && agree, hist ? hist.length + ' items, ' + (hist[0] ? hist[0].cells.length : 0) + ' sessions' + (square ? '' : '; squares off') + (agree ? '' : '; not the plan progress') : 'no history');
    }

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

    // 4b2. where your shots land: the parts add up, and a row lists exactly its shots
    {
      const s0 = ER.shots.chosen(), c = ER.shots.landSum(s0);
      const sum = (g, vs) => vs.reduce((a, v) => a + c.get(g + ':' + v).n, 0);
      const cells = ['L', 'M', 'R'].flatMap((x) => ['s', 'h', 'l'].map((d) => x + d));
      const adds = c.n === s0.lands.length && sum('cell', cells) === c.n && sum('dep', ['s', 'h', 'l']) === c.n && sum('col', ['L', 'M', 'R']) === c.n
        && sum('dir', ['x', 'd', 'm', 'c']) === c.n && s0.lands.every((r) => r.ok && r.role !== 'S' && r.lz > 0);
      check('where your shots land: the parts add up', adds, c.n + ' shots');
      const picks = qa('[data-draw="sx-land-rows"] .er-sxpick');
      if (c.n >= 5) {
        const i = picks.findIndex((b) => !b.disabled);
        picks[i].click();
        await wait(80);
        const only = ER.shots.state.only, [, g, v] = only.split(':');
        const l = ER.shots.chosen().list;
        const listed = picks.length === 10 && l.length === c.get(g + ':' + v).n && l.length > 0 && !q('#sx-only-wrap').hidden;
        q('#sx-only-clear').click();
        await wait(80);
        const back = ER.shots.chosen().list.length === s0.base.length && q('#sx-only-wrap').hidden;
        check('where your shots land: a row lists its shots, and back', listed && back, only + ' ' + l.length);
      } else {
        check('where your shots land: a row lists its shots, and back', q('#sx-land-wrap').hidden, 'too few shots: hidden');
      }
    }

    // 4b3. your speed, spin and timing: the bands add up, and a row lists exactly its shots
    {
      const s0 = ER.shots.chosen(), c = ER.shots.hitSum(s0);
      const sum = (g, vs) => vs.reduce((a, v) => a + c.get(g + ':' + v).n, 0);
      const cells = [0, 1, 2, 3, 4, 5].flatMap((x) => [0, 1, 2, 3, 4].map((y) => '' + x + y));
      const adds = c.n === s0.hits.length && sum('spd', [0, 1, 2, 3, 4, 5]) === c.n && sum('cell', cells) === c.n && sum('rise', ['r', 'f']) <= c.n
        && sum('since', [0, 1, 2, 3, 4]) <= c.n && c.ok === s0.hits.filter((r) => r.ok).length && s0.hits.every((r) => r.shot !== 'X' && r.role !== 'S');
      check('speed, spin and timing: the bands add up', adds, c.n + ' shots');
      const picks = qa('[data-draw="sx-hit-rows"] .er-sxpick');
      if (c.n >= 5) {
        const i = picks.findIndex((b) => !b.disabled);
        picks[i].click();
        await wait(80);
        const only = ER.shots.state.only, [, g, v] = only.split(':');
        const l = ER.shots.chosen().list;
        const listed = picks.length === 13 && l.length === c.get(g + ':' + v).n && l.length > 0 && !q('#sx-only-wrap').hidden;
        q('#sx-only-clear').click();
        await wait(80);
        const back = ER.shots.chosen().list.length === s0.base.length && q('#sx-only-wrap').hidden;
        check('speed, spin and timing: a row lists its shots, and back', listed && back, only + ' ' + l.length);
      } else {
        check('speed, spin and timing: a row lists its shots, and back', q('#sx-hit-wrap').hidden, 'too few shots: hidden');
      }
    }

    // 4b4. these shots over time: every step holds all the shots, and a dot lists its shots
    {
      const s0 = ER.shots.chosen();
      let bad = '', seen = '';
      for (const step of ['month', 'week', 'session']) {
        q(`#sx-time-step [data-per="${step}"]`).click();
        await wait(60);
        const t = ER.shots.timeSum(ER.shots.chosen()), rows = t.rows;
        const adds = rows.reduce((a, c) => a + c.n, 0) === s0.base.length && rows.reduce((a, c) => a + c.ok, 0) === t.ok
          && rows.every((c, i) => !i || rows[i - 1].date <= c.date) && rows.every((c) => c.lo <= c.rate + 1e-9 && c.rate <= c.hi + 1e-9);
        const pressed = q('#sx-time-step [aria-pressed="true"]');
        const drawn = q('#sx-time-wrap').hidden === rows.length < 2 && qa('[data-draw="sx-time"] circle').length === (rows.length < 2 ? 0 : rows.length)
          && !!pressed && pressed.dataset.per === t.step;
        if (!adds || !drawn) bad += ' ' + step;
        seen += ' ' + rows.length;
      }
      check('over time: every step holds all the shots', !bad, 'dots:' + seen + (bad ? '; wrong:' + bad : ''));
      const t = ER.shots.timeSum(ER.shots.chosen());
      if (t.rows.length > 1) {
        qa('[data-draw="sx-time"] rect')[0].dispatchEvent(new MouseEvent('click', {bubbles: true}));
        await wait(80);
        const only = ER.shots.state.only, l = ER.shots.chosen().list;
        const listed = only === 'T:per:' + t.rows[0].key && l.length === t.rows[0].n && !q('#sx-only-wrap').hidden;
        q('#sx-only-clear').click();
        await wait(80);
        const back = ER.shots.chosen().list.length === s0.base.length && q('#sx-only-wrap').hidden;
        check('over time: a dot lists its shots, and back', listed && back, only + ' ' + l.length);
      } else {
        check('over time: a dot lists its shots, and back', q('#sx-time-wrap').hidden, 'one period: hidden');
      }
    }

    // 4b5. side by side: a landed shot and a miss on two tables, their clocks tied at your contact
    {
      const pair = ER.replay.pair, list = pair.list();
      if (!list || !list.length) {
        check('side by side: two tables in step', q('#sx-pair-go').disabled, 'no pair to show here');
      } else {
        q('#sx-pair-go').click();
        for (let i = 0; i < 40 && qa('[data-draw="sx-pair"] svg').length < 2 && !q('[data-draw="sx-pair"] p'); i += 1) await wait(150);
        const p = pair.state, two = qa('[data-draw="sx-pair"] svg.er-r3d').length === 2 && p.sides.length === 2;
        let tied = false, fair = false;
        if (two) {
          q('#sx-pair-play').click();
          await wait(40);
          if (p.playing) q('#sx-pair-play').click();
          const seek = q('#sx-pair-seek');
          seek.value = String(Math.round(1000 * (0 - p.lo) / (p.hi - p.lo)));
          seek.dispatchEvent(new Event('input', {bubbles: true}));
          await wait(40);
          tied = p.sides.every((c) => Math.abs(c.t - c.hit) < 0.01 && c.from <= c.hit && c.hit < c.to && c.hits.length === 2 && c.hits[1].you && !c.hits[0].you);
          fair = p.sides[0].rec.ok && !p.sides[1].rec.ok && p.sides[0].rec !== p.sides[1].rec && !q('#sx-pair-ctl').hidden;
        }
        // Open this point brings up the shot's own match before its replay
        let opened = !two;
        if (two) {
          const want = p.sides[1].rec;
          qa('[data-draw="sx-pair"] .er-pairside button')[1].click();
          opened = !!(await until(() => ER.matchKey() === want.m.key && shown() === want.pt.key, 10000));
          if (ER.viewer && ER.viewer.isOpen()) ER.viewer.close();
          await wait(200);
        }
        q('#sx-pair-hide').click();
        await wait(60);
        const closed = !qa('[data-draw="sx-pair"] svg').length && q('#sx-pair-ctl').hidden && !q('#sx-pair-go').hidden;
        check('side by side: two tables in step', two && tied && fair && opened && closed, list.length + ' pairs' + (two ? '' : '; not drawn') + (tied ? '' : '; clocks apart') + (opened ? '' : '; its point did not open') + (closed ? '' : '; not closed'));
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

    // 4c2. what works for you: the lists hold only what the rules allow, and a line opens its card
    {
      const w = ER.shots.works();
      const fair = w.serves.length <= 3 && w.serves.every((c, i) => c.n >= 30 && c.won * w.serve.n > w.serve.won * c.n && (!i || w.serves[i - 1].lo >= c.lo))
        && w.strokes.length <= 6 && w.strokes.every((k) => k.best.n >= 20 && k.rest.n >= 20 && k.gap > 0)
        && w.pats.length === 2 && w.pats.every((p) => p.rows.length <= 3 && p.rows.every((c) => c.move > 0 && c.n >= 30))
        && w.place.every((c) => c.wonMove > 0) && w.pace.every((c) => c.wonMove > 0) && w.att.won <= w.att.n && w.att.rest.n >= 0;
      const lis = (n) => qa(`[data-draw="${n}"] > li`).length;
      const drawn = lis('wk-serves') === Math.max(1, w.serves.length) && lis('wk-strokes') === Math.max(1, w.strokes.length)
        && lis('wk-patterns') === w.pats.reduce((a, p) => a + 1 + Math.max(1, p.rows.length), 0) && lis('wk-place') >= 1 && !!q('[data-draw="wk-note"]').textContent;
      check('what works: the lists hold only what the rules allow', fair && drawn,
        [w.serves.length, w.strokes.length, w.pats[0].rows.length, w.pats[1].rows.length, w.place.length + w.pace.length].join(' '));
      const btn = q('[data-draw="wk-strokes"] button') || q('[data-draw="wk-place"] button');
      if (btn) {
        btn.click();
        await wait(80);
        const f = ER.shots.filters, opened = !f.shot && !f.out && !f.depth && !f.pace && ER.shots.chosen().base.length > 0;
        q('#sx-clear').click();
        await wait(80);
        check('what works: a line opens its card', opened && !ER.shots.state.only && !ER.shots.filters.level, 'filters set and cleared');
      } else {
        check('what works: a line opens its card', true, 'no line to open here');
      }
    }

    // 4d. then and now: each stretch is earlier matches at the same levels, and every measure has its row
    {
      const sel = q('#then-mode');
      let bad = '', seen = 0;
      for (const mode of ['weeks4', 'same', 'before']) {
        sel.value = mode;
        sel.dispatchEvent(new Event('change'));
        await wait(60);
        const t = ER.thenNow(), a = t.a;
        if (!a.n) continue;
        const first = a.rows[0], lv = new Set(a.levels);
        const fair = t.mode === mode && t.then.every((r) => lv.has(r.level) && (r.date < first.date || (r.date === first.date && r.start <= first.start)))
          && (mode !== 'same' || t.then.length <= a.n) && (!t.rows || (t.rows.length === 12 && t.sum.pts === t.then.reduce((x, r) => x + r.points, 0)));
        const drawn = qa('[data-draw="then-rows"] tr').length === (t.rows ? 12 : 0) && q('#then-table').hidden === !t.rows;
        if (!fair || !drawn) bad += ' ' + mode;
        seen += t.then.length;
      }
      check('then and now: earlier matches at the same levels, a row for each measure', !bad, seen + ' matches then' + (bad ? '; wrong:' + bad : ''));
    }

    // 4e. training journal: an entry is kept, marked on the charts, opens its before and since, and goes again
    {
      const kept = ['account', 'browser', 'workspace'].includes(ER.notes.where());
      if (!kept) {
        check('journal: an entry is kept, marked and compared', q('#journal-add').disabled, 'notes cannot be kept here: the form is off');
      } else {
        const days = ER.rows('days'), day = days[Math.floor(days.length / 2)].date, before = ER.journal.list().length;
        q('#journal-date').value = day;
        q('#journal-kind').value = 'equipment';
        q('#journal-text').value = 'Page test entry';
        q('#journal-form').dispatchEvent(new Event('submit', {cancelable: true, bubbles: true}));
        await wait(200);
        const list = ER.journal.list(), e = list.find((x) => x.text === 'Page test entry');
        const li = () => qa('[data-draw="journal-list"] > li');
        const added = list.length === before + 1 && !!e && e.kind === 'equipment' && e.date === day && li().length === list.length
          && qa('#chart-progress .er-jmark').length >= 1 && q('#journal-text').value === '';
        li().find((x) => x.textContent.includes('Page test entry')).querySelector('[data-act="effect"]').click();
        await wait(150);
        const t = ER.journalEffect();
        const fair = !!t && t.since.every((r) => r.date >= day) && t.before.every((r) => r.date < day) && !q('#journal-effect').hidden
          && (t.rows ? t.rows.length === 12 && qa('[data-draw="journal-effect-rows"] tr').length === 12 : q('#journal-effect-table').hidden);
        const del = () => li().find((x) => x.textContent.includes('Page test entry')).querySelector('[data-act="remove"]');
        del().click();
        await wait(60);
        del().click();
        await wait(200);
        const gone = ER.journal.list().length === before && q('#journal-effect').hidden && qa('#chart-progress .er-jmark').length === before;
        check('journal: an entry is kept, marked and compared', added && fair && gone,
          (t ? t.before.length + ' matches before, ' + t.since.length + ' since' : 'no comparison') + (added ? '' : '; not added') + (fair ? '' : '; wrong table') + (gone ? '' : '; not removed'));
      }
    }

    // 4f. session goals: a goal is kept, judged on the session shown from its own counts, and goes again
    {
      const kept = ['account', 'browser', 'workspace'].includes(ER.notes.where());
      if (!kept) {
        check('goals: kept, judged on the session, removed', q('#goal-add').disabled, 'notes cannot be kept here: the form is off');
      } else {
        const before = ER.goals.list().length, li = () => qa('[data-draw="session-goals"] > li');
        ER.shots.apply1('role', 'A');
        ER.shots.apply1('spin', 't');
        await wait(80);
        const add = async (m, t) => {
          q('#goal-measure').value = m;
          q('#goal-target').value = String(t);
          q('#goal-form').dispatchEvent(new Event('submit', {cancelable: true, bubbles: true}));
          await wait(200);
        };
        const ballOn = !q('#goal-measure option[value="ball"]').disabled;
        await add('retOk', 1);
        await add('ball', 100);
        q('#sx-clear').click();
        await wait(80);
        const s = ER.sessionRow(), rows = ER.goals.forSession(s), a = rows.find((r) => r.g.m === 'retOk'), b = rows.find((r) => r.g.m === 'ball');
        const today = a && a.g.from, counts = a && a.on === (a.g.from <= s.date);
        const sums = ER.rows('match_sums'), keys = new Set(ER.rows('matches').filter((m) => m.session === s.key && (m.vs === 'AI') === !ER.people()).map((m) => m.key));
        const ret = sums.filter((r) => keys.has(r.key)).reduce((x, r) => [x[0] + r.retOk, x[1] + r.ret], [0, 0]);
        const fair = ballOn && rows.length === before + 2 && !!a && !!b && counts && b.g.q.role === 'A' && b.g.q.spin === 't' && Object.keys(b.g.q).length === 2
          && (!a.on || (a.k === ret[0] && a.n === ret[1] && (a.n < 10 ? a.met === null : a.met === true)))
          && (!b.on || (b.k <= b.n && (b.n < 10 ? b.met === null : b.met === (b.k === b.n)))) && li().length === rows.length;
        for (const text of [a && a.name, b && b.name]) {
          const del = () => li().find((x) => x.textContent.includes(text)).querySelector('[data-act="remove"]');
          del().click();
          await wait(60);
          del().click();
          await wait(200);
        }
        check('goals: kept, judged on the session, removed', fair && ER.goals.list().length === before,
          (a ? a.k + ' of ' + a.n + ' returns; ' : '') + (b ? b.k + ' of ' + b.n + ' balls' : '') + (fair ? '' : '; wrong') + ' (set ' + today + ', session ' + s.date + ')');
      }
    }

    // 4g. personal records: each is the best of its kind at the level shown, counted again here
    {
      const r = await until(() => ER.records()), d = ER.shots.data(), L = ER.level();
      const cells = qa('[data-draw="records"] > div');
      const ms = d.ms.filter((m) => m.level === L), at = new Set(ms.map((m) => m.key));
      const rally = Math.max(0, ...d.ps.filter((p) => p.won === 1 && at.has(p.match)).map((p) => p.hits));
      const fast = Math.max(0, ...d.recs.filter((x) => x.ok && x.shot !== 'X' && x.m.level === L && x.speed != null).map((x) => x.speed));
      let run = 0, best = 0;
      ms.forEach((m) => {
        run = m.result === 'Won' ? run + 1 : 0;
        best = Math.max(best, run);
      });
      const ok = r && cells.length === 4 && (r.rally ? r.rally.p.hits : 0) === rally && (r.shot ? r.shot.speed : 0) === fast && (r.run ? r.run.length : 0) === best
        && (!r.run || r.run.every((m) => m.result === 'Won' && m.level === L))
        && (!r.session || (r.session.level === L && d.ss.every((x) => x.level !== L || x.matches < 3 || x.pointRate <= r.session.pointRate)));
      check('personal records: the best of each kind', ok, r ? `rally ${rally}, shot ${fast}, run ${best}, ${cells.length} cells` : 'no records');
    }

    // 4h. your floor: one match in four of the window sits at or under it, and the chart is drawn
    {
      const f = await until(() => ER.floor());
      if (!f || !f.rows.length) {
        check('your floor: the lower quarter of the last matches', f && q('[data-draw="floor-now"]').textContent.trim().length > 10 && !q('#chart-floor svg'), 'too few matches for a run');
      } else {
        const last = f.rows[f.rows.length - 1], win = f.at.slice(-f.W), under = win.filter((x) => x.v <= last.lo).length;
        const ok = last.lo <= last.mid && under >= Math.floor(f.W / 4) && under <= Math.ceil(f.W / 2) && f.rows.length === f.at.length - f.W + 1
          && qa('#chart-floor svg path').length === 2 && qa('#chart-floor svg circle').length >= f.at.length
          && (!f.move || (f.move.a + f.move.b >= f.W / 2 - 1 && [-1, 0, 1].includes(f.move.clear)));
        check('your floor: the lower quarter of the last matches', ok, `${f.at.length} matches, ${under} of ${f.W} at or under the floor`);
      }
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
      const areaWas = ER.area(), yWas = window.scrollY;
      if (idx < rows.length && rows[idx].querySelector('button')) rows[idx].querySelector('button').click();
      else ER.set({match: other.m.key}, null, {after: () => ER.replay.show(other.pt.key, other.n, true)});
      const got = await until(() => ER.matchKey() === other.m.key && shown() === other.pt.key && q('#chart-replay svg'), 10000);
      check('a shot opens its point in the replay' + (far ? ' (another month)' : ''), got, 'on the table: ' + (shown() === other.pt.key));
      // the replay comes to the list: a window over the area you are in, with the replay's own card in it
      const over = await until(() => ER.viewer && ER.viewer.isOpen() && q('#viewer #match-replay #chart-replay svg') && !q('.er-area #match-replay'), 3000);
      check('the replay opens over the area you are in', !!over && ER.area() === areaWas && seen(q('#chart-replay')), ER.area());
      q('#viewer-close').click();
      const homed = await until(() => !ER.viewer.isOpen() && q('#area-review #match #match-replay') && !q('#viewer #match-replay'), 3000);
      check('closing it puts the replay back and leaves you at the list', !!homed && ER.area() === areaWas && Math.abs(window.scrollY - yWas) < 4,
        ER.area() + ', moved ' + Math.round(window.scrollY - yWas));
      // and it can be opened where it lives, with a way back to the list
      ER.replay.show(other.pt.key, other.n, true);
      await until(() => ER.viewer.isOpen(), 3000);
      q('#viewer-home').click();
      const lives = await until(() => !ER.viewer.isOpen() && ER.area() === 'review' && seen(q('#area-review #chart-replay')) && !q('#back-btn').hidden, 3000);
      check('the replay opens in Match review, with a way back', !!lives, ER.area() + ', steps back: ' + ER.trail());
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
    const words = () => [q('#shots h2'), q('[data-draw="sx-summary"]'), q('.er-areatab'), q('#area-shots h1')];
    ER.go({area: 'shots', part: ''});
    await wait(120);
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
      for (const id of SECTIONS) {
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
      // one area is on screen at a time: read them all
      let text = '';
      for (const a of qa('.er-area')) {
        ER.go({area: a.dataset.area, part: ''});
        await wait(150);
        text += '\n' + page.innerText;
      }
      ER.go({area: 'progress', part: ''});
      await wait(150);
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
