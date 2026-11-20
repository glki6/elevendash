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
  const asHost = (rows) => (!Array.isArray(rows) ? rows : rows.map((r) => {
    if (typeof r !== 'object' || r === null || Array.isArray(r)) return r;
    const o = {};
    for (const k of Object.keys(r)) o[k] = cell(r[k]);
    return o;
  }));
  // The data is in the page in one of two forms (site.py). Plain: one JSON block, read here and now. Packed: one
  // block a dataset, deflated and in base64, which keeps the file at about a third of the size. Packed blocks are
  // unpacked before the page first draws, except the point replays (data-lazy): a month of those is unpacked when a
  // match of that month is first shown, and the page redraws when it is there, as a dashboard host loads a source.
  const DATA = {};
  const plain = document.getElementById('ed-data');
  if (plain) {
    const all = JSON.parse(plain.textContent);
    for (const id of Object.keys(all)) DATA[id] = asHost(all[id]);
  }
  const packed = new Map();
  document.querySelectorAll('script[data-ed]').forEach((el) => packed.set(el.dataset.ed, {el, lazy: el.hasAttribute('data-lazy'), state: ''}));
  const unpack = async (id) => {
    const b = packed.get(id);
    const bin = atob(b.el.textContent);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    const text = await new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('deflate'))).text();
    DATA[id] = asHost(JSON.parse(text));
    b.el.textContent = '';
    packed.delete(id);
  };
  const CONF = read('ed-conf');
  const root = document.documentElement;
  const q = new URLSearchParams(location.search);
  const PDF = q.has('pdf');
  if (PDF) root.classList.add('pdf');

  const errors = (window.__errors = []);
  window.addEventListener('error', (e) => errors.push(String(e.message)));
  // a dataset still packed: start unpacking it and say it is loading; the page is redrawn when it is in
  const fetchPacked = (id) => {
    const b = packed.get(id);
    if (b.state === '') {
      b.state = 'loading';
      unpack(id).then(() => later(), (e) => {
        b.state = 'error';
        errors.push(id + ': ' + e.message);
        later();
      });
    }
    return {status: b.state, data: []};
  };

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
  // as a dashboard host does: data listeners first, then every drawing. The drawings in the areas of the page set aside
  // (.er-off on a [data-area]) come after the ones on screen, a few at a time, so a long history shows its first
  // area at once and stays answering while the rest is drawn. A PDF or a print draws everything at once.
  const away = (el) => !root.classList.contains('pdf') && !!el.closest('[data-area].er-off');
  const drawOne = (fn, name, el) => {
    try {
      fn(el);
    } catch (e) {
      errors.push(name + ': ' + e.message);
      console.error(name, e);
    }
  };
  let pass = null;        // the drawings still to do from the latest pass; a new pass drops what an older one left
  const runAll = () => {
    frame();
    listeners.forEach((fn) => call(fn, 'onData'));
    const rest = [];
    draws.forEach((fn, name) => {
      document.querySelectorAll('[data-draw="' + name + '"]').forEach((el) => {
        if (away(el)) rest.push([fn, name, el]);
        else drawOne(fn, name, el);
      });
    });
    const mine = (pass = rest);
    const step = () => {
      if (pass !== mine) return;
      const end = performance.now() + 25;
      while (rest.length && performance.now() < end) drawOne(...rest.shift());
      if (rest.length) setTimeout(step, 0);
    };
    if (rest.length) setTimeout(step, 0);
  };
  // the drawings still waiting, done now: for a step that needs the whole page as it will be (open a point elsewhere)
  const flush = () => {
    const rest = pass || [];
    pass = null;
    while (rest.length) drawOne(...rest.shift());
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
    flush: () => flush(),
    setParams(p) {
      Object.assign(params, p);
      toHash();
      later();
    },
    data(id) {
      if (Object.prototype.hasOwnProperty.call(DATA, id)) return {status: 'ok', data: DATA[id]};
      return packed.has(id) ? fetchPacked(id) : {status: 'missing', data: []};
    },
    // dash.draw(name, fn) defines a drawing; dash.draw(name) draws it again
    draw(name, fn) {
      if (fn === undefined) {
        const f = draws.get(name);
        if (f) document.querySelectorAll('[data-draw="' + name + '"]').forEach((el) => call(() => f(el), name));
        return;
      }
      draws.set(name, fn);
    },
    // a listener runs now and again whenever a parameter, the width or the data changes
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

  const pages = [];
  const begin = () => {
    // the page's scripts, in order; as on a dashboard host, a fault in one stops only that one
    pages.forEach((fn, i) => call(fn, 'page script ' + (i + 1)));
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
  };
  const tooOld = () => {
    const p = document.createElement('p');
    p.className = 'ed-foot';
    p.textContent = 'This file needs a newer browser to open (one from 2023 or later). 開啟這個檔案需要較新的瀏覽器（2023 年或之後的版本）。';
    document.body.prepend(p);
    root.dataset.edDrawn = 'old';
  };
  window.__elevendash = {
    page: (fn) => pages.push(fn),
    start() {
      const first = [...packed].filter(([, b]) => !b.lazy).map(([id]) => id);
      if (!first.length) return begin();             // plain data: draw now, in this very task
      if (typeof DecompressionStream !== 'function') return tooOld();
      first.forEach((id) => (packed.get(id).state = 'loading'));
      Promise.all(first.map(unpack)).then(begin, (e) => {
        errors.push('data: ' + e.message);
        tooOld();
      });
    },
  };
})();
