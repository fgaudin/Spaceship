# Simpit gateway: a fallback plant (proof of concept)

`gateway-ksp` talks to KSP through **kRPC**. If kRPC ever stops being usable (a KSP or mod update it does not
follow, a bug it cannot get round), this gateway talks to KSP through **Kerbal Simpit** instead: the plugin that
drives Arduino cockpits over a serial port. The gateway plays the Arduino. It publishes the same `tlm/*` topics and
takes the same `cmd/*` as `gateway-ksp` (protocol/topics.md), for the part Simpit can do, so the cockpit logic, the
panels and Mission Control do not change. Run one plant at a time: this one, `gateway-ksp` or the mock.

```
  cockpit ── cmd/* ──▶ gateway-simpit ── serial (tty0tty or USB) ──▶ Kerbal Simpit plugin ── KSP
          ◀── tlm/* ──                ◀── registered channels ──
```

## What it covers

| From the game (registered channels) | Topic |
|---|---|
| ALTITUDE (sea level, surface) | `tlm/flight` alt, radar |
| VELOCITY (orbital, surface, vertical) | `tlm/flight` v_orb, speed, vs, hs |
| APSIDES, APSIDES_TIME, ORBIT, SOI | `tlm/orbit` apo, peri, t_apo, t_peri, e, a, i, lan, argp, nu, period, body |
| ROTATION_DATA | `tlm/attitude` pitch, heading, roll, prograde |
| FLIGHT_STATUS, ACTION_STATUS, SAS_MODE_INFO, DELTAV, VESSEL_NAME | `tlm/vessel` situation, stage, crew, comm, sas, rcs, gear, lights, brakes, sas_mode, stage_dv, name |
| LF, OX, MONO, ELECTRIC (and the stage's LF, OX) | `tlm/resources` |
| SCENE_CHANGE | `gateway/status` scene |

| Command | Simpit message |
|---|---|
| `cmd/throttle` | THROTTLE (int16, 0..32767) |
| `cmd/stage`, `cmd/abort` | AG_ACTIVATE stage / abort |
| `cmd/sas`, `cmd/rcs`, `cmd/gear`, `cmd/lights`, `cmd/brakes` | AG_ACTIVATE / AG_DEACTIVATE |
| `cmd/sas_mode` | SAS_MODE (the autopilot mode number) |
| `cmd/rotate`, `cmd/translate` | ROTATION, TRANSLATION (int16 −32767..32767, all axes) |
| `cmd/action_group` | CAG_TOGGLE |
| `cmd/warp` step / stop | TIMEWARP up / down / ×1 |

**Not there** (Simpit does not carry it): UT and MET (`tlm/time`), the engines and parts (engine matrix, NEXT STAGE,
heat by part, parachutes), the target's docking geometry, maneuver nodes, science, STATION, the mission clock. Those
panels stay dark or show dashes. Enough to fly up, around and down; not the whole Mun mission.

## Running it (on the host, with KSP)

Kerbal Simpit 2.3.1 is in the stock install (`GameData/KerbalSimpit`). The protocol here is the bundled Arduino
library's (`KerbalSimpitRevamped-Arduino/src`, library version 1.3.0, which the gateway sends in its handshake).

1. A pair of serial ports that answer the modem-line calls (not a socat pty: see below), e.g. tty0tty's
   `/dev/tnt0` ↔ `/dev/tnt1`, or two USB-serial adapters crossed.
2. With KSP closed, in `GameData/KerbalSimpit/Settings.cfg`, `PortName = /dev/tnt0` (KSP's end), then start KSP.
3. Stop `gateway-ksp` (`docker compose stop gateway-ksp`), then
   `SIMPIT_PORT=/dev/tnt1 MQTT_HOST=localhost python gateway.py` (`pip install -r requirements.txt`).

A real serial line works too (two USB-serial adapters crossed, `SIMPIT_PORT=/dev/ttyUSB1`, `SIMPIT_BAUD` as in
Settings.cfg). The gateway sends an echo request every 2 s and starts again when the plugin goes quiet for 6 s.

## The code

| File | What it is |
|---|---|
| `simpit/protocol.py` | The wire format: COBS framing, XOR checksum, the handshake, message numbers, payload structs. |
| `simpit/link.py` | The serial link as a device: SYN / SYNACK / ACK, channel registration, packets in and out, echoes. |
| `simpit/bridge.py` | Simpit messages ↔ topics, pure (no serial, no MQTT). |
| `gateway.py` | The service: serial port, MQTT, the loop. |
| `tests/` | COBS against a line-for-line port of the library's C, framing, the handshake against a simulated plugin, the translation both ways. |

## A pty does not work on Linux (found 2026-11-21)

With `PortName = /tmp/simpit-ksp` (a socat pty), Simpit logs `Error opening serial port /tmp/simpit-ksp:
Inappropriate ioctl for device`: KSP's Mono runtime asks the port for serial line controls (modem signals) that a
pseudo-terminal does not have. The link needs a port that answers them:
- **two USB-serial adapters** with TX and RX crossed (and GND): KSP opens `/dev/ttyUSB0`, the gateway `/dev/ttyUSB1`;
- **tty0tty**, a kernel module that makes pairs of virtual serial ports (`/dev/tnt0` ↔ `/dev/tnt1`) with the modem
  lines: built for the running kernel and loaded as root;
- an ESP32 or Arduino in the middle, as the library's users do, forwarding to the gateway over USB or the network.

Also: Simpit writes its Settings.cfg back when KSP quits, so PortName must be set with KSP closed.

## Not checked yet

Tried against a simulated plugin over a pty (the gateway's own loop: handshake, channels, a telemetry message
out as `tlm/flight`, a throttle command in), not against KSP. To check in KSP: that the plugin accepts the handshake
and the ports above on Linux; the units of the ORBIT message's angles (passed on as they come); which way
TRANSLATION's X, Y and Z point (mapped as the library's translation demo maps its stick).
