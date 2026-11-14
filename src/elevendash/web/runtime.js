// elevendash runtime: the few things the dashboard page asks of its host (data, parameters, drawing), so the page
// works as a plain file in any browser. site.py writes the data and settings into two JSON blocks of the page.
//
// The page registers drawings with dash.draw(name, fn); every element with data-draw="name" is drawn by fn. Changing
// a parameter (level, match, session) redraws everything on the next frame. Where it matters, it behaves as the
// Claude dashboard host does, so the page can be tested here. Parameters that differ from the defaults sit in the address
// (#match=...), so a link opens the same view.
(() => {
  const read = (id) => JSON.parse(document.getElementById(id).textContent);
  // As a dashboard host does, a cell holding a list or an object reaches the page as JSON text, so the page is
  // tested here against what it gets there.
  const cell = (v) => {
    if (typeof v !== 'object' || v === null) return v;
    if (!Array.isArray(v) && Object.prototype.hasOwnProperty.call(v, 'value') && typeof v.value !== 'object') return v.value;
    return JSON.stringify(v);
  };
  const DATA = read('ed-data');
  for (const id of Object.keys(DATA)) {
    const rows = DATA[id];
    if (!Array.isArray(rows)) continue;
    DATA[id] = rows.map((r) => {
      if (typeof r !== 'object' || r === null || Array.isArray(r)) return r;
      const o = {};
      for (const k of Object.keys(r)) o[k] = cell(r[k]);
      return o;
    });
  }
  const CONF = read('ed-conf');
  const root = document.documentElement;
  const q = new URLSearchParams(location.search);
  const PDF = q.has('pdf');
  if (PDF) root.classList.add('pdf');

  const errors = (window.__errors = []);
  window.addEventListener('error', (e) => errors.push(String(e.message)));

  const KEYS = Object.keys(CONF.params);
  const fromHash = () => {
    const h = new URLSearchParams(location.hash.slice(1));
    const p = {};
    for (const k of KEYS) {
      if (h.has(k)) p[k] = typeof CONF.params[k] === 'number' ? Number(h.get(k)) : h.get(k);
    }
    return p;
  };
  // ?theme=light and ?lang=zh pick the look and language a file opens with (elevendash pdf uses them)
  const fromQuery = () => {
    const p = {};
    for (const k of ['theme', 'lang']) if (q.has(k) && k in CONF.params) p[k] = q.get(k);
    return p;
  };
  // what the address leaves out: the file's defaults, as the query changed them
  const START = Object.assign({}, CONF.params, fromQuery());
  const params = Object.assign({}, START, fromHash());
  // the file's own frame (around the page) follows the page's theme and language too
  const frame = () => {
    root.dataset.theme = params.theme === 'light' ? 'light' : 'dark';
    root.lang = params.lang === 'zh' ? 'zh-Hant' : 'en';
  };
  frame();
  const toHash = () => {
    const h = new URLSearchParams();
    for (const k of KEYS) {
      if (params[k] !== START[k] && params[k] !== '' && params[k] != null) h.set(k, params[k]);
    }
    const s = h.toString();
    try {
      history.replaceState(null, '', s ? '#' + s : location.href.split('#')[0]);
    } catch (e) {
      // some browsers refuse this for local files; the view still works, the address just does not follow it
    }
  };

  const draws = new Map();
  const listeners = [];
  const call = (fn, what) => {
    try {
      fn();
    } catch (e) {
      errors.push(what + ': ' + e.message);
      console.error(what, e);
    }
  };
  // as a dashboard host does: data listeners first, then every drawing
  const runAll = () => {
    frame();
    listeners.forEach((fn) => call(fn, 'onData'));
    draws.forEach((fn, name) => {
      document.querySelectorAll('[data-draw="' + name + '"]').forEach((el) => {
        try {
          fn(el);
        } catch (e) {
          errors.push(name + ': ' + e.message);
          console.error(name, e);
        }
      });
    });
  };

  // Printing (the page's Save as PDF button, or the browser's own Print): the look and language on screen, every
  // section open, the charts redrawn at the printed width, then back as it was.
  let printing = null;
  const enterPrint = () => {
    if (printing || PDF) return;
    printing = {opened: [...document.querySelectorAll('details:not([open])')]};
    root.classList.add('pdf');
    printing.opened.forEach((d) => (d.open = true));
    runAll();
  };
  const leavePrint = () => {
    if (!printing) return;
    const p = printing;
    printing = null;
    root.classList.remove('pdf');
    p.opened.forEach((d) => (d.open = false));
    runAll();
  };
  window.addEventListener('beforeprint', enterPrint);
  window.addEventListener('afterprint', leavePrint);

  // A change of parameter redraws on the next frame, as a dashboard host does, never inside the caller.
  let queued = false;
  const later = () => {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => {
      queued = false;
      runAll();
    });
  };

  window.dash = {
    colors: Array.from({length: CONF.colors}, (_, i) => 'var(--chart-' + i + ')'),
    params: () => Object.assign({}, params),
    setParams(p) {
      Object.assign(params, p);
      toHash();
      later();
    },
    data: (id) => (Object.prototype.hasOwnProperty.call(DATA, id) ? {status: 'ok', data: DATA[id]} : {status: 'missing', data: []}),
    // dash.draw(name, fn) defines a drawing; dash.draw(name) draws it again
    draw(name, fn) {
      if (fn === undefined) {
        const f = draws.get(name);
        if (f) document.querySelectorAll('[data-draw="' + name + '"]').forEach((el) => call(() => f(el), name));
        return;
      }
      draws.set(name, fn);
    },
    // all data is in the page from the start; a listener runs now and again whenever a parameter or the width changes
    onData(fn) {
      listeners.push(fn);
      call(fn, 'onData');
    },
    print() {
      enterPrint();
      setTimeout(() => window.print(), 30);
    },
    // hand a file the page made (a Blob) to the browser's own download
    save({filename, data}) {
      const url = URL.createObjectURL(data);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 30000);
      return Promise.resolve();
    },
  };

  window.__elevendash = {
    start() {
      if (PDF) document.querySelectorAll('details').forEach((d) => (d.open = true));
      runAll();
      root.dataset.edDrawn = String(errors.length);     // for tests: drawn, with this many errors
      let t;
      window.addEventListener('resize', () => {
        if (printing) return;
        clearTimeout(t);
        t = setTimeout(runAll, 60);
      });
      window.addEventListener('hashchange', () => {
        Object.assign(params, CONF.params, fromHash());
        runAll();
      });
    },
  };
})();
