/* RETRO, retrofire officer: the way home. Periapsis against the entry corridor, the Δv to deorbit from apoapsis,
   entry loads. */
import { box, figures, fixed, km } from '../ui.js';
import { orbit, flight, store, vessel } from '../bus.js';
import { bodyOf } from '../bodies.js';

// Kerbin entry corridor for a capsule (vacuum periapsis): shallower skips or overheats less but lands long.
const CORRIDOR_LOW_M = 25000, CORRIDOR_HIGH_M = 45000;
const DEORBIT_TARGET_PERIAPSIS_M = 35000;

let setEntry;

export function mount(root) {
  setEntry = figures(box(root, 'ENTRY', { at: [0, 0] }), [['peri', 'Periapsis'], ['corridor', 'Corridor'], ['deorbit', 'Deorbit Δv at apoapsis'],
    ['toAtmosphere', 'Time to atmosphere'], ['g', 'Load'], ['q', 'Dynamic pressure'], ['heat', 'Hottest part'], ['chute', 'Opening the chutes']]);
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

export function update() {
  const o = orbit(), body = bodyOf(o.body), f = flight();
  const atKerbin = o.body === 'Kerbin';
  const inCorridor = o.peri != null && o.peri >= CORRIDOR_LOW_M && o.peri <= CORRIDOR_HIGH_M;
  setEntry('peri', km(o.peri, 1));
  setEntry('corridor', atKerbin ? (inCorridor ? 'IN' : o.peri > CORRIDOR_HIGH_M ? 'above (no entry)' : 'BELOW (steep)')
    : `not at Kerbin (${o.body || '?'})`, atKerbin ? (inCorridor ? 'good' : o.peri < CORRIDOR_LOW_M ? 'bad' : '') : '');
  const deorbit = atKerbin && o.peri > CORRIDOR_HIGH_M ? deorbitDeltaV(o, body) : null;
  setEntry('deorbit', deorbit == null ? '—' : fixed(deorbit, 1, 'm/s retrograde'));
  const descending = f.alt > o.atm && f.vs < -0.1 && !(o.peri >= o.atm);
  setEntry('toAtmosphere', o.atm != null && descending ? fixed((f.alt - o.atm) / -f.vs, 0, 's') : '—');
  setEntry('g', fixed(f.g, 2, 'g'));
  setEntry('q', fixed(f.q == null ? null : f.q / 1000, 1, 'kPa'));
  const heat = store['tlm/thermal']?.max;
  setEntry('heat', heat == null ? '—' : `${Math.round(heat * 100)} % of limit`, heat > 0.8 ? 'bad' : heat > 0.6 ? 'warn' : '');
  const chute = vessel().chute_safe;
  setEntry('chute', chute || '—', { safe: 'good', risky: 'warn', unsafe: 'bad' }[chute] || '');
}
