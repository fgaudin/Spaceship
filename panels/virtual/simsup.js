/* SimSup page: a UI for the simsup service (simsup/). It only shows what the service publishes and sends requests on
   sim/simsup/cmd; the service holds the failures, triggers, scenarios and log, so closing the page loses nothing.

   URL: simsup.html?broker=ws://host:9001 */

import { connectBus, parse } from './bus.js';

const TRIGGERS = [['now', 'now'], ['met', 'at MET s'], ['alt_below', 'below m'], ['alt_above', 'above m'], ['stage', 'at stage']];
const STALE_AFTER_MS = 2000;

const element = (id) => document.getElementById(id);
const create = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
};
const formatMet = (seconds) => {
  if (seconds == null) return '--:--:--';
  const whole = Math.max(0, Math.floor(seconds));
  return [whole / 3600, (whole / 60) % 60, whole % 60].map((part) => String(Math.floor(part)).padStart(2, '0')).join(':');
};
const number = (value, decimals = 0) => (value == null || !Number.isFinite(value) ? '—' : value.toFixed(decimals));

const telemetry = {};
let catalogue = [], state = { active: [], armed: [], debrief: [], frozen: false }, log = [], telemetryAt = 0;
let client = null;
const send = (request) => client.publish('sim/simsup/cmd', JSON.stringify(request), { qos: 1 });

/* ---------- flight and what the crew sees ---------- */
function drawFlight() {
  const vessel = telemetry['tlm/vessel'] || {}, flight = telemetry['tlm/flight'] || {}, clock = telemetry['tlm/time'] || {};
  const stale = Date.now() - telemetryAt > STALE_AFTER_MS;
  const rows = [
    ['Vessel', vessel.name || '—'], ['Situation', vessel.situation || '—'], ['MET', formatMet(clock.met)],
    ['Altitude', `${number(flight.alt / 1000, 2)} km`], ['Speed', `${number(flight.speed, 1)} m/s`],
    ['Stage', vessel.stage ?? '—'], ['Throttle', `${number((vessel.throttle || 0) * 100)} %`],
    ['SAS', vessel.sas ? vessel.sas_mode || 'on' : 'off'], ['Telemetry', stale ? 'STALE' : 'live'],
  ];
  element('flight').replaceChildren(...rows.flatMap(([name, value]) => [create('dt', '', name), create('dd', '', String(value))]));
}

function drawAlarms(alarms) {
  const unacked = new Set(alarms.unacked || []);
  const nodes = (alarms.active || []).map((legend) => create('span', unacked.has(legend) ? 'unacked' : '', legend));
  element('alarms').replaceChildren(...(nodes.length ? nodes : [create('span', 'ss-empty', 'no alarm')]));
}

/* ---------- failures ---------- */
function buildFailures() {
  const groups = new Map();
  for (const failure of catalogue) {
    if (!groups.has(failure.group)) groups.set(failure.group, []);
    groups.get(failure.group).push(failure);
  }
  const container = element('failures');
  container.replaceChildren();
  for (const [group, failures] of groups) {
    const box = create('div', 'ss-group');
    box.append(create('h3', '', group.toUpperCase()));
    for (const failure of failures) box.append(buildFailure(failure));
    container.append(box);
  }
  drawState();
}

function buildFailure(failure) {
  const row = create('div', 'ss-failure');
  row.dataset.failure = failure.id;
  const title = create('div');
  title.append(create('div', '', failure.title), create('div', 'where', `${failure.id} · ${failure.where}`));
  const toggle = create('button', 'ss-btn', 'INJECT');
  toggle.type = 'button';
  const controls = create('div', 'controls');
  const parameterInputs = Object.entries(failure.parameters).map(([name, value]) => {
    const input = create('input');
    input.value = value;
    input.name = name;
    input.setAttribute('aria-label', `${failure.id} ${name}`);
    return input;
  });
  const parameters = () => Object.fromEntries(parameterInputs.map((input) => [input.name, input.value]));
  const trigger = create('select');
  trigger.setAttribute('aria-label', `${failure.id} trigger`);
  for (const [value, label] of TRIGGERS) trigger.append(Object.assign(create('option', '', label), { value }));
  const triggerValue = create('input', 'value');
  triggerValue.type = 'number';
  triggerValue.setAttribute('aria-label', `${failure.id} trigger value`);
  const arm = create('button', 'ss-btn', 'ARM');
  arm.type = 'button';
  controls.append(...parameterInputs, trigger, triggerValue, arm);

  toggle.addEventListener('click', () => {
    const active = state.active.some((each) => each.failure === failure.id);
    send(active ? { action: 'clear', failure: failure.id } : { action: 'inject', failure: failure.id, parameters: parameters() });
  });
  arm.addEventListener('click', () => {
    if (trigger.value === 'now') {
      send({ action: 'inject', failure: failure.id, parameters: parameters() });
      return;
    }
    const value = Number(triggerValue.value);
    if (triggerValue.value === '' || !Number.isFinite(value)) { triggerValue.focus(); return; }
    send({ action: 'arm', failure: failure.id, parameters: parameters(), trigger: { [trigger.value]: value } });
  });
  row.append(title, toggle, controls);
  return row;
}

