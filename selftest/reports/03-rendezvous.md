# Report 3: rendezvous and docking in low Kerbin orbit

Stock KSP 1.12.5, kRPC 0.7.0, two stock Kerbal 1-5 (one crew each). Every burn came from the course's formulas
(`planner/rdv.js` on Moonshot's timing.phys.js, planes.phys.js and the docking chapter's gate rule); KSP's orbit
propagation was used once, as a check of the closest approach. Result: **docked**.

| Step | Course method | Planned | Flown |
|---|---|---|---|
| Target ascent | TM-6/7 gravity turn, apoapsis cutoff | 100 km circular | 109 × 84 km (parallel staging, G9), then circularised; 122 × 121 km after the 50 % throttle on load (G11) |
| Chaser liftoff time | TM-11 `liftoff` / `liftoffDelay` with Kerbin's rotation; 20 min coast margin | target 2.56° ahead of the pad; apoapsis 214 s after liftoff | liftoff on time; cutoff 107.6 s (plan 106.4 s); apoapsis ≈ 2 s from the plan |
| Chaser orbit | TM-9/10 circularisation | 80 km | 84.9 × 70.7 km (83 s burn on a lofted arc), circularised at 85.3 × 84.9 km |
| Plane | TM-8 check | — | relative inclination 0.103° (3.98 m/s as a plane change): left to the terminal phase |
| Transfer | TM-11 phase angle and wait, TM-2 vis-viva | required 6.82°, wait 24 805 s (synodic 7.0 h), 29.43 m/s, TOF 986 s | 29.41 m/s; closest approach 100 m, 40 s before the planned arrival |
| Terminal phase | docking chapter: null the drift, braking gates ρ/400 s, handover at 100 m | from 6.8 km at 33 m/s | one 17 m/s engine trim, then RCS; LOS rate under ~1°/min; 118.8 m, 0.027 m/s after 1507 s |
| Docking | onto the port axis at 30 m, close inside the capture envelope (0.03–0.3 m/s, 0.3 m, 10°) | 0.15 m/s, then 0.1 m/s | contact at 0.093 m/s, 0.10 m lateral, 0.4° |

Propellant: chaser monopropellant 70 → 11.8 units, of which about 30 were wasted by physics warp (G12).

What the course gave directly: the liftoff time, the phase angle and wait, the Hohmann Δv, the gate rule and the capture
envelope. What I had to add: the closed-loop law that follows the gates (velocity error = gate speed along the line of
sight minus the measured relative velocity), the choice of ports, the waypoint onto the port axis, and the split between
main engine (errors above 1.5 m/s) and RCS.

Problems, none from the course's rendezvous theory: G9 (parallel staging model), G10 (gate constants in a UI file),
G11 (throttle at 50 % after a load), G12 (physics warp and RCS), a deadlock in my kRPC logger (`kio.py`, fixed), a launch
without crew (all four kerbals were assigned), and KSP running at 0.07× when its window is hidden.
