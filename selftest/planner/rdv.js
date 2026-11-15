/* Rendezvous planning with the course's formulas. JSON on stdin, JSON on stdout.

   phase: TM-11 (timing.phys.js): Hohmann phase angle, wait, TIG, TOF; TM-2 vis-viva for the two burns.
     in  { cmd: 'phase', r1, r2, phi0 (rad, target ahead of chaser, in the direction of motion), t0 (UT), mu? }
     out { phiReq, wait, tig, tof, syn, dv1, dv2, at }
   plane: TM-8 (planes.phys.js): pure plane change magnitude, for checking the vector Δv.
     in  { cmd: 'plane', v, di (rad) }   out { dv }
   liftoff: TM-11 ascent timing (timing.phys.js liftoff, liftoffDelay with the site's rotation omega).
     in  { cmd: 'liftoff', hLow, hTgt, tAsc, thAsc, tCoast, phiNow (target ahead of the site), omega }
     out { phiLift, delay, tH, tTotal, period }
   tb: TM-10 burn time.  in { cmd: 'tb', dv, m, F, isp }  out { tb }
   gate: terminal braking gate (docking.js; the constants are in the chapter UI file, copied here: gaps.md G10).
     in  { cmd: 'gate', rho }            out { v, TAU_G, V_MIN, HANDOVER, env } */
'use strict';
const { C, Phys, moonshot } = require('./profile');
const T = moonshot('timing');
const P = moonshot('planes');
const TAU_G = 400, V_MIN = 0.05, HANDOVER = 100;
const ENV = { vmin: 0.03, vmax: 0.3, lat: 0.3, ang: 10, latRate: 0.15 };

const CMDS = {
  phase({ r1, r2, phi0, t0 = 0, mu = C.muE }) {
    const s = T.setup({ mu, r1, r2, t0, th1: 0, th2: phi0 });
    const at = (r1 + r2) / 2;
    const vv = (r, a) => Math.sqrt(mu * (2 / r - 1 / a));
    return { phiReq: s.phiReq, wait: s.wait, tig: s.tig, tof: s.tof, syn: s.syn, at,
             dv1: vv(r1, at) - Math.sqrt(mu / r1), dv2: Math.sqrt(mu / r2) - vv(r2, at) };
  },
  liftoff({ hLow, hTgt, tAsc, thAsc, tCoast = 0, phiNow, omega = 0, mu = C.muE, R = C.RE }) {
    const L = T.liftoff(mu, R, hLow, hTgt, tAsc, thAsc, tCoast);
    return { phiLift: L.phiLift, delay: T.liftoffDelay(L.phiLift, phiNow, L.nC, omega), tH: L.tH, tTotal: L.tTotal, period: L.period };
  },
  tb({ dv, m, F, isp }) { return { tb: Phys.burnTime(Math.abs(dv), m, F, isp) }; },
  plane({ v, di }) { return { dv: P.planeDv(v, di) }; },
  gate({ rho }) { return { v: Math.max(rho / TAU_G, V_MIN), TAU_G, V_MIN, HANDOVER, env: ENV }; },
};

let input = '';
process.stdin.on('data', (d) => (input += d));
process.stdin.on('end', () => {
  const q = JSON.parse(input || '{}');
  const f = CMDS[q.cmd];
  if (!f) { console.error('unknown cmd ' + q.cmd); process.exit(2); }
  console.log(JSON.stringify(f(q)));
});
