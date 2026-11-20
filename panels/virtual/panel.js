/* The virtual console: every module of the capsule, drawn at its physical size and laid out as in the capsule, each one
   a dumb I/O node standing in for its board. Nothing reflows: a module is W×H U (1 U = 100 mm), its panels sit at
   fixed U positions and their controls at fixed mm positions; only the zoom changes.

     protocol/panels/console.json   the capsule: zones (overhead, main), each a grid of modules in U
     protocol/panels/<module>.json  one module (one board): its panels, their controls, each panel's bus namespace

   One view, like a map: the wheel zooms around the pointer, dragging pans, every control works at any zoom.
   Double-click a module (or #<module> in the address) to fit it; Esc fits the whole console. Each module publishes
   raw inputs on panel/<bus>/in/<control>, draws what arrives on panel/<bus>/out/<output> and its heartbeat on
   panel/<module>/status, over its own bus connection like its board would. There are no rules here: interlocks,
   lamps and displays are the cockpit logic's job.

   URL: index.html[#<module>][?broker=ws://host:9001]; index.html?panel=<module> fits that module (old links). */

import { connectBus, parse } from './bus.js';
import { createElement, createWidgetBuilders } from './widgets.js';
import { describeBudget, moduleBudget, overBudget, overLimits } from './budget.js';
import { handControllerKey, releaseHandControllers, startHandControllers } from './hand_controllers.js';

const U_MM = 100;                            // a slot; a panel is built smaller by its clearance
const PANEL_CLEARANCE_MM = 0.5;              // on each side: a 1 U panel is 99 mm, neighbours are 1 mm apart
const PX_PER_MM = 96 / 25.4;                 // CSS millimetres
const MAX_FIT_ZOOM = 1;                      // fitting never draws bigger than real size; + does
const ZOOM_STEP = 1.25;
const VIEW_MARGIN_PX = 32;
const LAYOUT_TOLERANCE_MM = 0.5;
const RESTORE_WINDOW_MS = 700;      // after connecting, time given to the broker to send back the retained positions
const STATUS_EVERY_MS = 5000;
const SNIFFER_MAX_LINES = 300;
const SNIFFER_TOPICS = ['panel/#', 'cmd/#', 'cw/#', 'tlm/#', 'sim/#'];
const SNIFFER_MAX_PAYLOAD_CHARACTERS = 160;
const SIDE_MIN_PX = 240;                     // the side column (help, bus): narrowest it can be dragged
const SIDE_MAX_FRACTION = 0.7;               // and widest, as a share of the window
const SIDE_WIDTH_KEY = 'console-side-width';
// keyboard key → keypad key, for consoles that have a keypad
const KEYPAD_SHORTCUTS = {
  Enter: 'ENTR', Backspace: 'CLR', '+': '+', '-': '-', '.': '.', ',': '.',
};

const outputs = new Map();     // output topic → [{ module, draw }]
const inputs = new Map();      // input topic  → { module, read, restore, retained, press?, nudge? }
const inputsByName = new Map();// control name → input, for the keyboard shortcuts
const keypadKeys = new Map();  // key → press()
const modules = new Map();     // module id → { definition, element, home, sizeU, client, restoring }
const layoutIssues = [];

