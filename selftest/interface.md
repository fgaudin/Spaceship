# What a Mun mission uses from KSP/kRPC (self-test, Log 2)

Source: every kRPC access went through `selftest/kio.py`; raw log in `logs/interface.jsonl` (first use per member and
phase, value type, argument types) and call counts in `logs/interface-counts.json`. 112 members were used on one Mun
landing and return (stock KSP 1.12.5, kRPC 0.7.0, Kerbal X). Units SI; angles in kRPC are radians for orbits, degrees
for autopilot/flight.

## 1. Features by group

| Group | kRPC members (read unless noted) | Rate | Phases | Backend hint |
|---|---|---|---|---|
| Time | `SpaceCenter.ut` | stream, every loop | all | Simpit or kRPC stream |
| Surface flight | `Flight.mean_altitude`, `surface_altitude`, `vertical_speed`, `horizontal_speed`, `speed`, `dynamic_pressure`, `g_force`, `drag`, `latitude`, `longitude` (flight in the body frame) | stream 20–50 Hz | ascent, descent, Mun ascent, entry | Simpit (simple scalars) |
| Vessel state | `Vessel.mass`, `thrust`, `available_thrust`, `vacuum_specific_impulse`, `situation`, `biome`, `crew` | stream (mass, thrust, situation); one-shot otherwise | all burns | Simpit for mass/thrust; kRPC for crew/biome |
| State vectors | `Vessel.position(frame)`, `Vessel.velocity(frame)` (non-rotating body frame; hybrid surface frame for landing) | one-shot per plan; stream 20 Hz in landing | TMI, MCC, TKI, descent | kRPC only (frames) |
| Orbit | `Orbit.apoapsis(_altitude)`, `periapsis(_altitude)`, `semi_major_axis`, `eccentricity`, `inclination`, `period`, `time_to_apoapsis`, `time_to_periapsis`, `time_to_soi_change`, `body`, `next_orbit`, `position_at(ut, frame)` | stream for apo/peri during burns; one-shot for planning; `position_at` many times per plan | all | apo/peri: Simpit; `position_at`, `next_orbit`: kRPC only |
| Bodies | `CelestialBody.gravitational_parameter`, `equatorial_radius`, `rotational_period/speed`, `sphere_of_influence`, `mass`, `surface_gravity`, `atmosphere_depth`, `pressure_at(h)`, `density_at(h)`, `orbit.*` (elements), `reference_frame`, `non_rotating_reference_frame`, `position(frame)` | one-shot (Kerbin profile, once per game) | survey, planning | kRPC only; cache in a retained topic |
| Staging | `Control.activate_next_stage` (write), `Control.current_stage`, `Parts.engines` → `Engine.active`, `has_fuel`, `part`, `max_vacuum_thrust`, `vacuum_specific_impulse`, `kerbin_sea_level_specific_impulse`; `Parts.all` → `Part.stage`, `decouple_stage`, `mass`, `dry_mass`, `title`, `resources.amount()` | flameout check every loop during ascent; stage table one-shot | ascent, TMI, entry | flameout/stage: Simpit; stage table: kRPC |
| Throttle | `Control.throttle` (write) | 50 Hz in closed loops | all burns | Simpit / HID (hot path) |
| Attitude | `AutoPilot.engaged` (write), `reference_frame` (write), `target_direction` (write), `target_pitch_and_heading` (call), `target_roll` (write), `error` (read); `Control.sas`, `sas_mode`, `speed_mode` (write) | target updates 20–50 Hz in ascent/landing | all | kRPC only (autopilot, frames); SAS mode: Simpit |
| Gear, chutes | `Control.gear` (write), `Parachute.deploy` (call), `Parts.parachutes` | event | landing, Mun ascent, entry | Simpit (action groups) |
| Geometry | `Vessel.bounding_box(frame)` (lowest point for radar height), `surface_reference_frame`, `ReferenceFrame.create_hybrid` | one-shot (after gear moves) | landing | kRPC only |
| Maneuver nodes (check only) | `Control.add_node(ut, prograde, …)`, `Node.orbit` → `next_orbit.periapsis_altitude`, `Node.remove` | one-shot per PAD | TMI, MCC, LOI, DOI, TKI | kRPC only |
| Time warp | `SpaceCenter.warp_to(ut)`, `rails_warp_factor`, `physics_warp_factor` (write), `warp_mode` | per coast | all coasts | kRPC (warp_to); Simpit has warp too |
| Game | `KRPC.paused` (write), `SpaceCenter.save(name)` | per phase | planning, saves | kRPC only |

