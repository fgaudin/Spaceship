/* The top bar of every page: brand, bus connection light, and the navigation, built from one list of pages.

   A page's HTML only gives what is its own:
     <header class="topbar" data-subtitle="FDAI · glass panel">
       <div class="links">…the page's own status items…</div>
     </header>
     <script type="module" src="shell.js"></script>
   The shell puts the brand, the light (#conn-dot, #conn-text, driven by bus.js) and the navigation in front.
   Adding a page: one line in PAGES. */

export const PAGES = [
  // [link, label]: I/O panels (drawn from protocol/panels/<id>.json by panel.js), then glass and station pages
  ['index.html', 'ENG'], ['index.html?panel=sys', 'SYS'], ['index.html?panel=cmp', 'CMP'],
  ['index.html?panel=rdv', 'RDV'], ['index.html?panel=com', 'COM'], ['index.html?panel=solo', 'SOLO'],
  ['index.html?panel=lab', 'LAB'],
  ['fdai.html', 'FDAI'], ['mfd.html', 'MFD'], ['cam.html', 'CAM'], ['simsup.html', 'SIMSUP'], ['mcc.html', 'MCC'],
];

/* The page the browser is on, written as in PAGES ("index.html?panel=sys", "fdai.html"). */
function currentLink() {
  const file = location.pathname.split('/').pop() || 'index.html';
  const panel = new URLSearchParams(location.search).get('panel');
  return file === 'index.html' && panel && panel !== 'eng' ? `index.html?panel=${panel}` : file;
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

buildTopBar();