/* A short fingerprint of a definition, reported in the status so a stale module can be spotted (FNV-1a). */
function fingerprint(text) {
  let hash = 2166136261;
  for (let index = 0; index < text.length; index++) {
    hash ^= text.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(16);
}

const mm = (value) => `${value}mm`;

/* The extent in U of things placed at `at` with a `size` (panels in a module, modules in a zone). */
function extent(placed, sizeOf) {
  let width = 0, height = 0;
  for (const thing of placed) {
    const [w, h] = sizeOf(thing);
    width = Math.max(width, thing.at[0] + w);
    height = Math.max(height, thing.at[1] + h);
  }
  return [width, height];
}

function overlapping(a, b) {
  return a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
}

function reportLayout(message, element) {
  layoutIssues.push(message);
  element?.classList.add('misplaced');
  console.warn(`layout: ${message}`);
}

/* Things placed on a grid of U that overlap (panels in a module, modules in a zone). */
function checkGrid(placed, sizeOf, nameOf, where) {
  const boxes = placed.map((thing) => {
    const [w, h] = sizeOf(thing);
    return { name: nameOf(thing), left: thing.at[0], top: thing.at[1], right: thing.at[0] + w, bottom: thing.at[1] + h };
  });
  boxes.forEach((a, i) => boxes.slice(i + 1).forEach((b) => {
    if (overlapping(a, b)) reportLayout(`${a.name} and ${b.name} overlap in ${where}`);
  }));
}

/* The faceplate of a panel of `size` U: its slot less the clearance on each side, in mm. */
const faceplateMm = (size) => size.map((u) => u * U_MM - 2 * PANEL_CLEARANCE_MM);

/* One panel: a plate in its W×H U slot with its engraved title and screws, each control at its mm position. */
function buildPanel(module, panel) {
  const [width, height] = panel.size;
  const [widthMm, heightMm] = faceplateMm(panel.size);
  // a bare panel is glass set straight into the console board: no faceplate, title or screws
  const plate = createElement('section', panel.bare ? 'plate bare' : 'plate', { title: `${panel.title} · ${width}×${height} U (${widthMm}×${heightMm} mm)` });
  Object.assign(plate.style, {
    left: mm(panel.at[0] * U_MM + PANEL_CLEARANCE_MM), top: mm(panel.at[1] * U_MM + PANEL_CLEARANCE_MM), width: mm(widthMm), height: mm(heightMm),
  });
  plate.dataset.panel = panel.id;
  if (!panel.bare) plate.append(createElement('div', 'plate-title', { textContent: panel.title }), createElement('i', 'screw-b'));

  if (panel.screen?.frame) plate.appendChild(buildScreenFrame(module, panel));
  if (panel.screen) plate.appendChild(buildScreen(module, panel));
  const node = modules.get(module.id);
  const prefix = `panel/${panel.bus}/`;
  const publishInput = (name, value, retained) => {
    if (node.client?.connected) node.client.publish(prefix + 'in/' + name, JSON.stringify({ v: value }), { qos: 1, retain: Boolean(retained) });
  };
  const scoped = {
    outputs: { set: (name, draw) => {
      const topic = prefix + 'out/' + name;
      if (!outputs.has(topic)) outputs.set(topic, []);
      outputs.get(topic).push({ module: module.id, draw });
    } },
    inputs: { set: (name, input) => {
      const topic = prefix + 'in/' + name;
      if (inputs.has(topic)) reportLayout(`${topic} is on two panels`);
      inputs.set(topic, { ...input, module: module.id });
      inputsByName.set(name, input);
    } },
    keypadKeys,
  };
  const builders = createWidgetBuilders(scoped, publishInput);
  for (const item of panel.items || []) {
    const control = createElement('div', `ctl ${item.cls || ''} t-${item.type}`);
    const build = builders[item.type];
    const nodes = build ? build(item) : [createElement('div', 'sub', { textContent: `? ${item.type}` })];
    control.append(...nodes, createElement('div', 'lbl', { textContent: item.label }));
    if (item.at) Object.assign(control.style, { left: mm(item.at[0]), top: mm(item.at[1]) });
    else reportLayout(`${module.id}/${panel.id}/${item.id} has no position`, control);
    control.dataset.item = item.id;
    plate.appendChild(control);
  }
  return plate;
}

/* A glass panel's screen: the page at the screen's own resolution, scaled to the screen's size in mm and centred
   under the panel's title. The page publishes its own status; the module has no I/O of its own. */
const SCREEN_TOP_MM = 14;
function buildScreen(module, panel) {
  const { page, mm: [widthMm, heightMm], px: [widthPx, heightPx], at, round } = panel.screen;
  const frame = createElement('div', `glass${round ? ' round' : ''}`, { title: `${panel.screen.inches || ''}" screen, ${widthPx}×${heightPx}` });
  const [plateWidthMm, plateHeightMm] = faceplateMm(panel.size);
  const left = at ? at[0] - widthMm / 2 : (plateWidthMm - widthMm) / 2;      // `at`: the screen's centre on the faceplate
  const top = at ? at[1] - heightMm / 2 : SCREEN_TOP_MM;
  Object.assign(frame.style, { left: mm(left), top: mm(top), width: mm(widthMm), height: mm(heightMm) });
  if (left < 0 || top < 0 || left + widthMm > plateWidthMm || top + heightMm > plateHeightMm) reportLayout(`${module.id}/${panel.id}: the screen does not fit the panel`, frame);
  const broker = new URLSearchParams(location.search).get('broker');
  const page_url = `${page}${page.includes('?') ? '&' : '?'}embed=1${broker ? `&broker=${encodeURIComponent(broker)}` : ''}`;
  const view = createElement('iframe', '', { src: page_url, title: panel.title, loading: 'eager' });
  Object.assign(view.style, { width: `${widthPx}px`, height: `${heightPx}px`, transform: `scale(${(widthMm * PX_PER_MM) / widthPx})` });
  frame.appendChild(view);
  return frame;
}

/* A riveted metal frame around a screen (`screen.frame`: {width, rivet, rivet_every, corner}, mm): a ring `width` wide
   around the glass, its outer corners rounded to `corner`, with rivets of `rivet` diameter along its middle, about
   `rivet_every` apart and one in each corner. */
function buildScreenFrame(module, panel) {
  const { mm: [glassWidth, glassHeight], at, frame: { width, rivet = 5, rivet_every: spacing = 30, corner = 3 } } = panel.screen;
  const [plateWidthMm, plateHeightMm] = faceplateMm(panel.size);
  const [centreX, centreY] = at || [plateWidthMm / 2, SCREEN_TOP_MM + glassHeight / 2];
  const [outerWidth, outerHeight] = [glassWidth + 2 * width, glassHeight + 2 * width];
  const [left, top] = [centreX - outerWidth / 2, centreY - outerHeight / 2];
  const ring = createElement('div', 'screen-frame');
  Object.assign(ring.style, { left: mm(left), top: mm(top), width: mm(outerWidth), height: mm(outerHeight), borderRadius: mm(corner) });
  if (left < -LAYOUT_TOLERANCE_MM || top < -LAYOUT_TOLERANCE_MM || left + outerWidth > plateWidthMm + LAYOUT_TOLERANCE_MM
      || top + outerHeight > plateHeightMm + LAYOUT_TOLERANCE_MM) reportLayout(`${module.id}/${panel.id}: the screen frame does not fit the panel`, ring);
  // the rivets' line: the middle of the ring, corner to corner
  const [lineWidth, lineHeight] = [outerWidth - width, outerHeight - width];
  const along = (length) => {
    const gaps = Math.max(1, Math.round(length / spacing));
    return Array.from({ length: gaps + 1 }, (_, index) => (index * length) / gaps);
  };
  const points = [
    ...along(lineWidth).flatMap((x) => [[x, 0], [x, lineHeight]]),
    ...along(lineHeight).slice(1, -1).flatMap((y) => [[0, y], [lineWidth, y]]),
  ];
  for (const [x, y] of points) {
    const head = createElement('i', 'rivet');
    Object.assign(head.style, { left: mm(width / 2 + x), top: mm(width / 2 + y), width: mm(rivet), height: mm(rivet) });
    ring.appendChild(head);
  }
  return ring;
}

/* One module: its panels on a grid of U, and the cover that opens it from the overview. */
function buildModule(module) {
  const sizeU = extent(module.panels, (panel) => panel.size);
  // a module of bare glass only (the windows) has no board of its own to draw: the glass is set into the console's
  const bare = module.panels.every((panel) => panel.bare);
  const element = createElement('article', bare ? 'module bare' : 'module', { id: `module-${module.id}` });
  Object.assign(element.style, { width: mm(sizeU[0] * U_MM), height: mm(sizeU[1] * U_MM) });
  modules.set(module.id, { definition: module, element, sizeU, client: null, restoring: true });
  for (const panel of module.panels) element.appendChild(buildPanel(module, panel));
  const code = module.id.toUpperCase();
  const tag = createElement('div', 'module-tag', { textContent: module.title.startsWith(code) ? module.title : `${code} · ${module.title}` });
  if (hardware && !bare) {                  // what the panels ask of the board (budget.js), under the name
    const budget = moduleBudget(module, hardware);
    budgets.set(module.id, budget);
    for (const line of describeBudget(budget)) tag.appendChild(createElement('div', 'module-budget', { textContent: line }));
    tag.classList.toggle('over-budget', overBudget(budget));
  }
  element.appendChild(tag);
  element.title = `${module.id.toUpperCase()} · ${module.title} · ${sizeU[0]}×${sizeU[1]} U · ${module.board} (double-click: fit)`;
  checkGrid(module.panels, (panel) => panel.size, (panel) => panel.id, `module ${module.id}`);
  return element;
}

/* A zone with a shape of its own (`outline`, corners in U): the grid is cut to it and the outline drawn around it. */
function buildOutlinedZone(grid, outline, widthMm, heightMm) {
  const corners = outline.map(([x, y]) => [x * U_MM, y * U_MM]);
  grid.style.clipPath = `polygon(${corners.map(([x, y]) => `${mm(x)} ${mm(y)}`).join(', ')})`;
  const body = createElement('div', 'zone-body');
  Object.assign(body.style, { width: mm(widthMm), height: mm(heightMm) });
  const drawing = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  drawing.classList.add('zone-outline');
  drawing.setAttribute('viewBox', `0 0 ${widthMm} ${heightMm}`);
  Object.assign(drawing.style, { width: mm(widthMm), height: mm(heightMm) });
  const shape = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
  shape.setAttribute('points', corners.map((corner) => corner.join(',')).join(' '));
  drawing.appendChild(shape);
  body.append(grid, drawing);
  return body;
}

/* The zones one under the other, in a column; a zone with a `side` (left or right) beside that column, its top at
   the column's top, or `top` U lower (the windows, alongside OVERHEAD and MAIN). A `flush` side zone has no title
   and touches the column. */
function buildConsole(consoleLayout, definitions) {
  const overview = document.getElementById('overview');
  const columns = { left: createElement('div', 'zone-side left'), centre: createElement('div', 'zone-column'),
    right: createElement('div', 'zone-side right') };
  overview.append(columns.left, columns.centre, columns.right);
  for (const zone of consoleLayout.zones) {
    if (zone.side && !(zone.side in columns && zone.side !== 'centre')) reportLayout(`zone ${zone.id}: side ${zone.side}`);
    const placed = zone.modules.filter((entry) => {
      if (definitions.has(entry.module)) return true;
      reportLayout(`console.json places ${entry.module}, which has no file`);
      return false;
    });
    const sizeOf = (entry) => modules.get(entry.module)?.sizeU || [0, 0];
    const section = createElement('section', 'zone', { ariaLabel: zone.title });
    const grid = createElement('div', 'zone-grid');
    for (const entry of placed) {
      const element = buildModule(definitions.get(entry.module));
      Object.assign(element.style, { left: mm(entry.at[0] * U_MM), top: mm(entry.at[1] * U_MM) });
      grid.appendChild(element);
    }
    // a zone may be given a size, larger than what it holds, so that its free places show
    const [usedWidth, usedHeight] = extent(placed, sizeOf);
    const [width, height] = [Math.max(usedWidth, zone.size?.[0] || 0), Math.max(usedHeight, zone.size?.[1] || 0)];
    if (zone.size && (usedWidth > zone.size[0] || usedHeight > zone.size[1])) reportLayout(`zone ${zone.id}: modules go past its size`);
    Object.assign(grid.style, { width: mm(width * U_MM), height: mm(height * U_MM) });
    checkGrid(placed, sizeOf, (entry) => entry.module, `zone ${zone.id}`);
    if (zone.align === 'center') section.classList.add('centered');
    if (zone.side && zone.top) section.style.marginTop = mm(zone.top * U_MM);
    if (zone.side && zone.flush) {
      section.classList.add('flush');
      columns[zone.side]?.classList.add('flush');
    }
    const body = zone.outline ? buildOutlinedZone(grid, zone.outline, width * U_MM, height * U_MM) : grid;
    section.append(createElement('div', 'zone-title', { textContent: zone.title }), body);
    (columns[zone.side] && zone.side !== 'centre' ? columns[zone.side] : columns.centre).appendChild(section);
  }
}

/* Controls must sit inside their panel and not on top of one another (measured once drawn). */
/* A box against a round screen: controls may sit in the corners around the circle. */
function touchesCircle(box, circle) {
  const radius = (circle.right - circle.left) / 2;
  const x = (circle.left + circle.right) / 2, y = (circle.top + circle.bottom) / 2;
  return Math.hypot(x - Math.max(box.left, Math.min(x, box.right)), y - Math.max(box.top, Math.min(y, box.bottom))) < radius;
}

function checkControls() {
  for (const plate of document.querySelectorAll('.plate')) {
    const plateBox = plate.getBoundingClientRect();
    const scale = plateBox.width / (plate.offsetWidth || 1);       // the zoom, so that the tolerance stays in mm
    const tolerance = LAYOUT_TOLERANCE_MM * PX_PER_MM * scale;
    const shrink = (box) => ({ left: box.left + tolerance, right: box.right - tolerance, top: box.top + tolerance, bottom: box.bottom - tolerance });
    // a screen is an obstacle like a control: nothing may sit on it
    const controls = [...plate.querySelectorAll(':scope > .ctl, :scope > .glass')].map((element) => ({
      element, box: shrink(element.getBoundingClientRect()), round: element.classList.contains('round'),
    }));
    const name = (element) => `${plate.closest('.module').id.replace('module-', '')}/${plate.dataset.panel}/${element.dataset.item || 'screen'}`;
    for (const { element, box } of controls) {
      if (box.left < plateBox.left || box.right > plateBox.right || box.top < plateBox.top || box.bottom > plateBox.bottom) {
        reportLayout(`${name(element)} sticks out of its panel`, element);
      }
    }
    controls.forEach((a, i) => controls.slice(i + 1).forEach((b) => {
      const hit = a.round ? touchesCircle(b.box, a.box) : b.round ? touchesCircle(a.box, b.box) : overlapping(a.box, b.box);
      if (hit) reportLayout(`${name(a.element)} and ${name(b.element)} overlap`, b.element);
    }));
  }
  const status = document.getElementById('layout-status');
  status.hidden = layoutIssues.length === 0;
  status.textContent = `layout: ${layoutIssues.length} issue${layoutIssues.length === 1 ? '' : 's'}`;
  status.title = layoutIssues.join('\n');
}

/* ---------- the view: one console, zoomed with the wheel and panned by dragging ---------- */

const MIN_ZOOM = 0.05;
const MAX_ZOOM = 3;
const WHEEL_ZOOM_RATE = 0.0015;              // per pixel of wheel travel
const WHEEL_LINE_PX = 33;                    // a wheel that counts in lines (Firefox's mouse wheel)
// where a press is meant for a control, not for panning
const INTERACTIVE = 'button, input, a, select, textarea, label, iframe, .rotary-wrap, .keypad';
const view = { zoom: 1 };
const consoleBox = () => document.getElementById('console');
const overview = () => document.getElementById('overview');

function showZoom() {
  document.getElementById('zoom-level').textContent = `${Math.round(view.zoom * 100)} %`;
  overview().style.setProperty('--view-zoom', view.zoom);    // keeps the module names one size at any zoom
}

/* While Left Alt is held: every module's name and boundary, and how many modules there are (boards to build: the
   windows, bare glass with no board, do not count). */
function showModules(on) {
  overview().classList.toggle('show-modules', on);
  let badge = document.getElementById('module-count');
  if (!badge) {
    badge = createElement('div', 'module-count', { id: 'module-count' });
    document.body.appendChild(badge);
  }
  const modules = [...overview().querySelectorAll('.module:not(.bare)')];
  const glass = modules.filter((module) => module.querySelector('.glass')).length;
  badge.textContent = `${modules.length} MODULES · ${modules.length - glass} I/O, ${glass} glass`;
  const powered = [...budgets.values()].filter((budget) => budget.board.rails_w);    // on PoE: what the switch must give
  if (powered.length) {
    const sum = (key) => powered.reduce((total, budget) => total + budget[key], 0).toFixed(0);
    const over = [...budgets.entries()].filter(([, budget]) => overBudget(budget))
      .map(([id, budget]) => `${id.toUpperCase()} (${overLimits(budget).join(', ')})`);
    badge.textContent += ` · PoE ${sum('typicalW')} W, ${sum('lampTestW')} W lamp test${over.length ? ` · over at lamp test: ${over.join(', ')}` : ''}`;
  }
  badge.hidden = !on;
}

/* The console and the side column (help, sniffer) fill the window under the top bar: nothing is below them. */
function sizeConsoleBox() {
  const workspace = document.getElementById('workspace');
  workspace.style.height = `${Math.max(200, window.innerHeight - workspace.offsetTop)}px`;
}

/* Zoom, keeping the point of the console under (x, y) where it is. */
function zoomAt(zoom, x, y) {
  const box = consoleBox(), content = overview();
  const before = content.getBoundingClientRect();
  const across = (x - before.left) / before.width, down = (y - before.top) / before.height;
  view.zoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, zoom));
  content.style.zoom = view.zoom;
  const after = content.getBoundingClientRect();
  box.scrollLeft += after.left + across * after.width - x;
  box.scrollTop += after.top + down * after.height - y;
  showZoom();
}

