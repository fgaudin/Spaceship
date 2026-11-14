# Capsule Simulator for a KSP Mun mission — plan & ideas

## Context
After finishing the Moonshot course (TM-1…TM-18), fly a hand-planned Mun mission from a full-size, immersive,
two-seat capsule with real switches. Requirements: testable, maintainable, scalable (10–20 panels).

Core idea: **the cockpit is a distributed system on one MQTT bus.** KSP is one of several possible "plants"
behind a gateway. Every component reads topics and publishes topics.

---

## 1. Architecture

```
 Panels (ESP32 PoE) ─┐                        ┌─ Gateway ── Simpit (serial, hot path) ──┐
 Glass panels (Pi) ──┼── MQTT broker ─────────┤          └─ kRPC (TCP, complex stuff) ──┼─ KSP 1.12.5
 Window panels (Pi) ─┤   (Mosquitto)          ├─ Cockpit logic (rules, C&W, breakers)   │   + HullCam
                     │                        ├─ Flight computer (DSKY, PADs, burns)    │   + camera
 Sticks (USB HID) ───┼────────────────────────┼─────────────────────────────────────────┘     streamer
                     │                        ├─ Mission Control / Instructor stations
                     │                        ├─ Mock plant (own physics, no KSP)
                     │                        └─ Recorder / replayer
```

### Topic namespaces and ownership (one writer per topic)
| Namespace | Writer | Meaning |
|---|---|---|
| `panel/<panel>/<control>` (inputs) | the panel | raw switch / encoder state |
| `panel/<panel>/<output>` (outputs) | cockpit logic | lamps, displays |
| `cmd/…` | cockpit logic, flight computer | requests to the game |
| `tlm/…` | gateway (or mock plant) | normalised game state, SI units |
| `cw/…` | cockpit logic | cautions, master alarm |
| `sim/failures/…` | instructor station | injected failures |
| `gateway/status` | gateway | connected, scene, vessel, paused |

Schemas live in `protocol/` (JSON Schema); every component is contract-tested against them.

### MQTT performance
Broker hop ~0.2–2 ms wired; KSP physics frame is 20 ms, so the bus is not the bottleneck. Rules: wired only,
TCP_NODELAY, QoS 0 for telemetry, retained for state, publish-on-change with rate caps.

### Gateway (only process talking to KSP)
- Translates `cmd/*` → backend calls and backend data → `tlm/*`. Topic → backend routing in config:
  Simpit for latency-sensitive inputs/telemetry (fire-and-forget, push), kRPC for maneuver nodes,
  autopilot, science, docking-port frames. kRPC reads always via **streams**, never polling.
- Gateway can speak the Simpit protocol itself over a virtual serial port (`socat`) — no Arduino in the path.
- Normalises names/units/frames; game resource names mapped in config.
- Handles scene changes, vessel switches, reverts: re-establishes streams/subscriptions, publishes resync.
- Custom C# KSP plugin only if Simpit + kRPC both fail the Phase 0 benchmark (would be a 3rd backend).

### Cockpit logic
- Pure function `(state, message) → (new state, messages)` wrapped in a thin MQTT shell → unit-testable.
- Owns rules KSP doesn't model: breakers, interlocks, C&W thresholds, lamp test, failures, camera selection.
- **KSP is the authority on physical state; cockpit only owns what KSP doesn't model.** Never assume a
  command worked: compare switch position with `tlm/*`. Per-control policy: *panel wins* (re-assert) or
  *game wins* (blink "disagree" lamp). Sync step on startup and every scene change.
- Keyboard bindings for panel-owned functions are removed in KSP. One owner per control axis at a time
  (MANUAL / AUTO mode switch: sticks vs burn executor; never MechJeb and executor together).
- Can be split later (electrical, C&W…) on the same pattern.

