# Spaceship: capsule simulator for KSP

Plan and ideas: [PLAN.md](PLAN.md). Agent self-test of the Moonshot course in KSP: [SELFTEST.md](SELFTEST.md), results in
[selftest/](selftest/) (status, gaps, interface needs).

## Prototype: the cockpit bus

```sh
docker compose up -d --build                  # broker + cockpit logic + mock plant + virtual panel
open http://localhost:8650                    # the virtual panel
docker compose stop plant-mock && docker compose --profile ksp up -d gateway-ksp   # KSP instead of the mock
```

The mock and the gateway both write `tlm/*` and every topic has one writer, so stop one before starting the other.

| Service | What it does | Code |
|---|---|---|
| `broker` | Mosquitto 2: MQTT on 1883, WebSockets on 9001 (for browser panels) | [broker/](broker/) |
| `cockpit` | Cockpit logic: interlocks, lamp test, caution & warning, displays, game/panel disagreement. Pure core + MQTT shell | [cockpit-logic/](cockpit-logic/) |
| `plant-mock` | Publishes `tlm/*` from its own simple physics, obeys `cmd/*`; failures for the instructor | [plant-mock/](plant-mock/) |
| `gateway-ksp` | The only process that talks to KSP: kRPC → `tlm/*`, `cmd/*` → kRPC (profile `ksp`, host network) | [gateway-ksp/](gateway-ksp/) |
| `panel` | nginx serving the virtual console and the glass and station pages; the console is drawn from `protocol/panels/` | [panels/virtual/](panels/virtual/) |

Topics, payloads and rules: [protocol/topics.md](protocol/topics.md).

### The virtual console
Every I/O module of the capsule, at its physical size and laid out as in the capsule: zones (overhead, main)
of modules, each module one board carrying panels of W×H U (1 U = 100 mm) with their controls at fixed places
([protocol/panels/README.md](protocol/panels/README.md)). Nothing reflows; only the zoom changes. It works like a map:
the wheel zooms around the pointer, dragging pans, and every control works at any zoom, so several modules can be
used at once; double-click a module to fit it, Esc (or the zoom percentage) fits the whole console, and
`index.html#cmp` opens fitted on one module. The **grid** checkbox draws 10 mm squares; misplaced controls are outlined in red.

Each module is a dumb I/O node like its future ESP32: it publishes raw inputs (`panel/eng/in/<control>`, retained for
switches), draws what the cockpit logic sends (`panel/eng/out/<output>`) and its heartbeat. Controls: guarded toggles (click the red guard to open
it; closing it pushes the switch off), toggles with their indicator LED, lit push buttons, a throttle lever, rotary
selectors (click / shift-click / wheel), 7-segment displays, LED bar graphs, an annunciator matrix, a tone.
Keys: Space = STAGE (when armed), ↑/↓ = throttle, T = lamp test, Left Alt (held) = every module's name and boundary. The **bus** checkbox shows a live sniffer. Resetting
the simulation and injecting failures are on the SIMSUP page.