function zoomAtCentre(zoom) {
  const box = consoleBox().getBoundingClientRect();
  zoomAt(zoom, box.left + box.width / 2, box.top + box.height / 2);
}

/* Zoom so that an element (a module, or the whole console) fills the window, never above real size, and centre it. */
function fit(element) {
  const box = consoleBox(), content = overview();
  const rect = element.getBoundingClientRect();
  const natural = [rect.width / view.zoom, rect.height / view.zoom];
  view.zoom = Math.min(MAX_FIT_ZOOM, (box.clientWidth - VIEW_MARGIN_PX) / natural[0], (box.clientHeight - VIEW_MARGIN_PX) / natural[1]);
  content.style.zoom = view.zoom;
  const target = element.getBoundingClientRect(), frame = box.getBoundingClientRect();
  box.scrollLeft += target.left + target.width / 2 - (frame.left + frame.width / 2);
  box.scrollTop += target.top + target.height / 2 - (frame.top + frame.height / 2);
  showZoom();
}

/* #<module> fits that module; no hash, the whole console. */
function showView() {
  const wanted = decodeURIComponent(location.hash.slice(1));
  const module = modules.get(wanted);
  fit(module ? module.element : overview());
  document.title = module ? `Capsule · ${wanted.toUpperCase()}` : 'Capsule · console';
}