### Flight computer
DSKY-style Verb/Noun entry of PADs (Δv in prograde/radial/normal + TIG), time-to-ignition, attitude error,
burn execution via kRPC autopilot or KRPC.MechJeb, or needles for manual flight. Uses the bus like anyone else.

### Mock plant + recorder
Publishes the same `tlm/*` from own physics (port of Moonshot `js/physics.js`: patched conics, CW, rocket
equation). Recorder saves real KSP flights; replays are regression fixtures.

---

## 2. Hardware

### Three kinds of panel
| Kind | Hardware | Examples |
|---|---|---|
| I/O panel (majority) | ESP32 PoE + MCP23017 / PCA9685 or TLC5947 / MAX7219 | SPS, staging/abort, RCS/SAS, electrical + breakers, C&W matrix, timers, DSKY, science, lighting/comms |
| Glass panel | Raspberry Pi + screen, browser kiosk, web instrument; small I/O board for bezel keys | FDAI, orbit, docking display (reuse TM-12 CW/COAS view), descent tapes |
| Direct HID device | RP2040 as USB joystick, hall sensors | rotational + translational hand controllers, throttle |

Panels are **dumb I/O nodes**: publish raw input changes, drive outputs, debounce, lamp test, heartbeat
(firmware version + config hash), safe/blinking state when the bus drops. No rules in firmware.

### Generic firmware (DCS-BIOS / MobiFlight idea)
- One PlatformIO firmware for every I/O panel: drivers (switch2, switch3, button, encoder, pot, led, 7seg,
  servo), debounce, network module, OTA, heartbeat.
- Each panel described by `panels/<name>.yaml` (pin → control → topic), code-generated into a C++ table at
  build time. Later option: config pushed at boot (no reflash).
- Network isolated in one module: `ETH.h` + lwIP (`WiFiClient`/`NetworkClient`) — not `Ethernet.h`.
  PubSubClient takes any `Client&`; ArduinoOTA and mDNS work over ETH. Core 3.x drives LAN8720 and W5500
  through the same API.
- Updates over the network (OTA, dual-slot with rollback, password protected); first flash over USB.

### Boards (Germany)
- **Olimex ESP32-POE-ISO** for bench/debug (isolated: USB + PoE together), **ESP32-POE** for installed panels.
  Sources: EXP-Tech (DE), DigiKey.de, TME, Tinytronics. ESP32-POE2 (25 W) for power-hungry panels.
- Alternative to evaluate: **Waveshare ESP32-S3-POE-ETH** (make sure "POE" is in the variant).
- Later: own KiCad carrier board (ESP32 module + Ethernet + PoE module + expanders + standard connectors),
  based on Olimex's open schematics.

### Network & power
- Ethernet star with an 802.3af/at PoE switch, ≥ 150 W total budget (no passive PoE).
- I/O panel ~1–5 W (af); glass/window panel Pi + 7" ~15 W (at); screens > 10" on mains, PoE for data.
- Separate fused 12 V distribution with E-stop for shakers, fans, big backlights.

