/* Powered descent plan (TM-15 descent.phys.js with Mun + Poodle values; TM-16 margins).
   descent.phys.js has its own hard-coded Moon/LM constants in P.C (read at call time; gM and c are derived at load,
   so they are recomputed here).
   in  { hc (circular orbit altitude, m), m0, prop (usable propellant, kg), F, isp, hp (PDI altitude), hHG, throttles }
   out { doi, best: { throttle, ... }, table } */
'use strict';
const { C } = require('./profile');
const D = require('./profile').moonshot('descent');

function plan(q) {
  Object.assign(D.C, { mu: C.muM, R: C.RM, F: q.F, isp: q.isp, hMin: q.hMin ?? 4000 });
  D.C.gM = D.C.mu / (D.C.R * D.C.R);
  D.C.c = D.C.isp * D.C.g0;
  const hp = q.hp, doi = D.doi(q.hc, hp);
  const table = [];
  for (const thr of q.throttles || [0.2, 0.25, 0.3, 0.4, 0.5, 0.7, 1.0]) {
    const r = D.simulate({ hc: q.hc, doiDv: doi.dv, m0: q.m0, prop: q.prop, throttle: thr, pdiRange: 0, hHG: q.hHG ?? 1500 });
    table.push({ throttle: thr, outcome: r.outcome, dvTotal: r.dvTotal, brakeTime: r.hg && r.hg.dt, brakeRange: r.hg && r.hg.dx,
      hgH: r.hg && r.hg.h, approachTime: r.approachTime, margin: r.margin, propLeft: r.td.prop, mTd: r.td.m,
      gravityLossBrake: r.gravityLossBrake });
  }
  // TM-16: pick the cheapest landing that still leaves the braking long enough to steer (≥ 40 s)
  const ok = table.filter((x) => x.outcome === 'landed' && x.brakeTime >= 40).sort((a, b) => a.dvTotal - b.dvTotal);
  return { doi, gM: D.C.gM, c: D.C.c, best: ok[0] || null, table };
}

let input = '';
process.stdin.on('data', (d) => (input += d));
process.stdin.on('end', () => console.log(JSON.stringify(plan(JSON.parse(input || '{}')))));