function fitAll() {
  if (location.hash) location.hash = '';          // hashchange fits
  else showView();
}

function fitModule(id) {
  if (location.hash === `#${id}`) showView();
  else location.hash = id;
}

function wireViews() {
  const box = consoleBox();
  box.addEventListener('wheel', (event) => {
    if (event.defaultPrevented) return;            // a knob took it
    event.preventDefault();
    const pixels = event.deltaY * (event.deltaMode === 1 ? WHEEL_LINE_PX : 1);
    zoomAt(view.zoom * Math.exp(-pixels * WHEEL_ZOOM_RATE), event.clientX, event.clientY);
  }, { passive: false });

  // Drag to pan: the left button on anything that is not a control, or the middle button anywhere.
  let drag = null;
  box.addEventListener('pointerdown', (event) => {
    const middle = event.button === 1;
    if (!middle && (event.button !== 0 || event.target.closest(INTERACTIVE))) return;
    if (middle) event.preventDefault();
    drag = { x: event.clientX, y: event.clientY, left: box.scrollLeft, top: box.scrollTop, id: event.pointerId };
    box.setPointerCapture(event.pointerId);
    box.classList.add('panning');
  });
  box.addEventListener('pointermove', (event) => {
    if (!drag || event.pointerId !== drag.id) return;
    box.scrollLeft = drag.left - (event.clientX - drag.x);
    box.scrollTop = drag.top - (event.clientY - drag.y);
  });
  const endDrag = () => { drag = null; box.classList.remove('panning'); };
  box.addEventListener('pointerup', endDrag);
  box.addEventListener('pointercancel', endDrag);
  box.addEventListener('auxclick', (event) => { if (event.button === 1) event.preventDefault(); });

  // Double-click on a module (not on a control): fit it.
  box.addEventListener('dblclick', (event) => {
    // the target is the console itself when panning captured the pointer: look under the pointer instead
    const under = document.elementFromPoint(event.clientX, event.clientY);
    const module = under?.closest('.module');
    if (module && !under.closest(INTERACTIVE)) fitModule(module.id.replace('module-', ''));
  });

  // The wheel over a glass page: the page sends it here (shell.js), in its own coordinates.
  window.addEventListener('message', (event) => {
    if (event.origin !== location.origin) return;
    if (event.data?.type === 'console-escape') fitAll();
    if (event.data?.type === 'console-modules') showModules(Boolean(event.data.on));
    if (event.data?.type === 'console-key') handControllerKey(event.data.code, Boolean(event.data.down));
    if (event.data?.type === 'console-key-release') releaseHandControllers();
    if (event.data?.type !== 'console-wheel') return;
    const frame = [...document.querySelectorAll('.glass iframe')].find((element) => element.contentWindow === event.source);
    if (!frame) return;
    const rect = frame.getBoundingClientRect();
    const scale = rect.height / frame.clientHeight;     // the page's pixels → the window's (its wheel travel too)
    const x = rect.left + event.data.x * scale, y = rect.top + event.data.y * scale;
    zoomAt(view.zoom * Math.exp(-event.data.pixels * scale * WHEEL_ZOOM_RATE), x, y);
  });

  window.addEventListener('hashchange', showView);
  window.addEventListener('resize', sizeConsoleBox);
  document.getElementById('zoom-in').addEventListener('click', () => zoomAtCentre(view.zoom * ZOOM_STEP));
  document.getElementById('zoom-out').addEventListener('click', () => zoomAtCentre(view.zoom / ZOOM_STEP));
  document.getElementById('zoom-fit').addEventListener('click', fitAll);
  document.getElementById('grid-toggle').addEventListener('change', (event) => document.body.classList.toggle('show-grid', event.target.checked));
}

