# Self-test status (resume from here)

Stock KSP 1.12.5 (install folder in the `KSP_DIR` environment variable), kRPC 0.7.0 on 127.0.0.1:50000.
Python: `Spaceship/.venv` (krpc==0.7.0). Run flight scripts from `selftest/flight/`. Temp output in `Spaceship/tmp/`.
Craft: stock Kerbal X (asparagus boosters, Mainsail core, Poodle upper stage with legs, Mk1-3 pod).

## Saves (KSP `space_center.load(name)`)
| Save | State |
|---|---|
| selftest-pad | on the pad, before launch |
| selftest-coast | ascent done, coasting to apoapsis 80 km |
| selftest-lko | parking orbit 80.2 × 78.2 km, 36.67 t, core still attached (8.7 t propellant) |
| selftest-pre-tmi | LKO, just before the TMI burn sequence |
| selftest-tmi | after the TMI burn (short, no encounter) |
| selftest-mcc | after MCC1: Mun encounter, periapsis 22 km, Poodle stage only, 15.08 t |
| selftest-mun-soi | inside the Mun SOI, before LOI |
| selftest-loi | Mun orbit 22.7 × 21.0 km, 13.880 t |
| selftest-pre-doi / selftest-doi / selftest-pdi | before DOI / after DOI / at powered descent initiation |
| selftest-landed / selftest-mun-surface | on the Mun |
| selftest-mun-orbit2 | bad orbit after the Mun ascent (38.3 × 2.65 km) |
| selftest-mun-orbit3 | Mun orbit 38.9 × 38.3 km, i 12.1°, 8.890 t |
| selftest-pre-tki / selftest-tki | before / after the trans-Kerbin burn |
| selftest-kerbin-soi / selftest-home | back in Kerbin's SOI / splashed down |

## Phases
- [x] Survey, Kerbin profile (`selftest/data/bodies.json`, `vessel.json`)
- [x] Ascent + circularisation (`flight/ascent.py`, report `reports/01-ascent.md`)
- [x] TMI (`flight/tmi.py`): 18.8 m/s short (G4), fixed by MCC1
- [x] MCC1 +19.25 m/s (`flight/mcc.py`), Mun periapsis 22 km; trim pending
- [x] Mun orbit insertion 284.5 m/s (`flight/loi.py`): 22.7 × 21.0 km, 13.880 t
- [x] Descent and landing (`flight/descent.py`): DOI 6.2 m/s, PDI 12 km, touchdown 1.33 m/s, Midlands 0.55°N 31.14°W, 11.173 t
- [x] Mun ascent (`flight/mun_ascent.py` + `circ.py`): 763 m/s (G6), orbit 38.9 × 38.3 km, i 12.1°, 8.890 t
- [x] Trans-Kerbin injection (`flight/tki.py`): 271.3 m/s (G7), Kerbin periapsis 24.4 km, 8.214 t
- [x] Entry and splashdown (`flight/entry.py`): Poodle dropped at 90 km, 4.0 g entry, chute 4 988 m at 247 m/s, splashed 0.77°S 162.26°E, crew of 3 safe

**MISSION PASSED** (2026-11-14, 23:48 local).

## Rendezvous and docking test (2026-11-15) — PASSED
Two stock Kerbal 1-5. Target in 122 × 121 km; chaser launched on the TM-11 liftoff time, 85 km parking orbit, Hohmann
from the measured phase angle, braking gates to 119 m, docking at 0.093 m/s. Report: `reports/03-rendezvous.md`.
Scripts: `flight/rdv.py` (name-target, liftoff, transfer, terminal, dock), `planner/rdv.js`. Saves: `rdv-target-*`,
`rdv-chaser-*` (last: `rdv-chaser-rdv-docked`). New gaps G9–G12 in `gaps.md`.
Notes: KSP throttles to ~0.07× when its window is hidden; zero the throttle after every load (G11); crews must be
available (`launch_vessel(..., crew=[...])`, recover old capsules first).

## Mun mission with a separate lander (2026-11-15) — PASSED
Craft "Mun LOR" (`craft/build_lor.py`): Kerbal X launcher, Mk1-3 orbiter, Kerbal 1-5 lander with legs. TMI,
transposition and docking, LOI, lander descent and landing (Highlands), TM-11 timed liftoff, plane change, rendezvous
and docking in Mun orbit, crew transfer, TKI, entry and landing on Kerbin. Report: `reports/04-mun-lor.md`. Scripts
added: `flight/td.py`, `flight/lor.py`, `rdv.py mun-liftoff / plane`, `planner/mun_ascent.js`. Saves `lor3-*` (last
`lor3-home`). Two earlier attempts lost their crews (v1 drag, v2 structure; G13, G14).

## Next step
All phases flown, and rendezvous + docking in LKO. Open: Mun ascent with a launch azimuth (G16); free return (TM-14) and entry corridor (TM-18) tests; second run on JNSQ.
Gaps in `gaps.md`, interface needs in `interface.md`, reports in `reports/`, logs in `logs/`, results in `data/*-result.json`.

## Cockpit prototype (2026-11-15)
- `docker compose up -d --build` → broker, cockpit logic, mock plant, virtual panel on http://localhost:8650 (see README.md).
- Unit tests 13/13, end-to-end (mock) 22/22. KSP gateway checked against the running game (telemetry, SAS mode mapping).
