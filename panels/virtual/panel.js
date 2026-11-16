/* Virtual panel: a dumb I/O node in a browser, standing in for a hardware panel. It draws itself from
   protocol/panels/<id>.json, publishes raw input changes on panel/<id>/in/<control> and draws whatever arrives on
   panel/<id>/out/<output>. There are no rules here: interlocks, lamps and displays are the cockpit logic's job.

   URL: index.html?panel=<id>&broker=ws://host:9001 */

import { createElement, createWidgetBuilders } from './widgets.js';

const PANEL_LINKS = [       // the navigation bar: [link, label, panel id]
  ['index.html', 'ENG', 'eng'], ['index.html?panel=sys', 'SYS', 'sys'], ['index.html?panel=cmp', 'CMP', 'cmp'],
  ['index.html?panel=rdv', 'RDV', 'rdv'], ['index.html?panel=com', 'COM', 'com'],
  ['index.html?panel=solo', 'SOLO', 'solo'], ['index.html?panel=lab', 'LAB', 'lab'],
  ['fdai.html', 'FDAI', 'fdai'], ['mfd.html', 'MFD', 'mfd'], ['cam.html', 'CAM', 'cam'], ['simsup.html', 'SIMSUP', 'simsup'], ['mcc.html', 'MCC', 'mcc'],
];
const RESTORE_WINDOW_MS = 700;      // after connecting, time given to the broker to send back the retained positions
const STATUS_EVERY_MS = 5000;
const SNIFFER_MAX_LINES = 300;
// What only the sniffer wants to see. Subscribed to while it is open: the telemetry alone is 50 messages a second.
const SNIFFER_ONLY_TOPICS = ['cmd/#', 'cw/#', 'tlm/#', 'sim/#'];
const SNIFFER_MAX_PAYLOAD_CHARACTERS = 160;
const THROTTLE_KEY_STEP = 0.05;
// keyboard key → keypad key, for panels that have a keypad
const KEYPAD_SHORTCUTS = {
  Enter: 'ENTR', Backspace: 'CLR', Escape: 'CLR', '+': '+', '-': '-', '.': '.', ',': '.',
};

const urlParameters = new URLSearchParams(location.search);
const panelId = urlParameters.get('panel') || 'eng';
const brokerUrl = urlParameters.get('broker') || `ws://${location.hostname || 'localhost'}:9001`;
const inputTopicPrefix = `panel/${panelId}/in/`;
const outputTopicPrefix = `panel/${panelId}/out/`;
const statusTopic = `panel/${panelId}/status`;

const registry = { outputs: new Map(), inputs: new Map(), keypadKeys: new Map() };
let client = null;
let restoringPositions = true;      // true while retained switch positions are being read back from the broker

function publishInput(control, value, retained) {
  if (!client || !client.connected) return;
  client.publish(inputTopicPrefix + control, JSON.stringify({ v: value }), { qos: 1, retain: Boolean(retained) });
}

