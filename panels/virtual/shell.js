/* The top bar of every page: brand, bus connection light, and the navigation, built from one list of pages.

   A page's HTML only gives what is its own:
     <header class="topbar" data-subtitle="FDAI · glass panel">
       <div class="links">…the page's own status items…</div>
     </header>
     <script type="module" src="shell.js"></script>
   The shell puts the brand, the light (#conn-dot, #conn-text, driven by bus.js) and the navigation in front.
   Adding a page: one line in PAGES.

   Stations: the instructor opens CONSOLE, MCC and WALL to the students from SimSup (stations/open, retained). A
   closed station's tab stays, greyed out and not clickable, and its page shows a "station closed" screen that also takes the keyboard (the
   console's keys move the hand controllers). Until SimSup has said anything, every station is open. SimSup's own
   page (password-protected by the web server) shows every tab. The glass pages (FDAI, CAM) have no tab: they live
   in the console's modules, and a page embedded there (?embed=1) is never closed by itself. */
import { connectBus, parse } from './bus.js';

export const PAGES = [
  // [link, label, station]: the console of I/O modules (protocol/panels/console.json, drawn by panel.js), then the
  // station pages; station: its id on stations/open, or none for a page always there
  ['probe.html', 'PROBE'], ['wall.html', 'WALL', 'wall'], ['mcc.html', 'MCC', 'mcc'], ['console.html', 'CONSOLE', 'console'],
  ['simsup.html', 'SIMSUP'],
];
const INSTRUCTOR_PAGE = 'simsup.html';
export const STATIONS = PAGES.filter(([, , station]) => station).map(([, label, station]) => [station, label]);

/* The page the browser is on, written as in PAGES ("console.html", "fdai.html"). */
function currentLink() {
  return location.pathname.split('/').pop() || 'probe.html';     // the site's root is the probe room
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function buildTopBar() {
  const header = document.querySelector('header.topbar');
  if (!header || header.dataset.built) return;
  header.dataset.built = 'yes';
  const brand = element('div', 'brand', 'CAPSULE ');
  brand.append(element('span', '', header.dataset.subtitle || ''));
  const connection = element('div', 'conn');
  const light = element('span', 'dot');
  light.id = 'conn-dot';
  const label = element('span', '', 'connecting…');
  label.id = 'conn-text';
  connection.append(light, label);
  const navigation = element('nav', 'nav');
  navigation.setAttribute('aria-label', 'Pages');
  const here = currentLink();
  for (const [link, name, station] of PAGES) {
    const anchor = element('a', 'navlink', name);
    anchor.href = link;
    if (station) anchor.dataset.station = station;
    if (link === here) anchor.setAttribute('aria-current', 'page');
    if (link === INSTRUCTOR_PAGE) {
      anchor.classList.add('navlink-right');      // the instructor's station: apart, at the right end of the bar
      header.append(anchor);
    } else navigation.append(anchor);
  }
  header.prepend(brand, connection, navigation);
}

/* A glass page shown inside the console (?embed=1, in its module's screen): no top bar, no notes, the content fitted
   to the screen (see .embedded in panel.css); Esc and the wheel act on the console, as they do everywhere on it. */
export const embedded = new URLSearchParams(location.search).has('embed');
// the hand controllers' and the throttle's keys (hand_controllers.js), passed on to the console
const CONSOLE_KEYS = /^(Key[WSADQEIJKLHN]|ShiftLeft|ControlLeft)$/;
if (embedded) {
  document.documentElement.classList.add('embedded');
  const typing = (event) => event.target.tagName === 'INPUT' || event.target.tagName === 'TEXTAREA';
  window.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') window.parent.postMessage({ type: 'console-escape' }, location.origin);
    if (event.code === 'AltLeft') window.parent.postMessage({ type: 'console-modules', on: true }, location.origin);
    if (CONSOLE_KEYS.test(event.code) && !typing(event)) {
      event.preventDefault();
      if (!event.repeat) window.parent.postMessage({ type: 'console-key', code: event.code, down: true }, location.origin);
    }
  });
  window.addEventListener('keyup', (event) => {
    if (event.code === 'AltLeft') window.parent.postMessage({ type: 'console-modules', on: false }, location.origin);
    if (CONSOLE_KEYS.test(event.code)) window.parent.postMessage({ type: 'console-key', code: event.code, down: false }, location.origin);
  });
  window.addEventListener('blur', () => window.parent.postMessage({ type: 'console-key-release' }, location.origin));
  // the wheel zooms the console, as it does everywhere else on it
  window.addEventListener('wheel', (event) => {
    event.preventDefault();
    const pixels = event.deltaY * (event.deltaMode === 1 ? 33 : 1);
    window.parent.postMessage({ type: 'console-wheel', pixels, x: event.clientX, y: event.clientY }, location.origin);
  }, { passive: false });
}

/* ---------- stations the instructor opens ---------- */
function closedScreen() {
  let screen = document.getElementById('station-closed');
  if (!screen) {
    screen = element('div', 'station-closed');
    screen.id = 'station-closed';
    screen.append(element('b', '', 'STATION CLOSED'), element('span', '', 'The instructor has not opened this station yet.'));
    document.body.append(screen);
  }
  return screen;
}

function applyStations(open) {
  const isOpen = (station) => open === null || open.includes(station);
  if (currentLink() !== 'simsup.html') {
    for (const anchor of document.querySelectorAll('.navlink[data-station]')) {
      const closed = !isOpen(anchor.dataset.station);
      anchor.classList.toggle('closed', closed);
      if (closed) { anchor.setAttribute('aria-disabled', 'true'); anchor.title = 'Closed by the instructor'; anchor.tabIndex = -1; }
      else { anchor.removeAttribute('aria-disabled'); anchor.removeAttribute('title'); anchor.removeAttribute('tabindex'); }
    }
  }
  const here = PAGES.find(([link]) => link === currentLink());
  const closed = Boolean(here && here[2] && !embedded && !isOpen(here[2]));
  document.documentElement.classList.toggle('station-is-closed', closed);
  closedScreen().hidden = !closed;
}

// a closed station takes no key: capture phase, before the page's own handlers
window.addEventListener('keydown', (event) => {
  if (document.documentElement.classList.contains('station-is-closed')) { event.stopImmediatePropagation(); event.preventDefault(); }
}, true);
window.addEventListener('keyup', (event) => {
  if (document.documentElement.classList.contains('station-is-closed')) event.stopImmediatePropagation();
}, true);

buildTopBar();
if (!embedded && typeof mqtt !== 'undefined') {
  connectBus({
    name: 'shell',
    onConnect: (client) => client.subscribe('stations/open', { qos: 1 }),
    onMessage: (topic, text) => {
      const payload = parse(text);
      if (payload && Array.isArray(payload.open)) applyStations(payload.open);
    },
  });
}
