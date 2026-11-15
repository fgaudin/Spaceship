/* Midcourse correction on the way out (TM-14), with TM-13's patched conics.

   The measured post-TMI orbit is put back in simulatePatched's terms: a "parking orbit" at the transfer's perigee,
   an impulse dv = v_p − v_c there, and the burn angle = angle of the perigee from the Kerbin→Mun line at perigee time.
   That is exact for a coplanar Kepler ellipse. The correction is along-track (prograde +, retrograde −) at tMcc after
   perigee, as in the course's MCC solver; we root-find the Mun periapsis altitude instead of the Earth return perigee.

   in  { rp, vp, angleDeg, tMcc, target, range }
   out { nominal: { periAlt, tSOI }, mcc: dv | null, after: { periAlt, tSOI, vinf } } */
'use strict';
const { Phys, C } = require('./profile');

function run(q) {
  const parkAlt = q.rp - C.RE, dv = q.vp - Math.sqrt(C.muE / q.rp);
  const sim = (mdv) => Phys.simulatePatched({ parkAlt, dv, burnAngle: q.angleDeg, mcc: mdv ? { t: q.tMcc, dv: mdv } : null, tMax: 4 * 86400 });
  const nom = sim(0);
  const periOf = (r) => (r.conic.soiIn ? r.conic.soiIn.periAlt : NaN);
  const out = { nominal: { periAlt: periOf(nom), tSOI: nom.conic.soiIn && nom.conic.soiIn.t, outcome: nom.outcome }, input: { parkAlt, dv } };
  const f = (x) => periOf(sim(x)) - q.target;
  const range = q.range ?? 20, N = 80;
  let best = null, prev = { x: -range, v: f(-range) };
  for (let i = 1; i <= N; i++) {
    const x = -range + 2 * range * i / N, v = f(x);
    if (isFinite(v) && isFinite(prev.v) && Math.sign(v) !== Math.sign(prev.v)) {
      let lo = prev.x, hi = x, vlo = prev.v;
      for (let k = 0; k < 50; k++) { const m = (lo + hi) / 2, vm = f(m); if (!isFinite(vm)) break; if (Math.sign(vm) === Math.sign(vlo)) { lo = m; vlo = vm; } else hi = m; }
      const c = (lo + hi) / 2;
      if (Math.abs(f(c)) < 2000 && (best === null || Math.abs(c) < Math.abs(best))) best = c;
    }
    prev = { x, v };
  }
  out.mcc = best;
  if (best !== null) { const r = sim(best); out.after = { periAlt: periOf(r), tSOI: r.conic.soiIn.t, vinf: r.conic.soiIn.vinf }; }
  return out;
}

let input = '';
process.stdin.on('data', (d) => (input += d));
process.stdin.on('end', () => console.log(JSON.stringify(run(JSON.parse(input || '{}')))));
