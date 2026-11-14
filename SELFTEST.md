# Agent self-test of the Moonshot course in KSP

## Goal
Check that Moonshot (TM-1…TM-19) is enough to fly to the Mun and back. An agent (Claude Code) plans every burn
from the course alone and flies it in KSP 1.12.5 through kRPC. Two by-products:
- a list of **course gaps**;
- the list of **KSP/kRPC features** a Mun mission really uses, as the seed for `protocol/` (topics in §1 of
  PLAN.md).

To run on the machine that has KSP. Nothing here needs the capsule hardware.

## Constraint: the agent is slow, KSP is real time
- Planning (PADs, phase angles, Δv) happens between agent steps with the game paused (`krpc.paused`).
- Closed loops (gravity turn, burn cut-off, descent and landing) run as short Python scripts written from the
  course's guidance laws, started in the background; the agent reads their logs afterwards.
- KSP's maneuver-node predictions (and MechJeb, if installed) are used only to check, never to plan.

## Setup on the KSP machine
- KSP 1.12.5 + kRPC (server on localhost:50000, auto-accept connections), `pip install krpc` in a venv.
- Moonshot checked out next to Spaceship (the planner runs Moonshot's `js/physics.js` in Node).
- A Mun-capable craft with known stages; a quicksave before each phase so a failure can be retried and
  attributed.

## Method
1. **Kerbin profile.** Read μ, R, rotation period, SOI and the Mun's orbit from kRPC
   (`body.gravitational_parameter`, `body.equatorial_radius`, `body.rotational_period`,
   `body.sphere_of_influence`, `body.orbit`…) and plug them into `js/physics.js` (Earth/Moon are hard-coded in
   `C` today). The course's own code computes the PADs, which tests the code as well as the text. This is also
   the "Kerbin profile" of PLAN.md §4.
2. **Fly phase by phase**, prediction from the course vs measurement from telemetry:

   | Phase | Course module | Prediction | Check in KSP |
   |---|---|---|---|
   | Ascent to 80 km LKO | TM-6/7 (gravity turn, pitch table, Δv losses) | Δv used, apoapsis | orbit, Δv left |
   | Circularise | TM-9/10 (PAD, burn time, finite burn) | Δv, burn time | e ≈ 0 |
   | Trans-Mun injection | TM-2/9/11/13 (vis-viva, phase angle, TIG) | Δv, TIG, encounter periapsis | `node.orbit.next_orbit` |
   | Midcourse | TM-14 (MCC solver) | correction Δv | Mun periapsis on target |
   | Mun orbit insertion | TM-13 (LOI) | Δv | low Mun orbit |
   | DOI, powered descent, landing | TM-15/16 | Δv, ignition point, hover margin | touchdown < 3 m/s |
   | Ascent + rendezvous (split craft) | TM-8/12 | lead angle, CW gates | docked |
   | Trans-Kerbin + entry | TM-17/18 | TEI Δv, Kerbin periapsis in corridor | splashdown |
   | Whole mission | TM-19 | Δv budget with margins | budget respected |

3. **Pass criteria** per phase, e.g. encounter periapsis ±10 %, Δv ±5 %. The mission passes on Kerbin
   splashdown.

## Log 1: course gaps (`selftest/gaps.md`)
One entry per miss:
- phase, and module/section in Moonshot's TODO numbering ("13.2" = TM-13, section 2);
- predicted vs measured;
- class: **theory** (a concept is missing), **numerical** (formula right, number off) or **execution**
  (script or piloting);
- proposed fix.

Only theory and numerical entries go to Moonshot's TODO. Expected suspects: SOI patching rules, launching from
a rotating body, Kerbin constants, aerobraking into Kerbin's 70 km atmosphere vs Apollo's entry corridor.

## Log 2: interface needs (`selftest/interface.md`)
All kRPC access goes through one wrapper (`selftest/kio.py`) that records every call, so the log is complete
by construction. Per feature:
- kRPC `service.class.member`, read or write, type, unit and reference frame, rate needed (stream or one-shot),
  and the flight phase that needed it;
- proposed topic in the PLAN.md namespaces: `tlm/…` (SI units), `cmd/…`, `gateway/status` (scene, vessel,
  paused, warp);
- backend hint: Simpit candidate (hot path, simple values) or kRPC only (maneuver nodes, autopilot, reference
  frames, `next_orbit` predictions, docking-port frames);
- what KSP/kRPC does not provide, so the cockpit must own it (PAD storage, TIG countdown, attitude error in the
  PAD frame, …);
- quirks: scene changes, vessel switch after staging or undocking, stream re-subscription, left-handed and
  rotating frames, warp limits, pause semantics.

End product: a draft topic table (topic, schema sketch, writer, rate, QoS/retained) to seed `protocol/`.

## Output
`selftest/` in the capsule repo:
- planner (Node, uses Moonshot's `js/physics.js`);
- flight scripts (Python, through `kio.py`) and flight logs;
- `gaps.md`, `interface.md`;
- a short report per phase.
