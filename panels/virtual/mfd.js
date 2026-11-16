/* MFD glass panel: four pages drawn on one canvas from the bus telemetry. A display only (no commands).
   ORBIT    top-down orbit: body, atmosphere, ellipse (a, e, argument of periapsis), vessel at its true anomaly, apsides
   ASCENT   tapes: altitude, vertical speed, speed, apoapsis; dynamic pressure and g bars
   LANDING  cross-pointer of the horizontal velocity in the heading frame (forward / right), radar altitude and V/S tapes,
            time to impact, TWR
   DOCKING  range, closing speed, line-of-sight rate and the course's braking gate (ρ / 400 s, floor 0.05 m/s);
            under 100 m with a targeted port: lateral offset cross-pointer, axial distance and speed, capture envelope
   ?demo=1 runs a synthetic state without a broker. */
import { connectBus, parse, showDemo } from './bus.js';

(() => {
  const params = new URLSearchParams(location.search);
  const DEMO = params.has('demo');
  const $ = (id) => document.getElementById(id);
  const cv = $('mfd'), g = cv.getContext('2d');
  const W = cv.width, H = cv.height;
  const BODIES = { Kerbin: { R: 600000, atm: 70000, mu: 3.5316e12, color: '#2c4a6b' }, Mun: { R: 200000, atm: 0, mu: 6.5138398e10, color: '#5d5f63' },
    Minmus: { R: 60000, atm: 0, mu: 1.7658e9, color: '#6f8f86' } };
  const TAU_G = 400, V_MIN = 0.05, ENV = { vmin: 0.03, vmax: 0.3, lat: 0.3 };       // docking chapter (gaps.md G10)
  const C = { fg: '#4cff7a', dim: '#1f6b37', amber: '#ffb000', red: '#ff3b2f', white: '#e8f2ea', grid: '#123a20', bg: '#030504' };
  const T = {};                                           // topic → payload
  let lastRx = 0;
  const PAGES = ['orbit', 'ascent', 'landing', 'docking'];
  const ui = { page: 'orbit', zoom: 0 };
  try { Object.assign(ui, JSON.parse(localStorage.getItem('mfd-ui') || '{}')); } catch { /* private window */ }

  const fmt = (x, d = 0, unit = '') => (x == null || !isFinite(x)) ? '----' : `${x.toFixed(d)}${unit}`;
  const km = (m) => (m == null ? null : m / 1000);
  const mmss = (t) => {
    if (t == null || !isFinite(t)) return '--:--';
    const s = Math.abs(t), sg = t < 0 ? '-' : '';
    if (s >= 3600) return `${sg}${Math.floor(s / 3600)}h${String(Math.floor(s / 60 % 60)).padStart(2, '0')}`;
    return `${sg}${String(Math.floor(s / 60)).padStart(2, '0')}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
  };
  const font = (px, w = 600) => `${w} ${px}px ui-monospace, "DejaVu Sans Mono", Menlo, monospace`;
  function text(s, x, y, { size = 18, color = C.fg, align = 'left', base = 'alphabetic', weight = 600 } = {}) {
    g.font = font(size, weight); g.fillStyle = color; g.textAlign = align; g.textBaseline = base; g.fillText(s, x, y);
  }
  function readout(rows, x, y, w = 250) {
    rows.forEach(([k, v, col], i) => {
      text(k, x, y + i * 30, { size: 15, color: C.dim });
      text(v, x + w, y + i * 30, { size: 19, color: col || C.fg, align: 'right' });
    });
  }
  function frameTitle(t, sub) {
    text(t, 24, 38, { size: 22 });
    if (sub) text(sub, W - 24, 38, { size: 15, color: C.dim, align: 'right' });
    g.strokeStyle = C.grid; g.lineWidth = 1; g.beginPath(); g.moveTo(20, 52); g.lineTo(W - 20, 52); g.stroke();
  }

  // ---------- ORBIT ----------
  function pageOrbit() {
    const o = T['tlm/orbit'] || {}, B = BODIES[o.body] || BODIES.Kerbin;
    frameTitle('ORBIT', o.body ? o.body.toUpperCase() : '');
    const cx = W / 2, cy = 275, a = o.a, e = o.e ?? 0;
    const ra = a && e < 1 ? a * (1 + e) : (B.R + 100000);
    const span = Math.max(B.R * 1.15, e < 1 && a ? ra : B.R * 4) * Math.pow(0.5, ui.zoom);
    const s = 205 / span;                                  // px per m
    // body and atmosphere
    if (B.atm) { g.fillStyle = 'rgba(76,150,255,.12)'; g.beginPath(); g.arc(cx, cy, (B.R + B.atm) * s, 0, 2 * Math.PI); g.fill(); }
    g.fillStyle = B.color; g.beginPath(); g.arc(cx, cy, B.R * s, 0, 2 * Math.PI); g.fill();
    g.strokeStyle = '#000'; g.lineWidth = 1; g.stroke();
    if (a && e != null) {
      const w = ((o.argp || 0) * Math.PI) / 180;           // periapsis direction, counter-clockwise from +x
      const p = a * (1 - e * e);
      const pt = (nu) => { const r = p / (1 + e * Math.cos(nu)); return [cx + r * s * Math.cos(nu + w), cy - r * s * Math.sin(nu + w)]; };
      g.strokeStyle = C.fg; g.lineWidth = 2; g.beginPath();
      const lim = e < 1 ? Math.PI : Math.acos(-1 / e) - 0.02;
      for (let k = 0; k <= 360; k++) {
        const nu = -lim + (2 * lim * k) / 360;
        const [x, y] = pt(nu);
        if (k === 0) g.moveTo(x, y); else g.lineTo(x, y);
      }
      g.stroke();
      // apsides
      const mark = (nu, label, col) => { const [x, y] = pt(nu); g.fillStyle = col; g.beginPath(); g.arc(x, y, 5, 0, 2 * Math.PI); g.fill();
        text(label, x + 9, y - 8, { size: 14, color: col }); };
      mark(0, 'Pe', C.amber);
      if (e < 1) mark(Math.PI, 'Ap', C.amber);
      if (o.nu != null) {
        const [x, y] = pt((o.nu * Math.PI) / 180);
        g.fillStyle = C.white; g.beginPath(); g.moveTo(x, y - 9); g.lineTo(x + 8, y + 7); g.lineTo(x - 8, y + 7); g.closePath(); g.fill();
      }
    } else text('NO ORBIT', cx, cy + 6, { size: 20, color: C.amber, align: 'center' });
    readout([
      ['APOAPSIS', o.apo == null ? 'ESCAPE' : `${fmt(km(o.apo), 1)} km`],
      ['PERIAPSIS', `${fmt(km(o.peri), 1)} km`, o.peri != null && o.peri < (B.atm || 0) ? C.amber : null],
      ['T APO', mmss(o.t_apo)], ['T PERI', mmss(o.t_peri)],
    ], 30, 520, 260);
    readout([
      ['PERIOD', mmss(o.period)], ['INC', `${fmt(o.i, 2)}°`], ['ECC', fmt(o.e, 4)], ['NU', `${fmt(o.nu, 1)}°`],
    ], 340, 520, 270);
  }

  // ---------- tapes ----------
  function tape(x, y, h, label, value, unit, span, step, fmtv, color = C.fg) {
    const w = 96;
    g.strokeStyle = C.grid; g.lineWidth = 1; g.strokeRect(x, y, w, h);
    text(label, x + w / 2, y - 10, { size: 14, color: C.dim, align: 'center' });
    if (value == null || !isFinite(value)) { text('----', x + w / 2, y + h / 2, { size: 18, color: C.amber, align: 'center', base: 'middle' }); return; }
    g.save(); g.beginPath(); g.rect(x, y, w, h); g.clip();
    const pxPer = h / span, mid = y + h / 2;
    const first = Math.ceil((value - span / 2) / step) * step;
    for (let v = first; v <= value + span / 2; v += step) {
      const yy = mid - (v - value) * pxPer;
      g.strokeStyle = C.dim; g.beginPath(); g.moveTo(x, yy); g.lineTo(x + 14, yy); g.stroke();
      text(fmtv(v), x + 20, yy + 5, { size: 13, color: C.dim });
    }
    g.restore();
    g.fillStyle = '#000'; g.fillRect(x - 4, mid - 15, w + 8, 30);
    g.strokeStyle = color; g.lineWidth = 2; g.strokeRect(x - 4, mid - 15, w + 8, 30);
    text(fmtv(value) + unit, x + w / 2, mid + 6, { size: 17, color, align: 'center' });
  }
  function hbar(x, y, w, label, v, max, warn) {
    text(label, x, y - 8, { size: 14, color: C.dim });
    g.strokeStyle = C.grid; g.strokeRect(x, y, w, 16);
    const f = Math.max(0, Math.min(1, (v || 0) / max));
    g.fillStyle = v > warn ? C.amber : C.fg; g.fillRect(x + 1, y + 1, (w - 2) * f, 14);
    g.strokeStyle = C.red; g.beginPath(); g.moveTo(x + w * warn / max, y - 3); g.lineTo(x + w * warn / max, y + 19); g.stroke();
  }

  // ---------- ASCENT ----------
  function pageAscent() {
    const f = T['tlm/flight'] || {}, o = T['tlm/orbit'] || {}, a = T['tlm/attitude'] || {};
    frameTitle('ASCENT / ENTRY', a.pitch != null ? `PITCH ${fmt(a.pitch, 1)}°` : '');
    const z = Math.pow(0.5, ui.zoom);
    tape(30, 100, 360, 'ALT km', km(f.alt), '', 40 * z, 5 * z, (v) => v.toFixed(z < 1 ? 1 : 0));
    tape(180, 100, 360, 'V/S m/s', f.vs, '', 400 * z, 50 * z, (v) => v.toFixed(0), f.vs < -5 && f.alt < 70000 ? C.amber : C.fg);
    tape(330, 100, 360, 'SPEED', f.speed, '', 1000 * z, 100 * z, (v) => v.toFixed(0));
    tape(480, 100, 360, 'APO km', km(o.apo), '', 40 * z, 5 * z, (v) => v.toFixed(z < 1 ? 1 : 0));
    hbar(30, 515, 280, `Q ${fmt(km(f.q), 1)} kPa`, f.q, 40000, 30000);
    hbar(340, 515, 270, `G ${fmt(f.g, 2)}`, f.g, 8, 5);
    readout([['PERI', `${fmt(km(o.peri), 1)} km`], ['T APO', mmss(o.t_apo)]], 30, 575, 270);
  }

  // ---------- LANDING ----------
  function pageLanding() {
    const f = T['tlm/flight'] || {}, a = T['tlm/attitude'] || {}, ve = T['tlm/vessel'] || {}, o = T['tlm/orbit'] || {};
    frameTitle('LANDING', o.body ? o.body.toUpperCase() : '');
    const cx = 210, cy = 255, R = 150;
    const scale = [10, 2, 0.5][Math.max(0, Math.min(2, ui.zoom))];
    // velocity in the heading frame: forward along the nose heading, right 90° clockwise
    let fwd = null, right = null;
    if (f.vn != null && f.ve != null && a.heading != null) {
      const h = (a.heading * Math.PI) / 180;
      fwd = f.vn * Math.cos(h) + f.ve * Math.sin(h);
      right = -f.vn * Math.sin(h) + f.ve * Math.cos(h);
    }
    g.strokeStyle = C.grid; g.lineWidth = 1;
    g.beginPath(); g.arc(cx, cy, R, 0, 2 * Math.PI); g.moveTo(cx - R, cy); g.lineTo(cx + R, cy); g.moveTo(cx, cy - R); g.lineTo(cx, cy + R); g.stroke();
    g.beginPath(); g.arc(cx, cy, R / 2, 0, 2 * Math.PI); g.stroke();
    text(`±${scale} m/s`, cx + R, cy + R + 22, { size: 13, color: C.dim, align: 'right' });
    text('FWD', cx, cy - R - 10, { size: 13, color: C.dim, align: 'center' });
    if (fwd != null) {
      const x = cx + Math.max(-1.1, Math.min(1.1, right / scale)) * R, y = cy - Math.max(-1.1, Math.min(1.1, fwd / scale)) * R;
      g.strokeStyle = C.amber; g.lineWidth = 3;
      g.beginPath(); g.moveTo(x, cy - R); g.lineTo(x, cy + R); g.moveTo(cx - R, y); g.lineTo(cx + R, y); g.stroke();
      g.fillStyle = C.white; g.beginPath(); g.arc(x, y, 6, 0, 2 * Math.PI); g.fill();
    } else text('NO DATA', cx, cy + 6, { size: 18, color: C.amber, align: 'center' });
    const B = BODIES[o.body] || BODIES.Kerbin;
    const gl = B.mu / Math.pow(B.R + (f.alt || 0), 2);
    const twr = ve.mass ? (ve.thrust_avail || 0) / (ve.mass * gl) : null;
    const tti = f.vs < -0.1 && f.radar != null ? f.radar / -f.vs : null;
    const z = Math.pow(0.5, ui.zoom);
    tape(450, 95, 300, 'RADAR m', f.radar, '', 400 * z, 50 * z, (v) => v.toFixed(0), f.radar < 50 ? C.amber : C.fg);
    readout([
      ['V/S', `${fmt(f.vs, 1)} m/s`, f.vs < -10 && f.radar < 200 ? C.red : null], ['H SPEED', `${fmt(f.hs, 1)} m/s`],
      ['FWD / RIGHT', fwd == null ? '----' : `${fwd.toFixed(1)} / ${right.toFixed(1)}`], ['TTI', tti == null ? '--' : `${tti.toFixed(0)} s`],
      ['TWR', fmt(twr, 2)],
    ], 30, 470, 380);
  }

  // ---------- DOCKING ----------
  function pageDocking() {
    const t = T['tlm/target'];
    frameTitle('RENDEZVOUS / DOCKING', t && t.set ? t.name : '');
    if (!t || !t.set) { text('NO TARGET', W / 2, H / 2, { size: 26, color: C.amber, align: 'center' }); return; }
    const gate = Math.max(t.range / TAU_G, V_MIN), over = t.closing > gate * 1.25;
    readout([
      ['RANGE', t.range > 2000 ? `${(t.range / 1000).toFixed(2)} km` : `${t.range.toFixed(1)} m`],
      ['CLOSING', `${fmt(t.closing, 2)} m/s`, over ? C.amber : null],
      ['GATE ρ/400', `${fmt(gate, 2)} m/s`],
      ['LOS RATE', `${fmt(t.los_rate, 3)}°/min`], ['REL V', `${fmt(t.rel_v, 2)} m/s`],
    ], 30, 100, 300);
    // range / closing-speed plane with the gate line
    const x0 = 360, y0 = 260, gw = 250, gh = 170;
    g.strokeStyle = C.grid; g.strokeRect(x0, y0 - gh, gw, gh);
    const rMax = t.range > 1000 ? 6000 : 1000, vMax = rMax / TAU_G * 1.5;
    g.strokeStyle = C.dim; g.setLineDash([5, 4]); g.beginPath();
    for (let k = 0; k <= 50; k++) { const r = (rMax * k) / 50, v = Math.max(r / TAU_G, V_MIN); const px = x0 + gw * r / rMax, py = y0 - gh * Math.min(1, v / vMax); k ? g.lineTo(px, py) : g.moveTo(px, py); }
    g.stroke(); g.setLineDash([]);
    const px = x0 + gw * Math.min(1, t.range / rMax), py = y0 - gh * Math.max(0, Math.min(1, t.closing / vMax));
    g.fillStyle = over ? C.amber : C.fg; g.beginPath(); g.arc(px, py, 6, 0, 2 * Math.PI); g.fill();
    text('range →', x0 + gw, y0 + 18, { size: 12, color: C.dim, align: 'right' });
    text('closing', x0 + 4, y0 - gh - 6, { size: 12, color: C.dim });
    // port alignment
    const p = t.port;
    if (p) {
      const cx = 200, cy = 470, R = 130, sc = [5, 1, 0.3][Math.max(0, Math.min(2, ui.zoom))];
      g.strokeStyle = C.grid; g.beginPath(); g.arc(cx, cy, R, 0, 2 * Math.PI); g.moveTo(cx - R, cy); g.lineTo(cx + R, cy); g.moveTo(cx, cy - R); g.lineTo(cx, cy + R); g.stroke();
      g.strokeStyle = C.dim; g.beginPath(); g.arc(cx, cy, R * Math.min(1, ENV.lat / sc), 0, 2 * Math.PI); g.stroke();
      const lat = Math.hypot(p.x, p.z), ok = lat <= ENV.lat;
      const x = cx + Math.max(-1.1, Math.min(1.1, p.x / sc)) * R, y = cy - Math.max(-1.1, Math.min(1.1, p.z / sc)) * R;
      g.fillStyle = ok ? C.fg : C.amber; g.beginPath(); g.arc(x, y, 7, 0, 2 * Math.PI); g.fill();
      text(`±${sc} m`, cx + R, cy + R + 20, { size: 12, color: C.dim, align: 'right' });
      const va = -p.v_axial, inEnv = va >= ENV.vmin && va <= ENV.vmax;
      readout([
        ['AXIAL', `${fmt(p.axial, 2)} m`], ['CLOSE RATE', `${fmt(va, 3)} m/s`, inEnv ? C.fg : C.amber],
        ['LATERAL', `${fmt(lat, 2)} m`, ok ? C.fg : C.amber], ['LAT RATE', `${fmt(Math.hypot(p.vx, p.vz), 3)} m/s`],
        ['CAPTURE', inEnv && ok ? 'IN ENVELOPE' : 'OUTSIDE', inEnv && ok ? C.fg : C.amber],
      ], 360, 340, 250);
    } else text('target a docking port for alignment', 30, 600, { size: 14, color: C.dim });
  }

  // ---------- frame loop ----------
  const draw = { orbit: pageOrbit, ascent: pageAscent, landing: pageLanding, docking: pageDocking };
  function frame() {
    if (DEMO) demo(performance.now() / 1000);
    g.fillStyle = C.bg; g.fillRect(0, 0, W, H);
    // faint scan lines
    g.fillStyle = 'rgba(76,255,122,.025)';
    for (let y = 0; y < H; y += 4) g.fillRect(0, y, W, 1);
    draw[ui.page]();
    if (!DEMO && performance.now() - lastRx > 2000) {
      g.fillStyle = 'rgba(3,5,4,.65)'; g.fillRect(0, 0, W, H);
      text('NO DATA', W / 2, H / 2, { size: 30, color: C.red, align: 'center', base: 'middle' });
    }
    requestAnimationFrame(frame);
  }

  function demo(t) {
    const nu = (t * 6) % 360 - 180;
    T['tlm/orbit'] = { body: 'Kerbin', a: 690000, e: 0.03, argp: 40, nu, apo: 110700, peri: 69300, period: 1880, t_apo: 600, t_peri: 1540, i: 0.1 };
    T['tlm/flight'] = { alt: 24000 + 2000 * Math.sin(t / 4), vs: 140 * Math.cos(t / 4), speed: 1150 + 20 * Math.sin(t / 3), q: 21000, g: 2.1,
      radar: 120 + 40 * Math.sin(t / 5), hs: 3.2, vn: 2 * Math.cos(t / 3), ve: 2.5 * Math.sin(t / 2) };
    T['tlm/attitude'] = { pitch: 32, heading: 90, roll: 0 };
    T['tlm/vessel'] = { mass: 4400, thrust_avail: 60000 };
    T['tlm/target'] = { set: true, name: 'Target', range: 600 + 200 * Math.sin(t / 6), closing: 1.6, los_rate: 0.2, rel_v: 1.65,
      port: { axial: 8.2, x: 0.18 * Math.sin(t), z: 0.1, v_axial: -0.14, vx: 0.01, vz: 0 } };
  }

  // ---------- keys ----------
  const paint = () => {
    document.querySelectorAll('[data-page]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.page === ui.page)));
    $('zoom-note').textContent = `×${Math.pow(2, ui.zoom)}`;
    try { localStorage.setItem('mfd-ui', JSON.stringify(ui)); } catch { /* ignore */ }
  };
  document.querySelectorAll('[data-page]').forEach((b) => b.addEventListener('click', () => { ui.page = b.dataset.page; paint(); }));
  $('k-zoom-in').addEventListener('click', () => { ui.zoom = Math.min(2, ui.zoom + 1); paint(); });
  $('k-zoom-out').addEventListener('click', () => { ui.zoom = Math.max(0, ui.zoom - 1); paint(); });
  addEventListener('keydown', (e) => {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const i = '1234'.indexOf(e.key);
    if (i >= 0) { ui.page = PAGES[i]; paint(); }
    if (e.key === '+' || e.key === '=') { ui.zoom = Math.min(2, ui.zoom + 1); paint(); }
    if (e.key === '-') { ui.zoom = Math.max(0, ui.zoom - 1); paint(); }
  });
  if (!PAGES.includes(ui.page)) ui.page = 'orbit';
  ui.zoom = Math.max(0, Math.min(2, ui.zoom | 0));
  paint();

  // ---------- bus ----------
  if (DEMO) { showDemo(); $('plant').textContent = 'plant: demo'; }
  else {
    connectBus({
      name: 'panel-mfd',
      will: { topic: 'panel/mfd/status', payload: { online: false } },
      onConnect: (client) => {
        client.subscribe(['tlm/#', 'gateway/status'], { qos: 0 });
        client.publish('panel/mfd/status', JSON.stringify({ online: true, fw: 'mfd-glass-0.1' }), { qos: 1, retain: true });
      },
      onMessage: (topic, text) => {
        const p = parse(text);
        if (p === undefined) return;
        if (topic === 'gateway/status') { $('plant').textContent = `plant: ${p.plant || '?'}${p.connected ? '' : ' (down)'}`; return; }
        T[topic] = p; lastRx = performance.now();
      },
    });
  }
  requestAnimationFrame(frame);
})();