/* A short fingerprint of the panel definition, reported in the status so a stale panel can be spotted (FNV-1a). */
function fingerprint(text) {
  let hash = 2166136261;
  for (let index = 0; index < text.length; index++) {
    hash ^= text.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(16);
}

function buildNavigation() {
  const navigation = document.getElementById('nav');
  if (!navigation) return;
  for (const [link, label, id] of PANEL_LINKS) {
    const anchor = createElement('a', 'navlink', { href: link, textContent: label });
    if (id === panelId) anchor.setAttribute('aria-current', 'page');
    navigation.appendChild(anchor);
  }
}

/* One plate per section of the definition, one widget per item. */
function buildPanel(definition) {
  document.title = `Capsule · ${definition.title}`;
  if (definition.layout) document.body.classList.add(`layout-${definition.layout}`);
  const builders = createWidgetBuilders(registry, publishInput);
  const panel = document.getElementById('panel');
  for (const section of definition.sections) {
    const plate = createElement('section', `plate ${section.class || ''}`);
    plate.append(createElement('div', 'plate-title', { textContent: section.title }), createElement('i', 'screw-b'));
    for (const item of section.items) {
      const wrapper = createElement('div', `ctl ${item.cls || ''} t-${item.type}`);
      const build = builders[item.type];
      const nodes = build ? build(item) : [createElement('div', 'sub', { textContent: `? ${item.type}` })];
      wrapper.append(...nodes, createElement('div', 'lbl', { textContent: item.label }));
      plate.appendChild(wrapper);
    }
    panel.appendChild(plate);
  }
}

/* The bus sniffer (the "bus" checkbox): a live list of messages, for debugging. Returns { sniff, isOpen };
   `onToggle(open)` is called when the checkbox changes. */
function createSniffer(onToggle) {
  const box = document.getElementById('sniffer');
  const list = document.getElementById('sniff-list');
  const topicFilter = document.getElementById('sniff-filter');
  const showTelemetry = document.getElementById('sniff-tlm');
  const startedAt = performance.now();
  document.getElementById('sniff-toggle').addEventListener('change', (event) => {
    box.hidden = !event.target.checked;
    onToggle(event.target.checked);
  });
  document.getElementById('sniff-clear').addEventListener('click', () => { list.textContent = ''; });
  function sniff(topic, payloadText) {
    if (box.hidden) return;
    if (!showTelemetry.checked && topic.startsWith('tlm/')) return;
    if (topicFilter.value && !topic.includes(topicFilter.value)) return;
    const line = createElement('li');
    const kind = topic.includes('/in/') ? 'in' : topic.startsWith('cmd/') ? 'cmd' : '';
    const seconds = ((performance.now() - startedAt) / 1000).toFixed(2).padStart(8);
    line.innerHTML = `${seconds}  <b class="${kind}"></b>  `;
    line.querySelector('b').textContent = topic;
    const tooLong = payloadText.length > SNIFFER_MAX_PAYLOAD_CHARACTERS;
    line.append(tooLong ? payloadText.slice(0, SNIFFER_MAX_PAYLOAD_CHARACTERS) + '…' : payloadText);
    list.prepend(line);
    while (list.childElementCount > SNIFFER_MAX_LINES) list.lastChild.remove();
  }
  return { sniff, isOpen: () => !box.hidden };
}

function connectToBus(definition) {
  const connectionDot = document.getElementById('conn-dot');
  const connectionText = document.getElementById('conn-text');
  const sniffer = createSniffer((open) => {
    if (!client.connected) return;
    if (open) client.subscribe(SNIFFER_ONLY_TOPICS, { qos: 1 });
    else client.unsubscribe(SNIFFER_ONLY_TOPICS);
  });
  const definitionFingerprint = fingerprint(JSON.stringify(definition));
  const startedAt = Date.now();
  const publishStatus = () => client.publish(statusTopic, JSON.stringify({
    online: true, fw: definition.fw, config: definitionFingerprint, uptime: Math.round((Date.now() - startedAt) / 1000),
  }), { qos: 1, retain: true });

  // `mqtt` is the global of vendor/mqtt.min.js. The "will" tells the bus the panel is gone if the page closes.
  client = mqtt.connect(brokerUrl, {
    clientId: `panel-${panelId}-${Math.random().toString(16).slice(2, 8)}`, reconnectPeriod: 1000, connectTimeout: 4000,
    will: { topic: statusTopic, payload: JSON.stringify({ online: false }), qos: 1, retain: true },
  });

  client.on('connect', () => {
    connectionDot.className = 'dot up';
    connectionText.textContent = `bus ${brokerUrl}`;
    restoringPositions = true;
    client.subscribe([`${inputTopicPrefix}#`, `${outputTopicPrefix}#`, 'gateway/status', 'cockpit/status'], { qos: 1 });
    if (sniffer.isOpen()) client.subscribe(SNIFFER_ONLY_TOPICS, { qos: 1 });
    // Switch positions are retained on the broker: take them back first, then publish every retained input once
    // (on the very first run, that publishes the defaults).
    setTimeout(() => {
      restoringPositions = false;
      for (const [name, input] of registry.inputs) if (input.retained) publishInput(name, input.read(), true);
    }, RESTORE_WINDOW_MS);
    publishStatus();
  });
  client.on('close', () => { connectionDot.className = 'dot down'; connectionText.textContent = 'bus disconnected'; });
  client.on('error', (error) => { connectionText.textContent = `bus error: ${error.message}`; });

  client.on('message', (topic, buffer, packet) => {
    const payloadText = buffer.toString();
    sniffer.sniff(topic, payloadText);
    let payload = {};
    try { payload = payloadText ? JSON.parse(payloadText) : {}; } catch { return; }
    if (topic.startsWith(outputTopicPrefix)) {
      const draw = registry.outputs.get(topic.slice(outputTopicPrefix.length));
      if (draw) draw(payload);
    } else if (topic.startsWith(inputTopicPrefix)) {
      // our own inputs echo back; only the retained ones seen while connecting are positions to restore
      const input = registry.inputs.get(topic.slice(inputTopicPrefix.length));
      if (restoringPositions && packet.retain && input && input.retained) input.restore(payload.v);
    } else if (topic === 'gateway/status') {
      const vessel = payload.vessel ? ` · ${payload.vessel}` : '';
      document.getElementById('plant').textContent = `plant: ${payload.plant || '?'} ${payload.connected ? '✓' : '✗'}${vessel}`;
    } else if (topic === 'cockpit/status') {
      document.getElementById('cockpit').textContent = `cockpit: ${payload.online ? '✓' : '✗'}`;
    }
  });
  setInterval(() => { if (client.connected) publishStatus(); }, STATUS_EVERY_MS);
}

/* The instructor's bench strip: reset the mock plant and inject failures. */
function wireInstructorBench() {
  document.querySelectorAll('[data-bench]').forEach((button) => button.addEventListener('click', () =>
    client.publish(button.dataset.bench, '{}', { qos: 1 })));
  document.querySelectorAll('[data-failure]').forEach((checkbox) => checkbox.addEventListener('change', () =>
    client.publish(`sim/failures/${checkbox.dataset.failure}`, JSON.stringify({ on: checkbox.checked }), { qos: 1, retain: true })));
}

/* Keyboard: keypad keys on panels that have one; Space = STAGE, T = lamp test, arrows = throttle. */
function wireKeyboard() {
  const { inputs, keypadKeys } = registry;
  const heldKeys = new Set();     // so that a held key presses its button once
  window.addEventListener('keydown', (event) => {
    const typingInAField = event.target.tagName === 'INPUT' && event.target.type !== 'range';
    if (typingInAField || heldKeys.has(event.code)) return;
    if (keypadKeys.size && !event.ctrlKey && !event.metaKey && !event.altKey) {
      const singleCharacter = event.key.length === 1 ? event.key.toLowerCase() : event.key;
      const key = /^[0-9]$/.test(event.key) ? event.key : KEYPAD_SHORTCUTS[singleCharacter];
      if (key && keypadKeys.has(key)) {
        event.preventDefault();
        keypadKeys.get(key)();
        return;
      }
    }
    if (event.code === 'Space' && event.target === document.body) {
      event.preventDefault();
      heldKeys.add(event.code);
      inputs.get('stage')?.press(true);
    }
    if (event.code === 'KeyT') { heldKeys.add(event.code); inputs.get('lamp_test')?.press(true); }
    if (event.code === 'ArrowUp') { event.preventDefault(); inputs.get('throttle')?.nudge(THROTTLE_KEY_STEP); }
    if (event.code === 'ArrowDown') { event.preventDefault(); inputs.get('throttle')?.nudge(-THROTTLE_KEY_STEP); }
  });
  window.addEventListener('keyup', (event) => {
    heldKeys.delete(event.code);
    if (event.code === 'Space') inputs.get('stage')?.press(false);
    if (event.code === 'KeyT') inputs.get('lamp_test')?.press(false);
  });
}

const definition = await (await fetch(`panels/${panelId}.json`, { cache: 'no-store' })).json();
buildNavigation();
buildPanel(definition);
connectToBus(definition);
wireInstructorBench();
wireKeyboard();
