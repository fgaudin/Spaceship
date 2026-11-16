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
| `panel` | nginx serving the virtual panel; the panel is drawn from `protocol/panels/eng.json` | [panels/virtual/](panels/virtual/) |

Topics, payloads and rules: [protocol/topics.md](protocol/topics.md).

### The virtual panel
A dumb I/O node like the future ESP32 panels: it publishes raw inputs (`panel/eng/in/<control>`, retained for switches)
and draws what the cockpit logic sends (`panel/eng/out/<output>`). Controls: guarded toggles (click the red guard to open
it; closing it pushes the switch off), toggles with their indicator LED, lit push buttons, a throttle lever, rotary
selectors (click / shift-click / wheel), 7-segment displays, LED bar graphs, an annunciator matrix, a tone.
Keys: Space = STAGE (when armed), ↑/↓ = throttle, T = lamp test. The **bus** checkbox shows a live sniffer. The bench
strip (instructor) resets the mock and injects failures (engine out, battery short, telemetry freeze).

**Panels** (top bar links): ENG (propulsion, staging, abort, SAS/RCS, C&W), SYS (`?panel=sys`), CMP (`?panel=cmp`, burn
computer), RDV (`?panel=rdv`, rendezvous and docking), DSKY (`?panel=dsky`), FDAI and MFD. The I/O panels are drawn from `protocol/panels/<id>.json`; their rules live in `cockpit-logic/`.

**SYS** (I/O panel): electrical (charge bar, EC and EC/s, solar panels, DSKY breaker), propellant for the current stage
(fuel, oxidizer, monoprop bars; stage Δv from the rocket equation, TWR against the local gravity), event timer (manual,
or counting down to TIG / apoapsis / periapsis / SOI change; with COUNT DOWN on, the manual timer counts down from a
value set with MIN + and SEC +10 and blinks at zero), chute arm + deploy, brakes, time warp (slower / faster / stop, and
WARP TO EVT: warp until 60 to 80 s before the event the timer's source selects), game (pause; quick save and quick load
behind SAVE ARM).

**ENG additions**: an engine status matrix (9 × 9 LEDs, one per engine, laid out as the engines sit across the vessel:
green = thrust, white = lit but idle or next to ignite, amber = has fuel but under half the thrust commanded, red =
flamed out or gone) with a count of burning engines; CUTOFF (throttle to 0, held until the lever is back at idle);
THRUST LIMIT knob and GIMBAL LOCK; two event lights, 0.05 G (drag is felt with the engine off while descending: the
entry has begun) and CONTACT (landed, or a leg or wheel touches the ground); ABORT MODE selector (what ABORT does: `ABORT_SEQUENCES`
in [cockpit-logic/cockpit/settings.py](cockpit-logic/cockpit/settings.py)); SAS modes TGT, A-TGT and MNVR.

**CMP** (I/O panel, burn computer): one PAD, one display per field (TIG, Δv prograde / normal / radial). Press a field's
button, key the value (TIG as hhmmss, Δv in m/s; keyboard: digits, `.`, `-`, Enter, Backspace), ENTER stores it and
moves to the next field (the field being keyed shows a cursor). A maneuver node made or moved in the game's map view is
loaded as the PAD (TIG = node time − half the burn time), and ATT ERR shows the angle to the burn attitude. A PAD read up by Mission Control (`pad/uplink`) blinks on the displays until UPLINK ACCEPT (CLR
rejects it). The computer shows time to TIG, Δv to go and the burn time at full thrust, and mirrors the PAD to KSP as a
maneuver node at TIG + half the burn time so that SAS MODE MNVR holds the burn attitude. BURN ARM zeroes the Δv counter;
from then on thrust / mass is counted and the throttle is cut when the PAD's Δv is reached (CUTOFF lamp, residual on
ΔV TO GO), until the lever is back at idle. The counter runs on telemetry (about 7 Hz with KSP), so the cutoff is as
fine as about 0.1 s of thrust: fly small burns on a low THRUST LIMIT (measured in KSP: 5 m/s asked, 4.65 delivered at
4.2 m/s²; 7.5 delivered at 41.6 m/s²).

