/* The top bar of every page: brand, bus connection light, and the navigation, built from one list of pages.

   A page's HTML only gives what is its own:
     <header class="topbar" data-subtitle="FDAI · glass panel">
       <div class="links">…the page's own status items…</div>
     </header>
     <script type="module" src="shell.js"></script>
   The shell puts the brand, the light (#conn-dot, #conn-text, driven by bus.js) and the navigation in front.
   Adding a page: one line in PAGES. */

export const PAGES = [
  // [link, label]: the console of I/O modules (protocol/panels/console.json, drawn by panel.js), then glass and
  // station pages
  ['index.html', 'CONSOLE'],
  ['fdai.html', 'FDAI'], ['cam.html', 'CAM'], ['simsup.html', 'SIMSUP'], ['mcc.html', 'MCC'], ['wall.html', 'WALL'],
];

/* The page the browser is on, written as in PAGES ("index.html", "fdai.html"). */
function currentLink() {
  return location.pathname.split('/').pop() || 'index.html';
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
  for (const [link, name] of PAGES) {
    const anchor = element('a', 'navlink', name);
    anchor.href = link;
    if (link === here) anchor.setAttribute('aria-current', 'page');
    navigation.append(anchor);
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

buildTopBar();