/* ---------- the bus ---------- */

/* Each module is its own node on the bus, as its board will be: its own connection, heartbeat and will. */
function connectModule(node) {
  const { definition } = node;
  // A module with a screen: its page reports panel/<module>/status itself, so the I/O node reports beside it (two
  // clients in the virtual console, one board on the hardware).
  const hasScreen = definition.panels.some((panel) => panel.screen);
  const statusTopic = `panel/${definition.id}/${hasScreen ? 'io/' : ''}status`;
  const buses = [...new Set(definition.panels.map((panel) => panel.bus))];
  const definitionFingerprint = fingerprint(JSON.stringify(definition));
  const startedAt = Date.now();
  const publishStatus = () => node.client.publish(statusTopic, JSON.stringify({
    online: true, fw: definition.fw, config: definitionFingerprint, uptime: Math.round((Date.now() - startedAt) / 1000),
  }), { qos: 1, retain: true });
  const ownInputs = () => [...inputs.entries()].filter(([, input]) => input.module === definition.id);

  node.client = connectBus({
    name: `panel-${definition.id}`,
    will: { topic: statusTopic, payload: { online: false } },
    onConnect(client) {
      node.restoring = true;
      client.subscribe(buses.flatMap((bus) => [`panel/${bus}/in/#`, `panel/${bus}/out/#`]), { qos: 1 });
      // Switch positions are retained on the broker: take them back first, then publish every retained input once
      // (on the very first run, that publishes the defaults).
      setTimeout(() => {
        node.restoring = false;
        for (const [topic, input] of ownInputs()) {
          if (input.retained) client.publish(topic, JSON.stringify({ v: input.read() }), { qos: 1, retain: true });
        }
      }, RESTORE_WINDOW_MS);
      publishStatus();
    },
    onMessage(topic, payloadText, packet) {
      const payload = parse(payloadText);
      if (payload === undefined) return;
      if (topic.includes('/out/')) {
        for (const output of outputs.get(topic) || []) if (output.module === definition.id) output.draw(payload);
      } else if (topic.includes('/in/')) {
        // our own inputs echo back; only the retained ones seen while connecting are positions to restore
        const input = inputs.get(topic);
        if (node.restoring && packet.retain && input?.retained && input.module === definition.id) input.restore(payload.v);
      }
    },
  });
  setInterval(() => { if (node.client.connected) publishStatus(); }, STATUS_EVERY_MS);
}

