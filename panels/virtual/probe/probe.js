/* The probe control room: the telemetry rows the instructor has cleared (probe/clearance, catalogue.js), charts and
   events of the flight, and the flight program: written here, uplinked to the probe's sequencer (probe/program),
   started and stopped (probe/exec). The sequencer runs in the cockpit logic (cockpit/probe_sequencer.py) and reports
   on probe/sequencer; it obeys only in probe mode (probe/mode, from SimSup).

   Nothing here works anything out that is not cleared: a row that is not cleared shows dashes, and its series stays
   off the charts and out of the CSV export. */

import { store, onMessage, onConnect, publish, client, telemetryLive, linkUp } from '../mcc/bus.js';
import { history, onHistory } from '../mcc/history.js';
import { stripChart, AMBER, CYAN, GREEN, MAGENTA, WHITE } from '../mcc/charts.js';
import { create, formatMet } from '../mcc/ui.js';
import { BOXES, telemetryGroups, ACTION_NEEDS, SAS_MODE_NEEDS, TRIGGER_NEEDS } from './catalogue.js';

const G0 = 9.80665;
// t/unit of each propellant KSP's engines burn (stock resource densities)
const PROPELLANT_KG_PER_UNIT = { LiquidFuel: 5, Oxidizer: 5, SolidFuel: 7.5, XenonGas: 0.1 };
const SAS_MODES = ['stability', 'prograde', 'retrograde', 'normal', 'antinormal', 'radial', 'antiradial', 'target',
  'antitarget', 'maneuver'];
const ACTIONS = [['stage', 'STAGE'], ['throttle', 'THROTTLE'], ['kick', 'KICK'], ['sas', 'SAS ON/OFF'],
  ['sas_mode', 'SAS MODE'], ['burn', 'BURN'], ['chute', 'CHUTES'], ['science', 'EXPERIMENTS']];
// what the room sees happen; not ORBIT, SUBORBITAL or ESCAPE (that is for the students to work out), nor C&W
const FLIGHT_EVENTS = /^(LIFTOFF|TOUCHDOWN|SPLASHDOWN|DOCKED|UNDOCKED|STAGE|ENGINE|LOS|AOS)\b/;
const DRAFT_KEY = 'probe-draft', SAVED_KEY = 'probe-programs';
const UPDATE_EVERY_MS = 250;

const element = (id) => document.getElementById(id);
const cleared = () => new Set(store['probe/clearance']?.groups || []);
const isCleared = (group) => group == null || cleared().has(group);

onConnect(() => client.subscribe(['probe/#', 'panel/cmp/out/#'], { qos: 0 }));

