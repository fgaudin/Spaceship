/* Ascent planner: the guidance the flight script flies, simulated with the course's models.

   Course sources: TM-6 (gravity turn, rotating Earth, loss ledger, upper-stage terminal guidance of Phys.simulateAscent),
   TM-7 (engines whose thrust falls with ambient pressure at fixed mass flow: launcher.phys.js thrustAt / mdot),
   TM-4 (rocket equation per stage), TM-5 (fitted exponential atmosphere, see profile.js).
   Planar, equatorial, inertial frame; Kerbin turns under the vehicle; drag on the air-relative velocity.

   Guidance (same as selftest/flight/ascent.py):
     1. vertical rise until kickT, pitch kick of kickA (ramped over 4 s);
     2. gravity turn: thrust along the air-relative velocity;
     3. from the first upper-stage phase above hSwitch: TM-6 terminal guidance toward a circular orbit at targetAlt;
     4. cutoff when the orbit's energy reaches that of the circular target orbit.

   node selftest/planner/ascent.js [--cda 4] [--kick 10 3] [--target 80000]   → selftest/data/ascent-plan.json */
'use strict';
const fs = require('fs');
const path = require('path');
const { Phys, C, DATA } = require('./profile');
const L = require('./profile').moonshot('launcher');
const { vehicleFromSurvey } = require('./vehicle');

