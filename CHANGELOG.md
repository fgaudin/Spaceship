# Changelog

What changed and why, in more detail than the commit messages. Newest first. Topic and panel names are those of
`protocol/topics.md` and `protocol/panels/`.

## 2026-11-16 — SOLO PADs, MCC polls and shared consoles

- **SOLO panel and flight-dynamics service** (`flight-dynamics/`): for a pilot flying without Mission Control,
  CIRC, PLANE, RDV TGT and INJECT (Mun or Minmus) ask for a PAD, which the service works out (two-body orbits,
  Hohmann transfers timed on the phase angle, plane change at the cheaper node) and reads up to the burn computer
  exactly as CAPCOM would. The gateway now also sends each orbit's longitude of the ascending node and time, and the
  target's orbit. The moons' orbits are KSP's stock elements, checked against the game. Students keep computing
  PADs by hand for the crew; the radio between them and the crew is still to come.
- **Flown in KSP** (`tests/e2e_ksp_solo.py`): CIRC from the suborbital coast to 82.2 × 73.5 km (e 0.0065); INJECT
  856 m/s to a Mun encounter; RDV transfer to a closest approach of 110 m. PLANE needs a low thrust limit for its
  small burns (see flight-dynamics/README.md).
- **Bugs those flights found:**
  - CIRC on a suborbital coast close to apoapsis moved the burn "one orbit later", through Kerbin: an event that
    will not come again now keeps its burn, with a 10 s minimum lead instead of 60.
  - A save left the game's throttle at 0.02: 1 kN for minutes, enough to twist an orbit by 25° and to stop KSP from
    time-warping, while the burn computer counted it as the burn. The cockpit re-sent the throttle only above a 0.02
    difference; now above 0.005.
  - SimSup's log could drop the last value of a lever (throttle back to 0): the latest value held back by the
    once-a-second limit is now always logged.
- **CKAN modlist** for stock KSP (`ckan/stock.ckan`), to reinstall the same mods; variants go beside it.
- **Poll banner in MCC:** while FLIGHT's poll is open, every console shows the question with large GO and NO-GO
  buttons, pulsing until answered.
- **Several consoles per laptop** (`mcc.html#fido+retro`): tabs are toggles; one answer for all consoles held,
  loop notes signed with all of them.

## 2026-11-16 — Mission Control