**RDV** (I/O panel): target name on an alphanumeric display, ◂ TGT / TGT ▸ (vessels around the same body, nearest
first), PORT ▸ (the target's free docking ports), CLEAR, CTRL FROM PORT; a DOCKED lamp and UNDOCK behind a guarded UNDOCK ARM. Range, closing speed and line-of-sight rate
against the course's ρ/400 s braking gate (OVERSPEED lamp, CLOSING caution). With a port targeted (PORT LED), three
plates in the order of the manoeuvre, all in the pilot's own axes so no roll is needed to read them: 1 yaw and pitch
to face the port squarely (ALIGNED under 2°; roll is shown against the port's own "up"), 2 where the port is, right and
up, each with its rate, 3 distance and closing speed, CAPTURE inside the capture envelope. Signs checked in KSP by
`tests/e2e_ksp_docking.py`.

**DSKY** (I/O panel): Apollo-style verb/noun keyboard (keys or V, N, digits, +, −, Enter, Backspace = CLR, P = PRO,
R = RSET, K = KEY REL). V16 N62 monitors speed / V/S / altitude, V16 N36 the MET, V82 the orbit (N44). V37 E 30 E: P30
loads a PAD (flashing V06 N33 TIG, then V06 N81 Δv; V25 E to key the values, PRO to accept). V37 E 40 E: P40 shows
time from ignition / Δv to go / Δv counted, asks for engine enable (flashing V99) at TIG − 5 s and, when the PAD's Δv
has been counted, cuts the throttle (VEL lamp) until the throttle lever is brought back to idle. Mission Control can
send a PAD on `dsky/uplink` (UPLINK ACTY).

**MFD** (glass panel, http://localhost:8650/mfd.html): ORBIT (orbit drawing and apsides), ASCENT (altitude, V/S,
speed and apoapsis tapes, q and g), LANDING (drift cross-pointer in the heading frame, radar altitude, time to impact,
TWR), DOCKING (range, closing speed and line-of-sight rate against the course's ρ/400 s braking gate; port alignment
and capture envelope when a docking port is targeted). `mfd.html?demo=1` runs without a broker.

**FDAI** (glass panel, http://localhost:8650/fdai.html, also linked from the panel's top bar): an attitude ball drawn
from `tlm/attitude` (pitch, heading, roll against the local horizon), with a roll index, prograde and retrograde markers,
three fly-to error needles (to prograde or retrograde, ±5° or ±50° full scale), three rate scales and a NO ATT flag when
the telemetry is older than 2 s. Bezel keys N, S, R, M. `fdai.html?demo=1` runs without a broker.

To fly the mock: CB MAIN BUS on, open the ENG ARM guard and arm, push the throttle, open STAGE ARM and arm, press STAGE.

### Where the code is
| Part | Files |
|---|---|
| Cockpit logic | [cockpit-logic/cockpit/](cockpit-logic/cockpit/): `core.py` (the `Cockpit` class: messages in, outputs out), `settings.py` (every threshold and table), `alarms.py` (caution and warning), `burn_computer.py`, `node_mirror.py` (PAD ↔ KSP maneuver node), `engines.py` (engine status matrix), `event_timer.py`, `panels/` (one module per panel: its inputs and its outputs), `messages.py` and `display_format.py` (payloads and number formats). [service.py](cockpit-logic/service.py) is the MQTT shell. |
| KSP gateway | [gateway-ksp/gateway.py](gateway-ksp/gateway.py) (main loop) and [gateway-ksp/ksp/](gateway-ksp/ksp/): `vessel_link.py` (kRPC connection, streams, telemetry payloads), `parts_watch.py` (engines, stage propellant, heat, ground contact, docking ports), `target.py` (rendezvous and docking geometry, target selection, undocking), `commands.py` (`cmd/*` → kRPC), `streams.py`. |
| Mock plant | [plant-mock/](plant-mock/): `simulation.py` (the model), `vehicle.py` (planet and launcher constants), `plant.py` (the service). |
| Virtual panel | [panels/virtual/](panels/virtual/): `panel.js` (page, bus, keyboard), `widgets.js` (one builder per item type), `seven_segment.js`. |

### Rules the cockpit logic implements
- ENG ARM gates the throttle; STAGE needs STAGE ARM (and an edge, holding does not stage twice); ABORT needs ABORT ARM.
- CB MAIN BUS off: every lamp and display dark, throttle commanded to 0, inputs ignored.
- LAMP TEST: every lamp on, displays show 8.8.8.
- Caution & warning, cautions (amber, MASTER CAUTION): LOW FUEL, LOW POWER, HIGH Q, SAS DISAGREE, FLAMEOUT, RCS LOW,
  CLOSING (above the braking gate), THROTTLE (lever up with ENG ARM off), ATT ERR (over 5° off the burn attitude from
  30 s before TIG), ΔV RESID (after cutoff, over 0.5 m/s or 2 %), PERI LOW (in orbit with the periapsis in the
  atmosphere or the terrain), SOI CHANGE (within 2 min), CHUTE (descending under 15 km, parachute neither armed nor
  out), COMM LOST. Warnings (red, MASTER ALARM blinking + tone): HIGH G, NO LINK, ENG FAIL, SINK RATE, OVERHEAT (a part
  over 80 % of its temperature limit), GEAR UP (under 300 m, descending, gear up). Pressing the master button acknowledges: the master lamp and tone go
  off, the annunciator stays lit (steady) while the condition lasts; a condition that clears and returns needs a new ack.
- KSP is the authority: indicator LEDs show the game's state and blink when it disagrees with the switch; SAS, RCS and
  lights are re-commanded once a second while they disagree (panel wins), gear is not (game wins).
- NO LINK when telemetry is older than 2 s or the plant reports disconnected; displays then show dashes.

### Tests
```sh
.venv/bin/python -m pytest -q cockpit-logic/tests     # unit tests of the pure logic, the DSKY and the burn computer (43)
.venv/bin/python tests/e2e_mock.py                    # end to end on the running stack with the mock (65 checks; `MQTT_PORT` selects another broker)
.venv/bin/python tests/e2e_ksp.py                     # end to end with KSP and gateway-ksp (85 checks; loads a save in orbit)
.venv/bin/python tests/e2e_ksp_docking.py --save lor3-rdv-handover   # docking display signs in KSP (8 checks)
.venv/bin/python tests/e2e_ksp_undock.py --save lor3-rdv-docked       # UNDOCK from the panel in KSP (5 checks)
```
(`.venv`: `python3 -m venv .venv && .venv/bin/pip install pytest paho-mqtt==2.1.0 krpc==0.7.0`.)