## 2. Draft topic table (seed for `protocol/`)

| Topic | Schema sketch | Writer | Rate | QoS / retained |
|---|---|---|---|---|
| `tlm/time` | `{ut, met, warp: {mode, rate}}` | gateway | 10 Hz | 0, retained |
| `tlm/flight` | `{alt, radar, vs, hs, speed, q, g, lat, lon}` (SI, body frame) | gateway | 20–50 Hz | 0 |
| `tlm/vessel` | `{mass, thrust, thrust_avail, isp_vac, situation, stage}` | gateway | 20 Hz | 0 |
| `tlm/orbit` | `{body, apo, peri, a, e, i, T, t_apo, t_peri, t_soi, next: {body, peri}}` | gateway | 2–5 Hz (20 Hz in burns) | 0, retained |
| `tlm/state` | `{body, frame: "nonrot", r: [3], v: [3], ut}` | gateway | on request / 1 Hz | 0 |
| `tlm/attitude` | `{pitch, heading, roll, ap_error}` | gateway | 20 Hz | 0 |
| `tlm/engines` | `[{id, stage, active, has_fuel, thrust}]` | gateway | 5 Hz + on change | 0 |
| `tlm/stages` | `[{stage, decouple, prop, dry, F_vac, isp_vac, isp_sl}]` | gateway | on change (staging, docking) | 1, retained |
| `tlm/bodies/<name>` | `{mu, R, T_rot, soi, atm_top, atm: [{h, p, rho}], orbit: {…}}` | gateway | once per game | 1, retained |
| `tlm/predict` | `{node_id, next: {body, peri, t_soi}}` (KSP's own prediction, check only) | gateway | on request | 1 |
| `cmd/throttle` | `{value}` | flight computer / panel | 50 Hz | 0 |
| `cmd/attitude` | `{mode: "direction"|"pitch_heading"|"sas", frame, dir: [3] | {pitch, heading}, roll}` | flight computer / panel | 20 Hz | 0 |
| `cmd/stage`, `cmd/gear`, `cmd/chute`, `cmd/sas_mode` | `{}` / `{on}` / `{mode}` | panel | event | 1 |
| `cmd/warp` | `{to_ut}` or `{rails, physics}` | flight computer / instructor | event | 1 |
| `cmd/game` | `{pause}`, `{save: name}`, `{load: name}` | instructor | event | 1 |
| `gateway/status` | `{connected, scene, vessel, paused, warp, krpc_version}` | gateway | on change | 1, retained |

## 3. What KSP/kRPC does not provide (the cockpit must own it)
- **PAD storage and TIG countdown**: kRPC has no PAD object; a node is a KSP-side Δv plan, not a PAD with attitude,
  burn time and centring. Every PAD here was computed by the course's formulas and flown by our executor.
- **Δv counter and cutoff on accumulated Δv** (TM-10), with re-arming across a staging event (gap G4).
- **Burn attitude held fixed in inertial space** from the PAD frame at TIG (kRPC gives the autopilot, not the PAD frame).
- **Radar height of the lowest point** (surface_altitude is from the centre of mass; the bounding box must be added).
- **Phase angle, burn position from the Mun line, SOI-patched predictions**: computed from state vectors.
- **Stage table with propellant per decouple group** (kRPC 0.7 dropped `resources_in_decouple_stage`; sum per part).

## 4. Quirks met
- kRPC server 0.7.0 needs the 0.7.0 Python client (pip's default matches; the old CKAN registry said 0.5.4).
- kRPC 0.7: `AutoPilot.engage()/disengage()` removed, use `engaged = True/False`; no `resources_in_decouple_stage`.
- `surface_velocity_reference_frame` is singular at rest (exception on the pad); read drag in the body frame.
- Streams can be stale for a few frames after staging: the dropped engine's thrust is still reported (G4).
  Read `thrust`/`available_thrust` directly in burn loops, or wait a few frames after `activate_next_stage`.
- KSP frames are left-handed (y = north/rotation axis); orbit planes are x-z. Signs of angles must be taken from the
  motion (r × v), not assumed.
- `warp_to` uses physics warp inside an atmosphere and rails warp outside; it returns when the time is reached.
- Pausing (`KRPC.paused = True`) freezes `ut`: a script that waits on `ut` must unpause first.
- `activate_next_stage` returns the list of new vessels (debris); `active_vessel` stays on the pod.
- Mun on rails around Kerbin's centre: n = √(μ_K/a³), not √((μ_K+μ_M)/a³).
