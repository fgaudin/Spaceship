/* Landing guidance for a high-TWR lander, simulated before flight (same law as flight/descent.py).

   Structure from TM-15/16: DOI half an orbit before PDI, braking at a fixed throttle until the horizontal speed is gone,
   arriving at high gate, then a vertical approach (sink rate 1 + h/50 m/s, as the course's P66-style approach).
   Changed from descent.phys.js (see gaps G5): the braking vertical channel commands a sink rate that brings the lander to
   high gate when the horizontal speed reaches zero, v_r,cmd = −(h − h_HG) / t_go with t_go = v_h / a_h, so it scales with
   the braking time; the approach throttle may go down to 0 (KSP engines), not the LM's 10 %.

   in  { hp (PDI altitude above the reference sphere), vp, m0, F, isp, throttle, hHG }  (Mun from the profile)
   out { outcome, t, brakeTime, dvBrake, dvApproach, dvTotal, prop, mTd, vTd, range } */
'use strict';
const { C } = require('./profile');

function simulate(q) {
  const mu = C.muM, R = C.RM, g0 = 9.80665, c = q.isp * g0;
  let r = R + q.hp, vr = 0, vt = q.vp, th = 0, m = q.m0, t = 0;
  const hHG = q.hHG ?? 1500, thr = q.throttle ?? 0.5, dt = 0.05;
  let phase = 'brake', dvB = 0, dvA = 0, tBrake = null, maxTilt = 0;
  const trace = [];
  while (t < 3000) {
    const h = r - R, g = mu / (r * r);
    let aT, ar, at;
    if (phase === 'brake') {
      aT = q.F * thr / m;
      const ahGuess = 0.9 * aT;
      const tgo = Math.max(3, vt / ahGuess);
      const vrCmd = -(h - hHG) / tgo;
      let av = g - vt * vt / r + 0.5 * (vrCmd - vr);
      av = Math.max(-0.9 * aT, Math.min(0.9 * aT, av));
      const ah = Math.sqrt(aT * aT - av * av);
      ar = av; at = -ah;
      dvB += aT * dt;
      if (vt <= 1) { phase = 'approach'; tBrake = t; }
    } else {
      const cmd = -(1 + h / (q.sinkK ?? 50));
      const aNeed = g + 0.8 * (cmd - vr);
      // null the horizontal residual with a small tilt (≤ 15°)
      const ahNeed = Math.max(-Math.tan(15 * Math.PI / 180) * aNeed, Math.min(Math.tan(15 * Math.PI / 180) * aNeed, -0.5 * vt));
      aT = Math.max(0, Math.min(q.F / m, Math.hypot(aNeed, ahNeed)));
      ar = aNeed > 0 ? aT * aNeed / Math.hypot(aNeed, ahNeed) : 0; at = aNeed > 0 ? aT * ahNeed / Math.hypot(aNeed, ahNeed) : 0;
      dvA += aT * dt;
    }
    vr += (vt * vt / r - g + ar) * dt;
    vt += (-vr * vt / r + at) * dt;
    r += vr * dt; th += vt / r * dt; t += dt;
    m -= m * Math.hypot(ar, at) / c * dt;
    if (trace.length === 0 || t - trace[trace.length - 1].t >= 5) trace.push({ t: +t.toFixed(1), h: Math.round(r - R), vr: +vr.toFixed(1), vt: +vt.toFixed(1), phase });
    if (r - R <= 0) break;
  }
  const out = { outcome: Math.abs(vr) < 3 && Math.abs(vt) < 1.5 ? 'landed' : 'crash', t, brakeTime: tBrake, dvBrake: dvB, dvApproach: dvA,
    dvTotal: dvB + dvA, mTd: m, prop: q.m0 - m, vTd: [vr, vt], range: th * R, trace };
  return out;
}

module.exports = { simulate };

if (require.main === module) {
  const D = require('./profile').moonshot('descent');
  const q0 = { hp: 9000, m0: 14000, F: 250000, isp: 350, hHG: 1500 };
  const rp = C.RM + q0.hp, ra = C.RM + 22000;
  q0.vp = Math.sqrt(C.muM * (2 / rp - 2 / (ra + rp)));
  for (const throttle of [0.2, 0.3, 0.4, 0.5, 0.7, 1.0]) {
    const r = simulate({ ...q0, throttle });
    console.log(`thr ${throttle}: ${r.outcome} brake ${r.brakeTime?.toFixed(0)} s, Δv brake ${r.dvBrake.toFixed(0)} + approach ${r.dvApproach.toFixed(0)} = ${r.dvTotal.toFixed(0)} m/s, prop ${r.prop.toFixed(0)} kg, td v ${r.vTd.map((x) => x.toFixed(2))}, range ${(r.range / 1e3).toFixed(1)} km, t ${r.t.toFixed(0)} s`);
  }
}
