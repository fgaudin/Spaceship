/* CAPCOM, capsule communicator: the only console that talks to the crew. Reads up PADs (pad/uplink), only with a
   radio link, and follows the readback: the PAD waits on the burn computer until the crew accepts it. Also a feed
   of what the crew does on the panels. */
import { create, box, figures, formatMet } from '../ui.js';
import { store, publish, onMessage, met, linkUp } from '../bus.js';

const FEED_LINES = 150;
const NOISY_CONTROLS = new Set(['throttle', 'rot_pitch', 'rot_yaw', 'rot_roll', 'trans_right', 'trans_up', 'trans_fwd', 'key']);
const feed = [];
let setStatus, sendButton, feedList, form;

export function mount(root) {
  const padBox = box(root, 'PAD READ-UP');
  form = create('form', 'mcc-pad');
  const field = (name, label, placeholder) => {
    const input = create('input');
    input.name = name;
    input.placeholder = placeholder;
    input.inputMode = 'decimal';
    input.setAttribute('aria-label', label);
    const wrap = create('label', '', label);
    wrap.append(input);
    form.append(wrap);
  };
  field('tig', 'TIG (MET h:m:s)', '0:12:30');
  field('pro', 'Δv prograde m/s', '0');
  field('nrm', 'Δv normal m/s', '0');
  field('rad', 'Δv radial m/s', '0');
  sendButton = create('button', 'mcc-btn', 'READ UP');
  form.append(sendButton);
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    const values = Object.fromEntries(new FormData(form));
    const parts = String(values.tig).split(':').map(Number);
    const tig = parts.reduce((total, part) => total * 60 + part, 0);
    const delta = ['pro', 'nrm', 'rad'].map((name) => Number(values[name] || 0));
    if (!parts.every(Number.isFinite) || !delta.every(Number.isFinite)) return;
    publish('pad/uplink', { tig_met: tig, dv: delta });
    publish('mcc/loop/capcom', { text: `PAD read up: TIG ${formatMet(tig)}, Δv ${delta.join(' / ')}`, met: met() });
  });
  padBox.append(form);
  setStatus = figures(box(root, 'READBACK'), [['link', 'Link'], ['waiting', 'On the burn computer'], ['loaded', 'Loaded PAD']]);

  const crew = box(root, 'CREW ACTIONS', 'wide');
  feedList = create('ol', 'mcc-feed');
  crew.append(feedList);
  onMessage((topic, payload, retained) => {
    if (retained || !topic.startsWith('panel/') || !topic.includes('/in/')) return;
    const [, panel, , control] = topic.split('/');
    if (NOISY_CONTROLS.has(control) || panel === 'hc') return;
    feed.push({ met: met(), text: `${panel.toUpperCase()} ${control} → ${payload.v}` });
    feed.splice(0, feed.length - FEED_LINES);
    feedList.replaceChildren(...feed.slice().reverse().map((line) => {
      const item = create('li');
      item.append(create('span', 'met', formatMet(line.met)), create('span', '', line.text));
      return item;
    }));
  });
}

export function update() {
  const up = linkUp();
  sendButton.disabled = !up;
  sendButton.textContent = up ? 'READ UP' : 'LOS: NO READ-UP';
  setStatus('link', up ? 'AOS' : 'LOS', up ? 'good' : 'bad');
  const waiting = store['panel/cmp/out/lamp_uplink']?.on;
  setStatus('waiting', waiting ? 'waiting for ACCEPT' : 'nothing waiting', waiting ? 'warn' : '');
  const pad = store['cmp/pad'] || {};
  setStatus('loaded', pad.tig == null ? 'none' : `TIG ${formatMet(pad.tig)}, Δv ${(pad.dv || []).map((value) => value.toFixed(1)).join(' / ')}`);
}
