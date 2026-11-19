// elevendash app (app.py): the bar above the dashboard. Import asks the app to copy new logs from the Quest (or the
// files picked) and rebuild; when it has new data the page reloads, and says what came in.
(() => {
  const A = window.__elevendashApp;
  const $ = (id) => document.getElementById(id);
  const zh = () => document.documentElement.lang === 'zh-Hant';
  const DONE = 'elevendash.app.done';
  const bar = {
    imp: $('ed-import'), files: $('ed-files'), input: $('ed-file-input'), msg: $('ed-msg'), setBtn: $('ed-set-btn'),
    set: $('ed-set'), help: $('ed-help'), log: $('ed-log'), quest: $('ed-quest'), hand: $('ed-hand'), theme: $('ed-theme'),
    lang: $('ed-lang'), setMsg: $('ed-set-msg'), home: $('ed-home'), folder: $('ed-folder'), shortcut: $('ed-shortcut'),
    rebuild: $('ed-rebuild'), version: $('ed-version'), quit: $('ed-quit'), phone: $('ed-phone'), phoneOn: $('ed-phone-on'),
    phoneBody: $('ed-phone-body'), phoneUrl: $('ed-phone-url'), phoneCopy: $('ed-phone-copy'), phoneNew: $('ed-phone-new'),
    phoneStartRow: $('ed-phone-startup-row'), phoneStart: $('ed-phone-startup'), phoneMsg: $('ed-phone-msg'), phoneQr: $('ed-phone-qr'),
  };
  let last = null;            // the last status
  let seq = null;             // jobs finished when this page first asked
  let mine = false;           // this page started the running job
  let timer = 0;
  let stopped = false;

  // a message in both languages; the page's language picks which shows
  const say = (el, en, zhText, cls) => {
    const a = document.createElement('span');
    a.dataset.l = 'en';
    a.textContent = en;
    const b = document.createElement('span');
    b.dataset.l = 'zh';
    b.lang = 'zh-Hant';
    b.textContent = zhText;
    el.replaceChildren(a, b);
    el.className = 'ed-app-msg' + (cls ? ' ' + cls : '');
  };
  const when = (iso) => {
    const d = new Date(iso);
    if (isNaN(d)) return '';
    return d.toLocaleString(zh() ? 'zh-Hant' : undefined, {weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit'});
  };
  const plural = (n, one, many) => n + ' ' + (n === 1 ? one : many);

  const idle = (s) => {
    if (!s.logs) return say(bar.msg, 'No logs yet.', '還沒有記錄。');
    const t = s.last_import ? when(s.last_import) : '';
    if (t) say(bar.msg, `${plural(s.logs, 'log', 'logs')} · last import ${t}`, `${s.logs} 個記錄 · 上次匯入 ${t}`);
    else say(bar.msg, plural(s.logs, 'log', 'logs'), `${s.logs} 個記錄`);
  };

  const showLog = (lines, open) => {
    bar.log.textContent = (lines || []).join('\n');
    bar.log.hidden = !open || !bar.log.textContent;
    bar.log.scrollTop = bar.log.scrollHeight;
  };

  const busy = (s) => {
    [bar.imp, bar.files, bar.rebuild].forEach((b) => (b.disabled = true));
    const step = (s.lines || []).filter((l) => l.trim()).slice(-1)[0] || '';
    const what = s.kind === 'site' ? ['Redrawing the dashboard…', '正在重繪儀表板…'] : s.kind === 'rebuild'
      ? ['Rebuilding from the logs…', '正在從記錄重新建立…'] : ['Importing…', '正在匯入…'];
    say(bar.msg, what[0] + (step ? ' ' + step.trim() : ''), what[1] + (step ? ' ' + step.trim() : ''));
    showLog(s.lines, mine);
  };

  const finished = (s) => {
    const r = s.result || {};
    [bar.imp, bar.files, bar.rebuild].forEach((b) => (b.disabled = false));
    showLog(s.lines, false);
    if (r.ok && r.changed) {
      try {
        sessionStorage.setItem(DONE, JSON.stringify(r));
      } catch (e) {
        // the message is lost, the reload is not
      }
      say(bar.msg, 'Done. Loading your dashboard…', '完成，正在載入儀表板…', 'ok');
      setTimeout(() => location.reload(), 300);
      return true;
    }
    bar.help.hidden = r.code !== 'unreachable';
    if (r.code === 'nothing') {
      say(bar.msg, 'No new logs on the Quest. Play a session and import again.', '頭戴裝置上沒有新記錄。打完一場再匯入。', 'ok');
      if (s.kind === 'files') say(bar.msg, 'Those logs are already in.', '這些記錄已經匯入過了。', 'ok');
    } else if (r.code === 'need_quest') {
      say(bar.msg, "Enter the Quest's address in Settings first.", '請先在「設定」中輸入頭戴裝置位址。', 'bad');
      openSettings(true);
    } else if (r.code === 'unreachable') {
      say(bar.msg, 'The Quest did not answer.', '頭戴裝置沒有回應。', 'bad');
    } else if (!r.ok) {
      say(bar.msg, 'Something went wrong. The details are below.', '發生錯誤，詳情如下。', 'bad');
      showLog(s.lines, true);
    }
    return false;
  };

  // The import report: logs the last build could not read as usual, and why (health.py). Hidden until there is one;
  // Hide puts it away until the next build has something to say.
  const HID = 'elevendash.app.report';
  const two = (en, zhText) => {
    const a = document.createElement('span'), b = document.createElement('span');
    a.dataset.l = 'en';
    a.textContent = en;
    b.dataset.l = 'zh';
    b.lang = 'zh-Hant';
    b.textContent = zhText;
    return [a, b];
  };
  const showReport = (rep) => {
    const box = $('ed-report');
    if (!box) return;
    const names = rep && rep.problems ? Object.keys(rep.problems) : [];
    let hid = '';
    try {
      hid = sessionStorage.getItem(HID) || '';
    } catch (e) {
      // shown again, then
    }
    box.hidden = !names.length || hid === rep.at;
    if (box.hidden) return;
    $('ed-report-head').replaceChildren(...two(names.length === 1 ? '1 log did not read as expected' : `${names.length} logs did not read as expected`,
      `有 ${names.length} 個記錄的讀取結果不如預期`));
    $('ed-report-list').replaceChildren(...names.map((n) => {
      const li = document.createElement('li'), code = document.createElement('code');
      code.textContent = n;
      li.append(code, ': ', ...two(rep.problems[n].map((p) => p.en).join('; '), rep.problems[n].map((p) => p.zh).join('；')));
      return li;
    }));
    $('ed-report-hide').onclick = () => {
      try {
        sessionStorage.setItem(HID, rep.at);
      } catch (e) {
        // hidden for this page only
      }
      box.hidden = true;
    };
  };

  // The welcome page's guide: check the headset connection step by step (the app asks the headset for its list of
  // logs, nothing else), then import.
  const guide = {form: $('ed-guide-form'), quest: $('ed-guide-quest'), check: $('ed-guide-check'), list: $('ed-guide-checks'), imp: $('ed-guide-import')};
  const STEPS = [
    ['address', ['That is an address.', '位址格式正確。'],
      ['That does not look like an address. It is numbers with dots, then a colon and a number, such as 192.168.1.20:8090.', '這看起來不像位址。位址是用點分隔的數字，加上冒號和一個數字，例如 192.168.1.20:8090。']],
    ['reach', ['Something answers at that address.', '該位址有回應。'],
      ['Nothing answers at that address. Is the headset awake with Eleven open, and on the same Wi-Fi as this computer? Check the numbers against the headset.', '該位址沒有回應。頭戴裝置是否醒著並開著 Eleven，而且與這部電腦連上同一個 Wi-Fi？請對照頭戴裝置上的數字。']],
    ['sharing', ["It is Eleven's File Sharing.", '這是 Eleven 的檔案分享。'],
      ["Something answers there, but it is not Eleven's File Sharing. In Eleven, start it under Settings › Network Settings › File Sharing, and check the number after the colon.", '那裡有回應，但不是 Eleven 的檔案分享。請在 Eleven 的「設定 › 網路設定 › 檔案分享」啟動它，並檢查冒號後面的數字。']],
    ['logs', null, ['File Sharing is on, but the headset has no game logs yet. Play a match, then check again.', '檔案分享已啟動，但頭戴裝置上還沒有遊戲記錄。打一場比賽後再檢查一次。']],
  ];
  const showChecks = (r) => {
    const by = new Map((r.steps || []).map((s) => [s.step, s]));
    guide.list.hidden = false;
    guide.list.replaceChildren(...STEPS.map(([id, ok, bad]) => {
      const s = by.get(id), li = document.createElement('li'), mark = document.createElement('b');
      li.className = !s ? 'wait' : s.ok ? 'ok' : 'bad';
      mark.textContent = !s ? '·' : s.ok ? '✓' : '✗';
      mark.setAttribute('aria-hidden', 'true');
      const text = !s ? ['Not checked yet.', '尚未檢查。'] : !s.ok ? bad
        : ok || [r.logs === 1 ? '1 game log found.' : `${r.logs} game logs found.`, `找到 ${r.logs} 個遊戲記錄。`];
      const span = document.createElement('span');
      span.append(...two(text[0], text[1]));
      li.append(mark, span);
      return li;
    }));
    guide.imp.disabled = !r.ok;
    if (r.ok) guide.imp.focus();
  };
  if (guide.form) {
    guide.form.addEventListener('submit', async (e) => {
      e.preventDefault();
      guide.check.disabled = true;
      guide.imp.disabled = true;
      try {
        const r = await A.api('POST', '/api/check', {quest: guide.quest.value});
        if (r.host) guide.quest.value = r.host;
        showChecks(r);
      } catch (err) {
        showChecks({steps: [], ok: false});
        say(bar.msg, 'The check could not run: ' + err.message, '無法檢查：' + err.message, 'bad');
      }
      guide.check.disabled = false;
    });
    guide.imp.addEventListener('click', async () => {
      guide.imp.disabled = true;
      try {
        render(await A.api('POST', '/api/settings', {quest: guide.quest.value}));
        start('quest');
      } catch (err) {
        guide.imp.disabled = false;
        say(bar.msg, err.message, err.message, 'bad');
      }
    });
  }

  const render = (s) => {
    last = s;
    showReport(s.report);
    if (guide.quest && s.quest && !guide.quest.value && document.activeElement !== guide.quest) guide.quest.value = s.quest;
    // on the phone the bar leaves out what only makes sense at the computer: its folders, shortcuts and the phone link
    bar.home.textContent = s.home || '';
    bar.home.parentElement.hidden = bar.folder.hidden = !s.home;
    if (s.home) document.querySelectorAll('.ed-home-text').forEach((el) => (el.textContent = s.home));
    bar.phone.hidden = bar.quit.hidden = !!s.remote;
    bar.version.textContent = 'elevendash ' + s.version;
    bar.shortcut.hidden = !s.shortcut;
    bar.rebuild.hidden = !s.logs;
    if (document.activeElement !== bar.quest && bar.set.hidden) {
      bar.quest.value = s.quest || '';
      bar.hand.value = s.settings.hand;
      bar.theme.value = s.settings.theme;
      bar.lang.value = s.settings.lang;
    }
    if (s.busy) return busy(s);
    if (seq !== null && s.seq !== seq && mine) {
      seq = s.seq;
      mine = false;
      if (finished(s)) return;
    } else {
      const other = seq !== null && s.seq !== seq && s.result && s.result.ok && s.result.changed;
      seq = s.seq;
      [bar.imp, bar.files, bar.rebuild].forEach((b) => (b.disabled = false));
      if (other) return say(bar.msg, 'New data came in from another tab. Reload this page to see it.', '另一個分頁匯入了新資料，重新載入此頁即可看到。', 'ok');
      if (!bar.msg.classList.contains('bad') && !bar.msg.classList.contains('ok')) idle(s);
    }
  };

  const poll = async () => {
    clearTimeout(timer);
    try {
      const s = await A.api('GET', '/api/status');
      stopped = false;
      render(s);
      timer = setTimeout(poll, s.busy ? 800 : 30000);
    } catch (e) {
      if (!stopped) {
        stopped = true;
        [bar.imp, bar.files, bar.rebuild].forEach((b) => (b.disabled = true));
        say(bar.msg, 'The app has stopped. Open Eleven Dashboard again to import.', '程式已停止。請重新開啟 Eleven 儀表板再匯入。', 'bad');
      }
      timer = setTimeout(poll, 30000);
    }
  };

  const start = async (source) => {
    bar.help.hidden = true;
    bar.msg.className = 'ed-app-msg';
    mine = true;
    try {
      const s = await A.api('POST', '/api/import', {source});
      if (s.httpStatus === 409) mine = false;      // another tab's job: follow it, it is not ours to report
      render(s);
    } catch (e) {
      mine = false;
      say(bar.msg, 'Could not start: ' + e.message, '無法開始：' + e.message, 'bad');
    }
    poll();
  };

  bar.imp.addEventListener('click', () => {
    if (last && !last.quest) {
      say(bar.msg, "Enter the Quest's address in Settings first.", '請先在「設定」中輸入頭戴裝置位址。', 'bad');
      return openSettings(true);
    }
    start('quest');
  });
  bar.rebuild.addEventListener('click', () => start('rebuild'));
  bar.files.addEventListener('click', () => bar.input.click());
  bar.input.addEventListener('change', async () => {
    const files = [...bar.input.files];
    bar.input.value = '';
    if (!files.length) return;
    const ok = files.filter((f) => /^ALL-\d{2}\.\d{2}\.\d{4}\.\d{1,2}\.\d{2}\.\d{2}\.(AM|PM)\.log$/.test(f.name));
    if (!ok.length) {
      return say(bar.msg, 'Those are not game logs. They are named like ALL-11.17.2026.3.31.58.PM.log.',
        '這些不是遊戲記錄。遊戲記錄的檔名像 ALL-11.17.2026.3.31.58.PM.log。', 'bad');
    }
    [bar.imp, bar.files].forEach((b) => (b.disabled = true));
    try {
      for (let i = 0; i < ok.length; i++) {
        say(bar.msg, `Copying ${i + 1} of ${ok.length}…`, `正在複製第 ${i + 1} 個，共 ${ok.length} 個…`);
        await A.api('POST', '/api/upload?name=' + encodeURIComponent(ok[i].name), undefined, ok[i]);
      }
    } catch (e) {
      [bar.imp, bar.files].forEach((b) => (b.disabled = false));
      return say(bar.msg, 'Copying failed: ' + e.message, '複製失敗：' + e.message, 'bad');
    }
    start('files');
  });

  // the phone link (Settings, on the computer only): a second address on this computer's Tailscale IP
  let phoneTimer = 0;
  const showPhone = (v) => {
    clearTimeout(phoneTimer);
    bar.phoneOn.checked = v.on;
    bar.phoneBody.hidden = bar.phoneQr.hidden = !v.listening;
    bar.phoneUrl.textContent = v.url;
    bar.phoneQr.innerHTML = v.qr;              // an SVG this app drew itself (qr.py)
    bar.phoneStartRow.hidden = !v.startup_possible;
    bar.phoneStart.checked = v.startup;
    if (v.on && !v.listening) {
      if (v.error) say(bar.phoneMsg, `Not ready: ${v.error}. Is Tailscale on? Trying again every half minute.`, `尚未就緒：${v.error}。Tailscale 開著嗎？每半分鐘會再試一次。`, 'bad');
      else say(bar.phoneMsg, 'Starting…', '正在啟動…');
      if (!bar.set.hidden) phoneTimer = setTimeout(loadPhone, 3000);
    } else if (!bar.phoneMsg.classList.contains('ok')) {
      bar.phoneMsg.textContent = '';
    }
  };
  const loadPhone = async () => {
    if (last && last.remote) return;
    try {
      showPhone(await A.api('GET', '/api/phone'));
    } catch (e) {
      say(bar.phoneMsg, e.message, e.message, 'bad');
    }
  };
  const setPhone = async (body, en, z) => {
    bar.phoneMsg.className = 'ed-app-msg';
    try {
      const v = await A.api('POST', '/api/phone', body);
      if (en) say(bar.phoneMsg, en, z, 'ok');
      showPhone(v);
    } catch (e) {
      say(bar.phoneMsg, e.message, e.message, 'bad');
      loadPhone();
    }
  };
  bar.phoneOn.addEventListener('change', () => setPhone({on: bar.phoneOn.checked}));
  bar.phoneNew.addEventListener('click', () => setPhone({new_key: true}, 'New link made. Scan the code again on your phone.', '已建立新連結。請在手機上再掃描一次。'));
  bar.phoneStart.addEventListener('change', () => setPhone({startup: bar.phoneStart.checked},
    bar.phoneStart.checked ? 'It will start when you sign in to Windows.' : 'It will no longer start with Windows.',
    bar.phoneStart.checked ? '登入 Windows 時會自動啟動。' : '不再隨 Windows 啟動。'));
  bar.phoneCopy.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(bar.phoneUrl.textContent);
      say(bar.phoneMsg, 'Link copied.', '已複製連結。', 'ok');
    } catch (e) {
      getSelection().selectAllChildren(bar.phoneUrl);
    }
  });

  const openSettings = (focusQuest) => {
    bar.set.hidden = false;
    bar.setBtn.setAttribute('aria-expanded', 'true');
    loadPhone();
    if (focusQuest) bar.quest.focus();
  };
  bar.setBtn.addEventListener('click', () => {
    const open = bar.set.hidden;
    if (open && last) render(last);
    bar.set.hidden = !open;
    bar.setBtn.setAttribute('aria-expanded', String(open));
    bar.setMsg.textContent = '';
    bar.phoneMsg.textContent = '';
    bar.phoneMsg.className = 'ed-app-msg';
    if (open) loadPhone();
  });
  bar.set.addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
      const s = await A.api('POST', '/api/settings', {quest: bar.quest.value, hand: bar.hand.value, theme: bar.theme.value, lang: bar.lang.value});
      say(bar.setMsg, 'Saved.', '已儲存。', 'ok');
      if (s.started) {
        mine = true;
        bar.set.hidden = true;
        bar.setBtn.setAttribute('aria-expanded', 'false');
      }
      render(s);
      poll();
    } catch (err) {
      say(bar.setMsg, err.message, err.message, 'bad');
    }
  });
  bar.folder.addEventListener('click', () => A.api('POST', '/api/folder').catch(() => {}));
  bar.quit.addEventListener('click', async () => {
    try {
      await A.api('POST', '/api/quit');
      clearTimeout(timer);
      stopped = true;
      [bar.imp, bar.files, bar.rebuild].forEach((b) => (b.disabled = true));
      say(bar.setMsg, 'Stopped. Open Eleven Dashboard again to use it.', '已結束。要使用時請重新開啟 Eleven 儀表板。', 'ok');
      say(bar.msg, 'The app has stopped.', '程式已停止。', 'bad');
    } catch (err) {
      say(bar.setMsg, err.message, err.message, 'bad');
    }
  });
  bar.shortcut.addEventListener('click', async () => {
    try {
      await A.api('POST', '/api/shortcut');
      say(bar.setMsg, 'Added to the Start menu and the desktop.', '已加到開始功能表和桌面。', 'ok');
    } catch (err) {
      say(bar.setMsg, err.message, err.message, 'bad');
    }
  });

  // after a reload that an import caused: say what came in
  try {
    const r = JSON.parse(sessionStorage.getItem(DONE) || 'null');
    sessionStorage.removeItem(DONE);
    if (r) {
      const head = (r.headline || []).join(' · ');
      const n = r.new || 0;
      const en = (n ? `Imported ${plural(n, 'log', 'logs')}. ` : 'Rebuilt. ') + head;
      const z = (n ? `已匯入 ${n} 個記錄。` : '已重新建立。') + head;
      say(bar.msg, en, z, 'ok');
    }
  } catch (e) {
    // nothing to say
  }
  poll();
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) poll();
  });
})();
