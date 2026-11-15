/* Trans-Mun injection planner (TM-2 vis-viva, TM-11 phase angle, TM-13 patched conics, TM-10 burn time).
   in  { parkAlt, periAlt (target Mun periapsis altitude, m), m, stages: [{ prop, dry, F, isp }] (burn order) }
   out { hand: {...}, best: { dv, burnAngle (deg, vessel ahead of... see below), tSOI, periAlt, vinf, dir }, tb }

   burnAngle (simulatePatched convention): at TIG the vessel is at angle φ from the Kerbin→Mun line, measured in the
   direction of motion (both orbit counter-clockwise seen from the north). */
'use strict';
const { Phys, C } = require('./profile');
const T = require('./profile').moonshot('timing');

function stagedBurnTime(dv, m, stages) {      // rocket equation stage by stage (TM-4/TM-10)
  let t = 0, left = dv, mm = m;
  for (const s of stages) {
    const ve = s.isp * C.g0, md = s.F / ve;
    const dvMax = ve * Math.log(mm / (mm - s.prop));
    const use = Math.min(left, dvMax);
    t += mm / md * (1 - Math.exp(-use / ve));
    left -= use;
    if (left <= 1e-9) return { tb: t, stagesUsed: stages.indexOf(s) + 1 };
    mm -= s.prop + s.dry;
  }
  return { tb: t, short: left };
}

function plan(q) {
  const r1 = C.RE + q.parkAlt, r2 = C.DEM;
  // hand calculation: Hohmann to the Mun's distance (TM-2/9) and its phase angle (TM-11)
  const at = (r1 + r2) / 2;
  const v1 = Math.sqrt(C.muE / r1), vp = Math.sqrt(C.muE * (2 / r1 - 1 / at));
  const tof = T.hohmannTime(C.muE, r1, r2);
  const phiReq = T.requiredPhase(C.muE, r1, r2);             // Mun ahead of the vessel at TIG, rad
  const hand = { dv: vp - v1, tof, munLeadDeg: phiReq * 180 / Math.PI, burnAngleDeg: -phiReq * 180 / Math.PI };
  // patched conics (TM-13): search Δv and burn angle for the target periapsis, cheapest Δv first
  const sim = (dv, ang) => Phys.simulatePatched({ parkAlt: q.parkAlt, dv, burnAngle: ang, tMax: 4 * 86400 });
  const res = [];
  for (let dv = hand.dv - 15; dv <= hand.dv + 40; dv += 1) {
    for (let a = hand.burnAngleDeg - 30; a <= hand.burnAngleDeg + 30; a += 0.5) {
      const r = sim(dv, a);
      if (r.conic.soiIn) res.push({ dv, a, periAlt: r.conic.soiIn.periAlt, tSOI: r.conic.soiIn.t, vinf: r.conic.soiIn.vinf, outcome: r.outcome });
    }
  }
  // the target: periapsis altitude within 2 km, lowest Δv; refine the angle by bisection-free fine scan
  const near = res.filter((x) => Math.abs(x.periAlt - q.periAlt) < 15e3).sort((a, b) => a.dv - b.dv);
  if (!near.length) return { hand, error: 'no encounter near the target periapsis', sample: res.slice(0, 5) };
  const dv0 = near[0].dv + (q.dvPad ?? 3);       // a few m/s above the minimum: a less grazing, less sensitive encounter
  let best = null;
  for (let a = near[0].a - 10; a <= near[0].a + 10; a += 0.02) {
    const r = sim(dv0, a);
    if (!r.conic.soiIn) continue;
    const err = Math.abs(r.conic.soiIn.periAlt - q.periAlt);
    if (!best || err < best.err) best = { err, dv: dv0, burnAngle: a, periAlt: r.conic.soiIn.periAlt, tSOI: r.conic.soiIn.t, vinf: r.conic.soiIn.vinf, ecc: r.conic.soiIn.e, outcome: r.outcome, minM: r.minM };
  }
  // sensitivity (TM-14): periapsis change per m/s and per degree
  const s1 = sim(best.dv + 1, best.burnAngle).conic.soiIn, s2 = sim(best.dv, best.burnAngle + 0.1).conic.soiIn;
  best.dPeri_dDv = s1 ? s1.periAlt - best.periAlt : null;
  best.dPeri_dDeg = s2 ? (s2.periAlt - best.periAlt) / 0.1 : null;
  const burn = q.stages ? stagedBurnTime(best.dv, q.m, q.stages) : null;
  return { hand, best, burn, nCandidates: near.length };
}

let input = '';
process.stdin.on('data', (d) => (input += d));
process.stdin.on('end', () => {
  const q = JSON.parse(input || '{}');
  console.log(JSON.stringify(plan({ parkAlt: 79e3, periAlt: 30e3, ...q })));
});
