/* Trans-Kerbin injection: TM-17 hand calculation (minimum-energy return, homeward.phys.js handMinEnergy).
   in  { alt (Mun orbit altitude), rpAlt (target Kerbin vacuum periapsis altitude) }
   out { dv, vinf, vhyp, vc, e, thInfDeg, tof, va } */
'use strict';
require('./profile');
const H = require('./profile').moonshot('homeward');
let input = '';
process.stdin.on('data', (d) => (input += d));
process.stdin.on('end', () => {
  const q = JSON.parse(input || '{}');
  const r = H.handMinEnergy(q.alt, q.rpAlt);
  console.log(JSON.stringify({ ...r, thInfDeg: r.thInf * 180 / Math.PI }));
});