function simulate(veh, prog) {
  const mu = C.muE, RE = C.RE, w = C.omegaE, g0 = C.g0;
  const hT = prog.targetAlt, epsT = -mu / (2 * (RE + hT));
  const dt = 0.1;
  // state: x, y, vx, vy (inertial, Kerbin centre); launch site on +y, east = +x; Kerbin spins clockwise seen from +z
  // (east is +x at the top), so the ground moves at +ωR along x at the site
  let s = [0, RE, w * RE, 0];
  let ph = 0, m = veh.m0, propLeft = veh.phases[0].prop, t = 0, mode = 'vertical';
  const L_ = { gravity: 0, drag: 0, steering: 0, ideal: 0 }, events = [], trace = [];
  let maxQ = { q: 0, t: 0, h: 0 };
  const geom = (s) => {
    const r = Math.hypot(s[0], s[1]), ur = [s[0] / r, s[1] / r], uh = [ur[1], -ur[0]];   // uh: local east
    // air velocity: subtract the ground's rotation (ω × r, clockwise: (ω y, −ω x))
    const va = [s[2] - w * s[1], s[3] + w * s[0]];
    const var_ = va[0] * ur[0] + va[1] * ur[1], vah = va[0] * uh[0] + va[1] * uh[1];
    const vr = s[2] * ur[0] + s[3] * ur[1], vh = s[2] * uh[0] + s[3] * uh[1];
    return { r, ur, uh, h: r - RE, va, vaMag: Math.hypot(...va), pathAir: Math.atan2(vah, var_), vr, vh };
  };
  function timeToGo(dv) {          // TM-6: burn time to gain dv from the current phase on
    let tt = 0, mm = m;
    for (let i = ph; i < veh.phases.length && dv > 0; i++) {
      const st = veh.phases[i], ve = st.ispVac * g0, md = L.mdot(st);
      const prop = i === ph ? propLeft : st.prop;
      const use = Math.min(dv, ve * Math.log(mm / (mm - prop)));
      tt += mm / md * (1 - Math.exp(-use / ve));
      dv -= use; mm -= prop + st.dry;
    }
    return tt;
  }
  function pitchFromVertical(G, accT) {
    if (mode === 'vertical') { if (t >= prog.kickT) mode = 'kick'; else return 0; }
    const kick = prog.kickA * Math.PI / 180 * Math.min(1, (t - prog.kickT) / 4);
    if (mode === 'kick' && t >= prog.kickT + 4 && G.pathAir >= kick) mode = 'turn';
    if (mode === 'kick') return kick;
    if (mode === 'turn' && prog.cutoff !== 'apo' && ph >= veh.upperFrom && G.h >= prog.hSwitch) { mode = 'terminal'; events.push({ t, label: 'terminal guidance', h: G.h }); }
    if (mode === 'turn') return Math.max(kick, G.pathAir);
    const vc = Math.sqrt(mu / (RE + hT));
    const T = Math.max(prog.tMin ?? 20, timeToGo(Math.max(0, vc - G.vh)));
    const aRdes = 6 * (hT - G.h) / (T * T) - 4 * G.vr / T;
    const need = aRdes + mu / (G.r * G.r) - G.vh * G.vh / G.r;
    const sb = Math.max(-0.5, Math.min(0.9, need / accT));
    return Math.PI / 2 - Math.asin(sb);
  }
  let outcome = null;
  while (!outcome && t < 1200) {
    const st = veh.phases[ph];
    const G = geom(s), p = Phys.pressure(G.h), F = L.thrustAt(st, p), accT = F / m;
    const th = pitchFromVertical(G, accT);
    const u = [Math.cos(th) * G.ur[0] + Math.sin(th) * G.uh[0], Math.cos(th) * G.ur[1] + Math.sin(th) * G.uh[1]];
    const rho = Phys.density(G.h), q = 0.5 * rho * G.vaMag * G.vaMag, D = q * veh.cdA / m;
    const ua = G.vaMag > 1e-6 ? [G.va[0] / G.vaMag, G.va[1] / G.vaMag] : [0, 0];
    const f = (tt, z) => { const r = Math.hypot(z[0], z[1]), k = mu / (r * r * r); return [z[2], z[3], -k * z[0] + accT * u[0] - D * ua[0], -k * z[1] + accT * u[1] - D * ua[1]]; };
    const gl = mu / (G.r * G.r);
    L_.gravity += gl * Math.cos(G.pathAir) * dt;
    L_.drag += D * dt;
    L_.steering += accT * (1 - (u[0] * ua[0] + u[1] * ua[1])) * dt;
    L_.ideal += accT * dt;
    if (q > maxQ.q) maxQ = { q, t, h: G.h };
    if (!trace.length || t - trace[trace.length - 1].t >= 5) trace.push({ t: +t.toFixed(1), h: Math.round(G.h), vAir: +G.vaMag.toFixed(1), pitch: +(90 - th * 180 / Math.PI).toFixed(2), path: +(90 - G.pathAir * 180 / Math.PI).toFixed(2), ph, m: Math.round(m), q: Math.round(q), mode });
    const md = L.mdot(st);
    const sn = Phys.rk4(f, t, s, dt);
    const r2 = Math.hypot(sn[0], sn[1]), eps = (sn[2] ** 2 + sn[3] ** 2) / 2 - mu / r2;
    if (prog.cutoff === 'apo' && mode === 'turn') {
      const vv = Math.hypot(sn[2], sn[3]), G2 = geom(sn);
      const e2 = Phys.elementsFromRV(r2, vv, Math.atan2(G2.vr, G2.vh), mu);
      if (e2.ra - RE >= hT) { s = sn; t += dt; m -= md * dt; propLeft -= md * dt; events.push({ t, label: 'cutoff (apoapsis)', h: Math.round(G2.h) }); outcome = 'cutoff'; break; }
    }
    if (mode === 'terminal' && eps >= epsT) { s = sn; t += dt; m -= md * dt; propLeft -= md * dt; events.push({ t, label: 'cutoff' }); outcome = 'cutoff'; break; }
    s = sn; t += dt; m -= md * dt; propLeft -= md * dt;
    if (r2 < RE) { outcome = 'crash'; break; }
    if (propLeft <= 0) {
      events.push({ t, label: `${st.name} burnout`, h: Math.round(geom(s).h) });
      if (ph === veh.phases.length - 1) { outcome = 'burnout'; break; }
      m -= st.dry - (-propLeft); ph++; propLeft = veh.phases[ph].prop;
    }
  }
  let circ = null;
  if (outcome === 'cutoff' && prog.cutoff === 'apo') {
    // coast (drag still acts below the atmosphere top) to apoapsis, then the circularisation PAD (TM-9: Δv = v_c − v_apo)
    let tc = t, cut = { t, h: geom(s).h };
    const fc = (tt, z) => { const r = Math.hypot(z[0], z[1]), k = mu / (r * r * r), G2 = geom(z);
      const D = 0.5 * Phys.density(G2.h) * G2.vaMag * G2.vaMag * veh.cdA / m;
      return [z[2], z[3], -k * z[0] - D * G2.va[0] / G2.vaMag, -k * z[1] - D * G2.va[1] / G2.vaMag]; };
    while (geom(s).vr > 0 && tc - t < 1200) { s = Phys.rk4(fc, tc, s, 0.5); tc += 0.5; }
    const G2 = geom(s), dvc = Math.sqrt(mu / G2.r) - G2.vh;
    circ = { tApo: tc, hApo: G2.h, dv: dvc, coast: tc - cut.t, vApo: G2.vh, thApo: Math.atan2(s[0], s[1]) };   // inertial angle from the site at liftoff (TM-11 thAsc)
    events.push({ t: tc, label: `apoapsis, circularise ${dvc.toFixed(1)} m/s`, h: Math.round(G2.h) });
  }
  const G = geom(s), v = Math.hypot(s[2], s[3]);
  const el = Phys.elementsFromRV(G.r, v, Math.atan2(G.vr, G.vh), mu);
  // Δv left: rest of the current phase + later phases (vacuum)
  let dvLeft = 0, mm = m;
  for (let i = ph; i < veh.phases.length; i++) {
    const st = veh.phases[i], prop = i === ph ? propLeft : st.prop;
    dvLeft += st.ispVac * g0 * Math.log(mm / (mm - prop)); mm -= prop + st.dry;
  }
  if (circ) dvLeft -= circ.dv;
  return { outcome, circ, t, h: G.h, v, el: { apo: el.ra - RE, peri: el.rp - RE, e: el.e }, phase: ph, propLeft, m, dvLeft, losses: L_, maxQ, events, trace };
}

