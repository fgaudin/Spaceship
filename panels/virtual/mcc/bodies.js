/* The bodies of a Mun trip: radius (m), top of the atmosphere (m, 0 without one), gravitational parameter (m³/s²). */
export const BODIES = {
  Kerbin: { radius: 600000, atmosphere: 70000, mu: 3.5316e12, color: '#2c4a6b' },
  Mun: { radius: 200000, atmosphere: 0, mu: 6.5138398e10, color: '#5d5f63' },
  Minmus: { radius: 60000, atmosphere: 0, mu: 1.7658e9, color: '#6f8f86' },
};
export const bodyOf = (name) => BODIES[name] || null;
