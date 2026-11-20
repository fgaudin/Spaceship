/* RETRO, retrofire officer: the way home. Periapsis against the entry corridor (scaled to the body's atmosphere),
   the Δv to deorbit from apoapsis, entry loads. */
import { box, figures, fixed, km } from '../ui.js';
import { orbit, flight, store, vessel } from '../bus.js';
import { bodyOf } from '../bodies.js';
import { chartBox } from '../consolechart.js';
import { AMBER, CYAN, GREEN, RED } from '../charts.js';

// The entry corridor for a capsule (vacuum periapsis), as fractions of the atmosphere's height: stock Kerbin's 25 to
// 45 km of 70, 29 to 51 km of JNSQ's 80. Shallower skips or overheats less but lands long.
const CORRIDOR_LOW = 0.36, CORRIDOR_HIGH = 0.64, DEORBIT_TARGET = 0.5;

let setEntry;

export function mount(root) {
  setEntry = figures(box(root, 'ENTRY', { at: [0, 0] }), [['peri', 'Periapsis'], ['corridor', 'Corridor'], ['deorbit', 'Deorbit Δv at apoapsis'],
    ['toAtmosphere', 'Time to atmosphere'], ['g', 'Load'], ['q', 'Dynamic pressure'], ['heat', 'Hottest part'], ['chute', 'Opening the chutes']]);
  chartBox(root, 'PERIAPSIS · ALTITUDE · km, last 15 min', { at: [1, 0], size: [2, 1] }, {
    series: [
      { label: 'PERIAPSIS', color: GREEN, unit: 'km', value: (c, i) => c.peri[i] / 1000 },
      { label: 'ALTITUDE', color: AMBER, unit: 'km', value: (c, i) => c.alt[i] / 1000 },
    ],
    scales: { y: { range: (u, min, max) => [Math.max(min, -100), Math.max(max, 1)] } },
  });
  chartBox(root, 'ENTRY LOADS · kPa · g · % of the heat limit', { at: [0, 1], size: [3, 1] }, {
    series: [
      { label: 'Q', color: AMBER, unit: 'kPa', value: (c, i) => (c.q[i] == null ? null : c.q[i] / 1000) },
      { label: 'G', color: CYAN, scale: 'g', unit: 'g', decimals: 2, value: (c, i) => c.g[i] },
      { label: 'HEAT', color: RED, scale: 'pct', unit: '%', decimals: 0, value: (c, i) => (c.heat[i] == null ? null : c.heat[i] * 100) },
    ],
    scales: { y: { range: (u, min, max) => [0, Math.max(max, 1)] }, g: { range: (u, min, max) => [0, Math.max(max, 1)] },
      pct: { range: [0, 100], hidden: true } },
  });
}

/* Δv (m/s) at apoapsis, retrograde, to bring the periapsis down to the target. */
function deorbitDeltaV(o, body, targetPeriapsis) {
  if (!body || o.apo == null || o.peri == null) return null;
  const apoapsisRadius = body.radius + o.apo;
  const speed = (radius, semiMajorAxis) => Math.sqrt(body.mu * (2 / apoapsisRadius - 1 / semiMajorAxis));
  const now = speed(apoapsisRadius, body.radius + (o.apo + o.peri) / 2);
  const after = speed(apoapsisRadius, body.radius + (o.apo + targetPeriapsis) / 2);
  return now - after;
}

export function update() {
  const o = orbit(), body = bodyOf(o.body), f = flight();
  // the atmosphere as the game has it: tlm/orbit's, else mcc/bodies' (or stock's)
  const atmosphere = o.atm ?? body?.atmosphere ?? 0;
  const low = CORRIDOR_LOW * atmosphere, high = CORRIDOR_HIGH * atmosphere;
  const inCorridor = o.peri != null && o.peri >= low && o.peri <= high;
  setEntry('peri', km(o.peri, 1));
  const range = `${Math.round(low / 1000)}–${Math.round(high / 1000)} km`;
  setEntry('corridor', atmosphere ? (inCorridor ? `IN (${range})` : o.peri > high ? `above ${range} (no entry)` : `BELOW ${range} (steep)`)
    : `no atmosphere (${o.body || '?'})`, atmosphere ? (inCorridor ? 'good' : o.peri < low ? 'bad' : '') : '');
  const deorbit = atmosphere && o.peri > high ? deorbitDeltaV(o, body, DEORBIT_TARGET * atmosphere) : null;
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