function drawState() {
  const active = new Set(state.active.map((each) => each.failure));
  for (const row of document.querySelectorAll('.ss-failure')) {
    const on = active.has(row.dataset.failure);
    row.classList.toggle('active', on);
    const button = row.querySelector('button');
    button.textContent = on ? 'CLEAR' : 'INJECT';
    button.classList.toggle('on', on);
  }
  const armed = state.armed.map((each) => {
    const item = create('li');
    const disarm = create('button', 'ss-btn ss-small', 'DISARM');
    disarm.type = 'button';
    disarm.addEventListener('click', () => send({ action: 'disarm', number: each.number }));
    item.append(create('span', '', each.text), disarm);
    item.style.display = 'flex';
    return item;
  });
  element('armed').replaceChildren(...(armed.length ? armed : [create('li', 'ss-empty', 'nothing armed')]));
  const freeze = element('freeze');
  freeze.classList.toggle('on', state.frozen);
  freeze.textContent = state.frozen ? 'UNFREEZE' : 'FREEZE';
  const debrief = state.debrief.map((entry) => {
    const row = create('tr');
    row.append(create('td', '', entry.failure), create('td', '', formatMet(entry.met)),
      create('td', '', entry.ack_after == null ? '—' : `${entry.ack_after} s`),
      create('td', '', entry.action_after == null ? '—' : `${entry.action_after} s`));
    return row;
  });
  const empty = create('tr');
  empty.append(Object.assign(create('td', 'ss-empty', 'no failure yet'), { colSpan: 4 }));
  element('debrief').replaceChildren(...(debrief.length ? debrief : [empty]));
}

/* ---------- scenarios ---------- */
function drawScenarios(scenarios) {
  element('scenarios').replaceChildren(...scenarios.map((scenario) => {
    const item = create('li');
    const start = create('button', 'ss-btn', 'START');
    start.type = 'button';
    start.addEventListener('click', () => send({ action: 'scenario', name: scenario.name }));
    item.append(create('strong', '', scenario.name), create('p', '', scenario.briefing || ''), start);
    if (scenario.save) item.append(create('span', 'ss-empty', `  save: ${scenario.save}`));
    return item;
  }));
}

/* ---------- log ---------- */
function drawLog() {
  const kind = element('log-filter').value;
  const lines = log.filter((line) => !kind || line.kind === kind).slice(-400).reverse();
  element('log').replaceChildren(...lines.map((line) => {
    const item = create('li', `kind-${line.kind}`);
    item.append(create('span', '', formatMet(line.met)), create('span', '', line.kind), create('span', '', line.text));
    return item;
  }));
}

function exportLog() {
  const blob = new Blob([JSON.stringify({ scenario: state.scenario, debrief: state.debrief, log }, null, 1)], { type: 'application/json' });
  const link = Object.assign(document.createElement('a'), { href: URL.createObjectURL(blob), download: `simsup-${new Date().toISOString().slice(0, 16)}.json` });
  link.click();
  URL.revokeObjectURL(link.href);
}

/* ---------- wiring ---------- */
element('freeze').addEventListener('click', () => send({ action: 'freeze', on: !state.frozen }));
element('reset').addEventListener('click', () => {
  if (confirm('Reset the simulation? The mock plant starts a new flight and the cockpit logic resets.')) {
    client.publish('sim/reset', '{}', { qos: 1 });
  }
});
element('clear-all').addEventListener('click', () => send({ action: 'clear_all' }));
element('new-session').addEventListener('click', () => {
  if (confirm('Clear the log and the debrief?')) send({ action: 'new_session' });
});
element('load-form').addEventListener('submit', (event) => {
  event.preventDefault();
  const save = element('load-save').value.trim();
  if (save) send({ action: 'load', save });
});
element('note-form').addEventListener('submit', (event) => {
  event.preventDefault();
  const text = element('note').value.trim();
  if (text) { send({ action: 'note', text }); element('note').value = ''; }
});
element('log-filter').addEventListener('change', drawLog);
element('export').addEventListener('click', exportLog);

const services = { plant: '?', cockpit: '?', simsup: '?' };
const drawServices = () => { element('services').textContent = `plant ${services.plant} · cockpit ${services.cockpit} · simsup ${services.simsup}`; };

function onMessage(topic, text) {
  const payload = parse(text);
  if (payload === undefined) return;
  if (topic.startsWith('tlm/')) { telemetry[topic] = payload; telemetryAt = Date.now(); return; }
  if (topic === 'cw/state') drawAlarms(payload);
  else if (topic === 'sim/simsup/scenarios') { catalogue = payload.failures || []; buildFailures(); drawScenarios(payload.scenarios || []); services.simsup = '✓'; drawServices(); }
  else if (topic === 'sim/simsup/state') { state = payload; drawState(); }
  else if (topic === 'sim/simsup/log') { log = payload.log || []; drawLog(); }
  else if (topic === 'gateway/status') { services.plant = payload.connected ? `${payload.plant} ✓` : '✗'; drawServices(); }
  else if (topic === 'cockpit/status') { services.cockpit = payload.online ? '✓' : '✗'; drawServices(); }
}

client = connectBus({
  name: 'simsup-page',
  onConnect: (connection) => connection.subscribe(['sim/simsup/#', 'tlm/time', 'tlm/flight', 'tlm/vessel', 'cw/state',
    'gateway/status', 'cockpit/status'], { qos: 0 }),
  onMessage,
});
setInterval(drawFlight, 500);