- **MCC** (`panels/virtual/mcc.html`, code in `panels/virtual/mcc/`): one tab per console, FLIGHT, FIDO, RETRO,
  GUIDO, BOOSTER, EECOM and CAPCOM, for one laptop per controller; the role is remembered on each laptop. No server:
  each console reads the bus, and the shared state (the go/no-go poll, each console's answer) is retained on the
  broker, so a late laptop catches up at once. A text loop to FLIGHT from every console. CAPCOM reads up PADs
  (`pad/uplink`) only with AOS and follows the readback. MCC never reads `sim/*`: controllers find failures from
  the vehicle. Checked in a browser with two separate sessions (poll, answer, loop, a late joiner) and a PAD read up
  to the burn computer. Architecture: `panels/virtual/mcc/README.md`.
- **SimSup stays its own page**, linked from the MCC: in Apollo the simulation team sat apart, and the controllers
  must not see which failures are coming.

## 2026-11-16 — SimSup, the instructor station

- **SimSup** (`simsup/`, page `simsup.html`): starts scenarios (a save, a briefing, failures with triggers),
  injects failures now or arms them on mission time, altitude or stage, freezes the game, loads saves, and logs the
  session: failures, alarms, crew inputs, commands, notes. The debrief gives the crew's time to acknowledge and to
  first act after each failure; the log exports as JSON. Architecture and failure catalogue: `simsup/README.md`.
- **Vehicle failures in KSP** (`gateway-ksp/ksp/failures.py`): engines out (all, or the outermost one, kept off),
  gimbals stuck, RCS dead, reaction wheels dead, parachutes dead, comm lost, telemetry frozen. The gateway also obeys
  `sim/freeze` (KSP paused) and `sim/load` (load a save). Failure state survives a kRPC reconnection.
- **Instrument failures in the cockpit** (`cockpit/injected_failures.py`): false caution or warning (by id or legend),
  panel dark and dead, display frozen, switch stuck.
- **Mock plant**: `sim/freeze`, and gimbal and parachute failures.
- **Tests**: `simsup/tests` (9), cockpit `test_injected_failures.py` (4), `tests/e2e_ksp_simsup.py` (25 checks in
  KSP: every failure injected and cleared with its effect checked in the game and on the panels).
- **GAPS.md**: the cockpit's open gaps found by flying, and the closed ones.

## 2026-11-16 — a landing and an ascent flown from the panels, DSKY removed, fixes they led to

Two scripted flights in KSP, acting only through panel inputs and reading only panel outputs, to find what unit tests
cannot.

- **Mun landing on the LAB figures** (`tests/e2e_ksp_landing.py`, 24 checks). Cross-pointer signs confirmed by turning
  the nose and watching the dot (NODE and RETRO). TO GROUND counts down with the clock. Braking started when BRAKE
  blinks: predicted height 581 m, used 571 m, stopped 59 m up; then a touchdown under 4 m/s.
- **Pad to parking orbit** (`tests/rehearsal_ksp_ascent.py`): kick, gravity turn on SAS MODE PRO, STAGE on each
  FLAMEOUT, CUTOFF on the apoapsis display, circularisation PAD keyed by hand, burn cut by the computer. Reached
  81.9 × 76.4 km. It prints the gaps it met and every alarm that came on.
- **Fixes that came out of them:**
  - A command KSP refuses (clearing a maneuver node on the pad, SAS while kRPC's autopilot is engaged) used to end the
    gateway's link and restart it, each time setting the throttle to zero. It is now logged and the link stays.
  - The cockpit sends the throttle again when the game's differs from the one commanded for over a second (gateway
    restart, save loaded), except in time warp.
  - The SAS mode last selected is sent again, up to five times, when the game shows another: KSP falls back to
    stability when SAS is switched on, and can drop a mode set in the frame its reference appears.
  - The burn computer shows the burn time as soon as a Δv is keyed, before the TIG: the crew needs it to work out
    the TIG.
  - PERI LOW no longer comes on while thrusting (it flashed at the end of the orbit insertion).
- **DSKY removed:** `cockpit/dsky.py`, its panel, its tests, the CB DSKY breaker, the `dsky/uplink` topic and the
  page styles. The Δv is now counted once, by the burn computer.
- **Gaps it found, then fixed:**
  - TWR read 0.00 and stage Δv was blank before ignition (unlit engines report no thrust). The gateway now sends
    each engine's rated thrust and its specific impulse in vacuum and at sea level, and the outside pressure; before
    ignition the cockpit uses the engines the next staging lights, and the gateway watches their tanks.
  - The orbit went out at 2 Hz, so a cutoff on the apoapsis display overshot by 1.7 km. While thrusting it now goes
    out at 10 Hz, from streams sped up for the burn.
  - A field selected for keying showed only a cursor; it now keeps its value until the first key.
  - The navball's speed reference had no control: SPEED REF knob (orbit, surface, target) and three lamps for the
    game's actual reference on the ENG panel; `cmd/speed_mode`, `tlm/vessel` speed_mode.
  - NO LINK came on once in the coast, cause unknown: the gateway now logs a command or a telemetry read that takes
    over 0.5 s, and the cockpit logs every telemetry gap over 1 s.
- **Left as they are:** nothing gives the circularisation Δv or adds up the TIG (Mission Control's job, as in Apollo);
  the Δv cutoff left 3.8 m/s at 38 m/s² (0.4 %, inside the ΔV RESID allowance).
- **SAS that does not take its mode.** In repeated flights SAS sometimes stayed in stability after being switched on
  (KSP resets the mode then), and a mode sent while SAS was off was refused. The gateway now keeps the mode the
  cockpit asked for, applies it when SAS comes on, and sets it again 0.5 s and 1.5 s after either. With it the ascent
  rehearsal reached 80.3 × 79.8 km (e 0.0004), the apoapsis cutoff overshooting by 0.5 km instead of 1.7.
- **Cross-pointer wrong while the ship turns** (PRO, RETRO, DRIFT, and `tlm/flight` v_right, v_fwd, v_down). The
  surface velocity was measured in a kRPC hybrid frame with the vessel's axes, which by default also takes the
  vessel's angular velocity: a turning ship picked up its turn rate times the distance to the planet's centre (3 300
  m/s read for 551). The dot then showed the ship 60° off retrograde while it was exactly on it, which looked like a
  SAS that would not turn. Both hybrid frames now take their motion from the planet's frame; checked against kRPC
  while yawing and pitching.
- **The landing test burns only when aligned.** A braking burn started 64° off retrograde swung the velocity, SAS
  chased the moving marker and the tank emptied: the lander crashed. The test now refuses to light the engine unless
  the cross-pointer shows NULL, and cuts the burn on a Δv budget or when the attitude wanders.
- **Hand controllers on the bus** (`panel/hc/in/*` → `cmd/rotate`, `cmd/translate`): what the USB joysticks will
  publish. SAS is released while the rotation stick is off centre: through kRPC, KSP does not do it by itself, and
  SAS fought the stick (half stick took 22 s to tip the rocket 3°). The ascent rehearsal now kicks on the stick
  instead of kRPC's autopilot and reached 82.6 × 74.1 km.
- **RCS FINE** switch on ENG: both sticks command 30 % of their throw, for docking.
- **CUTOFF lamp blinks** while the cutoff holds and the throttle lever is still up: the engine restarts only once the
  lever has been back to idle, and nothing said so.
- **NO LINK explained:** the one seen in the coast came from the first rehearsal, before refused commands stopped
  dropping the link. Every gap logged since is a save load (2 to 4 s).
- **BRAKE lamp margins** raised to 1.6 (on) and 1.3 (blinking) times the predicted braking height: a landing used 7 %
  more height than predicted (651 m for 608) and stopped 4 m above the ground.

## 2026-11-16 — engine matrix through staging, COM panel, experimental LAB tab, camera monitor

Checked by 53 unit tests, 76 checks on the mock plant and, in KSP, the three earlier scripts plus a new one that
launches an asparagus rocket through two booster stagings.

- **Engine status after staging.** With several engines, flamed-out engines stayed red and ENG FAIL came on after
  they were staged away. Two causes, both fixed:
  - The stage number (`tlm/vessel`, 10 Hz) reaches the cockpit before the new engine list (`tlm/engines`, 2 Hz). For
    that moment the dropped engines were remembered as burning in the new stage, then found missing: "lost".
    `tlm/engines` now carries the stage number its list was read in, and the cockpit uses that one.
  - An engine that ran dry in an earlier stage and stays attached while later engines burn is spent, not failed: it
    leaves the matrix and raises nothing. When every lit engine is dry, they all stay red: that is the cue to stage.
  - `tests/e2e_ksp_boosters.py` flies it in KSP; it fails on the old logic with exactly the reported symptom.
- **COM panel** (`protocol/panels/com.json`): AOS and LOS lamps, signal strength, first station or relay and hops,
  time in the present state, ANTENNA DEPLOY. New `tlm/comm` and `cmd/antenna`.
- **LAB tab** (`protocol/panels/lab.json`), experimental panels:
  - Cross-pointer: one LED matrix and a selector showing the angle to the burn direction, to retrograde or
    prograde, or to face the target port; the port's offset; or the lander's drift. Needs the surface velocity in the
    vessel's own axes (`tlm/flight` v_right, v_fwd, v_down) and the node's yaw and pitch (`tlm/node`).
  - Landing: time to the ground, height needed to brake at full thrust, BRAKE lamp.
  - Navigation: body, latitude, longitude, inclination. With the landing plate, this covers what only the DSKY
    showed (N43 and N60).
  - Action groups 1 to 10 with their state (`tlm/groups`, `cmd/action_group`).
  - Camera selector for the monitor.
- **Camera monitor** (`panels/virtual/cam.html`): shows one camera of the Kerbcast mod over WebRTC, chosen from the
  LAB panel. The page is the camera node on the bus (`cam/list`, `cam/status`); the cockpit publishes `cam/select`.

## 2026-11-16 — code restructured for reading, gateway made lighter on KSP

No change to what the cockpit does. Checked by 43 unit tests, 65 checks on the mock plant and 98 checks in KSP
(85 general, 8 docking, 5 undocking).

- **Cockpit logic is a package.** `logic.py` (731 lines), `computer.py` and `fmt.py` become `cockpit-logic/cockpit/`:
  - `core.py`: the `Cockpit` class, which receives bus messages and returns the messages to publish.
  - `settings.py`: every threshold and table, with its unit in the name, including what ABORT does in each mode.
  - `panels/`: one module per panel (engine, systems, rendezvous, computer), each with its inputs and its outputs.
  - `burn_computer.py`, `alarms.py`, `engines.py`, `event_timer.py`, `node_mirror.py`, `messages.py`, `display_format.py`.
  - `dsky.py` moves in unchanged: it is due to be dropped.
- **KSP gateway is a main loop plus a package.** `gateway.py` keeps the loop; `ksp/` holds the streams, the link to the
  active vessel, the part-by-part watch, the target and docking geometry, and the commands.
- **Mock plant** split into `vehicle.py` (planet and launcher constants), `simulation.py` (the model) and `plant.py`
  (the service).
- **Virtual panel** split into three ES modules: `panel.js` (page and bus), `widgets.js` (one builder per item type)
  and `seven_segment.js`.
- **Names:** abbreviations replaced by full words throughout (`tlm` → `telemetry`, `dv_acc` → `delta_v_counted`,
  `tfi` → `time_from_ignition`). Each module starts with what it is for.
- **Protocol:** every 7-segment and alphanumeric payload now carries `blink` (before, only some did).
- **Gateway performance.** KSP computed all 73 telemetry streams on every game update: about 4 ms each time on a
  16-part vessel. Now 1.2 ms:
  - Every stream has a rate. The five the burn computer counts with (universal time, mission time, mass, thrust,
    throttle) stay at every update; what is published at 10 Hz runs at 20 Hz; the rest at 4 Hz. Vessel-wide resource
    amounts were the dearest (0.5 ms each) and are among the slow ones.
  - Surface velocity comes from one stream in a frame with the horizon's axes, in place of two calls to the game on
    every cycle. Same values.
  - Target telemetry reads what hardly changes (frames, target name, control point) on the slow cycle only, or when
    the target changes.
  - Telemetry cycles start on a fixed beat: 10.0 Hz measured, against 9.2 Hz before.
  - Burn cutoff is as precise as before: 5.06 m/s delivered for a 5 m/s PAD.
- **Virtual panel performance:** a page subscribes to telemetry and commands only while its bus sniffer is open.
- **Measured and left alone:** the cockpit logic takes 0.14 ms per bus message (under 1 % of a core); the bus carries
  50 messages and 7.5 kB per second.
- **README:** new "Where the code is" table.

## 2026-11-15 — KSP interface and virtual cockpit

The first working system: KSP 1.12.5 flown from panels in a browser, over MQTT.

- **Architecture.** One Mosquitto broker, one writer per topic. Panels are dumb I/O nodes drawn from
  `protocol/panels/<id>.json`; all the rules are in the cockpit logic; the gateway is the only process that talks to
  KSP (kRPC 0.7.0). A mock plant writes the same topics as the gateway, so the cockpit can be tested without the game.
  Only one of the two may run.
- **Panels:**
  - ENG: throttle, ENG ARM and STAGE ARM guards, STAGE, CUTOFF, thrust limiter, gimbal lock, SAS modes, ABORT with a
    mode selector (pad, ascent, orbit, descent), a 20-legend caution and warning annunciator with master buttons,
    lamp test and tone, CONTACT and 0.05 G lights.
  - Engine status without glass: an LED matrix lays the engines out as seen from behind, green burning, amber
    starved, red lost, with a count of those burning.
  - SYS: electrical and propellant displays, event timer (stopwatch and preset countdown), warp, WARP TO EVT, pause,
    quick save and load.
  - CMP, the burn computer: a PAD is TIG plus Δv prograde, normal and radial. It can be typed in or uplinked
    (`pad/uplink`, waiting for ACCEPT). BURN ARM zeroes the Δv counter and the computer cuts the throttle when the
    PAD's Δv is reached. The PAD is mirrored to a KSP maneuver node at TIG plus half the burn time, and a node made in
    the game is loaded as the PAD.
  - RDV: target selection, range, closing speed and line-of-sight rate, then the docking figures in the pilot's own
    axes (where the port is, how fast it drifts, yaw, pitch and roll errors), CTRL FROM PORT, DOCKED lamp and UNDOCK
    behind UNDOCK ARM.
  - FDAI and MFD glass pages, and a DSKY.
- **Rules worth knowing:**
  - The panel wins: SAS, RCS and lights are commanded again once a second when the game disagrees with the switch.
  - Controls that set something the craft's builder may have set (thrust limiter, gimbal, pause, control point) act
    only when moved, not on their first reported position.
  - A cutoff holds the throttle at zero until the lever is back under 5 %.
  - NO LINK when the telemetry is older than 2 s.
  - Only a port-to-port docking lights DOCKED: a port with a part stacked on it in the VAB also reports "docked".
- **Tests:** unit tests of the logic, `tests/e2e_mock.py` on the mock plant, and three scripts that fly in KSP
  (`e2e_ksp.py`, `e2e_ksp_docking.py`, `e2e_ksp_undock.py`); the docking one checks every sign by firing RCS and
  watching the figures move.
- **Docs:** `README.md`, `PANELS.md` (panel design; the layout decision is a centre console flyable from either
  seat, with glass kept to a minimum), `protocol/topics.md`.

## 2026-11-14 — initial import

`PLAN.md` (the project plan) and `SELFTEST.md` (flying KSP by script to learn what the cockpit needs).
