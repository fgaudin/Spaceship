/* Virtual panel: a dumb I/O node in a browser (PLAN.md §2). It draws itself from protocol/panels/<id>.json, publishes
   raw input changes to panel/<id>/in/<control> and draws whatever panel/<id>/out/<output> says. No rules here: lamps,
   interlocks, C&W and displays are the cockpit logic's job. */
'use strict';
(async function () {
  const params = new URLSearchParams(location.search);
  const PANEL_ID = params.get('panel') || 'eng';
  const BROKER = params.get('broker') || `ws://${location.hostname || 'localhost'}:9001`;
  const def = await (await fetch(`panels/${PANEL_ID}.json`, { cache: 'no-store' })).json();
  const IN = (c) => `panel/${PANEL_ID}/in/${c}`;
  const OUT = `panel/${PANEL_ID}/out/`;
  const root = document.getElementById('panel');
  const outputs = new Map();      // output name → render(payload)
  const inputs = new Map();       // input name → { get, set, retained }
  const keyButtons = new Map();   // keypad key → press()
  let client = null, restoring = true;

  const el = (tag, cls, attrs = {}) => { const e = document.createElement(tag); if (cls) e.className = cls; Object.assign(e, attrs); return e; };
  const send = (ctl, v, retained) => {
    if (!client || !client.connected) return;
    client.publish(IN(ctl), JSON.stringify({ v }), { qos: 1, retain: !!retained });
  };

  /* ---------- 7-segment glyphs ---------- */
  const SEG = { '0': 'abcdef', '1': 'bc', '2': 'abdeg', '3': 'abcdg', '4': 'bcfg', '5': 'acdfg', '6': 'acdefg', '7': 'abc', '8': 'abcdefg',
    '9': 'abcdfg', '-': 'g', ' ': '', 'E': 'adefg', 'r': 'eg', 'o': 'cdeg', 'L': 'def', 'H': 'bcefg', 'P': 'abefg', 'A': 'abcefg',
    'F': 'aefg', 'C': 'adef', 'd': 'bcdeg', 'n': 'ceg', 't': 'defg', 'u': 'cde', 'b': 'cdefg', 'S': 'acdfg', 'y': 'bcdfg',
    '+': 'gh', '_': 'd' };
  const SEG_SHAPES = {
    // h first: drawn under the others, so that when it is off it does not hide the middle of g (a dash looked like two dots)
    h: 'M10,9.5 L11.6,11 L11.6,23 L10,24.5 L8.4,23 L8.4,11 Z',          // the plus sign's vertical bar
    a: 'M4,1 L16,1 L14,4 L6,4 Z', b: 'M17,2 L17,15 L14.5,16.5 L14.5,5 Z', c: 'M17,19 L17,32 L14.5,29 L14.5,17.5 Z',
    d: 'M4,33 L16,33 L14,30 L6,30 Z', e: 'M3,19 L3,32 L5.5,29 L5.5,17.5 Z', f: 'M3,2 L3,15 L5.5,16.5 L5.5,5 Z',
    g: 'M4.5,17 L6.5,15.3 L13.5,15.3 L15.5,17 L13.5,18.7 L6.5,18.7 Z',
  };
  function seg7(item) {
    const box = el('div', `seg7 ${item.color || ''}`);
    const digits = [];
    for (let i = 0; i < item.digits; i++) {
      const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      svg.setAttribute('viewBox', '0 0 21 34');
      const d = {};
      for (const [k, path] of Object.entries(SEG_SHAPES)) {
        const p = document.createElementNS(svg.namespaceURI, 'path');
        p.setAttribute('d', path); p.setAttribute('class', 's'); svg.appendChild(p); d[k] = p;
      }
      const dp = document.createElementNS(svg.namespaceURI, 'circle');
      dp.setAttribute('cx', '19.3'); dp.setAttribute('cy', '32'); dp.setAttribute('r', '1.4'); dp.setAttribute('class', 's');
      svg.appendChild(dp); d.dp = dp;
      box.appendChild(svg); digits.push(d);
    }
    const render = (p) => {
      const cells = [];
      const text = p.blank ? '' : String(p.text ?? '');
      for (const ch of text) {
        if (ch === '.' && cells.length && !cells[cells.length - 1].dp) cells[cells.length - 1].dp = true;
        else cells.push({ ch, dp: ch === '.' });
      }
      while (cells.length < digits.length) cells.unshift({ ch: ' ', dp: false });
      const show = cells.slice(-digits.length);
      box.classList.toggle('flash', !!p.blink && !p.blank);
      show.forEach((c, i) => {
        const on = SEG[c.ch === '.' ? ' ' : c.ch] ?? 'g';
        for (const k of 'abcdefgh') digits[i][k].classList.toggle('on', on.includes(k));
        digits[i].dp.classList.toggle('on', c.dp);
      });
    };
    render({ text: '', blank: true });
    return { node: box, render };
  }

  /* ---------- controls ---------- */
  function toggle(item, onChange) {
    const b = el('button', 'toggle', { type: 'button', title: item.label });
    b.innerHTML = '<span class="nut"></span><span class="bat"></span><span class="pos on">ON</span><span class="pos off">OFF</span>';
    let v = item.default ?? 0;
    const set = (x) => { v = x ? 1 : 0; b.setAttribute('aria-pressed', v ? 'true' : 'false'); };
    set(v);
    b.addEventListener('click', () => { if (b.disabled) return; set(!v); onChange(v); });
    return { node: b, get: () => v, set };
  }

  // an indicator LED that belongs to a switch (drawn above it): shows the game's state, blinks on disagree
  function ownLed(item) {
    if (!item.led) return [];
    const d = el('div', `led ${item.led.color || 'green'}`, { title: `${item.label} indicator` });
    outputs.set(item.led.out, (p) => { d.classList.toggle('lit', !!p.on); d.classList.toggle('blink', !!p.on && !!p.blink); });
    return [d];
  }

  const builders = {
    toggle(item) {
      const t = toggle(item, (v) => send(item.in, v, true));
      inputs.set(item.in, { get: t.get, set: t.set, retained: true });
      return [...ownLed(item), t.node];
    },
    guarded_toggle(item) {
      const wrap = el('div', 'guarded');
      const t = toggle(item, (v) => send(item.in, v, true));
      const guard = el('button', 'guard', { type: 'button', title: `${item.label} guard` });
      let open = false;
      const setOpen = (o) => {
        open = o; wrap.classList.toggle('open', o); t.node.disabled = !o;
        if (!o && t.get()) { t.set(0); send(item.in, 0, true); }    // closing the guard pushes the switch off
      };
      guard.addEventListener('click', () => setOpen(!open));
      wrap.append(t.node, guard);
      setOpen(false);
      inputs.set(item.in, { get: t.get, set: (x) => { if (x) setOpen(true); t.set(x); }, retained: true });
      return [...ownLed(item), wrap];
    },
    button(item) { return builders.lamp_button({ ...item, plain: true }); },
    lamp_button(item) {
      const b = el('button', `btn ${item.plain ? 'plain' : item.color || 'amber'}`, { type: 'button', textContent: item.label });
      let down = false;
      const press = (x) => { if (x === down) return; down = x; b.classList.toggle('down', x); send(item.in, x ? 1 : 0, false); };
      b.addEventListener('pointerdown', (e) => { b.setPointerCapture(e.pointerId); press(true); });
      b.addEventListener('pointerup', () => press(false));
      b.addEventListener('pointercancel', () => press(false));
      b.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); press(true); } });
      b.addEventListener('keyup', (e) => { if (e.key === 'Enter' || e.key === ' ') press(false); });
      inputs.set(item.in, { get: () => (down ? 1 : 0), set: () => {}, retained: false, press });
      if (item.out) outputs.set(item.out, (p) => { b.classList.toggle('lit', !!p.on); b.classList.toggle('blink', !!p.on && !!p.blink); });
      return [b];
    },
    led(item) {
      const d = el('div', `led ${item.color || 'green'}`);
      outputs.set(item.out, (p) => { d.classList.toggle('lit', !!p.on); d.classList.toggle('blink', !!p.on && !!p.blink); });
      return [d];
    },
    annunciator(item) {
      const g = el('div', 'annun');
      g.style.gridTemplateColumns = `repeat(${item.cols || 3}, 1fr)`;
      for (const c of item.cells) {
        const cell = el('div', `cell ${c.color || 'amber'}`, { textContent: c.label });
        outputs.set(c.out, (p) => { cell.classList.toggle('lit', !!p.on); cell.classList.toggle('blink', !!p.on && !!p.blink); });
        g.appendChild(cell);
      }
      return [g];
    },
    seg7(item) {
      const s = seg7(item);
      outputs.set(item.out, s.render);
      return [s.node];
    },
    bar(item) {
      const b = el('div', 'bar');
      const n = item.segments || 10, cells = [];
      for (let i = 0; i < n; i++) { const c = el('i'); if (i >= n * 0.7) c.classList.add('hi'); if (i === n - 1) c.classList.add('top'); b.appendChild(c); cells.push(c); }
      outputs.set(item.out, (p) => { const k = Math.round((p.v || 0) * n); cells.forEach((c, i) => c.classList.toggle('on', i < k)); });
      return [b];
    },
    rotary(item) {
      const wrap = el('div', 'rotary-wrap');
      const knob = el('button', 'rotary', { type: 'button', title: `${item.label} (click: next, shift-click or wheel: back)` });
      const ptr = el('span', 'ptr');
      knob.appendChild(ptr);
      const n = item.positions.length, span = Math.min(270, 45 * (n - 1)), a0 = -span / 2;
      const ticks = item.positions.map((label, i) => {
        const a = (a0 + (n > 1 ? span * i / (n - 1) : 0)) * Math.PI / 180;
        const t = el('span', 'tick', { textContent: label });
        t.style.left = `${50 + 46 * Math.sin(a)}%`; t.style.top = `${56 - 46 * Math.cos(a)}%`;
        wrap.appendChild(t); return t;
      });
      let v = item.default ?? 0;
      const set = (x) => { v = ((x % n) + n) % n; ptr.style.transform = `rotate(${a0 + (n > 1 ? span * v / (n - 1) : 0)}deg)`;
        ticks.forEach((t, i) => t.classList.toggle('sel', i === v)); };
      const step = (d) => { set(v + d); send(item.in, v, true); };
      knob.addEventListener('click', (e) => step(e.shiftKey ? -1 : 1));
      knob.addEventListener('contextmenu', (e) => { e.preventDefault(); step(-1); });
      knob.addEventListener('wheel', (e) => { e.preventDefault(); step(e.deltaY > 0 ? 1 : -1); }, { passive: false });
      knob.addEventListener('keydown', (e) => { if (e.key === 'ArrowRight') step(1); if (e.key === 'ArrowLeft') step(-1); });
      wrap.appendChild(knob);
      set(v);
      inputs.set(item.in, { get: () => v, set, retained: true });
      return [wrap];
    },
    pot(item) {
      const r = el('input', 'pot', { type: 'range', min: 0, max: 1, step: 0.01, value: item.default ?? 0, title: item.label });
      const val = el('div', 'pot-val', { textContent: `${Math.round((item.default ?? 0) * 100)} %` });
      let last = 0;
      const show = () => { val.textContent = `${Math.round(r.value * 100)} %`; };
      r.addEventListener('input', () => { show(); const now = performance.now(); if (now - last > 50) { last = now; send(item.in, +r.value, true); } });
      r.addEventListener('change', () => send(item.in, +r.value, true));
      inputs.set(item.in, { get: () => +r.value, set: (x) => { r.value = x; show(); }, retained: true, nudge: (d) => {
        r.value = Math.max(0, Math.min(1, +r.value + d)); show(); send(item.in, +r.value, true); } });
      return [r, val];
    },
    keypad(item) {
      // momentary keys on one input: each press publishes {v: key} (not retained); the DSKY logic reads the sequence
      const pad = el('div', 'keypad');
      const key = (k, cls = '') => {
        const b = el('button', `key ${cls}`, { type: 'button', textContent: (item.labels || {})[k] || k });
        if (!k) { b.disabled = true; b.classList.add('blank'); return b; }
        const press = () => { b.classList.add('down'); send(item.in, k, false); setTimeout(() => b.classList.remove('down'), 120); };
        b.addEventListener('pointerdown', (e) => { e.preventDefault(); press(); });
        b.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); press(); } });
        keyButtons.set(k, press);
        return b;
      };
      const side = (keys, cls) => { const c = el('div', `keycol ${cls}`); keys.forEach((k) => c.appendChild(key(k, 'tall'))); return c; };
      const mid = el('div', 'keygrid');
      if (item.rows[0].length !== 5) mid.style.gridTemplateColumns = `repeat(${item.rows[0].length}, 3.3rem)`;
      for (const row of item.rows) for (const k of row) mid.appendChild(key(k));
      pad.append(side(item.left || [], 'left'), mid, side(item.right || [], 'right'));
      return [pad];
    },
    matrix(item) {
      // LED matrix (engine status): payload {rows: ["..g..", …]}, one character per LED: g, a, r, w or . (off)
      const m = el('div', 'matrix');
      m.style.gridTemplateColumns = `repeat(${item.cols}, 1fr)`;
      const cells = [];
      for (let i = 0; i < item.rows * item.cols; i++) { const c = el('i'); m.appendChild(c); cells.push(c); }
      const names = { g: 'green', a: 'amber', r: 'red', w: 'white' };
      outputs.set(item.out, (p) => cells.forEach((c, i) => {
        const ch = ((p.rows || [])[Math.floor(i / item.cols)] || '')[i % item.cols];
        c.className = names[ch] || '';
      }));
      return [m];
    },
    alpha(item) {
      // alphanumeric LED display (a row of 14-segment or dot-matrix characters): payload {text, blank}
      const d = el('div', 'alpha');
      d.style.width = `${item.chars * 0.86 + 1}rem`;
      outputs.set(item.out, (p) => { d.textContent = p.blank ? '' : String(p.text ?? '').slice(0, item.chars); });
      return [d];
    },
    buzzer(item) {
      const b = el('div', 'buzzer', { title: 'tone' });
      let audio = null, osc = null;
      outputs.set(item.out, (p) => {
        b.classList.toggle('lit', !!p.on);
        try {
          if (p.on && !osc) {
            audio = audio || new AudioContext();
            osc = audio.createOscillator(); const g = audio.createGain();
            osc.type = 'square'; osc.frequency.value = 760; g.gain.value = 0.04;
            const lfo = audio.createOscillator(), lg = audio.createGain();
            lfo.frequency.value = 3; lg.gain.value = 0.04; lfo.connect(lg).connect(g.gain); lfo.start();
            osc.connect(g).connect(audio.destination); osc.start();
          } else if (!p.on && osc) { osc.stop(); osc = null; }
        } catch (e) { /* no audio until a user gesture: the visual cue stays */ }
      });
      return [b];
    },
  };

  /* ---------- build ---------- */
  document.title = `Capsule · ${def.title}`;
  if (def.layout) document.body.classList.add(`layout-${def.layout}`);
  const nav = document.getElementById('nav');
  if (nav) {
    for (const [href, label, id] of [['index.html', 'ENG', 'eng'], ['index.html?panel=sys', 'SYS', 'sys'], ['index.html?panel=cmp', 'CMP', 'cmp'],
      ['index.html?panel=rdv', 'RDV', 'rdv'], ['index.html?panel=dsky', 'DSKY', 'dsky'],
      ['fdai.html', 'FDAI', 'fdai'], ['mfd.html', 'MFD', 'mfd']]) {
      const a = el('a', 'navlink', { href, textContent: label });
      if (id === PANEL_ID) a.setAttribute('aria-current', 'page');
      nav.appendChild(a);
    }
  }
  for (const sec of def.sections) {
    const plate = el('section', `plate ${sec.class || ''}`);
    plate.append(el('div', 'plate-title', { textContent: sec.title }), el('i', 'screw-b'));
    for (const item of sec.items) {
      const wrap = el('div', `ctl ${item.cls || ''} t-${item.type}`);
      const parts = builders[item.type] ? builders[item.type](item) : [el('div', 'sub', { textContent: `? ${item.type}` })];
      wrap.append(...parts, el('div', 'lbl', { textContent: item.label }));
      plate.appendChild(wrap);
    }
    root.appendChild(plate);
  }

  /* ---------- bus ---------- */
  const dot = document.getElementById('conn-dot'), ctext = document.getElementById('conn-text');
  const sniffList = document.getElementById('sniff-list'), sniffFilter = document.getElementById('sniff-filter');
  const sniffTlm = document.getElementById('sniff-tlm'), sniffer = document.getElementById('sniffer');
  document.getElementById('sniff-toggle').addEventListener('change', (e) => { sniffer.hidden = !e.target.checked; });
  document.getElementById('sniff-clear').addEventListener('click', () => { sniffList.textContent = ''; });
  const t0 = performance.now();
  function sniff(topic, payload) {
    if (sniffer.hidden) return;
    if (!sniffTlm.checked && topic.startsWith('tlm/')) return;
    if (sniffFilter.value && !topic.includes(sniffFilter.value)) return;
    const li = el('li');
    const cls = topic.includes('/in/') ? 'in' : topic.startsWith('cmd/') ? 'cmd' : '';
    li.innerHTML = `${((performance.now() - t0) / 1000).toFixed(2).padStart(8)}  <b class="${cls}"></b>  `;
    li.querySelector('b').textContent = topic;
    li.append(payload.length > 160 ? payload.slice(0, 160) + '…' : payload);
    sniffList.prepend(li);
    while (sniffList.childElementCount > 300) sniffList.lastChild.remove();
  }

  const statusTopic = `panel/${PANEL_ID}/status`;
  const started = Date.now();
  client = mqtt.connect(BROKER, {
    clientId: `panel-${PANEL_ID}-${Math.random().toString(16).slice(2, 8)}`, reconnectPeriod: 1000, connectTimeout: 4000,
    will: { topic: statusTopic, payload: JSON.stringify({ online: false }), qos: 1, retain: true },
  });
  client.on('connect', () => {
    dot.className = 'dot up'; ctext.textContent = `bus ${BROKER}`;
    restoring = true;
    client.subscribe([`panel/${PANEL_ID}/in/#`, `${OUT}#`, 'gateway/status', 'cockpit/status', 'cmd/#', 'cw/#', 'tlm/#', 'sim/#'], { qos: 1 });
    // after the retained switch positions have come back, publish every retained input once (first run: defaults)
    setTimeout(() => {
      restoring = false;
      for (const [name, c] of inputs) if (c.retained) send(name, c.get(), true);
    }, 700);
    client.publish(statusTopic, JSON.stringify({ online: true, fw: def.fw, config: hash(JSON.stringify(def)), uptime: 0 }), { qos: 1, retain: true });
  });
  client.on('close', () => { dot.className = 'dot down'; ctext.textContent = 'bus disconnected'; });
  client.on('error', (e) => { ctext.textContent = `bus error: ${e.message}`; });
  client.on('message', (topic, buf, pkt) => {
    const text = buf.toString();
    sniff(topic, text);
    let p = {};
    try { p = text ? JSON.parse(text) : {}; } catch { return; }
    if (topic.startsWith(OUT)) { const r = outputs.get(topic.slice(OUT.length)); if (r) r(p); return; }
    if (topic.startsWith(`panel/${PANEL_ID}/in/`)) {
      if (restoring && pkt.retain) { const c = inputs.get(topic.split('/').pop()); if (c && c.retained) c.set(p.v); }
      return;
    }
    if (topic === 'gateway/status') document.getElementById('plant').textContent = `plant: ${p.plant || '?'} ${p.connected ? '✓' : '✗'}${p.vessel ? ' · ' + p.vessel : ''}`;
    if (topic === 'cockpit/status') document.getElementById('cockpit').textContent = `cockpit: ${p.online ? '✓' : '✗'}`;
  });
  setInterval(() => client.connected && client.publish(statusTopic,
    JSON.stringify({ online: true, fw: def.fw, config: hash(JSON.stringify(def)), uptime: Math.round((Date.now() - started) / 1000) }),
    { qos: 1, retain: true }), 5000);

  function hash(s) { let h = 2166136261; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return (h >>> 0).toString(16); }

  /* ---------- bench (instructor, mock plant) ---------- */
  document.querySelectorAll('[data-bench]').forEach((b) => b.addEventListener('click', () => client.publish(b.dataset.bench, '{}', { qos: 1 })));
  document.querySelectorAll('[data-failure]').forEach((c) => c.addEventListener('change', () =>
    client.publish(`sim/failures/${c.dataset.failure}`, JSON.stringify({ on: c.checked }), { qos: 1, retain: true })));

  /* ---------- keyboard ---------- */
  const held = new Set();
  window.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT' && e.target.type !== 'range') return;
    if (held.has(e.code)) return;
    if (keyButtons.size && !e.ctrlKey && !e.metaKey && !e.altKey) {
      const map = { Enter: 'ENTR', Backspace: 'CLR', v: 'VERB', n: 'NOUN', p: 'PRO', r: 'RSET', k: 'KREL', '+': '+', '-': '-', '.': '.', ',': '.',
        Escape: 'CLR' };
      const k = /^[0-9]$/.test(e.key) ? e.key : map[e.key.length === 1 ? e.key.toLowerCase() : e.key];
      if (k && keyButtons.has(k)) { e.preventDefault(); keyButtons.get(k)(); return; }
    }
    if (e.code === 'Space' && e.target === document.body) { e.preventDefault(); held.add(e.code); inputs.get('stage')?.press(true); }
    if (e.code === 'KeyT') { held.add(e.code); inputs.get('lamp_test')?.press(true); }
    if (e.code === 'ArrowUp') { e.preventDefault(); inputs.get('throttle')?.nudge(0.05); }
    if (e.code === 'ArrowDown') { e.preventDefault(); inputs.get('throttle')?.nudge(-0.05); }
  });
  window.addEventListener('keyup', (e) => {
    held.delete(e.code);
    if (e.code === 'Space') inputs.get('stage')?.press(false);
    if (e.code === 'KeyT') inputs.get('lamp_test')?.press(false);
  });
})();
