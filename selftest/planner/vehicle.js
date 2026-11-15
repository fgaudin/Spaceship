/* The vehicle as a list of burn phases, from selftest/data/vessel.json (survey.py).

   Asparagus staging (Kerbal X): every engine lit at liftoff draws from the outermost booster pair still attached, so each
   decouple group's propellant is one phase, burned by all engines not yet dropped. A phase's Isp is the mixture value
   ΣF / Σ(F/Isp) (TM-4: the engines' mass flows add). Engines lit later (the Poodle) get their own phase.
   KSP keeps an engine's mass flow fixed and lets thrust follow Isp(p), as TM-7 assumes.

   Solid boosters (Kerbal 1-5): no crossfeed. A solid group burns only its own propellant, while the liquid engines lit
   with it drain their own tanks at the same time; that drain is taken off the core's later phase (selftest/gaps.md G9). */
'use strict';
const fs = require('fs');
const path = require('path');
const { C, DATA } = require('./profile');

function vehicleFromSurvey(file = path.join(DATA, 'vessel.json')) {
  const v = JSON.parse(fs.readFileSync(file, 'utf8'));
  const groups = Object.keys(v.stages).map(Number).sort((a, b) => b - a);
  const payloadGroup = Math.min(...groups);
  const firstIgnition = Math.max(...v.engines.map((e) => e.stage));
  const phases = [];
  const solid = (e) => e.propellants && e.propellants.length === 1 && e.propellants[0] === 'SolidFuel';
  const mdot = (e) => e.max_thrust_vac / (e.isp_vac * C.g0);
  const drained = {};                                   // group -> propellant already burned in an earlier phase
  for (const g of groups) {
    const st = v.stages[g];
    let prop = st.mass - st.dry - (drained[g] || 0);
    if (g === payloadGroup || prop < 1) continue;
    // engines burning this group's propellant: lit at liftoff and not dropped before it (asparagus), or the group's own
    // a group's own engines: only those lit first (a payload riding in the group, like the Mun LOR lander under the
    // orbiter's separation decoupler, has engines of its own that never fire on ascent)
    const own0 = v.engines.filter((e) => e.decouple_stage === g);
    const firstLit = Math.max(...own0.map((e) => e.stage));
    const own = own0.filter((e) => e.stage === firstLit);
    let lit = own.some((e) => e.stage === firstIgnition)
      ? v.engines.filter((e) => e.stage === firstIgnition && e.decouple_stage <= g)
      : own;
    if (own.length && own.every(solid) && own[0].stage === firstIgnition) {
      const core = lit.filter((e) => !solid(e));
      const tA = prop / own.reduce((a, e) => a + mdot(e), 0);
      for (const e of core) drained[e.decouple_stage] = (drained[e.decouple_stage] || 0) + mdot(e) * tA;
      prop += core.reduce((a, e) => a + mdot(e) * tA, 0);
    }
    const fVac = lit.reduce((a, e) => a + e.max_thrust_vac, 0);
    const ispVac = fVac / lit.reduce((a, e) => a + e.max_thrust_vac / e.isp_vac, 0);
    // sea-level thrust at the same mass flow: F_SL = F_vac · Isp_SL / Isp_vac per engine
    const fSL = lit.reduce((a, e) => a + e.max_thrust_vac * e.isp_asl / e.isp_vac, 0);
    const ispSL = ispVac * fSL / fVac;
    phases.push({ name: `group ${g} (${lit.length} eng)`, group: g, prop, dry: st.dry, fVac, ispVac, ispSL,
      engines: lit.map((e) => e.title), lateIgnition: lit[0].stage !== firstIgnition });
  }
  const payload = v.stages[payloadGroup].mass;
  let m = payload + phases.reduce((a, p) => a + p.prop + p.dry, 0);
  const m0 = m;
  for (const p of phases) { p.m0 = m; p.dv = p.ispVac * C.g0 * Math.log(m / (m - p.prop)); m -= p.prop + p.dry; }
  const first = phases[0];
  return {
    name: v.name, m0, payload, phases, dvVac: phases.reduce((a, p) => a + p.dv, 0),
    twr0: first.fVac * first.ispSL / first.ispVac / (m0 * C.g0),
    upperFrom: phases.findIndex((p) => p.engines.length === 1),     // first phase after the boosters are gone
  };
}

module.exports = { vehicleFromSurvey };
