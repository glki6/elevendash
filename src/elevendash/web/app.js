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
    rebuild: $('ed-rebuild'), version: $('ed-version'), phone: $('ed-phone'), phoneOn: $('ed-phone-on'),
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

  const render = (s) => {
    last = s;
    // on the phone the bar leaves out what only makes sense at the computer: its folders, shortcuts and the phone link
    bar.home.textContent = s.home || '';
    bar.home.parentElement.hidden = bar.folder.hidden = !s.home;
    if (s.home) document.querySelectorAll('.ed-home-text').forEach((el) => (el.textContent = s.home));
    bar.phone.hidden = !!s.remote;
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
