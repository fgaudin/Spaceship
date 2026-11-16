/* RETRO, retrofire officer: the way home. Periapsis against the entry corridor, the Δv to deorbit from apoapsis,
   entry loads, and which abort mode fits the moment against the one the crew has selected. */
import { box, figures, fixed, km } from '../ui.js';
import { orbit, flight, vessel, store } from '../bus.js';
import { bodyOf } from '../bodies.js';

// Kerbin entry corridor for a capsule (vacuum periapsis): shallower skips or overheats less but lands long.
const CORRIDOR_LOW_M = 25000, CORRIDOR_HIGH_M = 45000;
const DEORBIT_TARGET_PERIAPSIS_M = 35000;
const ABORT_MODES = ['PAD', 'ASCENT', 'ORBIT', 'DESCENT'];

let setEntry, setAbort;

export function mount(root) {
  setEntry = figures(box(root, 'ENTRY'), [['peri', 'Periapsis'], ['corridor', 'Corridor'], ['deorbit', 'Deorbit Δv at apoapsis'],
    ['g', 'Load'], ['q', 'Dynamic pressure'], ['heat', 'Hottest part']]);
  setAbort = figures(box(root, 'ABORT MODE'), [['advised', 'Fits now'], ['selected', 'Crew selected'], ['match', 'Check']]);
}

/* Δv (m/s) at apoapsis, retrograde, to bring the periapsis down to the target. */
function deorbitDeltaV(o, body) {
  if (!body || o.apo == null || o.peri == null) return null;
  const apoapsisRadius = body.radius + o.apo;
  const speed = (radius, semiMajorAxis) => Math.sqrt(body.mu * (2 / apoapsisRadius - 1 / semiMajorAxis));
  const now = speed(apoapsisRadius, body.radius + (o.apo + o.peri) / 2);
  const after = speed(apoapsisRadius, body.radius + (o.apo + DEORBIT_TARGET_PERIAPSIS_M) / 2);
  return now - after;
}

export function advisedAbortMode() {
  const craft = vessel(), height = flight().alt || 0, body = orbit().body;
  if (craft.situation === 'pre_launch') return 'PAD';
  if (body && body !== 'Kerbin') return 'DESCENT';
  if (craft.situation === 'orbiting' || height > 70000) return 'ORBIT';
  return 'ASCENT';
}

export function update() {
  const o = orbit(), body = bodyOf(o.body), f = flight();
  const atKerbin = o.body === 'Kerbin';
  const inCorridor = o.peri != null && o.peri >= CORRIDOR_LOW_M && o.peri <= CORRIDOR_HIGH_M;
  setEntry('peri', km(o.peri, 1));
  setEntry('corridor', atKerbin ? (inCorridor ? 'IN' : o.peri > CORRIDOR_HIGH_M ? 'above (no entry)' : 'BELOW (steep)')
    : `not at Kerbin (${o.body || '?'})`, atKerbin ? (inCorridor ? 'good' : o.peri < CORRIDOR_LOW_M ? 'bad' : '') : '');
  const deorbit = atKerbin && o.peri > CORRIDOR_HIGH_M ? deorbitDeltaV(o, body) : null;
  setEntry('deorbit', deorbit == null ? '—' : fixed(deorbit, 1, 'm/s retrograde'));
  setEntry('g', fixed(f.g, 2, 'g'));
  setEntry('q', fixed(f.q == null ? null : f.q / 1000, 1, 'kPa'));
  const heat = store['tlm/thermal']?.max;
  setEntry('heat', heat == null ? '—' : `${Math.round(heat * 100)} % of limit`, heat > 0.8 ? 'bad' : heat > 0.6 ? 'warn' : '');

  const advised = advisedAbortMode();
  const knob = store['panel/eng/in/abort_mode']?.v;
  const selected = knob == null ? null : ABORT_MODES[Number(knob) % ABORT_MODES.length];
  setAbort('advised', advised, 'strong');
  setAbort('selected', selected || '—');
  setAbort('match', selected === advised ? 'agrees' : selected ? `call the crew: ${advised}` : '—', selected === advised ? 'good' : 'warn');
}