### Mechanical
Panel grid on a standard (5.75" DZUS-style), laser-cut/3D-printed faceplates with backlit legends,
aluminium extrusion frame, adjustable-depth mounts behind every window, enclosed black area behind windows.

---

## 3. Windows

- Each window = a monitor (Pi + browser) showing one **HullCam VDS** camera streamed out of KSP with
  **kerbcam** (H.264/WebRTC, Linux) or **JRTI** / **Kerbcast**; OfCourseIStillLoveYou as fallback.
  Gives several real KSP views at once for ascent and landing. (Synthetic renderer rejected.)
- Each camera aimed from the seat's eye point through the window centre; FOV = 2·atan(size / (2·distance)).
- **Two seats: each seat has its own windows** (like Gemini / LM). Shared windows are off by ~27° for the
  other seat. CDR: sticks, primary windows, staging/abort. LMP: systems, DSKY, checklist, comms, science.
- `cockpit-geometry.yaml` is the single source of truth (eye per seat, windows with centre/size/normal) →
  generates camera FOV/aim, monitor placement, faceplate cut-outs.
- Main KSP view: IVA with props stripped via ModuleManager (`!PROP`), or base model replaced to remove walls,
  or a HullCam nose camera. Camera selector (panel or flight phase) owns the main view.
- Optional **Fresnel collimation** per window (screen near focal length → image at infinity, more forgiving
  of head movement). Test with a cheap page-magnifier sheet first.
- Docking: dedicated window with docking-port camera, optional physical COAS (reticle on tilted glass).

---

## 4. Course ↔ cockpit
- Compute PADs (TLI, MCC, LOI, DOI, PDI, TEI) by hand with Kerbin/Mun constants; enter via DSKY.
- Mission Control station reuses the capstone planning desk (Δv budget, PADs, readback drill) + voice loop.
- Add a "Kerbin profile" to Moonshot so exercises can use Kerbin/Mun numbers.
- Agent self-test (SELFTEST.md): an agent flies the Mun mission via kRPC from the course alone; yields the
  course gaps, the Kerbin profile and a draft topic table for `protocol/`.
- Science panel: experiments, transmit/store, per-biome objectives in the flight plan.

## 5. Immersion (after the core works)
Instructor station with failure injection (Apollo 13 style), Master Alarm + C&W matrix, working circuit
breakers, hand controllers + abort handle, MET/event timers, bass shakers from acceleration, cabin audio,
reclined seats, enclosed shell, dim integral lighting.

---

## 6. Roadmap
| Phase | Goal | Done when |
|---|---|---|
| 0. Spikes | KSP 1.12.5 frozen via CKAN modlist; Mosquitto; benchmark kRPC streams vs Simpit-via-gateway vs HID; HullCam + kerbcam/JRTI (latency, FPS with 4–6 cameras, compatibility); stripped IVA test; agent self-test of the course, see SELFTEST.md | Latency numbers per transport and per camera; transport chosen per signal type |
| 1. Software skeleton | Monorepo, `protocol/`, gateway, mock plant, cockpit logic core, one web instrument, recorder | Same instrument runs against KSP and mock; CI contract tests on mock |
| 2. First panel | "Hello MQTT" on each board (PoE, reconnect after cable pull, OTA); generic firmware + YAML; engine/staging panel | Panel works on mock, then KSP, without reflash |
| 3. Sticks + DSKY | HID controllers; DSKY + burn executor | Kerbin circularisation from a hand-computed PAD |
| 4. Structure | Frame, seats, panel grid, power, windows per `cockpit-geometry.yaml` | Panels/windows mounted; any panel swappable in < 5 min |
| 5. Mission | Mun flight plan, checklists, Mission Control station, science panel | Full Mun landing and return from the capsule |
| 6. Immersion | C&W + instructor station, audio, shakers, Fresnel windows | Mission with injected failures, recovered |

## 7. Repo layout (separate repo from Moonshot)
```
capsule/
  protocol/  gateway-ksp/  plant-mock/  cockpit-logic/  flight-computer/
  glass/  windows/  mission-control/  instructor/
  firmware/  panels/  cockpit-geometry.yaml
  tools/  (recorder, bus sniffer, panel test jig, panel health page)
  ksp/      (CKAN modlist export, ModuleManager patches)
  docker-compose.yml
```

## 8. Testability
Contract tests on `protocol/`; cockpit logic and flight computer as pure functions; PlatformIO native tests
for firmware logic; panel test jig driven by panel YAML; replays as regression fixtures; power-on self-test
and panel health page; post-mod-change smoke test (all `tlm/*` arrive, each `cmd/*` has an effect).

## Open decisions
- Space and budget (panel count, number of window monitors).
- Apollo-flavoured layout vs original Kerbal-themed layout.
- Gateway / logic language: Python (fastest with kRPC) vs stricter alternatives.
