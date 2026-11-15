/* Mun ascent profile, for TM-11 liftoff timing: simulate flight/mun_ascent.py's steering law (point mass, 2D, vacuum,
   rotating Mun) and report the time and the inertial angle from liftoff to the circularisation point (apoapsis).

   in  { target (m), m0, F, isp, mu, R, omega (rad/s), hClear? }   out { tAsc, thAsc, dvAscent, dvCirc, apo }
   Law (mun_ascent.py): vertical to hClear, then elevation e = 90° (1 − v_h / (0.85 v_c)), floored at 5° (30° below
   1.5 km while v_r < 20 m/s); cutoff when the apoapsis reaches the target; coast to apoapsis; circularise there. */
'use strict';
const { Phys } = require('./profile');
const G0 = 9.80665;

function simulate({ target, m0, F, isp, mu, R, omega = 0, hClear = 60 }) {
  const vc = Math.sqrt(mu / (R + target));
  // inertial frame, site at (0, R), Mun turning counter-clockwise: the site moves towards +x
  let s = [0, R, omega * R, 0], m = m0, t = 0, dv = 0;
  const mdot = F / (isp * G0);
  const dt = 0.05;
  for (; t < 2000; t += dt) {
    const r = Math.hypot(s[0], s[1]), ur = [s[0] / r, s[1] / r], uh = [ur[1], -ur[0]].map((x) => -x);   // east = +x at the site
    const vr = s[2] * ur[0] + s[3] * ur[1];
    // horizontal speed relative to the turning surface
    const vh = s[2] * uh[0] + s[3] * uh[1] - omega * r;
    const h = r - R;
    let e = h < hClear ? 90 : 90 * (1 - vh / (0.85 * vc));
    e = Math.max(e, 5);
    if (h < 1500 && vr < 20) e = Math.max(e, 30);
    const er = (e * Math.PI) / 180;
    const a = F / m;
    const ax = a * (Math.sin(er) * ur[0] + Math.cos(er) * uh[0]) - (mu / (r * r)) * ur[0];
    const ay = a * (Math.sin(er) * ur[1] + Math.cos(er) * uh[1]) - (mu / (r * r)) * ur[1];
    s = [s[0] + s[2] * dt, s[1] + s[3] * dt, s[2] + ax * dt, s[3] + ay * dt];
    m -= mdot * dt; dv += a * dt;
    const v2 = s[2] ** 2 + s[3] ** 2, eps = v2 / 2 - mu / Math.hypot(s[0], s[1]);
    const hh = s[0] * s[3] - s[1] * s[2], ecc = Math.sqrt(Math.max(0, 1 + (2 * eps * hh * hh) / (mu * mu)));
    const ra = (-mu / (2 * eps)) * (1 + ecc);
    if (eps < 0 && ra - R >= target) break;
  }
  // coast to apoapsis
  for (let k = 0; k < 40000; k++) {
    const r = Math.hypot(s[0], s[1]);
    const vr = (s[0] * s[2] + s[1] * s[3]) / r;
    if (vr <= 0) break;
    const g = mu / (r * r * r);
    s = [s[0] + s[2] * dt, s[1] + s[3] * dt, s[2] - g * s[0] * dt, s[3] - g * s[1] * dt];
    t += dt;
  }
  const r = Math.hypot(s[0], s[1]);
  const vh = Math.hypot(s[2], s[3]);
  return { tAsc: t, thAsc: Math.atan2(s[0], s[1]), dvAscent: dv, dvCirc: Math.sqrt(mu / r) - vh, apo: r - R };
}

let input = '';
process.stdin.on('data', (d) => (input += d));
process.stdin.on('end', () => console.log(JSON.stringify(simulate(JSON.parse(input || '{}')))));
module.exports = { simulate };
void Phys;