**Modules** (on the CONSOLE page): ENG (C&W, engine and staging, ascent and descent displays, propellant, radio link, abort), SYS (time warp, lights and fan, event timer, save), RES (electrical, life support), AUX (camera, action groups), LND (landing aid), RNT (reentry and recovery), SCI (science), CMP (burn
computer), RDV (target and docking), SOLO (PAD requests, the orbit and navigation), and the glass modules FDAI (attitude) and CAM
(camera monitor), drawn as screens with the live page in them. FDAI and CAM are also pages of their own (for a
Pi's kiosk browser), next to SIMSUP and MCC in the top bar. The modules are drawn from `protocol/panels/<id>.json`; their rules live in `cockpit-logic/`.

**SYS** (I/O modules on the `sys` bus: SYS overhead; RES in MAIN's right column with ELECTRICAL and LIFE SUPPORT; PROPELLANT on the ENG module): electrical (charge bar, EC and EC/s, solar panels, fuel cells), propellant for the
whole vessel (fuel, oxidizer, monoprop and xenon bars) with BURN TIME (the stage's propellant at the present thrust, or at full thrust) and RCS ΔV (an estimate, from the stock thrusters' 240 s), life support (TAC Life Support: food, water and oxygen bars, the hours each lasts for the crew aboard, recyclers not counted, and CREW; LS LOW and LS OUT on the annunciator), event timer (manual,
or counting down to TIG / apoapsis / periapsis / SOI change; with COUNT DOWN on, the manual timer counts down from a
value set with MIN + and SEC +10 and blinks at zero), time warp (slower / faster / stop, and WARP TO EVT: warp until 60 to 80 s before the
event the timer's source selects; pause), save (QUICK SAVE, QUICK LOAD, and REVERT TO LAUNCH behind the guarded REVERT ARM), lights and fan (FAN does nothing in the virtual cockpit; CABIN and BACKLIGHT light the cockpit itself
through `cockpit/lighting`: on the console page the plates brighten and the legends glow; EXTERNAL is the craft's
lights).

**LANDING AID** (module in MAIN, on the `eng` bus): DRIFT right and up across the craft's axis (for a lander on its tail, which way it slides), and four green lamps below 1000 m: SINK OK (under 2 m/s + 10 % of the radar altitude), DRIFT OK (1 m/s), UPRIGHT (within 10°), GEAR DOWN; CONTACT under them.

**REENTRY · RECOVERY** (module in MAIN, on the `sys` bus): CHUTE ARM, CHUTE, BRAKES, ablator, the hottest part as a percentage of its limit, time to the atmosphere at the present sink rate, outside temperature and pressure, the 0.05 G light, and KSP's verdict on opening the chutes (SAFE, RISKY, UNSAFE). **SCIENCE** (module in MAIN, `sci` bus): step through the experiments; RUN, SEND, DUMP, RESET the one shown, RUN ALL, with its state, biome and science value.

**ENG** (I/O module): CAUTION & WARNING (the MET is on the camera monitor's panel); ASCENT · DESCENT (altitude in m, above the sea or the ground by ALT REF; horizontal, vertical and total speed against the orbit or the surface by the SPEED REF knob, TGT reading the surface; g, dynamic pressure in kPa, TIME TO IMPACT: the height over the sink rate, dashes when climbing or on an orbit that stays above the surface; HOVER TIME: the seconds the stage can hold the craft still, its Δv over the local gravity, dashes when the engines cannot lift it; GEAR); ENGINE (ENG ARM, throttle,
STAGE ARM and STAGE, the stage number, CUTOFF, THRUST LIMIT knob, GIMBAL LOCK, stage fuel, stage Δv from the rocket
equation, for the engines the next staging lights before ignition, and the current TWR: the thrust now against the local gravity, 0 with the engines off); an engine status matrix (9 × 9 LEDs, one per engine, laid out as the engines sit across the vessel:
green = thrust, white = lit but idle or next to ignite, amber = has fuel but under half the thrust commanded, red =
flamed out or gone; engines staged away leave the matrix, and so does an engine that ran dry in an earlier stage and
is still attached) with a count of burning engines; CUTOFF (throttle to 0, held until the lever is back at idle; the lamp blinks while the lever is still up);
ABORT behind ABORT ARM fires KSP's abort group, and only that (what the craft's builder wired to it); two event
lights in the C&W grid, 0.05 G (drag is felt with the engine off while descending: the entry has begun) and CONTACT
(landed, or a leg or wheel touches the ground). The attitude switches are under the FDAI ball (below), still on the
`eng` bus.

**Hand controllers** (`hc`, no page yet): the USB joysticks will publish `panel/hc/in/rot_pitch`, `rot_yaw`,
`rot_roll`, `trans_right`, `trans_up` and `trans_fwd` (−1 to 1); tests publish them today. The cockpit passes them on
as `cmd/rotate` and `cmd/translate`, and releases SAS while the rotation stick is off centre (KSP does that for the
keyboard, not for inputs through kRPC), putting it back in the panel's mode when the stick is centred. RCS FINE (ENG, amber LED) scales
both sticks to 30 % for docking (KSP's own precision mode cannot be reached through kRPC). The mock plant ignores
them.

**CMP** (I/O panel, burn computer): one PAD, one display per field (TIG, Δv prograde / normal / radial). Press a field's
button, key the value (TIG as hhmmss, Δv in m/s; keyboard: digits, `.`, `-`, Enter, Backspace), ENTER stores it and
moves to the next field (a selected field keeps showing its value until the first key, then what is keyed and a cursor). A maneuver node made or moved in the game's map view is
loaded as the PAD (TIG = node time − half the burn time), and ATT ERR shows the angle to the burn attitude. A PAD read up by Mission Control (`pad/uplink`) blinks on the displays until UPLINK ACCEPT (CLR
rejects it). The computer shows time to TIG, Δv to go and the burn time at full thrust, and mirrors the PAD to KSP as a
maneuver node at TIG + half the burn time so that SAS MODE MNVR holds the burn attitude. BURN ARM zeroes the Δv counter;
from then on thrust / mass is counted and the throttle is cut when the PAD's Δv is reached (CUTOFF lamp, residual on
ΔV TO GO), until the lever is back at idle. The counter runs on telemetry (about 7 Hz with KSP), so the cutoff is as
fine as about 0.1 s of thrust: fly small burns on a low THRUST LIMIT (measured in KSP: 5 m/s asked, 4.65 delivered at
4.2 m/s²; 7.5 delivered at 41.6 m/s²).

**RDV** (I/O module): TARGET: target name on an alphanumeric display, ◂ TGT / TGT ▸ (vessels around the same body,
nearest first), PORT ▸ (the target's free docking ports), CLEAR, CTRL FROM PORT. With a port targeted (PORT LED),
ROTATION and TRANSLATION, in the pilot's own axes so no roll is needed to read them: yaw, pitch and roll to face the
port squarely (roll against the port's own "up"), each with its rate in °/s; where the port is, LATERAL (+ right) and
VERTICAL (+ up), and the RANGE along its axis, each with its rate (the range rate is negative while closing, as in
docking procedures). DOCKING: range and closing speed to the target vessel (KM LED from
100 km), CAPTURE inside the capture envelope, DOCKED, and UNDOCK behind a guarded UNDOCK ARM. The
CLOSING caution still watches the course's ρ/400 s braking gate. Signs checked in KSP by `tests/e2e_ksp_docking.py`.

**COM** (the LINK · ANTENNA panel, on the ENG module, on the `com` bus): the radio link to the ground. AOS and LOS lamps (acquisition and loss of signal; the one that
just came on blinks for 10 s), signal strength bar, the first station or relay on the way and the number of hops, how
long the link has been in its present state, and ANTENNA DEPLOY (acts only when moved, so a restart cannot retract
the antennas).

**The `lab` bus** (no module of its own any more): panels first tried as experiments, now placed on other modules.
- NAVIGATION (on the SOLO module): body orbited, latitude, longitude.
- ORBIT (on the SOLO module, on the `lab` bus, 2 U wide): apoapsis and periapsis in km, the time to each, inclination.
- ACTION GROUPS (on the AUX module in MAIN, on the `lab` bus): the craft's ten custom groups, each button lit while its group is on.
- CAMERA (on the AUX module in MAIN, on the `lab` bus): CAM ◂ ▸ pick the camera shown on the monitor, with its name and number, and a LIVE LED.

**CAM** (glass panel, http://localhost:8650/cam.html): a monitor for the craft's cameras, fed by the
Kerbcast mod's WebRTC streams (hull cameras, docking port cameras, kerbals' helmets, the
launch pad camera). It shows the camera the CAMERA panel selects (`cam/select`) and publishes what it can show
(`cam/list`). Kerbcast listens on the KSP machine only, unless its `BindAddress` setting is changed
(`cam.html?kerbcast=http://host:8088`).

**SOLO** (I/O module, `index.html#solo`): for a pilot flying without Mission Control. CIRC, PLANE, RDV TGT and INJECT
(knob: Mun or Minmus) ask the flight-dynamics service for a PAD, which it reads up to the burn computer as CAPCOM
would; the display says what it sent or why not. The ORBIT panel sits next to it. How it works: [flight-dynamics/README.md](flight-dynamics/README.md).

**MCC** (Mission Control, http://localhost:8650/mcc.html): one tab per flight controller (FLIGHT, FIDO, RETRO,
GUIDO, BOOSTER, EECOM, CAPCOM), meant for one laptop per controller on the same network. A go/no-go poll run by
FLIGHT, a text loop, and CAPCOM reads up PADs to the burn computer when the link is up. MCC does not see injected
failures. How it works: [panels/virtual/mcc/README.md](panels/virtual/mcc/README.md).

**SIMSUP** (instructor station, http://localhost:8650/simsup.html): starts scenarios (a save plus failures),
injects failures now or arms them on mission time, altitude or stage, freezes the game, and logs the session for a
debrief with the crew's response times. Vehicle failures act in KSP through the gateway (engines, gimbals, RCS,
reaction wheels, parachutes, comms, telemetry); instrument failures in the cockpit (false alarm, dark panel, frozen
display, stuck switch). How it works: [simsup/README.md](simsup/README.md).

**FDAI** (glass module, 2 × 2 U, its panel ATTITUDE: the ball on a 4" round screen, pitch, heading and roll with their
rates on 7-segment displays beside it, the FDAI controls in the corners around it (MARKERS top left, NEEDLES and ERROR
SCALE at the bottom), and under them SAS, SAS MODE with TGT, A-TGT and MNVR,
SPEED REF (the navball's speed reference, which SAS PRO and RETRO follow: orbit, surface or target; it acts only when
turned, and its LED blinks while the game's reference is another one, since KSP changes it by itself), RCS, RCS FINE.
The page alone: http://localhost:8650/fdai.html, also linked from the panel's top bar): an attitude ball drawn
from `tlm/attitude` (pitch, heading, roll against the local horizon), with a roll index, prograde and retrograde markers,
three fly-to error needles (to prograde or retrograde, ±5° or ±50° full scale), three rate scales and a NO ATT flag when
the telemetry is older than 2 s. What the needles show (prograde, retrograde, off), their scale (±5° or ±50°) and the
markers are set by the FDAI controls on the ATTITUDE panel, never on the glass (`panel/eng/out/fdai`). The screen view
(`?embed=1`) shows only the ball and its roll ring; the page alone in a browser keeps its readouts and rate scales. `fdai.html?demo=1` runs without a broker.

To fly the mock: open the ENG ARM guard and arm, push the throttle, open STAGE ARM and arm, press STAGE.

### Where the code is
| Part | Files |
|---|---|
| Cockpit logic | [cockpit-logic/cockpit/](cockpit-logic/cockpit/): `core.py` (the `Cockpit` class: messages in, outputs out), `settings.py` (every threshold and table), `alarms.py` (caution and warning), `burn_computer.py`, `node_mirror.py` (PAD ↔ KSP maneuver node), `engines.py` (engine status matrix), `event_timer.py`, `panels/` (one module per panel: its inputs and its outputs), `messages.py` and `display_format.py` (payloads and number formats). [service.py](cockpit-logic/service.py) is the MQTT shell. |
| KSP gateway | [gateway-ksp/gateway.py](gateway-ksp/gateway.py) (main loop) and [gateway-ksp/ksp/](gateway-ksp/ksp/): `vessel_link.py` (kRPC connection, streams, telemetry payloads), `parts_watch.py` (engines, stage propellant, heat, ground contact, docking ports), `target.py` (rendezvous and docking geometry, target selection, undocking), `commands.py` (`cmd/*` → kRPC), `streams.py`. |
| Flight dynamics | [flight-dynamics/](flight-dynamics/): `orbits.py` (two-body orbits), `planner.py` (the four PADs), `service.py`. [README](flight-dynamics/README.md). |
| Mission Control | [panels/virtual/mcc/](panels/virtual/mcc/): `mcc.js` (tabs, poll, loop), `bus.js`, `roster.js`, one module per console in `consoles/`. Architecture: [mcc/README.md](panels/virtual/mcc/README.md). |
| SimSup | [simsup/](simsup/): `simsup_core.py` (the logic), `service.py`, `scenarios.json`; the page is `panels/virtual/simsup.*`. Architecture: [simsup/README.md](simsup/README.md). |
| Laser-cut faceplates | [panels/cut/](panels/cut/): `make_templates.py` (SVG templates for LightBurn from `protocol/panels/`, with layout checks), `footprints.json` (each component's cutout and size, placeholders until the parts are in hand). [README](panels/cut/README.md). |
| Mock plant | [plant-mock/](plant-mock/): `simulation.py` (the model), `vehicle.py` (planet and launcher constants), `plant.py` (the service). |
| Virtual panel | [panels/virtual/](panels/virtual/): `shell.js` (every page's top bar and navigation, from one list of pages), `bus.js` (every page's bus connection), `panel.js` (the console: zones, modules and panels at their physical size, overview and module view, one bus connection per module, layout checks, keyboard), `widgets.js` (one builder per item type), `seven_segment.js`; `cam.js` (camera monitor), `fdai.js`, `simsup.js`, `mcc/`. A new page: its HTML header holds only its own status items, it loads `shell.js`, and it gets one line in `PAGES` in `shell.js`. |

### Rules the cockpit logic implements
- ENG ARM gates the throttle; STAGE needs STAGE ARM (and an edge, holding does not stage twice); ABORT needs ABORT ARM.
- No power (the craft's electric charge is gone; or `cb_main` off, an input kept for a breaker that may come back):
  every lamp, display and cockpit light dark, throttle commanded to 0, sticks released, inputs ignored
  (`cockpit/power`).
- LAMP TEST: every lamp on, displays show 8.8.8.
- Caution & warning, cautions (amber, MASTER CAUTION): LOW FUEL, LOW POWER, HIGH Q, SAS DISAGREE, FLAMEOUT, RCS LOW,
  CLOSING (above the braking gate), THROTTLE (lever up with ENG ARM off), ATT ERR (over 5° off the burn attitude from
  30 s before TIG), ΔV RESID (after cutoff, over 0.5 m/s or 2 %), CHUTE (descending under 15 km, parachute neither armed nor
  out), COMM LOST, LS LOW (food, water or oxygen under 10 %, with a crew aboard). Warnings (red, MASTER ALARM blinking + tone): HIGH G, NO LINK, ENG FAIL, SINK RATE, OVERHEAT (a part
  over 80 % of its temperature limit), GEAR UP (under 300 m, descending, gear up), LS OUT (one of them empty, with a crew aboard). Pressing the master button acknowledges: the master lamp and tone go
  off, the annunciator stays lit (steady) while the condition lasts; a condition that clears and returns needs a new ack.
- KSP is the authority: indicator LEDs show the game's state and blink when it disagrees with the switch; SAS, RCS and
  external lights are re-commanded once a second while they disagree (panel wins); gear, solar panels and fuel
  cells are not (game wins).
  The SAS mode last selected is sent again, up to five times, when the game shows another one (KSP falls back to
  stability when SAS is switched on).
- NO LINK when telemetry is older than 2 s or the plant reports disconnected; displays then show dashes.

### Tests
```sh
.venv/bin/python -m pytest -q cockpit-logic/tests     # unit tests of the pure logic, the panels and the burn computer (65)
.venv/bin/python tests/e2e_mock.py                    # end to end on the running stack with the mock (76 checks; `MQTT_PORT` selects another broker)
.venv/bin/python tests/e2e_ksp.py                     # end to end with KSP and gateway-ksp (85 checks; loads a save in orbit)
.venv/bin/python tests/e2e_ksp_docking.py --save lor3-rdv-handover   # docking display signs in KSP (8 checks)
.venv/bin/python tests/e2e_ksp_undock.py --save lor3-rdv-docked       # UNDOCK from the panel in KSP (5 checks)
.venv/bin/python -m pytest -q simsup/tests             # SimSup logic (9)
.venv/bin/python -m pytest -q flight-dynamics/tests    # the PAD sums (8)
.venv/bin/python tests/e2e_ksp_solo.py [circ] [plane] [rdv] [inject]   # each SOLO PAD flown in KSP and its outcome checked
.venv/bin/python tests/e2e_ksp_simsup.py --save lor3-selftest-pad    # every SimSup failure, freeze and load in KSP (25 checks)
.venv/bin/python tests/rehearsal_ksp_ascent.py --save lor3-selftest-pad   # pad to orbit from the panels and the stick topics; prints gaps and alarms
.venv/bin/python tests/e2e_ksp_boosters.py --save lor3-selftest-pad   # engine matrix through booster flameouts and staging (9 checks; launches)
.venv/bin/python tests/e2e_ksp_landing.py --save lor3-selftest-pdi    # a Mun landing on the ASCENT · DESCENT figures
```
(`.venv`: `python3 -m venv .venv && .venv/bin/pip install pytest paho-mqtt==2.1.0 krpc==0.7.0`.)
