/* The Kerbin profile: loads Moonshot's physics with Kerbin/Mun constants read from kRPC (selftest/data/bodies.json).

   Moonshot's constants are hard-coded for Earth/Moon in Phys.C, and the chapter physics files copy them when they load
   (`const mu = C.muE` in launcher.phys.js, R_SOI and EM in physics.js). So the order matters: require physics.js, patch C
   and the atmosphere, then require the chapter files. `moonshot(name)` does that.
   The atmosphere is fitted the TM-5 way: a least-squares line through ln(p) and ln(ρ) against altitude. */
'use strict';
const fs = require('fs');
const path = require('path');

const MOONSHOT = process.env.MOONSHOT || path.resolve(__dirname, '../../../moonshot');
const DATA = path.resolve(__dirname, '../data');
const bodies = JSON.parse(fs.readFileSync(path.join(DATA, 'bodies.json'), 'utf8'));
const K = bodies.Kerbin, M = bodies.Mun;

// least-squares fit of ln(y) = ln(y0) − h/H over the rows with h ≤ hMax (TM-5, "fitting the scale height")
function fitExp(rows, key, hMax) {
  const pts = rows.filter((r) => r.h <= hMax && r[key] > 0).map((r) => [r.h, Math.log(r[key])]);
  const n = pts.length, sx = pts.reduce((a, p) => a + p[0], 0), sy = pts.reduce((a, p) => a + p[1], 0);
  const sxx = pts.reduce((a, p) => a + p[0] * p[0], 0), sxy = pts.reduce((a, p) => a + p[0] * p[1], 0);
  const slope = (n * sxy - sx * sy) / (n * sxx - sx * sx), icpt = (sy - slope * sx) / n;
  return { y0: Math.exp(icpt), H: -1 / slope };
}
const atmFit = { hMax: 40000 };
atmFit.rho = fitExp(K.atmosphere, 'rho', atmFit.hMax);
atmFit.p = fitExp(K.atmosphere, 'p', atmFit.hMax);

// Build a Kerbin copy of physics.js: substitute the constants in its source, so that everything computed at load time
// (EM, R_SOI) uses them too. Chapter files then find this copy as globalThis.Phys.
const vm = require('vm');
let src = fs.readFileSync(path.join(MOONSHOT, 'js/physics.js'), 'utf8');
const omega = 2 * Math.PI / K.rotational_period;
const subs = { muE: K.mu, RE: K.R, omegaE: omega, muM: M.mu, RM: M.R, DEM: M.orbit.a, rho0: atmFit.rho.y0, H: atmFit.rho.H, p0: K.atmosphere[0].p };
for (const [key, val] of Object.entries(subs)) {
  const re = new RegExp(`(\\n\\s+${key}:\\s*)[-0-9.e+]+`);
  if (!re.test(src)) throw new Error('profile: constant not found in physics.js: ' + key);
  src = src.replace(re, `$1${val}`);
}
// physics.js hard-codes the pressure scale height (7 500 m) and cuts density at 200 km
src = src.replace('Math.exp(-Math.max(0, h) / 7500)', `Math.exp(-Math.max(0, h) / ${atmFit.p.H})`)
  .replace('function density(h) { return h > 200000 ? 0', `function density(h) { return h > ${K.atmosphere_depth} ? 0`)
  .replace('function pressure(h) { return C.p0', `function pressure(h) { return h > ${K.atmosphere_depth} ? 0 : C.p0`);
const sandbox = { module: { exports: {} }, globalThis: {}, Math, console };
sandbox.globalThis = sandbox;
vm.runInNewContext(src, sandbox, { filename: 'physics.js (Kerbin)' });
const Phys = sandbox.module.exports;
const C = Phys.C;
C.atmTop = K.atmosphere_depth;
// KSP moves the Mun on rails around Kerbin's centre: n = √(μ_K / a³). Moonshot's EM uses μ⊕ + μ☾ (right for the real
// Moon, barycentric); here that is 0.9 % too fast, ~0.7° of Mun motion over a transfer. simulatePatched reads EM.w per call.
Phys.EM.w = Math.sqrt(C.muE / Math.pow(C.DEM, 3));
globalThis.Phys = Phys;          // chapter files: `root.Phys || require('../physics.js')`

// interpolation in kRPC's own table, to compare the fit with the "truth"
function tableAt(key, h) {
  const rows = K.atmosphere;
  if (h <= 0) return rows[0][key];
  for (let i = 1; i < rows.length; i++) if (h <= rows[i].h) {
    const a = rows[i - 1], b = rows[i], w = (h - a.h) / (b.h - a.h);
    return a[key] > 0 && b[key] > 0 ? Math.exp(Math.log(a[key]) * (1 - w) + Math.log(b[key]) * w) : a[key] * (1 - w);
  }
  return 0;
}

const cache = {};
function moonshot(name) {
  if (!cache[name]) cache[name] = require(path.join(MOONSHOT, 'js/ch', name + '.phys.js'));
  if (cache[name].C && 'muE' in cache[name].C && cache[name].C !== C) throw new Error(name + ' did not pick up the Kerbin physics');
  return cache[name];
}

module.exports = { Phys, C, K, M, bodies, atmFit, tableAt, moonshot, MOONSHOT, DATA };

if (require.main === module) {
  console.log('Kerbin profile');
  console.log(`  mu ${C.muE.toExponential(5)}  R ${C.RE}  omega ${C.omegaE.toExponential(5)} rad/s  surface speed ${(C.omegaE * C.RE).toFixed(1)} m/s`);
  console.log(`  Mun: mu ${C.muM.toExponential(5)}  R ${C.RM}  a ${C.DEM}  SOI (Laplace) ${(Phys.R_SOI / 1e3).toFixed(0)} km vs KSP ${(M.soi / 1e3).toFixed(0)} km`);
  console.log(`  density fit (h ≤ ${atmFit.hMax / 1e3} km): rho0 ${atmFit.rho.y0.toFixed(3)} kg/m³, H ${atmFit.rho.H.toFixed(0)} m`);
  console.log(`  pressure fit: p0 ${atmFit.p.y0.toFixed(0)} Pa, H ${atmFit.p.H.toFixed(0)} m`);
  for (const h of [0, 10e3, 20e3, 30e3, 40e3, 50e3, 60e3, 65e3]) {
    console.log(`   h ${(h / 1e3).toString().padStart(2)} km  rho fit ${Phys.density(h).toExponential(3)}  KSP ${tableAt('rho', h).toExponential(3)}  ratio ${(Phys.density(h) / tableAt('rho', h)).toFixed(2)}`);
  }
}
