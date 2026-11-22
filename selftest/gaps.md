# Course gaps found by the KSP self-test

Stock KSP 1.12.5 + kRPC 0.7.0, Kerbal X. One entry per miss (SELFTEST.md, "Log 1").
Class: **theory** (a concept is missing), **numerical** (formula right, number off), **execution** (script or piloting),
**code** (Moonshot's physics code, not its text). Only theory and numerical entries go to Moonshot's TODO.

## G1. Terminal ascent guidance needs a long upper-stage burn (TM-6) — theory
- Phase: ascent planning.
- The course's upper-stage law (Phys.simulateAscent: radial acceleration `6(h_T − h)/T² − 4 v_r/T`, T = time to go)
  is the Saturn V one: S-II + S-IVB burn for ~8 min. On Kerbal X the core burns 97 s at TWR ≈ 2, T is short, the
  demanded radial acceleration exceeds what the engine can give, the pitch saturates at +64°, the apoapsis overshoots
  and the law then dives at −30°: steering loss ~900 m/s, Δv left in LKO 2 420 m/s instead of ~3 400.
- What worked: the TM-7 shape (gravity turn, cutoff on a target) with the target being the apoapsis, a coast, and a
  circularisation PAD at apoapsis (TM-9/10). Planner: worst case 3 325 m/s left over CdA × 0.5…2.
- Proposed fix: in TM-6 or TM-7, say when closed-loop terminal guidance applies (long burn, low TWR, T ≫ time to climb)
  and give the "apoapsis cutoff + circularisation" profile used by small launchers, with its Δv cost.
- **Fixed in Moonshot (2026-11-22)**: TM-6 section 6.3 "Direct insertion or coast to apogee" (the guidance demand
  6Δh/T², Explorer 1's coast to apogee, the circularisation Δv from the cutoff state, when to use which), a practice
  problem and a concept question.

## G2. One exponential does not fit a real atmosphere (TM-5) — numerical
- Phase: Kerbin profile.
- Least-squares fit of ln ρ over 0–40 km (the TM-5 method): ρ₀ = 1.51 kg/m³ (KSP: 1.14), H = 5 444 m. Error against
  KSP's table: +33 % at sea level, −15 % at 10 km, −30…−35 % at 50–60 km. The pressure fit is similar (H = 5 441 m).
- The course's model is fine for orbit planning (drag losses are ~100 m/s here), but the numbers are off where drag peaks
  (Max Q near 7 km) and in the upper layers that set the aerobraking/entry corridor.
- Proposed fix: TM-5 could show the residuals of the fit and say why the scale height changes with altitude
  (temperature), and that the fit range should match the use (0–15 km for Max Q, 40–70 km for entry).

## G3. Earth/Moon constants are hard-coded (physics.js and chapter files) — code
- Phase: Kerbin profile.
- `Phys.C` holds Earth/Moon values; chapter files copy them at load (`const mu = C.muE` in launcher.phys.js), `R_SOI`
  and `EM` are computed at load, `pressure()` hard-codes a 7 500 m scale height, `density()` cuts at 200 km.
  A Kerbin profile has to patch C before requiring the chapter files (selftest/planner/profile.js does that).
- Proposed fix: a `Phys.setBody({...})` / profile object read at call time; or chapter files read `C.muE` at call time.

## Confirmations (no gap)
- Laplace sphere of influence `D (μ☾/μ⊕)^(2/5)` with Kerbin/Mun values gives 2 430 km, exactly KSP's Mun SOI (KSP uses
  the same formula), so TM-13's patched conics map one-to-one onto KSP.

## G4. Δv counter fooled by stale thrust after staging — execution (not a course gap)
- Phase: TMI. Planned 855.9 m/s (patched conics), counter said 855.9, flown 837.1 (from the perigee speed): 18.8 m/s short,
  apoapsis 9 085 km instead of reaching the Mun. kRPC's `thrust` stream still gave the dropped Mainsail's 1 500 kN for a
  few frames after decoupling, divided by the new 15 t mass. Fixed in `burn.py` (direct reads, thrust capped by
  available thrust × throttle). Recovered with a +19.25 m/s MCC 150 s after perigee (TM-14), solved with the course's
  patched conics: Mun periapsis 22 km (model 30.0 km, KSP node 29.7 km).
- Course note (TM-10): the course's "cut off on accumulated Δv" is right, but a burn that crosses a staging event needs
  the Δv split per stage on the PAD (and the counter re-armed).

## Confirmations (TMI)
- Hohmann hand calculation 856.9 m/s vs patched-conic search 855.9 m/s; TIG from the TM-11 phase angle (Mun lead 123.48°
  in the patched model, 110.88° for the Hohmann to the Mun's centre). Perigee measured at −123.45° from the Mun, at TIG.
- Course patched-conic Mun periapsis 30.4 km vs KSP node 41.7 km for the same PAD (0.3 m/s or 0.16° equivalent).
- KSP moves the Mun at n = √(μ_K/a³); Moonshot's EM.w uses μ⊕+μ☾ (0.9 % faster here). Patched in profile.js.

## G5. Descent guidance tuned for the LM's timescale and throttle range (TM-15/16) — theory
- Phase: descent planning. descent.phys.js with Mun + Poodle values (F 250 kN, Isp 350 s, TWR on the Mun ≈ 13):
  - throttle 0.4–1.0: braking crashes (high gate at −5…−40 m): the glide-tracking gains (0.004 on altitude, 0.12 on
    altitude rate) are tuned for the LM's ~10 min braking; with 40–75 s of braking they cannot follow the glide;
  - throttle 0.2–0.3: the approach never ends ("dry"): the 10 % minimum throttle (the DPS limit) gives more thrust than
    the Mun's weight, so the lander hovers until it runs out.
- What works (planner/landing.js, flight/descent.py): same structure, vertical channel commanding
  v_r = −(h − h_HG)/t_go with t_go = v_h/a_h (scales with the braking time), throttle 0–100 % on the approach,
  high gate 800 m, sink 1 + h/10. Simulated: 785 m/s from a 12 km PDI.
- Proposed fix: TM-16 could state the braking guidance in time-to-go form, and say
  that the minimum throttle and TWR decide whether a vertical approach can descend at all.
- Code: descent.phys.js has its own hard-coded Moon/LM constants (C.mu, C.R, C.F, C.isp; gM and c derived at load) — G3.

## Confirmations (LOI)
- LOI PAD from vis-viva: 284.47 m/s retrograde at periapsis, burn 16.5 s; flown 284.46 m/s; orbit 22.7 × 21.0 km
  (KSP node check 22.0 × 22.0). Mass after 13.880 t, as predicted by the rocket equation (13.88 t).

## G6. Mun ascent profile and a burn frame at near-zero speed — execution
- Phase: Mun ascent. My pitch law (elevation 90°(1 − v_h/0.85 v_c)) stays vertical when v_h is small, and the Poodle
  (TWR ≈ 13) reached the 20 km apoapsis straight up in 10 s. The circularisation PAD at apoapsis (537 m/s) was then
  flown along a "prograde" taken from a ~7 m/s velocity: wrong direction, orbit 38.3 × 2.65 km, i 12.1°, periapsis below
  the peaks. Rescued with a 21.6 m/s circularisation at apoapsis (38.9 × 38.3 km). Cost: ascent 763 m/s (from the mass)
  against ~600 for a proper pitch program.
- Course note (TM-7/TM-10): no module flies an ascent from an airless body (the LM ascent: vertical rise, then pitch over
  to a near-horizontal attitude within seconds); and the PAD frame (prograde/radial/normal) is undefined at a standstill,
  so a PAD built at the top of a vertical climb must be given in the local horizontal frame.

## G7. "v∞" at infinity vs at the sphere of influence (TM-17 hand calculation) — numerical
- Phase: TKI. The minimum-energy hand calculation (homeward.phys.js handMinEnergy) gives v∞ = 371 m/s, Δv = 304.4 m/s.
  KSP's patch is at the SOI radius (2 430 km, only 12 Mun radii), where the speed is √(v∞² + 2μ/R_SOI) = 437 m/s.
  Flown as is, KSP's node check (and the 3D patched-conic check) gave a Kerbin periapsis of −437 km (into the ground).
  Asking for 371 m/s *at the SOI* (v∞ = 290 m/s, Δv = 271.3 m/s) and placing the burn with the patched conics in 3D
  (12° inclined Mun orbit): 30.0 km predicted, KSP node 29.4 km, flown 24.4 km.
- For the real Moon the effect is smaller (SOI ≈ 38 R☾) but not zero; the course's solver (fly(), patched at R_SOI) is
  right, only the hand recipe uses the asymptotic speed. Proposed fix: TM-17 should say where the patch is made and
  apply vis-viva at the SOI radius in the hand calculation.
- Also: homeward.phys.js places the TEI for a clockwise lunar orbit only (Apollo's); a counter-clockwise orbit needs the
  mirrored burn position (burn θ∞ behind the asymptote direction, not ahead). The hand placement was 17° off here once
  the 12° inclination is included.

## G8. Thrust limiters ignored by my survey — execution (not a course gap)
- Phase: rendezvous test, target launch (Kerbal 1-5). The craft file limits the Swivel to 60 % and the Hammers to 40 %;
  the survey used `max_vacuum_thrust` (100 %), so the planner saw TWR 3.3 instead of ~1.5 and chose a 20° kick at 4 s.
  The gravity turn flattened at 2.2 km and the vehicle fell back (crew lost; sandbox). Fixed: `survey.py` records
  `Engine.thrust_limit` and scales the thrust. Lesson for the cockpit: the stage table must carry the limiter, and a
  pre-launch check should compare the planned TWR with `available_thrust / (m g)` on the pad.
- Course note (TM-6/7): the course could say how the kick depends on TWR (a high-TWR kick on a low-TWR vehicle is fatal).

## G9. Parallel staging without crossfeed (TM-4/6) — theory
- Phase: rendezvous test, target ascent (Kerbal 1-5). Two radial Hammer SRBs burn beside the core Swivel, with no fuel
  lines. The course stages are serial (Saturn V), and my asparagus model (Kerbal X) gave the boosters' phase all three
  engines but only the SRB propellant: planned burnout 41 s, flown 59 s; the core tank was empty at 99 s, not 139 s.
  The ascent was lofted (465 m/s at a 100 km apoapsis, a 1781 m/s circularisation) and ended 109 × 84 km.
- Fixed in `planner/vehicle.js`: a solid group burns only its own propellant; the liquid core lit with it drains its own
  tank meanwhile, and that drain is removed from the core's later phase. The replanned 80 km ascent matches the flown
  timeline (SRB out 59.3 s, core out 97.4 s).
- Course note (TM-4/6): the rocket equation per stage assumes each stage's engines burn that stage's propellant. Parallel
  stages (boosters + core, Titan IIIC, Shuttle) need the "phase" view: Δv per interval between drops, with mass flows
  from several tanks. Worth a paragraph and a practice problem.

## G10. Terminal-phase rules live in a UI file (docking chapter) — code
- The braking gate (ρ / 400 s, floor 0.05 m/s, handover at 100 m) and the probe capture envelope are constants in
  `js/ch/docking.js`, which needs the browser (App, UI) at load time. A `docking.phys.js` like the other chapters would let
  a planner import them; `planner/rdv.js` copies the numbers for now.

## G11. KSP sets the throttle to 50 % when a save loads — execution (not a course gap)
- Phase: rendezvous, after a desktop crash. Loading `rdv-target-lko-circ` made the target (active, Terrier lit) burn at
  50 % until I switched vessels: 109 × 109 km became 121 × 109 km and most of its propellant was gone. Fix in my scripts:
  zero the throttle right after any load or vessel switch. Cockpit: the gateway must command the panel's throttle (or 0)
  as soon as it binds a vessel, and the panel throttle should start at 0 with ENG ARM off.

## G12. Physics warp makes the autopilot waste RCS — execution (not a course gap)
- Phase: rendezvous terminal phase. With physics warp ×3 while coasting above 400 m, the kRPC autopilot (RCS on, holding
  the nose on the target) oscillated and fired the RCS against itself: 30 of 70 monopropellant units in 150 s. Without warp
  the whole approach from 400 m to 119 m used 0.5 unit. Rule: no physics warp while RCS and the autopilot are both on.

## Confirmations (rendezvous)
- TM-11 liftoff timing (timing.phys.js liftoff/liftoffDelay, with Kerbin's rotation as ω): the chaser reached its
  insertion apoapsis within 2 s of the planned time.
- TM-11 Hohmann phasing from the measured phase angle (6.82° required, 7.0 h synodic wait): 29.43 m/s burn, closest
  approach 100 m (KSP propagation check), 40 s before the planned arrival. The 0.1° relative inclination was left to
  the terminal phase as planned (4 m/s if burned as a plane change).
- Terminal braking gates (docking chapter, ρ/400 s): from 6.8 km at 33 m/s, one engine trim (17 m/s), then RCS only;
  LOS rate held under ~1°/min; handover at 118.8 m with 0.027 m/s relative speed after 1507 s.
- Docking: approach along the target port's axis from 30 m at 0.15 then 0.1 m/s; contact at 0.093 m/s, 0.10 m lateral,
  0.4° — inside the chapter's capture envelope (0.03–0.3 m/s, 0.3 m, 10°). Report: `reports/03-rendezvous.md`.

## G13. Drag area of an odd stack, guessed instead of measured (TM-5/6) — numerical
- Phase: Mun LOR v1 ascent (Kerbal X launcher + Kerbal 1-5 orbiter + stock Two-Stage Lander, 140 t). I planned with
  CdA 6 m² (Kerbal X alone flies well with ~4). The 4 m-wide lander made it ≈ 20 m² (400 kN of drag at q = 20 kPa).
  The planner's robust sweep (CdA ×0.5 … ×2) did not cover it; the turn flattened at 25 km in thick air, the core burned
  out with the apoapsis at 26 km, and the ascent stager did not light the Poodle (the core's `has_fuel` stayed True;
  fixed: zero available thrust counts as a flameout). Abort: pod separated, chute at 4.9 km, Bill splashed down; the
  lander crew (Bob, Lodfrid) were lost.
- Course note (TM-5/6): the course gives CdA for its vehicle. A launch with a new shape needs either a CdA estimate
  from the frontal area and a shape factor, or a measurement in flight: drag = m·(a_gravity+thrust − a_measured), and
  a rule to re-plan or abort when the measured CdA leaves the planned range (here it was known by t = 45 s).
- Redesign (v2): lander = a Kerbal 1-5 upper stack with legs (4.4 t, 1.25 m), orbiter = Mk1-3 command stack on a
  1.25 m service module (`craft/build_lor.py`).

## G14. Stack stiffness and separation hardware for a craft built by hand — execution (not a course gap)
- Mun LOR v2, second ascent: the 2.5 m command stack on a 1.25 m column of two docking ports Jr and three TD-12s bent;
  the flight-path angle fell from 80° to 33° in 12 s at 2.8 km and the vehicle went flat at 3.6 km (crew lost; pad
  save reloaded). With autostrut (heaviest part) and rigid attachment on the 50 parts above the core, the same plan flew
  to 82 × 77 km. The course has no structures; the cockpit should show a structural-load or wobble caution if KSP
  exposes one (it does not through kRPC).
- After TMI the orbiter's TD-12 fired and stayed on the lander's docking face (a TD-12 keeps its lower side; my builder
  assumed the opposite). `DockingPort.undock()` on the lander's pre-attached port released it ("decouple node"), and
  the port went to "ready". Fixed in `craft/build_lor.py`: the orbiter's engine sits directly on the lander's port and
  the separation is that port's decouple.

## G15. Vehicle constants left in the Mun-phase scripts — execution (not a course gap)
- `descent.py` stopped the Mun LOR lander at PDI: its "propellant low" test was a Kerbal X mass (7400 kg). Now the
  vessel's dry mass + 30 kg. Same family as G8/G9: every script must take the vehicle from the survey or from kRPC.
- With that fixed, the descent law of G5 (built for the Kerbal X Poodle, TWR ≈ 15 in Mun gravity) landed the Kerbal 1-5
  lander (TWR ≈ 8) unchanged: high gate at 738 m, touchdown at 1.37 m/s vertical, 0.01 m/s horizontal, 749 m/s used.

## G16. Mun ascent law with no initial heading: straight up, then the wrong plane — execution (course note)
- `mun_ascent.py` steers e = 90° (1 − v_h / 0.85 v_c): from rest on the Mun v_h = 0, so it stays vertical. On the first
  mission a small sideways drift started the turn; here it did not (v_h 1.8 m/s at cutoff, 12.9 s): a vertical pop-up to
  20 km, then a 537 m/s circularisation in a near-arbitrary horizontal direction. Orbit 22 × 19 km, 9.2° from the
  orbiter's plane; a TM-8 plane change (87 m/s) fixes it, ~90 m/s more than needed in all.
- The planner (planner/mun_ascent.js) simulated the same law and predicted the same pop-up; it did not flag it.
- Course note (TM-11 lunar ascent): the LM flew a heading in the CSM's plane from the first seconds (azimuth from the
  CSM's orbit, planes chapter); the ascent law should state the launch azimuth, not only the pitch program.