/* The bus sniffer (the "bus" checkbox): a live list of messages, for debugging. */
function createSniffer() {
  const box = document.getElementById('sniffer');
  const list = document.getElementById('sniff-list');
  const topicFilter = document.getElementById('sniff-filter');
  const showTelemetry = document.getElementById('sniff-tlm');
  const startedAt = performance.now();
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
  return { sniff, box };
}

/* The console's own connection: plant and cockpit status in the top bar, the sniffer. */
/* GAME in the side column: how fast KSP runs, game seconds per real second with the warp taken out, over the last few
   seconds of tlm/time. Under 1, the game cannot keep up (its frame rate itself is not available through kRPC). */
const GAME_SPEED_WINDOW_MS = 3000;
const gameClock = [];
function showGameSpeed() {
  const now = performance.now();
  while (gameClock.length && now - gameClock[0].at > GAME_SPEED_WINDOW_MS) gameClock.shift();
  const element = document.getElementById('game-speed');
  const first = gameClock[0], last = gameClock[gameClock.length - 1];
  let text = 'no telemetry', tone = '';
  if (last?.paused) text = 'paused';
  else if (first && last && last.at - first.at > 1000 && last.ut != null && first.ut != null) {
    const speed = (last.ut - first.ut) / ((last.at - first.at) / 1000) / last.warp;
    text = `${speed.toFixed(2)}× real time · warp ${last.warp}×`;
    tone = speed >= 0.95 ? 'good' : speed >= 0.8 ? 'warn' : 'bad';
  }
  element.textContent = text;
  element.className = `game-speed ${tone}`;
}
setInterval(showGameSpeed, 1000);

