/* Two-body orbits for the MCC's drawings, as in flight-dynamics/orbits.py: elements in degrees as the plant sends
   them (tlm/orbit, tlm/target's orbit, mcc/bodies), positions in the body's inertial frame (x towards the reference
   direction, z along the rotation axis, metres).

   The ground track: the orbit run forward in time, each point turned into latitude and longitude on a body that
   rotates under it. The inertial longitude is pinned to the ground by the vessel's own longitude now, so the
   reference direction of the game's frame never needs to be known. */

const RAD = Math.PI / 180;
const TWO_PI = 2 * Math.PI;

const wrap = (angle) => ((angle % TWO_PI) + TWO_PI) % TWO_PI;
export const wrapLongitude = (degrees) => ((((degrees + 180) % 360) + 360) % 360) - 180;

export function meanAnomaly(nu, e) {
  if (e < 1) {
    const eccentric = 2 * Math.atan2(Math.sqrt(1 - e) * Math.sin(nu / 2), Math.sqrt(1 + e) * Math.cos(nu / 2));
    return wrap(eccentric - e * Math.sin(eccentric));
  }
  const hyperbolic = 2 * Math.atanh(Math.sqrt((e - 1) / (e + 1)) * Math.tan(nu / 2));
  return e * Math.sinh(hyperbolic) - hyperbolic;
}

export function trueAnomaly(mean, e) {
  if (e < 1) {
    let eccentric = e < 0.8 ? mean : Math.PI;
    for (let step = 0; step < 50; step++) {
      const change = (eccentric - e * Math.sin(eccentric) - mean) / (1 - e * Math.cos(eccentric));
      eccentric -= change;
      if (Math.abs(change) < 1e-10) break;
    }
    return 2 * Math.atan2(Math.sqrt(1 + e) * Math.sin(eccentric / 2), Math.sqrt(1 - e) * Math.cos(eccentric / 2));
  }
  let hyperbolic = Math.asinh(mean / e);
  for (let step = 0; step < 50; step++) {
    const change = (e * Math.sinh(hyperbolic) - hyperbolic - mean) / (e * Math.cosh(hyperbolic) - 1);
    hyperbolic -= change;
    if (Math.abs(change) < 1e-10) break;
  }
  return 2 * Math.atan(Math.sqrt((e + 1) / (e - 1)) * Math.tanh(hyperbolic / 2));
}

/* Elements in radians with μ: from tlm/orbit (true anomaly at ut) or from mcc/bodies (mean anomaly at epoch). */
export function elements(orbit, mu) {
  if (!orbit || orbit.a == null || orbit.e == null || !mu) return null;
  const el = { a: orbit.a, e: orbit.e, i: (orbit.i || 0) * RAD, lan: (orbit.lan || 0) * RAD, argp: (orbit.argp || 0) * RAD, mu };
  el.n = Math.sqrt(mu / Math.abs(el.a) ** 3);
  if (orbit.m0 != null) { el.m0 = orbit.m0; el.ut = orbit.epoch || 0; }
  else { el.m0 = meanAnomaly((orbit.nu || 0) * RAD, el.e); el.ut = orbit.ut; }
  return el;
}

export const closed = (el) => el.e < 1;
export const period = (el) => (closed(el) ? TWO_PI / el.n : Infinity);
export const radiusAt = (el, nu) => (el.a * (1 - el.e * el.e)) / (1 + el.e * Math.cos(nu));

export function trueAnomalyAt(el, ut) {
  let mean = el.m0 + el.n * (ut - el.ut);
  if (closed(el)) mean = wrap(mean);
  return trueAnomaly(mean, el.e);
}

/* [x, y, z] of the point at true anomaly nu. */
export function positionAt(el, nu) {
  const r = radiusAt(el, nu), u = el.argp + nu;
  const cosLan = Math.cos(el.lan), sinLan = Math.sin(el.lan), cosI = Math.cos(el.i);
  return [r * (cosLan * Math.cos(u) - sinLan * Math.sin(u) * cosI),
    r * (sinLan * Math.cos(u) + cosLan * Math.sin(u) * cosI),
    r * Math.sin(u) * Math.sin(el.i)];
}

export const positionAtTime = (el, ut) => positionAt(el, trueAnomalyAt(el, ut));

/* The anomaly range worth drawing: the whole ellipse, or a hyperbola out to `limit` metres from the centre. */
export function anomalyRange(el, limit) {
  if (closed(el)) return [-Math.PI, Math.PI];
  const asymptote = Math.acos(-1 / el.e);
  const p = el.a * (1 - el.e * el.e);
  const reach = limit ? Math.acos(Math.max(-1, Math.min(1, (p / limit - 1) / el.e))) : asymptote - 0.02;
  const edge = Math.min(asymptote - 0.01, reach);
  return [-edge, edge];
}

/* The time from `ut` until the orbit is next at true anomaly nu (closed orbits), or until it gets there (open). */
export function timeTo(el, ut, nu) {
  const now = el.m0 + el.n * (ut - el.ut);
  const then = meanAnomaly(nu, el.e);
  return closed(el) ? wrap(then - now) / el.n : (then - now) / el.n;
}

/* The ground offset at `ut`: geographic longitude minus inertial longitude (degrees), from the vessel's longitude. */
export function groundOffset(el, ut, longitudeNow) {
  const [x, y] = positionAtTime(el, ut);
  return longitudeNow - Math.atan2(y, x) / RAD;
}

/* Latitude and longitude under an inertial position at `ut`, the body turning once in `rotationPeriod` seconds. */
export function groundPoint(position, ut, offset, offsetUt, rotationPeriod) {
  const [x, y, z] = position;
  const r = Math.hypot(x, y, z);
  const turned = rotationPeriod ? (360 * (ut - offsetUt)) / rotationPeriod : 0;
  return { lat: Math.asin(z / r) / RAD, lon: wrapLongitude(Math.atan2(y, x) / RAD + offset - turned), r };
}

/* The orbit ahead on the ground: [{t, lat, lon}] from `ut` for `seconds`, and where it meets the surface (impact)
   or leaves the sphere of influence. */
export function groundTrack(el, body, ut, longitudeNow, seconds, steps = 720) {
  const offset = groundOffset(el, ut, longitudeNow);
  const points = [];
  let end = null;
  for (let step = 0; step <= steps; step++) {
    const t = ut + (seconds * step) / steps;
    const point = groundPoint(positionAtTime(el, t), t, offset, ut, body.rotation);
    if (point.r < body.radius) { end = { ...point, t, kind: 'impact' }; break; }
    if (body.soi && point.r > body.soi) { end = { ...point, t, kind: 'soi' }; break; }
    points.push({ t, lat: point.lat, lon: point.lon });
  }
  return { points, end, offset };
}

/* Where a body's sun is overhead at `ut`, from mcc/bodies' reading: the body turns under it once a rotation, and
   its planet's year moves it on the other way. */
export function subsolarAt(body, top, reading, ut) {
  if (!body?.subsolar || !reading) return null;
  const elapsed = ut - reading.ut;
  const turn = body.rotation ? (-360 * elapsed) / body.rotation : 0;
  const year = top?.orbit?.period ? (360 * elapsed) / top.orbit.period : 0;
  return { lat: body.subsolar.lat, lon: wrapLongitude(body.subsolar.lon + turn + year) };
}
