// elevendash app (app.py): runs before the dashboard's own scripts. It gives the page a way to talk to the app on
// this computer, and keeps match notes in the workspace (notes.json) instead of the browser.
(() => {
  const A = window.__elevendashApp;
  A.api = async (method, path, body, raw) => {
    const headers = {'X-Elevendash': A.conf.token};
    if (!raw && body !== undefined) headers['Content-Type'] = 'application/json';
    let r;
    try {
      r = await fetch(path, {method, headers, body: raw || (body === undefined ? undefined : JSON.stringify(body)), cache: 'no-store'});
    } catch (e) {
      throw Object.assign(new Error('The app is not answering. Open Eleven Dashboard again, then reload this page.'), {status: 0, body: {}});
    }
    const j = await r.json().catch(() => ({}));
    if (!r.ok && r.status !== 409) throw Object.assign(new Error(A.plain(j.error, r.status)), {status: r.status, body: j});
    return Object.assign(j, {httpStatus: r.status});
  };
  // The app's answer to a refused request, in words for the person using it rather than the code's own
  A.plain = (error, status) => {
    const e = String(error || '').trim();
    if (e === 'key' || e === 'host') return 'This page is from an earlier start of the app. Reload it and try again.';
    if (e === 'phone key') return 'This link needs a new key. On the computer, open Settings › Open on my phone and scan the code again.';
    if (e === 'only on the computer itself') return 'That is done on the computer itself, not on the phone.';
    if (e === 'too large') return 'That is too large for the app to take.';
    if (!e || e === 'not found' || e === 'bad length') return 'The app could not take that request. Reload the page and try again.' + (status ? ` (${status})` : '');
    return e[0].toUpperCase() + e.slice(1) + (/[.!?]$/.test(e) ? '' : '.');
  };
  A.notes = {
    load: () => A.api('GET', '/api/notes').then((o) => {
      delete o.httpStatus;
      return o;
    }),
    save: (all) => A.api('PUT', '/api/notes', all),
  };
})();