function connectConsole() {
  const sniffer = createSniffer();
  const client = connectBus({
    name: 'console',
    onConnect(connected) {
      connected.subscribe(['gateway/status', 'cockpit/status', 'cockpit/lighting', 'tlm/time'], { qos: 1 });
      if (!sniffer.box.hidden) connected.subscribe(SNIFFER_TOPICS, { qos: 1 });
    },
    onMessage(topic, payloadText) {
      sniffer.sniff(topic, payloadText);
      const payload = parse(payloadText);
      if (payload === undefined) return;
      if (topic === 'tlm/time') {
        gameClock.push({ at: performance.now(), ut: payload.ut, warp: payload.warp || 1, paused: payload.paused });
      } else if (topic === 'gateway/status') {
        const vessel = payload.vessel ? ` · ${payload.vessel}` : '';
        document.getElementById('plant').textContent = `plant: ${payload.plant || '?'} ${payload.connected ? '✓' : '✗'}${vessel}`;
      } else if (topic === 'cockpit/status') {
        document.getElementById('cockpit').textContent = `cockpit: ${payload.online ? '✓' : '✗'}`;
      } else if (topic === 'cockpit/lighting') {
        // LIGHTS panel: the cabin light brightens the plates, the backlight makes the legends glow
        document.body.classList.add('lighting-known');
        document.body.classList.toggle('cabin-light', Boolean(payload.cabin));
        document.body.classList.toggle('backlight', Boolean(payload.backlight));
      }
    },
  });
  document.getElementById('sniff-toggle').addEventListener('change', (event) => {
    sniffer.box.hidden = !event.target.checked;
    if (!client.connected) return;
    if (event.target.checked) client.subscribe(SNIFFER_TOPICS, { qos: 1 });
    else client.unsubscribe(SNIFFER_TOPICS);
  });
}

/* The side column's grip: drag it to make the column wider (bus lines stop wrapping), arrows nudge it, double-click
   goes back to the default width. The width is kept in this browser. */
