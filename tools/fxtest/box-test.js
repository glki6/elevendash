// Test: the page scrolls inside a box of its own, as in the live viewer. Click a point from 51 px below the refocus
// position and record every scroll position of that box.
(async () => {
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const post = (o) => fetch('/log', {method: 'POST', body: JSON.stringify(o)});
  const box = document.getElementById('dash-root');
  let court = null;
  for (let i = 0; i < 80; i += 1) {
    court = document.getElementById('chart-replay');
    if (court && court.getBoundingClientRect().height > 100 && document.querySelectorAll('.er-hit[data-pick]').length > 3) break;
    await wait(250);
  }
  await wait(1500);
  const out = {step: 'ready', ua: navigator.userAgent.slice(-14), inner: [window.innerWidth, window.innerHeight], box: [box.clientHeight, box.scrollHeight]};
  await post(out);
  const offs = (new URLSearchParams(location.search).get('offs') || '51_51_200_-300').split('_').map(Number);
  let n = 0;
  for (const off of offs) {
    // the refocus position from below: court bottom on the bottom edge (or its top under the margin, if it fits)
    box.scrollTop = box.scrollHeight;
    await wait(200);
    court.scrollIntoView({behavior: 'instant', block: 'nearest'});
    await wait(200);
    const home = box.scrollTop;
    box.scrollTop = home + off;
    await wait(700);
    const start = box.scrollTop, t0 = performance.now(), pts = [[0, start]];
    const on = () => pts.push([Math.round(performance.now() - t0), Math.round(box.scrollTop)]);
    box.addEventListener('scroll', on);
    const bars = Array.from(document.querySelectorAll('.er-hit[data-pick]')).filter((b) => !b.classList.contains('on'));
    const b = bars[(n += 3) % bars.length];
    ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach((t) => b.dispatchEvent(new (t[0] === 'p' ? PointerEvent : MouseEvent)(t, {bubbles: true})));
    await wait(2200);
    box.removeEventListener('scroll', on);
    const ys = pts.map((p) => p[1]);
    const r = court.getBoundingClientRect();
    await post({step: 'off ' + off, home, start, end: box.scrollTop, min: Math.min(...ys), max: Math.max(...ys), court: [Math.round(r.top), Math.round(r.bottom)], first: pts.slice(0, 8)});
  }
  await post({step: 'done'});
})();
