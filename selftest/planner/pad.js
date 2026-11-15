/* PADs computed with the course's formulas. JSON on stdin, JSON on the last stdout line.

   circ: circularise at an apsis (TM-2 vis-viva, TM-9 PAD, TM-10 burn time and centring)
     in  { cmd: 'circ', r, a, m, F, isp }            r: radius of the apsis (m), a: semi-major axis now (m)
     out { dv, vNow, vc, tb, lead }                  lead: start the burn tb/2 before the apsis */
'use strict';
const { Phys, C } = require('./profile');

function circ({ r, a, m, F, isp, mu = C.muE }) {
  const vNow = Math.sqrt(mu * (2 / r - 1 / a));        // vis-viva
  const vc = Math.sqrt(mu / r);
  const dv = vc - vNow;
  const tb = Phys.burnTime(Math.abs(dv), m, F, isp);
  return { dv, vNow, vc, tb, lead: tb / 2 };
}

const CMDS = { circ };

let input = '';
process.stdin.on('data', (d) => (input += d));
process.stdin.on('end', () => {
  const q = JSON.parse(input || '{}');
  const f = CMDS[q.cmd];
  if (!f) { console.error('unknown cmd ' + q.cmd); process.exit(2); }
  console.log(JSON.stringify(f(q)));
});
