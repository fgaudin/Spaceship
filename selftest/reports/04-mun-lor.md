# Report 4: Mun landing with a separate lander (lunar-orbit rendezvous)

Stock KSP 1.12.5, kRPC 0.7.0. Craft "Mun LOR" assembled by `craft/build_lor.py` from stock parts:
- launcher: Kerbal X core and boosters, with its Poodle stage as the translunar stage;
- orbiter: Mk1-3 command module, heat shield, Kerbal 1-5 service module with a Terrier;
- lander: a Kerbal 1-5 upper stack with three legs.

Crew: Dunvey (orbiter), Sigrid (lander). Every burn came from the course's formulas and the planners in
`planner/`; KSP's predictions were used only as checks.

## Timeline

| Phase | Method | Planned | Flown |
|---|---|---|---|
| Ascent | TM-6/7, apoapsis cutoff, CdA 10 (robust ×0.5–2) | 80 km | 82.3 × 77.4 km, i 0.12°; core did the circularisation (1345 m/s) |
| TMI | TM-11/13 phase angle, hand Hohmann; node check only | 855.45 m/s, Mun periapsis 29 km (node check 29.2 km) | 855.43 m/s; Mun periapsis 80 km (kept: a good parking altitude) |
| Transposition & docking | docking chapter ("tde"): separate, back off 25 m, turn, dock | | docked at 0.106 m/s, 0.10 m lateral; spent Poodle stage dropped |
| LOI | TM-13, vis-viva at periapsis, centred burn | −271.4 m/s; node check 70.6 × 70.6 km | −271.35 m/s → 71.1 × 70.1 km, i 2.6° |
| Undocking | | | lander 4.50 t, adapter dropped, engine on |
| DOI | TM-15 | −30.0 m/s, periapsis 10.8 km (node check) | 30.03 m/s → 70.4 × 10.4 km |
| Powered descent | TM-15/16 structure, law of G5 | | high gate 738 m; touchdown 1.37 m/s vertical, 0.01 m/s horizontal, 749 m/s; 0.88° N 38.07° W (Highlands) |
| Lunar liftoff time | TM-11 `liftoff`, Mun rotation, ascent profile from `planner/mun_ascent.js` | orbiter 30.1° ahead at liftoff | on time; ascent law went vertical (G16) |
| Mun ascent | TM-7 shape, circularisation PAD | 20 km | 22.1 × 18.7 km, but 9.2° out of the orbiter's plane |
| Plane change | TM-8 (planes.phys.js planeDv), at the relative node | 87.33 m/s | 87.18 m/s → 0.038° |
| Transfer | TM-11 phase angle, Hohmann | 27.54 m/s | 27.52 m/s; closest approach 1.85 km (KSP check) |
| Terminal phase | braking gates ρ/400 s | from 6.7 km at 26 m/s | one 11.6 m/s engine trim, then RCS; handover 99.9 m at 0.025 m/s |
| Docking | port axis from 30 m | | contact 0.099 m/s, 0.10 m lateral |
| Crew transfer | `SpaceCenter.transfer_crew` | | Sigrid into the Mk1-3; lander jettisoned; orbiter 6.40 t |
| TKI | TM-17 (SOI-corrected, G7) + 3D patched check | 261.41 m/s | 261.39 m/s → Kerbin periapsis 32.8 km |
| Entry | TM-18 | periapsis 32.8 km | service module dropped at 90 km; peak 2.5 g; chute at 4979 m, 238 m/s; **landed** at 0.10° N 160.39° W (Mountains), Dunvey and Sigrid safe |

Result: **passed**. Both crew are home. The heat shield was missing after the landing on a mountain; it was not
decoupled, so it probably broke at touchdown. The entry script then stopped on a telemetry stream of the vessel it held
before the service-module separation (cosmetic: the capsule had already landed).

## What the course gave, what I added

The course gave every burn: phase angles, waits, Hohmann and plane-change Δv, burn times and centring, the lunar
liftoff timing and the braking gates. It also gave the transposition-and-docking sequence, as a docking-chapter
scenario.

What I had to add:
- the craft itself, since no stock design carries a separate lander;
- the stiffening;
- the separation hardware;
- crew transfer;
- the plane change after a bad ascent;
- several fixes to scripts that had Kerbal X built in.

## Losses and fixes

Two crews were lost before the successful flight. Both were sandbox losses, recovered by reloading the pad save.

- **v1 (stock Two-Stage Lander):** CdA was about 20 m², three times the plan, and the stack could not reach orbit (G13).
- **v2:** the stack bent at its docking ports and decouplers and went flat at 3.6 km (G14). Fixed with autostrut and
  rigid attachment.
- **New gaps G13–G16:**
  - drag area;
  - structure and separation hardware;
  - vehicle constants left in the scripts;
  - the Mun ascent's missing launch azimuth.