/* ---------- formatting ---------- */
const finite = (value) => value != null && Number.isFinite(value);
const fmt = (value, decimals, unit = '') => (finite(value) ? `${value.toFixed(decimals)}${unit ? ` ${unit}` : ''}` : '—');
const distance = (metres) => {
  if (!finite(metres)) return '—';
  return Math.abs(metres) >= 100000 ? `${(metres / 1000).toFixed(1)} km` : Math.abs(metres) >= 10000
    ? `${(metres / 1000).toFixed(2)} km` : `${metres.toFixed(0)} m`;
};
function duration(seconds) {
  if (!finite(seconds)) return '—';
  const sign = seconds < 0 ? '-' : '', whole = Math.round(Math.abs(seconds));
  const d = Math.floor(whole / 86400), h = Math.floor(whole / 3600) % 24, m = Math.floor(whole / 60) % 60, s = whole % 60;
  const clock = `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  return `${sign}${d ? `${d}d ` : ''}${d || h ? `${String(h).padStart(2, '0')}:` : ''}${clock}`;
}
const angle = (degrees, positive, negative) => (finite(degrees)
  ? `${Math.abs(degrees).toFixed(3)}° ${degrees >= 0 ? positive : negative}` : '—');
const panelText = (output) => store[`panel/cmp/out/${output}`]?.text;

/* ---------- the readings ---------- */
function propellantKg(resources) {
  return Object.entries(resources || {}).reduce((sum, [name, value]) => sum + (PROPELLANT_KG_PER_UNIT[name] || 0) * (value.amount || 0), 0);
}

function reading(id) {
  const flight = store['tlm/flight'] || {}, orbit = store['tlm/orbit'] || {}, vessel = store['tlm/vessel'] || {};
  const attitude = store['tlm/attitude'] || {}, resources = store['tlm/resources'] || {}, thermal = store['tlm/thermal'] || {};
  const target = store['tlm/target'] || {}, pad = store['cmp/pad'] || {};
  const radius = finite(flight.alt) && finite(orbit.radius) ? flight.alt + orbit.radius : null;
  switch (id) {
    case 'alt': return distance(flight.alt);
    case 'vs': return fmt(flight.vs, 1, 'm/s');
    case 'radius': return finite(radius) ? `${(radius / 1000).toFixed(2)} km` : '—';
    case 'v_orb': return fmt(flight.v_orb, 1, 'm/s');
    case 'fpa': return finite(flight.vs) && flight.v_orb > 0
      ? `${(Math.asin(Math.max(-1, Math.min(1, flight.vs / flight.v_orb))) * 180 / Math.PI).toFixed(2)}°` : '—';
    case 'apo': return distance(orbit.apo);
    case 'peri': return distance(orbit.peri);
    case 'period': return duration(orbit.period);
    case 'sma': return finite(orbit.a) ? `${(orbit.a / 1000).toFixed(1)} km` : '—';
    case 'ecc': return fmt(orbit.e, 4);
    case 'lat': return angle(flight.lat, 'N', 'S');
    case 'lon': return angle(flight.lon, 'E', 'W');
    case 't_apo': return duration(orbit.t_apo);
    case 't_peri': return duration(orbit.t_peri);
    case 'inc': return fmt(orbit.i, 2, '°');
    case 'lan': return fmt(orbit.lan, 2, '°');
    case 'body': return orbit.body ? orbit.body.toUpperCase() : '—';
    case 't_soi': return orbit.body ? (finite(orbit.t_soi) ? duration(orbit.t_soi) : 'NONE') : '—';
    case 'radar': return distance(flight.radar);
    case 'hs': return fmt(flight.hs, 1, 'm/s');
    case 'stage': return vessel.stage ?? '—';
    case 'mass': return finite(vessel.mass) ? `${(vessel.mass / 1000).toFixed(3)} t` : '—';
    case 'thrust': return finite(vessel.thrust) ? `${(vessel.thrust / 1000).toFixed(1)} kN` : '—';
    case 'throttle': return finite(vessel.throttle) ? `${(vessel.throttle * 100).toFixed(0)} %` : '—';
    case 'prop': return resources.stage ? `${propellantKg(resources.stage).toFixed(0)} kg` : '—';
    case 'isp': return vessel.isp > 0 ? `${vessel.isp.toFixed(1)} s` : '—';
    case 'dv': {
      const mass = vessel.mass, burnt = propellantKg(resources.stage);
      return vessel.isp > 0 && mass > burnt && resources.stage ? `${(vessel.isp * G0 * Math.log(mass / (mass - burnt))).toFixed(0)} m/s` : '—';
    }
    case 'twr': {
      const g = finite(radius) && orbit.mu ? orbit.mu / radius ** 2 : null;
      return g && vessel.mass ? fmt((vessel.thrust_avail || 0) / (vessel.mass * g), 2) : '—';
    }
    case 'pitch': return fmt(attitude.pitch, 1, '°');
    case 'heading': return fmt(attitude.heading, 1, '°');
    case 'pro_pitch': return fmt(attitude.prograde?.pitch, 1, '°');
    case 'sas': return vessel.sas == null ? '—' : vessel.sas ? (vessel.sas_mode || 'on').toUpperCase() : 'OFF';
    case 'burn_state': return pad.state ? pad.state.toUpperCase() : '—';
    case 'vg': return pad.state && pad.state !== 'idle' && panelText('disp_vg') ? `${panelText('disp_vg')} m/s` : '—';
    case 'tb': return pad.state && pad.state !== 'idle' && /\d/.test(panelText('disp_tb') || '') ? `${panelText('disp_tb')} s` : '—';
    case 'att_err': return pad.state && pad.state !== 'idle' && /\d/.test(panelText('disp_att') || '') ? `${panelText('disp_att')}°` : '—';
    case 'charge': {
      const charge = resources.total?.ElectricCharge;
      return charge?.max ? `${(100 * charge.amount / charge.max).toFixed(0)} %` : '—';
    }
    case 'p': return finite(flight.p) ? `${(flight.p / 1000).toFixed(3)} kPa` : '—';
    case 'temp': return fmt(thermal.outside, 1, '°C');
    case 'q': return finite(flight.q) ? `${(flight.q / 1000).toFixed(2)} kPa` : '—';
    case 'g': return fmt(flight.g, 2, 'g');
    case 'heat': return finite(thermal.max) ? `${(thermal.max * 100).toFixed(0)} %` : '—';
    case 'tgt': return target.set ? target.name : 'NONE';
    case 'range': return target.set ? distance(target.range) : '—';
    case 'rel_v': return target.set ? fmt(target.rel_v, 2, 'm/s') : '—';
    case 'closing': return target.set ? fmt(target.closing, 2, 'm/s') : '—';
    default: return '—';
  }
}

/* ---------- the telemetry boxes ---------- */
let valueCells = [];               // [{id, cell}] of the rows cleared
let clearanceShown = null;

function buildBoxes() {
  const groups = cleared();
  clearanceShown = [...groups].sort().join(',');
  valueCells = [];
  for (const [boxId, title] of BOXES) {
    const container = element(`box-${boxId}`);
    container.replaceChildren(create('h2', '', title));
    for (const group of telemetryGroups().filter((each) => each.box === boxId)) {
      const on = groups.has(group.id);
      const list = create('dl', `pr-group${on ? '' : ' locked'}`);
      list.title = on ? group.title : `${group.title}: not cleared yet (${group.module})`;
      for (const [id, label] of group.rows) {
        const row = create('div', 'pr-reading');
        const value = create('dd', '', on ? '—' : '— — —');
        row.append(create('dt', '', label), value);
        list.append(row);
        if (on) valueCells.push({ id, cell: value });
      }
      container.append(list);
    }
  }
  buildCharts();
  drawDraft();
}

function updateReadings() {
  const live = telemetryLive();
  document.querySelectorAll('.pr-box').forEach((box) => box.classList.toggle('pr-stale', !live));
  for (const { id, cell } of valueCells) cell.textContent = String(reading(id));
}

/* ---------- the strip bar ---------- */
function updateStrip() {
  const clock = store['tlm/time'] || {}, vessel = store['tlm/vessel'] || {}, sequencer = store['probe/sequencer'] || {};
  element('met').textContent = formatMet(clock.met);
  const link = element('link');
  link.textContent = !telemetryLive() ? 'NO DATA' : linkUp() ? 'AOS' : 'LOS';
  link.className = !telemetryLive() || !linkUp() ? 'los' : '';
  element('vessel').textContent = vessel.name || '—';
  const state = element('seq-state');
  state.textContent = (sequencer.state || '—').toUpperCase();
  state.className = sequencer.state === 'running' ? '' : sequencer.state === 'stopped' ? 'alert' : 'dim';
  element('seq-next').textContent = nextStepText(sequencer, clock);
  element('mode-warning').hidden = Boolean(store['probe/mode']?.on);
  const gateway = store['gateway/status'], cockpit = store['cockpit/status'];
  element('services').textContent = `plant ${gateway ? (gateway.connected ? `${gateway.plant} ✓` : '✗') : '?'} · cockpit ${cockpit ? (cockpit.online ? '✓' : '✗') : '?'}`;
}

/* When a step is due: seconds from now, or null. */
function dueIn(step, sequencer, clock) {
  if ('burnout' in step) return null;
  if ('t' in step) return sequencer.go_ut != null && clock.ut != null ? sequencer.go_ut + step.t - clock.ut : null;
  return clock.met != null ? step.met - clock.met : null;
}

function nextStepText(sequencer, clock) {
  const step = sequencer.steps?.[sequencer.current];
  if (sequencer.state !== 'running' || !step) return '—';
  if (step.status === 'active') return `${step.do.toUpperCase()} …`;
  if ('burnout' in step) return `${step.do.toUpperCase()} at burnout`;
  const seconds = dueIn(step, sequencer, clock);
  return `${step.do.toUpperCase()} ${seconds == null ? '' : `in ${duration(Math.max(0, seconds))}`}`;
}

/* ---------- charts ---------- */
const CHARTS = {
  'chart-alt': [
    { group: 'altitude', label: 'ALT', color: AMBER, unit: 'km', decimals: 2, value: (c, i) => c.alt[i] / 1000 },
    { group: 'apsides', label: 'APO', color: CYAN, unit: 'km', decimals: 1, dash: [6, 4], value: (c, i) => c.apo[i] / 1000 },
    // a periapsis under the ground (−600 km on the way up) would squash the rest: only above the surface
    { group: 'apsides', label: 'PERI', color: MAGENTA, unit: 'km', decimals: 1, dash: [6, 4], value: (c, i) => (c.peri[i] >= 0 ? c.peri[i] / 1000 : null) },
  ],
  'chart-speed': [
    { group: 'altitude', label: 'VS', color: GREEN, unit: 'm/s', value: (c, i) => c.vs[i] },
    { group: 'state', label: 'V ORB', color: WHITE, unit: 'm/s', value: (c, i) => c.vorb[i] },
  ],
};
let charts = [];

function buildCharts() {
  charts = [];
  for (const [id, lines] of Object.entries(CHARTS)) {
    const old = element(id);
    const area = create('div', 'pr-chart');
    area.id = id;
    old.replaceWith(area);
    const series = lines.filter((line) => isCleared(line.group));
    if (!series.length) { area.append(create('div', 'pr-chart-empty', 'NOT CLEARED')); continue; }
    requestAnimationFrame(() => {
      const chart = stripChart(area, { series });
      chart.update(history().columns);
      charts.push(chart);
    });
  }
}
onHistory(() => { for (const chart of charts) chart.update(history().columns); });

/* ---------- events ---------- */
function drawEvents() {
  const flightEvents = (history().events || [])
    .filter((event) => FLIGHT_EVENTS.test(event.text) || (isCleared('soi') && event.text.startsWith('SOI ')))
    .map((event) => ({ met: event.t, text: event.text, kind: 'flight' }));
  const sequencerEvents = (store['probe/sequencer']?.log || []).map((line) => ({ ...line, kind: 'seq' }));
  // newest first; at the same MET, the later one first (each list is in the order things happened)
  const all = [...flightEvents, ...sequencerEvents].map((event, order) => ({ ...event, order }))
    .sort((a, b) => (b.met ?? -1) - (a.met ?? -1) || b.order - a.order).slice(0, 200);
  element('events').replaceChildren(...all.map((event) => {
    const item = create('li', event.kind);
    item.append(create('span', '', formatMet(event.met)), create('span', '', event.text));
    return item;
  }));
}
onHistory(drawEvents);

/* The cleared columns of the flight so far, one sample a second, as CSV for the students' spreadsheet. */
const EXPORT_COLUMNS = [['alt', 'altitude', 'alt_m'], ['vs', 'altitude', 'vs_mps'], ['vorb', 'state', 'v_orb_mps'],
  ['apo', 'apsides', 'apo_m'], ['peri', 'apsides', 'peri_m'], ['lat', 'position', 'lat_deg'], ['lon', 'position', 'lon_deg'],
  ['radar', 'landing', 'radar_m'], ['mass', 'mass', 'mass_kg'], ['thrust', 'mass', 'thrust_n'], ['thr', 'mass', 'throttle'],
  ['q', 'loads', 'q_pa'], ['g', 'loads', 'g'], ['heat', 'thermal', 'heat_frac'], ['ec', 'power', 'charge_frac']];

function exportCsv() {
  const columns = history().columns;
  const chosen = EXPORT_COLUMNS.filter(([, group]) => isCleared(group));
  const lines = [['met_s', ...chosen.map(([, , header]) => header)].join(',')];
  columns.t.forEach((t, index) => {
    lines.push([t, ...chosen.map(([name]) => (columns[name][index] ?? ''))].join(','));
  });
  const blob = new Blob([lines.join('\n')], { type: 'text/csv' });
  const name = `${(store['tlm/vessel']?.name || 'probe').replace(/\W+/g, '-')}-${new Date().toISOString().slice(0, 16)}.csv`;
  const link = Object.assign(document.createElement('a'), { href: URL.createObjectURL(blob), download: name });
  link.click();
  URL.revokeObjectURL(link.href);
}

/* ---------- the program draft ---------- */
let draft = loadDraft();

function loadDraft() {
  try {
    const saved = JSON.parse(localStorage.getItem(DRAFT_KEY));
    if (saved && Array.isArray(saved.steps)) return saved;
  } catch { /* a draft that does not parse is dropped */ }
  return { name: '', steps: [{ when: 't', time: 0, do: 'stage' }] };
}
const keepDraft = () => localStorage.setItem(DRAFT_KEY, JSON.stringify(draft));
const savedPrograms = () => { try { return JSON.parse(localStorage.getItem(SAVED_KEY)) || {}; } catch { return {}; } };

/* "90", "1:30" or "1:02:03" → seconds; null when it is not a time. */
function parseTime(text) {
  const parts = String(text).trim().split(':');
  if (!parts.length || parts.length > 3 || parts.some((part) => !/^\d+(\.\d+)?$/.test(part))) return null;
  return parts.reduce((total, part) => total * 60 + Number(part), 0);
}
const showTime = (seconds) => (seconds >= 60 ? duration(seconds) : String(seconds));

const DEFAULTS = { throttle: { v: 1 }, sas: { on: true }, sas_mode: { mode: 'stability' },
  kick: { pitch: 0, yaw: 0, roll: 0, s: 2 }, burn: { dv: [0, 0, 0], throttle: 1 } };

function numberInput(label, value, step, onChange, attributes = {}) {
  const wrap = create('label', '', label);
  const input = create('input');
  Object.assign(input, { type: 'number', step, value, ...attributes });
  input.addEventListener('change', () => { if (input.value !== '' && Number.isFinite(Number(input.value))) onChange(Number(input.value)); });
  wrap.append(input);
  return wrap;
}

function settingsFor(step) {
  const box = create('div', 'settings');
  const set = (key) => (value) => { step[key] = value; keepDraft(); };
  if (step.do === 'throttle') box.append(numberInput('%', Math.round(step.v * 100), 1, (value) => set('v')(Math.max(0, Math.min(100, value)) / 100), { min: 0, max: 100 }));
  if (step.do === 'sas') {
    const select = create('select');
    select.append(new Option('ON', 'on'), new Option('OFF', 'off'));
    select.value = step.on ? 'on' : 'off';
    select.addEventListener('change', () => set('on')(select.value === 'on'));
    box.append(select);
  }
  if (step.do === 'sas_mode') {
    const select = create('select');
    for (const mode of SAS_MODES) {
      const option = new Option(mode.toUpperCase(), mode);
      option.disabled = !isCleared(SAS_MODE_NEEDS[mode]);
      select.append(option);
    }
    select.value = step.mode;
    select.addEventListener('change', () => set('mode')(select.value));
    box.append(select);
  }
  if (step.do === 'kick') {
    for (const axis of ['pitch', 'yaw', 'roll']) {
      box.append(numberInput(axis[0].toUpperCase(), step[axis], 0.05, (value) => set(axis)(Math.max(-1, Math.min(1, value))), { min: -1, max: 1 }));
    }
    box.append(numberInput('s', step.s, 0.5, set('s'), { min: 0.1, max: 60 }));
  }
  if (step.do === 'burn') {
    ['P', 'N', 'R'].forEach((name, index) => box.append(numberInput(name, step.dv[index], 0.1,
      (value) => { step.dv[index] = value; keepDraft(); })));
    box.append(numberInput('%', Math.round(step.throttle * 100), 1, (value) => set('throttle')(Math.max(1, Math.min(100, value)) / 100), { min: 1, max: 100 }));
  }
  if (!box.childElementCount) box.append(create('span', 'pr-hint', '—'));
  return box;
}

function drawDraft() {
  element('program-name').value = draft.name || '';
  const body = element('draft');
  body.replaceChildren(...draft.steps.map((step, index) => {
    const row = create('tr');
    if (!stepCleared(step)) row.className = 'not-cleared';
    const when = create('select');
    when.title = 'T+: seconds after GO · MET: mission time · BURNOUT+: seconds after the engines the next staging drops run dry';
    for (const [value, label] of [['t', 'T+'], ['met', 'MET'], ['burnout', 'BURNOUT+']]) {
      const option = new Option(label, value);
      option.disabled = !isCleared(TRIGGER_NEEDS[value]);
      when.append(option);
    }
    when.value = step.when;
    when.disabled = step.do === 'burn';            // a burn's TIG is a mission time
    when.addEventListener('change', () => { step.when = when.value; keepDraft(); });
    const time = create('input', 'time');
    time.value = showTime(step.time);
    time.addEventListener('change', () => {
      const seconds = parseTime(time.value);
      time.classList.toggle('bad', seconds == null);
      if (seconds != null) { step.time = seconds; keepDraft(); }
    });
    const action = create('select');
    for (const [id, label] of ACTIONS) {
      const option = new Option(label, id);
      option.disabled = !isCleared(ACTION_NEEDS[id]);
      action.append(option);
    }
    action.value = step.do;
    action.addEventListener('change', () => {
      for (const key of Object.keys(step)) if (!['when', 'time'].includes(key)) delete step[key];
      Object.assign(step, { do: action.value }, structuredClone(DEFAULTS[action.value] || {}));
      if (step.do === 'burn') step.when = 'met';
      keepDraft();
      drawDraft();
    });
    const tools = create('div', 'tools');
    const button = (text, title, onClick) => {
      const each = create('button', 'pr-btn icon', text);
      Object.assign(each, { type: 'button', title });
      each.addEventListener('click', () => { onClick(); keepDraft(); drawDraft(); });
      return each;
    };
    tools.append(
      button('▲', 'Move up', () => { if (index) draft.steps.splice(index - 1, 0, draft.steps.splice(index, 1)[0]); }),
      button('▼', 'Move down', () => { if (index < draft.steps.length - 1) draft.steps.splice(index + 1, 0, draft.steps.splice(index, 1)[0]); }),
      button('⧉', 'Duplicate', () => draft.steps.splice(index + 1, 0, structuredClone(step))),
      button('✕', 'Remove', () => draft.steps.splice(index, 1)),
    );
    const cells = [String(index + 1), when, time, action, settingsFor(step), tools];
    row.append(...cells.map((content) => {
      const cell = create('td');
      cell.append(content);
      return cell;
    }));
    return row;
  }));
  drawSaved();
}

function drawSaved() {
  const select = element('saved');
  const names = Object.keys(savedPrograms()).sort();
  select.replaceChildren(new Option('saved programs…', ''), ...names.map((name) => new Option(name, name)));
}

/* The draft as the sequencer takes it (cockpit/probe_sequencer.py parse_program). */
function wireProgram() {
  return {
    name: draft.name || 'program',
    steps: draft.steps.map((step) => {
      const { when, time, ...rest } = step;
      return { [step.do === 'burn' ? 'met' : when]: time, ...rest };
    }),
  };
}

const stepCleared = (step) => isCleared(ACTION_NEEDS[step.do]) && isCleared(TRIGGER_NEEDS[step.when])
  && !(step.do === 'sas_mode' && !isCleared(SAS_MODE_NEEDS[step.mode]));

function uplink() {
  const notCleared = draft.steps.findIndex((step) => !stepCleared(step));
  if (notCleared >= 0) { showMessage(`STEP ${notCleared + 1} IS NOT CLEARED`); return; }
  if (!store['probe/mode']?.on) { showMessage('PROBE MODE OFF: NOTHING WILL LISTEN'); return; }
  publish('probe/program', wireProgram());
}

let localMessage = '';
function showMessage(text) {
  localMessage = text;
  drawOnboard();
  setTimeout(() => { if (localMessage === text) { localMessage = ''; drawOnboard(); } }, 4000);
}

/* ---------- on board ---------- */
function stepText(step) {
  switch (step.do) {
    case 'throttle': return `THROTTLE ${(step.v * 100).toFixed(0)} %`;
    case 'sas': return `SAS ${step.on ? 'ON' : 'OFF'}`;
    case 'sas_mode': return `SAS ${step.mode.toUpperCase()}`;
    case 'kick': return `KICK ${['pitch', 'yaw', 'roll'].filter((axis) => step[axis]).map((axis) => `${axis.toUpperCase()} ${step[axis] > 0 ? '+' : ''}${step[axis]}`).join(' ') || 'NONE'} FOR ${step.s} s`;
    case 'burn': return `BURN P ${step.dv[0]} N ${step.dv[1]} R ${step.dv[2]} m/s`;
    default: return step.do.toUpperCase();
  }
}

function drawOnboard() {
  const sequencer = store['probe/sequencer'] || {}, clock = store['tlm/time'] || {};
  element('onboard-name').textContent = sequencer.name ? `${sequencer.name} · ${(sequencer.state || '').toUpperCase()}` : 'no program';
  element('onboard-message').textContent = localMessage || sequencer.message || '';
  element('onboard').replaceChildren(...(sequencer.steps || []).map((step, index) => {
    const next = sequencer.state === 'running' && index === sequencer.current && step.status === 'wait';
    const item = create('li', next ? 'next' : step.status);
    const when = 'burnout' in step ? `BURNOUT+${showTime(step.burnout)}` : 't' in step ? `T+${showTime(step.t)}` : `MET ${formatMet(step.met)}`;
    let status = step.status.toUpperCase();
    if (next) { const seconds = dueIn(step, sequencer, clock); status = seconds == null ? 'WAITING' : duration(Math.max(0, seconds)); }
    item.append(create('span', '', String(index + 1)), create('span', '', when), create('span', '', stepText(step)), create('span', 'status', status));
    return item;
  }));
  const state = sequencer.state;
  element('go').disabled = state !== 'loaded';
  element('stop').disabled = state !== 'running' && state !== 'done';   // a finished program can leave the engine burning
  element('clear').disabled = !state || state === 'empty' || state === 'running';
}

/* ---------- wiring ---------- */
element('program-name').addEventListener('change', (event) => { draft.name = event.target.value.trim(); keepDraft(); });
element('add').addEventListener('click', () => {
  const last = draft.steps[draft.steps.length - 1];
  draft.steps.push({ when: last?.when === 'met' ? 'met' : 't', time: (last?.time || 0) + 1, do: 'stage' });
  keepDraft();
  drawDraft();
});
element('save').addEventListener('click', () => {
  const name = (draft.name || '').trim() || prompt('Name of the program?');
  if (!name) return;
  draft.name = name;
  localStorage.setItem(SAVED_KEY, JSON.stringify({ ...savedPrograms(), [name]: draft }));
  keepDraft();
  drawDraft();
});
element('saved').addEventListener('change', (event) => {
  const program = savedPrograms()[event.target.value];
  if (program) { draft = structuredClone(program); keepDraft(); drawDraft(); }
});
element('delete').addEventListener('click', () => {
  const name = element('saved').value || draft.name;
  const all = savedPrograms();
  if (name && all[name] && confirm(`Delete the saved program ${name}?`)) {
    delete all[name];
    localStorage.setItem(SAVED_KEY, JSON.stringify(all));
    drawSaved();
  }
});
element('uplink').addEventListener('click', uplink);
element('go').addEventListener('click', () => {
  if (confirm(`GO: start ${store['probe/sequencer']?.name || 'the program'} on board now?`)) publish('probe/exec', { do: 'go' });
});
element('stop').addEventListener('click', () => publish('probe/exec', { do: 'stop' }));
element('clear').addEventListener('click', () => publish('probe/exec', { do: 'clear' }));
element('export').addEventListener('click', exportCsv);

onMessage((topic) => {
  if (topic === 'probe/clearance') {
    const shown = [...cleared()].sort().join(',');
    if (shown !== clearanceShown) buildBoxes();
  } else if (topic === 'probe/sequencer') {
    drawOnboard();
    drawEvents();
  }
});

buildBoxes();
drawOnboard();
setInterval(() => { updateReadings(); updateStrip(); }, UPDATE_EVERY_MS);
setInterval(drawOnboard, 1000);         // the countdowns
