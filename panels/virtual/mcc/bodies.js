/* The bodies, as the game has them: mcc-data reads them from KSP (mcc/bodies: JNSQ's are not stock's). Until it has,
   or with the mock plant, stock KSP's figures for a Mun trip. A body: radius (m), atmosphere (top, m, 0 without),
   mu (m³/s²), rotation (sidereal day, s), soi (m), parent (name), orbit (elements in degrees, m0 and epoch),
   subsolar ({lat, lon} where its sun was overhead at the reading), color (for drawings). */
import { store } from './bus.js';

const STOCK = {
  Kerbin: { radius: 600000, atmosphere: 70000, mu: 3.5316e12, rotation: 21549.425, soi: 84159286, color: '#2c4a6b' },
  Mun: { radius: 200000, atmosphere: 0, mu: 6.5138398e10, rotation: 138984.38, soi: 2429559, parent: 'Kerbin',
    orbit: { a: 12000000, e: 0, i: 0, lan: 0, argp: 0, m0: 1.7, epoch: 0, period: 138984.38 }, color: '#5d5f63' },
  Minmus: { radius: 60000, atmosphere: 0, mu: 1.7658e9, rotation: 40400, soi: 2247428, parent: 'Kerbin',
    orbit: { a: 47000000, e: 0, i: 6, lan: 78, argp: 38, m0: 0.9, epoch: 0, period: 1077310.5 }, color: '#6f8f86' },
};
const COLORS = { Kerbin: '#2c4a6b', Mun: '#5d5f63', Minmus: '#6f8f86', Duna: '#8a4a32', Ike: '#5a5652', Eve: '#5b3a78',
  Gilly: '#6a5242', Laythe: '#2f5a7a', Jool: '#4d7a2c', Dres: '#6a625a', Moho: '#6a4c3a', Eeloo: '#9a9ca0', Sun: '#d9a400' };

export const reading = () => store['mcc/bodies'] || null;

export function bodyOf(name) {
  const live = reading()?.bodies?.[name];
  if (live) {
    return { name, radius: live.radius, atmosphere: live.atmosphere || 0, mu: live.mu, rotation: live.rotation_period,
      soi: live.soi, parent: live.parent, orbit: live.orbit, subsolar: live.subsolar, color: COLORS[name] || '#55606b', live: true };
  }
  return STOCK[name] ? { name, ...STOCK[name] } : null;
}

/* The bodies orbiting `name` (its moons). */
export function moonsOf(name) {
  const bodies = reading()?.bodies;
  if (bodies) return Object.keys(bodies).filter((other) => bodies[other].parent === name).map(bodyOf);
  return Object.keys(STOCK).filter((other) => STOCK[other].parent === name).map(bodyOf);
}

/* The planet a body belongs to (itself for a planet): its year moves the sun across the sky. */
export function planetOf(name) {
  let body = bodyOf(name);
  while (body?.parent && bodyOf(body.parent)?.parent) body = bodyOf(body.parent);
  return body;
}

/* kept for the consoles that list them */
export const BODIES = STOCK;