function wireSideResize() {
  const side = document.getElementById('side'), grip = document.getElementById('side-grip');
  const clamp = (width) => Math.round(Math.min(window.innerWidth * SIDE_MAX_FRACTION, Math.max(SIDE_MIN_PX, width)));
  const setWidth = (width, keep = true) => {
    side.style.flexBasis = width == null ? '' : `${clamp(width)}px`;
    if (!keep) return;
    try {
      if (width == null) localStorage.removeItem(SIDE_WIDTH_KEY);
      else localStorage.setItem(SIDE_WIDTH_KEY, String(clamp(width)));
    } catch { /* private window */ }
  };
  try {
    const saved = Number(localStorage.getItem(SIDE_WIDTH_KEY));
    if (saved > 0) setWidth(saved, false);
  } catch { /* private window */ }
  grip.addEventListener('pointerdown', (event) => {
    event.preventDefault();
    grip.setPointerCapture(event.pointerId);
    grip.classList.add('dragging');
    const startX = event.clientX, startWidth = side.getBoundingClientRect().width;
    const move = (moveEvent) => setWidth(startWidth + startX - moveEvent.clientX, false);
    const up = (upEvent) => {
      grip.removeEventListener('pointermove', move);
      grip.removeEventListener('pointerup', up);
      grip.removeEventListener('pointercancel', up);
      grip.classList.remove('dragging');
      setWidth(startWidth + startX - upEvent.clientX);
    };
    grip.addEventListener('pointermove', move);
    grip.addEventListener('pointerup', up);
    grip.addEventListener('pointercancel', up);
  });
  grip.addEventListener('dblclick', () => setWidth(null));
  grip.addEventListener('keydown', (event) => {
    const step = { ArrowLeft: 40, ArrowRight: -40 }[event.key];
    if (!step) return;
    event.preventDefault();
    setWidth(side.getBoundingClientRect().width + step);
  });
}

/* Keyboard: Esc fits the whole console; keypad keys (Backspace = CLR); Space = STAGE, T = lamp test; the hand
   controllers and the throttle on KSP's keys (hand_controllers.js). */
function wireKeyboard() {
  const heldKeys = new Set();     // so that a held key presses its button once
  window.addEventListener('blur', () => showModules(false));     // Alt released in another window never reaches us
  window.addEventListener('keydown', (event) => {
    if (event.code === 'AltLeft') {
      event.preventDefault();                                    // no browser menu
      showModules(true);
      return;
    }
    const typingInAField = event.target.tagName === 'INPUT' && !['range', 'checkbox'].includes(event.target.type);
    if (!typingInAField && handControllerKey(event.code, true)) {
      event.preventDefault();                                    // Ctrl + a stick key: no browser shortcut
      return;
    }
    if (typingInAField || heldKeys.has(event.code)) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      fitAll();
      return;
    }
    if (keypadKeys.size && !event.ctrlKey && !event.metaKey && !event.altKey) {
      const singleCharacter = event.key.length === 1 ? event.key.toLowerCase() : event.key;
      const key = /^[0-9]$/.test(event.key) ? event.key : KEYPAD_SHORTCUTS[singleCharacter];
      if (key && keypadKeys.has(key)) {
        event.preventDefault();
        keypadKeys.get(key)();
        return;
      }
    }
    if (event.code === 'Space' && (event.target === document.body || event.target === consoleBox())) {
      event.preventDefault();
      heldKeys.add(event.code);
      inputsByName.get('stage')?.press(true);
    }
    if (event.code === 'KeyT') { heldKeys.add(event.code); inputsByName.get('lamp_test')?.press(true); }
  });
  window.addEventListener('keyup', (event) => {
    if (event.code === 'AltLeft') {
      event.preventDefault();
      showModules(false);
    }
    if (handControllerKey(event.code, false)) return;
    heldKeys.delete(event.code);
    if (event.code === 'Space') inputsByName.get('stage')?.press(false);
    if (event.code === 'KeyT') inputsByName.get('lamp_test')?.press(false);
  });
}

async function fetchJson(path) {
  return (await fetch(path, { cache: 'no-store' })).json();
}

const consoleLayout = await fetchJson('panels/console.json');
let hardware = null;                        // the I/O and power assumptions (budget.js); the console works without them
try { hardware = await fetchJson('panels/hardware.json'); } catch { /* no estimate */ }
const budgets = new Map();                  // module id → its estimate
const ids = [...new Set(consoleLayout.zones.flatMap((zone) => zone.modules.map((entry) => entry.module)))];
const definitions = new Map((await Promise.all(ids.map(async (id) => {
  try { return [id, await fetchJson(`panels/${id}.json`)]; } catch { return null; }
}))).filter(Boolean));

const oldPanelLink = new URLSearchParams(location.search).get('panel');
if (oldPanelLink && !location.hash) history.replaceState(null, '', `#${oldPanelLink}`);

buildConsole(consoleLayout, definitions);
wireViews();
wireKeyboard();
startHandControllers({ container: document.getElementById('hand-controllers'), throttle: inputsByName.get('throttle')?.nudge });
wireSideResize();
sizeConsoleBox();
showView();
requestAnimationFrame(() => requestAnimationFrame(checkControls));
// a module made only of glass has no I/O: its pages connect themselves
for (const node of modules.values()) if (node.definition.panels.some((panel) => panel.items?.length)) connectModule(node);

connectConsole();
