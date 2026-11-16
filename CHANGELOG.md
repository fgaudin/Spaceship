# Changelog

What changed and why, in more detail than the commit messages. Newest first. Topic and panel names are those of
`protocol/topics.md` and `protocol/panels/`.

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