function arg(name, n = 1) { const i = process.argv.indexOf('--' + name); return i < 0 ? null : process.argv.slice(i + 1, i + 1 + n).map(Number); }

if (require.main === module) {
  const veh = vehicleFromSurvey();
  veh.cdA = (arg('cda') || [4])[0];
  const target = (arg('target') || [80000])[0];
  console.log(`vehicle: m0 ${(veh.m0 / 1e3).toFixed(2)} t, Δv vac ${veh.dvVac.toFixed(0)} m/s, TWR0 ${veh.twr0.toFixed(2)}, CdA ${veh.cdA} m²`);
  for (const p of veh.phases) console.log(`  ${p.name.padEnd(14)} F_vac ${(p.fVac / 1e3).toFixed(0).padStart(5)} kN  Isp ${p.ispSL.toFixed(0)}/${p.ispVac.toFixed(0)} s  prop ${(p.prop / 1e3).toFixed(2)} t  dry ${(p.dry / 1e3).toFixed(2)} t  tb ${L.burnTime(p).toFixed(1)} s  Δv ${p.dv.toFixed(0)}`);
  let best = null;
  const sweep = [];
  for (const kickT of [4, 6, 8, 10, 12, 15, 20]) for (const kickA of [2, 3, 4, 5, 6, 8, 10, 12, 15, 20]) {
    // robust choice: score each program by its worst case over the drag uncertainty (CdA ×0.5 … ×2)
    const prog = { kickT, kickA, cutoff: 'apo', targetAlt: target };
    const runs = [0.5, 1, 2].map((k) => simulate({ ...veh, cdA: veh.cdA * k }, prog));
    const r = runs[1], worst = Math.min(...runs.map((x) => (x.outcome === 'cutoff' && x.circ && x.circ.hApo > target - 5e3 ? x.dvLeft : -1e9)));
    sweep.push({ kickT, kickA, outcome: r.outcome, hApo: r.circ && r.circ.hApo, dvLeft: r.dvLeft, worst, maxQ: r.maxQ.q });
    if (worst > -1e9 && (!best || worst > best.worst)) best = { prog, r, worst };
  }
  if (!best) { console.log('no program reaches orbit'); console.table(sweep.slice(0, 20)); process.exit(1); }
  const { prog, r } = best;
  console.log(`best: kick at ${prog.kickT} s by ${prog.kickA}°, cutoff when apoapsis = ${target / 1e3} km; worst-case Δv left ${best.worst.toFixed(0)} m/s`);
  if (r.circ) console.log(`  coast ${r.circ.coast.toFixed(0)} s to apoapsis ${(r.circ.hApo / 1e3).toFixed(1)} km, circularisation ${r.circ.dv.toFixed(1)} m/s`);
  console.log(`  cutoff t ${r.t.toFixed(1)} s, apo ${(r.el.apo / 1e3).toFixed(1)} km, peri ${(r.el.peri / 1e3).toFixed(1)} km, phase ${veh.phases[r.phase].name}`);
  console.log(`  losses: gravity ${r.losses.gravity.toFixed(0)}, drag ${r.losses.drag.toFixed(0)}, steering ${r.losses.steering.toFixed(0)}; ideal Δv spent ${r.losses.ideal.toFixed(0)} m/s`);
  console.log(`  max Q ${(r.maxQ.q / 1e3).toFixed(1)} kPa at ${r.maxQ.t.toFixed(0)} s, ${(r.maxQ.h / 1e3).toFixed(1)} km; Δv left (vac) ${r.dvLeft.toFixed(0)} m/s`);
  for (const e of r.events) console.log(`  event t ${e.t.toFixed(1)} ${e.label}${e.h != null ? ' h ' + (e.h / 1e3).toFixed(1) + ' km' : ''}`);
  const out = { made: new Date().toISOString(), vehicle: veh, prog, result: { ...r, trace: undefined }, trace: r.trace };
  fs.writeFileSync(path.join(DATA, 'ascent-plan.json'), JSON.stringify(out, null, 1));
}

module.exports = { simulate };
