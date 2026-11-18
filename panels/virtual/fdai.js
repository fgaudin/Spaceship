/* FDAI glass panel. A display only: it subscribes to tlm/attitude (pitch, heading, roll in degrees against the local
   horizon, plus the surface prograde direction) and draws the ball. What the needles show, their scales and the
   markers are set by the ATTITUDE panel's FDAI controls: the cockpit sends them on panel/eng/out/fdai.

   Geometry. Local-level axes (north, east, up). The nose f, the right wing r and the body-up u follow from heading ψ,
   pitch θ and roll φ (right wing down positive). The ball is seen from behind the nose: a pixel (x right, y up) of the
   unit disc looks along d = x·r + y·u + z·f with z = √(1 − x² − y²); its elevation and azimuth pick the colour.
   ?demo=1 runs without a broker; ?broker=ws://host:9001 overrides the broker. */
import { connectBus, parse, showDemo } from './bus.js';

(() => {
  const params = new URLSearchParams(location.search);
  const DEMO = params.has('demo');
  const ON_GLASS = params.has('embed');    // the round screen: the rates are on the panel's displays, not drawn here
  const D2R = Math.PI / 180, R2D = 180 / Math.PI;
  const $ = (id) => document.getElementById(id);
  const cv = $('ball'), g = cv.getContext('2d');
  const W = cv.width, CX = W / 2, CY = W / 2, RB = 190, RING = 214;       // ball radius, roll ring radius (px)
  const wrap180 = (a) => ((a + 180) % 360 + 360) % 360 - 180;
  const clamp = (x, a, b) => Math.max(a, Math.min(b, x));

  // ---------- state ----------
  let target = null;                       // latest sample { pitch, heading, roll, prograde }
  let shown = null;                        // smoothed attitude actually drawn
  let rates = { p: 0, y: 0, r: 0 };        // deg/s, low-passed
  let lastRx = 0, lastSample = null;
  const REFS = ['PROGRADE', 'RETROGRADE', 'OFF'], SCALES = [5, 50], RATES = [1, 5, 10];
  const ui = { ref: 0, scale: 0, rate: 1, markers: true };     // until the cockpit says (and in the demo)
  const indexOf = (list, value, fallback) => (list.indexOf(value) >= 0 ? list.indexOf(value) : fallback);
  const applySettings = (settings) => {                         // panel/eng/out/fdai
    ui.ref = indexOf(REFS, String(settings.needles || '').toUpperCase(), ui.ref);
    ui.scale = indexOf(SCALES, settings.error_scale, ui.scale);
    ui.rate = indexOf(RATES, settings.rate_scale, ui.rate);
    if (typeof settings.markers === 'boolean') ui.markers = settings.markers;
  };

  // ---------- attitude maths ----------
  function axes(a) {
    const ps = a.heading * D2R, th = a.pitch * D2R, ph = a.roll * D2R;
    const f = [Math.cos(th) * Math.cos(ps), Math.cos(th) * Math.sin(ps), Math.sin(th)];
    const r0 = [-Math.sin(ps), Math.cos(ps), 0];
    const u0 = [-Math.sin(th) * Math.cos(ps), -Math.sin(th) * Math.sin(ps), Math.cos(th)];
    const c = Math.cos(ph), s = Math.sin(ph);
    const r = [r0[0] * c - u0[0] * s, r0[1] * c - u0[1] * s, r0[2] * c - u0[2] * s];
    const u = [u0[0] * c + r0[0] * s, u0[1] * c + r0[1] * s, u0[2] * c + r0[2] * s];
    return { f, r, u };
  }
  const dirOf = (pitch, heading) => {
    const th = pitch * D2R, ps = heading * D2R;
    return [Math.cos(th) * Math.cos(ps), Math.cos(th) * Math.sin(ps), Math.sin(th)];
  };
  const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
  // world direction → body components (x right, y up, z forward)
  const toBody = (A, w) => [dot(w, A.r), dot(w, A.u), dot(w, A.f)];

  // ---------- the ball, pixel by pixel ----------
  const N = 2 * RB, img = g.createImageData(N, N);
  const SKY = [208, 214, 220], GND = [40, 42, 46], HOR = [255, 176, 0];
  const LSKY = [30, 34, 40], LGND = [226, 222, 208];
  function renderBall(A, dim) {
    const d = img.data, { f, r, u } = A;
    let k = 0;
    for (let j = 0; j < N; j++) {
      const y = (RB - j - 0.5) / RB;
      for (let i = 0; i < N; i++, k += 4) {
        const x = (i + 0.5 - RB) / RB, q = x * x + y * y;
        if (q >= 1) { d[k + 3] = 0; continue; }
        const z = Math.sqrt(1 - q);
        const wn = x * r[0] + y * u[0] + z * f[0], we = x * r[1] + y * u[1] + z * f[1], wu = x * r[2] + y * u[2] + z * f[2];
        const el = Math.asin(clamp(wu, -1, 1)) * R2D, az = Math.atan2(we, wn) * R2D;
        const sky = el >= 0;
        let c = sky ? SKY : GND;
        const lc = sky ? LSKY : LGND;
        // line coverage: horizon, parallels every 10° (30° heavier), meridians every 30° (90° heavier)
        const aa = 0.3 / Math.max(z, 0.25);
        let cov = 0, col = lc;
        const ae = Math.abs(el);
        const hz = 1 - (ae - 0.55) / aa;
        if (hz > 0) { cov = Math.min(1, hz); col = HOR; }
        else {
          const m10 = Math.abs(ae - Math.round(ae / 10) * 10), heavy = Math.round(ae / 10) % 3 === 0;
          let a = 1 - (m10 - (heavy ? 0.42 : 0.22)) / aa;
          if (ae < 85) {
            const ce = Math.cos(el * D2R);
            const m30 = Math.abs(az - Math.round(az / 30) * 30) * ce, card = Math.round(az / 30) % 3 === 0;
            // minor meridians are dashed between the parallels so the ball does not look like a cage
            const show = card || (ae % 10) < 5;
            if (show) a = Math.max(a, 1 - (m30 - (card ? 0.42 : 0.2)) / aa);
          } else if (ae > 88.2) { a = 1; col = sky ? [53, 224, 111] : [255, 59, 47]; }
          cov = clamp(a, 0, 1);
        }
        const sh = (0.42 + 0.58 * z) * (dim ? 0.45 : 1);
        d[k] = (c[0] + (col[0] - c[0]) * cov) * sh;
        d[k + 1] = (c[1] + (col[1] - c[1]) * cov) * sh;
        d[k + 2] = (c[2] + (col[2] - c[2]) * cov) * sh;
        d[k + 3] = q > 0.985 ? 255 * (1 - q) / 0.015 : 255;
      }
    }
  }
  const off = document.createElement('canvas');
  off.width = off.height = N;
  const og = off.getContext('2d');

  // labels painted on the ball: elevation numbers on the cardinal meridians, heading (÷10) on the horizon
  function drawLabels(A) {
    g.textAlign = 'center'; g.textBaseline = 'middle';
    const put = (el, az, text, size, fill) => {
      const b = toBody(A, dirOf(el, az));
      if (b[2] < 0.3) return;
      const b2 = toBody(A, dirOf(el, az + 2));                    // towards increasing azimuth: the text baseline
      const ang = Math.atan2(-(b2[1] - b[1]), b2[0] - b[0]);
      g.save();
      g.translate(CX + b[0] * RB, CY - b[1] * RB); g.rotate(ang); g.scale(1, Math.max(0.35, b[2]));
      g.font = `600 ${size}px "DIN Alternate", "Roboto Condensed", system-ui, sans-serif`;
      g.fillStyle = fill; g.globalAlpha = clamp((b[2] - 0.3) / 0.25, 0, 1);
      g.fillText(text, 0, 0);
      g.restore();
    };
    for (let az = 0; az < 360; az += 30) {
      put(-4.2, az, az % 90 === 0 ? 'NESW'[az / 90] : String(az / 10), az % 90 === 0 ? 17 : 14, '#f1ede0');
      if (az % 90 !== 0) continue;                                 // elevation numbers on the cardinal meridians only
      for (const el of [30, 60, -30, -60]) put(el + 3.6, az + 6, String(Math.abs(el)), 13, el > 0 ? '#1e2228' : '#e2ded0');
    }
  }

  function marker(A, w, kind) {
    const b = toBody(A, w);
    if (b[2] < 0.05) return;
    const x = CX + b[0] * RB, y = CY - b[1] * RB, s = 13;
    g.save();
    g.lineWidth = 2.6; g.strokeStyle = '#0b0c0d'; g.globalAlpha = clamp(b[2] / 0.2, 0, 1);
    for (const pass of [0, 1]) {
      if (pass) { g.lineWidth = 1.6; g.strokeStyle = kind === 'pro' ? '#b8ff3d' : '#ffd23d'; }
      else g.lineWidth = 4.2;
      g.beginPath(); g.arc(x, y, s * 0.62, 0, 2 * Math.PI);
      if (kind === 'pro') {
        g.moveTo(x - s, y); g.lineTo(x - s * 0.62, y); g.moveTo(x + s * 0.62, y); g.lineTo(x + s, y);
        g.moveTo(x, y - s * 0.62); g.lineTo(x, y - s);
      } else {
        const k = s * 0.44;
        g.moveTo(x - k, y - k); g.lineTo(x + k, y + k); g.moveTo(x + k, y - k); g.lineTo(x - k, y + k);
        g.moveTo(x, y - s * 0.62); g.lineTo(x, y - s);
        g.moveTo(x - s * 0.54, y + s * 0.31); g.lineTo(x - s * 0.87, y + s * 0.5);
        g.moveTo(x + s * 0.54, y + s * 0.31); g.lineTo(x + s * 0.87, y + s * 0.5);
      }
      g.stroke();
    }
    g.restore();
  }

  // ---------- fixed parts: case, roll ring, rate scales, aircraft symbol ----------
  function drawCase() {
    g.clearRect(0, 0, W, W);
    const grd = g.createRadialGradient(CX, CY - 60, 60, CX, CY, 280);
    grd.addColorStop(0, '#191c1f'); grd.addColorStop(1, '#0a0b0c');
    g.fillStyle = grd; g.beginPath(); g.arc(CX, CY, 272, 0, 2 * Math.PI); g.fill();
    g.lineWidth = 2; g.strokeStyle = '#000'; g.stroke();
    g.fillStyle = '#060707'; g.beginPath(); g.arc(CX, CY, RING + 14, 0, 2 * Math.PI); g.fill();
    // roll scale on the case: every 10°, long ticks at 30°, numbers at 30/60/90
    g.strokeStyle = '#ece8dc'; g.fillStyle = '#ece8dc';
    g.font = '600 11px "DIN Alternate", "Roboto Condensed", system-ui, sans-serif'; g.textAlign = 'center'; g.textBaseline = 'middle';
    for (let a = -180; a < 180; a += 10) {
      const t = a * D2R, big = a % 30 === 0, r1 = RING - (big ? 13 : 8);
      g.lineWidth = big ? 2 : 1.2;
      g.beginPath(); g.moveTo(CX + Math.sin(t) * r1, CY - Math.cos(t) * r1); g.lineTo(CX + Math.sin(t) * RING, CY - Math.cos(t) * RING); g.stroke();
      if (big && a !== 0 && Math.abs(a) <= 150) g.fillText(String(Math.abs(a)), CX + Math.sin(t) * (RING + 9), CY - Math.cos(t) * (RING + 9));
    }
    g.beginPath(); g.moveTo(CX, CY - RING + 1); g.lineTo(CX - 7, CY - RING - 12); g.lineTo(CX + 7, CY - RING - 12); g.closePath(); g.fill();
  }

  function rateScale(kind, value) {
    // roll rate on top, pitch rate on the right, yaw rate at the bottom; pointer deflection = rate / full scale
    const full = RATES[ui.rate], d = clamp(value / full, -1.08, 1.08), L = 120, o = 252;
    g.save();
    g.translate(CX, CY);
    if (kind === 'pitch') g.rotate(Math.PI / 2);
    if (kind === 'yaw') g.rotate(Math.PI);
    g.strokeStyle = '#ece8dc'; g.lineWidth = 1.4; g.fillStyle = '#ece8dc';
    g.beginPath(); g.moveTo(-L, -o); g.lineTo(L, -o); g.stroke();
    for (let k = -4; k <= 4; k++) {
      const x = k * L / 4, h = k % 2 === 0 ? 9 : 5;
      g.beginPath(); g.moveTo(x, -o); g.lineTo(x, -o + h); g.stroke();
    }
    // pitch: up rate moves the pointer up (scale rotated: −x is up); yaw at the bottom is mirrored back
    const sgn = kind === 'roll' ? 1 : -1;
    const x = sgn * d * L;
    g.fillStyle = '#ffe14d';
    g.beginPath(); g.moveTo(x, -o + 1); g.lineTo(x - 7, -o - 13); g.lineTo(x + 7, -o - 13); g.closePath(); g.fill();
    g.restore();
  }

  function drawOverlay(A, a) {
    // roll pointer on the ball's rim: where "up" (zenith) appears from behind the nose
    const ux = A.r[2], uy = A.u[2], n = Math.hypot(ux, uy);
    if (n > 0.02) {
      const t = Math.atan2(ux, uy);
      g.save(); g.translate(CX, CY); g.rotate(t);
      g.fillStyle = '#ffb000';
      g.beginPath(); g.moveTo(0, -RING + 15); g.lineTo(-8, -RB - 1); g.lineTo(8, -RB - 1); g.closePath(); g.fill();
      g.restore();
    }
    // error needles: fly-to. Reference direction in body axes → yaw and pitch error; roll error is to wings level.
    const ref = REFS[ui.ref];
    if (ref !== 'OFF' && a.prograde) {
      let w = dirOf(a.prograde.pitch, a.prograde.heading);
      if (ref === 'RETROGRADE') w = w.map((x) => -x);
      const b = toBody(A, w);
      const ey = Math.atan2(b[0], b[2]) * R2D, ep = Math.atan2(b[1], Math.hypot(b[0], b[2])) * R2D, er = -wrap180(a.roll);
      const full = SCALES[ui.scale], span = RB * 0.72;
      const nx = clamp(ey / full, -1, 1) * span, ny = -clamp(ep / full, -1, 1) * span, nr = clamp(er / full, -1, 1) * span * 0.6;
      g.save();
      g.lineCap = 'round';
      for (const pass of [0, 1]) {
        g.strokeStyle = pass ? '#ffe14d' : '#0b0c0d'; g.lineWidth = pass ? 3 : 5.5;
        g.beginPath();
        g.moveTo(CX + nx, CY - RB * 0.78); g.lineTo(CX + nx, CY + RB * 0.78);          // yaw needle (vertical)
        g.moveTo(CX - RB * 0.78, CY + ny); g.lineTo(CX + RB * 0.78, CY + ny);          // pitch needle (horizontal)
        g.moveTo(CX + nr, CY - RB * 0.97); g.lineTo(CX + nr, CY - RB * 0.8);           // roll needle (short, top)
        g.stroke();
      }
      g.restore();
    }
    // fixed aircraft symbol
    g.save();
    g.lineCap = 'round'; g.lineJoin = 'round';
    for (const pass of [0, 1]) {
      g.strokeStyle = pass ? '#ff8c1a' : '#0b0c0d'; g.lineWidth = pass ? 4 : 7;
      g.beginPath();
      g.moveTo(CX - 62, CY); g.lineTo(CX - 22, CY); g.lineTo(CX - 11, CY + 12); g.lineTo(CX, CY); g.lineTo(CX + 11, CY + 12);
      g.lineTo(CX + 22, CY); g.lineTo(CX + 62, CY);
      g.stroke();
    }
    g.fillStyle = '#ff8c1a'; g.beginPath(); g.arc(CX, CY, 3, 0, 2 * Math.PI); g.fill();
    g.restore();
    // glass highlight
    const hl = g.createRadialGradient(CX - 70, CY - 90, 10, CX - 40, CY - 60, 210);
    hl.addColorStop(0, 'rgba(255,255,255,.13)'); hl.addColorStop(1, 'rgba(255,255,255,0)');
    g.fillStyle = hl; g.beginPath(); g.arc(CX, CY, RB, 0, 2 * Math.PI); g.fill();
    g.lineWidth = 3; g.strokeStyle = '#000'; g.beginPath(); g.arc(CX, CY, RB + 1, 0, 2 * Math.PI); g.stroke();
  }

  // ---------- frame ----------
  let lastDraw = null, lastT = performance.now();
  const fmt = (x, signed) => (x == null || !isFinite(x)) ? '---.-' : (signed && x >= 0 ? '+' : '') + x.toFixed(1);
  function frame(now) {
    const dt = Math.min(0.1, (now - lastT) / 1000); lastT = now;
    if (DEMO) demo(now / 1000);
    const stale = !target || (!DEMO && now - lastRx > 2000);
    if (target) {
      if (!shown) shown = { ...target };
      const k = 1 - Math.exp(-dt / 0.09);
      shown.pitch += (target.pitch - shown.pitch) * k;
      shown.heading = ((shown.heading + wrap180(target.heading - shown.heading) * k) % 360 + 360) % 360;
      shown.roll = wrap180(shown.roll + wrap180(target.roll - shown.roll) * k);
      shown.prograde = target.prograde;
    }
    const a = shown || { pitch: 0, heading: 0, roll: 0, prograde: null };
    const key = `${a.pitch.toFixed(2)}|${a.heading.toFixed(2)}|${a.roll.toFixed(2)}|${stale}|${ui.ref}${ui.scale}${ui.rate}${ui.markers}|` +
      `${rates.p.toFixed(2)}${rates.y.toFixed(2)}${rates.r.toFixed(2)}|${a.prograde ? a.prograde.pitch + ',' + a.prograde.heading : ''}`;
    if (key !== lastDraw) {
      lastDraw = key;
      const A = axes(a);
      drawCase();
      renderBall(A, stale);
      og.putImageData(img, 0, 0);
      g.drawImage(off, CX - RB, CY - RB);
      if (!stale) {
        g.save(); g.beginPath(); g.arc(CX, CY, RB, 0, 2 * Math.PI); g.clip();
        drawLabels(A);
        if (ui.markers && a.prograde) {
          const w = dirOf(a.prograde.pitch, a.prograde.heading);
          marker(A, w, 'pro'); marker(A, w.map((x) => -x), 'retro');
        }
        g.restore();
      }
      drawOverlay(A, a);
      if (!ON_GLASS) { rateScale('roll', stale ? 0 : rates.r); rateScale('pitch', stale ? 0 : rates.p); rateScale('yaw', stale ? 0 : rates.y); }
      $('flag').hidden = !stale;
      $('r-pitch').textContent = stale ? '---.-' : fmt(a.pitch, true);
      $('r-hdg').textContent = stale ? '---.-' : fmt(a.heading, false);
      $('r-roll').textContent = stale ? '---.-' : fmt(a.roll, true);
    }
    requestAnimationFrame(frame);
  }

  function sample(p, tSec) {
    if (typeof p.pitch !== 'number') return;
    if (lastSample && tSec > lastSample.t) {
      const dt = tSec - lastSample.t, k = Math.min(1, dt / 0.4);
      rates.p += ((p.pitch - lastSample.pitch) / dt - rates.p) * k;
      rates.y += (wrap180(p.heading - lastSample.heading) * Math.cos(p.pitch * D2R) / dt - rates.y) * k;
      rates.r += (wrap180(p.roll - lastSample.roll) / dt - rates.r) * k;
    }
    lastSample = { t: tSec, pitch: p.pitch, heading: p.heading, roll: p.roll };
    target = { pitch: p.pitch, heading: p.heading, roll: p.roll, prograde: p.prograde || null };
    lastRx = performance.now();
  }

  let demoLast = 0;
  function demo(t) {
    if (t - demoLast < 0.1) return;
    demoLast = t;
    const pitch = 35 + 30 * Math.sin(t / 7), heading = (70 + 25 * Math.sin(t / 11) + 360) % 360, roll = 20 * Math.sin(t / 5);
    sample({ pitch, heading, roll, prograde: { pitch: 31, heading: 78 } }, t);
  }

  // ---------- bus ----------
  const statusTopic = 'panel/fdai/status';
  if (DEMO) { showDemo(); $('plant').textContent = 'plant: demo'; }
  else {
    connectBus({
      name: 'panel-fdai',
      will: { topic: statusTopic, payload: { online: false } },
      onConnect: (client) => {
        client.subscribe(['tlm/attitude', 'gateway/status', 'panel/eng/out/fdai'], { qos: 0 });
        client.publish(statusTopic, JSON.stringify({ online: true, fw: 'fdai-glass-0.2' }), { qos: 1, retain: true });
      },
      onMessage: (topic, text) => {
        const p = parse(text);
        if (p === undefined) return;
        if (topic === 'tlm/attitude') sample(p, performance.now() / 1000);
        else if (topic === 'panel/eng/out/fdai') applySettings(p);
        else if (topic === 'gateway/status') $('plant').textContent = `plant: ${p.plant || '?'}${p.connected ? '' : ' (down)'}`;
      },
    });
  }
  requestAnimationFrame(frame);
})();
