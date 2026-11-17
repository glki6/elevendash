// elevendash app (app.py): runs before the dashboard's own scripts. It gives the page a way to talk to the app on
// this computer, and keeps match notes in the workspace (notes.json) instead of the browser.
(() => {
  const A = window.__elevendashApp;
  A.api = async (method, path, body, raw) => {
    const headers = {'X-Elevendash': A.conf.token};
    if (!raw && body !== undefined) headers['Content-Type'] = 'application/json';
    const r = await fetch(path, {method, headers, body: raw || (body === undefined ? undefined : JSON.stringify(body)), cache: 'no-store'});
    const j = await r.json().catch(() => ({}));
    if (!r.ok && r.status !== 409) throw Object.assign(new Error(j.error || 'HTTP ' + r.status), {status: r.status, body: j});
    return Object.assign(j, {httpStatus: r.status});
  };
  A.notes = {
    load: () => A.api('GET', '/api/notes').then((o) => {
      delete o.httpStatus;
      return o;
    }),
    save: (all) => A.api('PUT', '/api/notes', all),
  };
})();
