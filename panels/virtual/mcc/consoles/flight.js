/* FLIGHT: the flight director. Mission phase and health at a glance, the crew's alarms, the go/no-go poll, the loop. */
import { create, box, figures, formatMet, km, fixed } from '../ui.js';
import { store, publish, onMessage, met, vessel, flight, orbit, linkUp, telemetryLive } from '../bus.js';
import { CONSOLES } from '../roster.js';

const LOOP_LINES = 200;
const loop = [];

export function phase() {
  const craft = vessel(), height = flight().alt, apoapsis = orbit().apo;
  switch (craft.situation) {
    case 'pre_launch': return 'PRELAUNCH';
    case 'flying': return (craft.thrust || 0) > 0 ? 'POWERED FLIGHT' : 'ATMOSPHERIC FLIGHT';
    case 'sub_orbital': return (flight().vs || 0) < 0 && height < 50000 ? 'DESCENT' : (craft.thrust || 0) > 0 ? 'POWERED FLIGHT' : 'SUBORBITAL';
    case 'orbiting': return (craft.thrust || 0) > 0 ? 'BURN' : 'ORBIT';
    case 'escaping': return apoapsis == null ? 'ESCAPE' : 'TRANSFER';
    case 'landed': return 'LANDED';
    case 'splashed': return 'SPLASHDOWN';
    default: return craft.situation ? craft.situation.toUpperCase() : '—';
  }
}

let setFigure, pollBoard, pollStatus, alarmsBox, loopList;

export function mount(root) {
  const status = box(root, 'STATUS', { at: [0, 0] });
  setFigure = figures(status, [['phase', 'Phase'], ['vessel', 'Vessel'], ['met', 'MET'], ['body', 'Body'],
    ['alt', 'Altitude'], ['speed', 'Speed'], ['link', 'Link'], ['tlm', 'Telemetry'], ['crew', 'Cockpit']]);

  alarmsBox = box(root, "CREW'S ALARMS", { at: [1, 0] });
  alarmsBox.append(create('div', 'mcc-alarms'));

  const poll = box(root, 'GO / NO-GO POLL', { at: [0, 1], size: [2, 1] });
  const form = create('form', 'mcc-inline');
  const question = create('input');
  question.placeholder = 'e.g. GO for TLI?';
  question.setAttribute('aria-label', 'Poll question');
  const open = create('button', 'mcc-btn', 'OPEN POLL');
  const close = create('button', 'mcc-btn', 'CLOSE');
  close.type = 'button';
  form.append(question, open, close);
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    // Clear the previous answers, then open: each console's answer is its own retained topic.
    for (const console of CONSOLES) if (console.id !== 'flight') publish(`mcc/poll/${console.id}`, {}, true);
    publish('mcc/poll', { open: true, question: question.value.trim() || 'GO / NO-GO?', met: met() }, true);
  });
  close.addEventListener('click', () => publish('mcc/poll', { ...(store['mcc/poll'] || {}), open: false }, true));
  pollStatus = create('p', 'mcc-note');
  pollBoard = create('div', 'mcc-poll');
  poll.append(form, pollStatus, pollBoard);

  const loopBox = box(root, 'LOOP', { at: [2, 0], size: [1, 2] });
  loopList = create('ol', 'mcc-feed');
  loopBox.append(loopList);
  onMessage((topic, payload, retained) => {
    if (!topic.startsWith('mcc/loop/') || retained) return;
    const roles = payload.roles || [topic.split('/')[2]];      // a laptop holding several consoles signs with all
    loop.push({ ...payload, role: roles.join('/') });
    loop.splice(0, loop.length - LOOP_LINES);
    drawLoop();
  });
}

function drawLoop() {
  loopList.replaceChildren(...loop.slice().reverse().map((line) => {
    const item = create('li');
    item.append(create('span', 'met', formatMet(line.met)), create('span', 'role', line.role.toUpperCase()), create('span', '', line.text));
    return item;
  }));
}

export function update() {
  const craft = vessel(), live = telemetryLive();
  setFigure('phase', phase(), 'strong');
  setFigure('vessel', craft.name || '—');
  setFigure('met', formatMet(met()));
  setFigure('body', orbit().body || '—');
  setFigure('alt', km(flight().alt, 2));
  setFigure('speed', fixed(flight().speed, 1, 'm/s'));
  setFigure('link', linkUp() ? 'AOS' : 'LOS', linkUp() ? 'good' : 'bad');
  setFigure('tlm', live ? 'live' : 'STALE', live ? 'good' : 'bad');
  setFigure('crew', store['cockpit/status']?.online ? 'online' : 'OFFLINE', store['cockpit/status']?.online ? 'good' : 'bad');

  const alarms = store['cw/state'] || {};
  const unacked = new Set(alarms.unacked || []);
  const chips = (alarms.active || []).map((legend) => create('span', unacked.has(legend) ? 'unacked' : '', legend));
  alarmsBox.querySelector('.mcc-alarms').replaceChildren(...(chips.length ? chips : [create('span', 'mcc-note', 'none')]));

  const poll = store['mcc/poll'] || {};
  pollStatus.textContent = poll.question ? `${poll.open ? 'OPEN' : 'closed'}: ${poll.question} (MET ${formatMet(poll.met)})` : 'no poll';
  pollBoard.replaceChildren(...CONSOLES.filter((console) => console.id !== 'flight').map((console) => {
    const answer = store[`mcc/poll/${console.id}`] || {};
    const tone = answer.go === true ? 'go' : answer.go === false ? 'nogo' : '';
    const cell = create('div', `mcc-poll-cell ${tone}`);
    cell.append(create('strong', '', console.name), create('span', '', answer.go === true ? 'GO' : answer.go === false ? 'NO-GO' : '—'));
    return cell;
  }));
}
