/* Mission Control: one page, one tab per console. Each controller opens it on their own laptop and picks the
   consoles they hold: one, or several when there are fewer people than roles (FIDO + RETRO). The tabs are toggles;
   the consoles held are shown side by side, each a standard screen of fixed layout, zoomed together to fit. The choice is remembered on that laptop and kept in the address
   (mcc.html#fido+retro).

   The poll banner speaks for every console held: one GO / NO-GO answers for all of them (FLIGHT's
   board still shows each). FLIGHT runs the poll and does not answer it. */
import { CONSOLES } from './roster.js';
import { store, publish, met } from './bus.js';
import { create, formatMet } from './ui.js';

const UPDATE_EVERY_MS = 500;
const CONSOLE_PX = [1200, 800];       // one console's standard screen (mcc.css)
const CONSOLE_GAP_PX = 16;
const MAX_ZOOM = 1.25;
const REMEMBERED_ROLES_KEY = 'mcc-roles';
const ROLE_SEPARATOR = '+';
const roots = {};
const knownRole = (id) => CONSOLES.some((console) => console.id === id);

function rememberedRoles() {
  try { return localStorage.getItem(REMEMBERED_ROLES_KEY); } catch { return null; }
}

function remember(roles) {
  try { localStorage.setItem(REMEMBERED_ROLES_KEY, roles.join(ROLE_SEPARATOR)); } catch { /* the address keeps it */ }
}

/* The consoles this laptop holds, in roster order. */
function heldRoles() {
  const wanted = (location.hash.slice(1) || rememberedRoles() || 'flight').split(ROLE_SEPARATOR).filter(knownRole);
  const roles = CONSOLES.map((console) => console.id).filter((id) => wanted.includes(id));
  return roles.length ? roles : ['flight'];
}

const answeringRoles = () => heldRoles().filter((role) => role !== 'flight');

function setHeldRoles(roles) {
  location.hash = roles.join(ROLE_SEPARATOR);          // hashchange redraws
}

function buildTabs() {
  const tabs = document.getElementById('tabs');
  for (const console of CONSOLES) {
    const tab = create('button', 'navlink mcc-tab', console.name);
    tab.type = 'button';
    tab.title = `${console.title} (click to hold or release this console)`;
    tab.dataset.role = console.id;
    tab.addEventListener('click', () => {
      const held = heldRoles();
      const next = held.includes(console.id) ? held.filter((role) => role !== console.id) : [...held, console.id];
      setHeldRoles(next.length ? next : held);      // at least one console
    });
    tabs.append(tab);

    const root = create('section', 'mcc-console-block');
    root.hidden = true;
    const heading = create('div', 'mcc-title');
    heading.append(create('h1', '', console.name), create('p', '', console.title));
    const body = create('div', 'mcc-console');
    root.append(heading, body);
    document.getElementById('consoles').append(root);
    console.module.mount(body);
    roots[console.id] = root;
  }
}

function showRoles() {
  const roles = heldRoles();
  remember(roles);
  for (const [id, root] of Object.entries(roots)) root.hidden = !roles.includes(id);
  for (const tab of document.querySelectorAll('#tabs .mcc-tab')) tab.setAttribute('aria-pressed', String(roles.includes(tab.dataset.role)));
  const names = roles.map((role) => CONSOLES.find((console) => console.id === role).name);
  document.title = `MCC · ${names.join(' + ')}`;
  fitConsoles();
}

/* The consoles held, side by side: the number of columns that lets them be drawn biggest in the window, all at the
   same zoom. A console never reflows; only the zoom changes. */
function fitConsoles() {
  const holder = document.getElementById('consoles');
  const count = heldRoles().length;
  holder.style.zoom = 1;
  const top = holder.getBoundingClientRect().top + window.scrollY;
  const available = [window.innerWidth - 2 * CONSOLE_GAP_PX, window.innerHeight - top - 2 * CONSOLE_GAP_PX];
  let best = { zoom: 0, columns: 1 };
  for (let columns = 1; columns <= count; columns++) {
    const rows = Math.ceil(count / columns);
    const zoom = Math.min(available[0] / (columns * CONSOLE_PX[0] + (columns - 1) * CONSOLE_GAP_PX),
      available[1] / (rows * CONSOLE_PX[1] + (rows - 1) * CONSOLE_GAP_PX));
    if (zoom > best.zoom) best = { zoom, columns };
  }
  holder.style.gridTemplateColumns = `repeat(${best.columns}, ${CONSOLE_PX[0]}px)`;
  holder.style.zoom = Math.min(MAX_ZOOM, best.zoom);
}

/* The answer of the consoles held: GO or NO-GO when they all agree, null otherwise (not yet, or mixed). */
function heldAnswer() {
  const answers = answeringRoles().map((role) => (store[`mcc/poll/${role}`] || {}).go);
  if (answers.length && answers.every((go) => go === true)) return true;
  if (answers.length && answers.every((go) => go === false)) return false;
  return null;
}

/* The poll banner: across the top while a poll is open, for a laptop that holds a console which answers it. Large and
   pulsing until answered (polls also come by voice, and must not be missed); then a strip with the answer, still
   changeable. */
function updateBanner() {
  const poll = store['mcc/poll'] || {}, answer = heldAnswer();
  const banner = document.getElementById('poll-banner');
  const wasHidden = banner.hidden;
  banner.hidden = answeringRoles().length === 0 || !poll.open;
  if (banner.hidden !== wasHidden) fitConsoles();      // the banner takes room above the consoles
  if (banner.hidden) return;
  banner.classList.toggle('waiting', answer === null);
  banner.classList.toggle('answered-go', answer === true);
  banner.classList.toggle('answered-nogo', answer === false);
  const names = answeringRoles().map((role) => CONSOLES.find((console) => console.id === role).name).join(' + ');
  document.getElementById('poll-banner-label').textContent = `FLIGHT POLL · ${names}`;
  document.getElementById('poll-banner-question').textContent = poll.question;
  document.getElementById('banner-go').classList.toggle('chosen', answer === true);
  document.getElementById('banner-nogo').classList.toggle('chosen', answer === false);
}

function updateClock() {
  document.getElementById('clock').textContent = `MET ${formatMet(met())}`;
}

function wireBanner() {
  const answer = (go) => {
    for (const role of answeringRoles()) publish(`mcc/poll/${role}`, { go, met: met() }, true);
  };
  for (const [id, go] of [['banner-go', true], ['banner-nogo', false]]) {
    document.getElementById(id).addEventListener('click', () => answer(go));
  }
}

buildTabs();
wireBanner();
showRoles();
window.addEventListener('hashchange', showRoles);
window.addEventListener('resize', fitConsoles);
setInterval(() => {
  for (const role of heldRoles()) CONSOLES.find((console) => console.id === role).module.update();
  updateClock();
  updateBanner();
}, UPDATE_EVERY_MS);
