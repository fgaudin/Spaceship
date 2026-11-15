# Cockpit bus protocol (prototype v0)

One MQTT broker; every topic has exactly one writer. Payloads are JSON, SI units (m, s, kg, N, m/s, Pa, degrees for
attitude angles). Seeded from the KSP self-test (`selftest/interface.md`).

## Namespaces and writers

| Topic | Writer | Payload | Rate | QoS / retain |
|---|---|---|---|---|
| `panel/<panel>/in/<control>` | the panel | `{"v": <value>}`: switch 0/1 (3-pos: -1/0/1), button 0/1 (momentary), pot 0..1, rotary int | on change | 1, **retained** for switches/pots/rotaries, not for buttons |
| `panel/<panel>/out/<output>` | cockpit logic | lamp/LED `{"on": bool, "blink": bool}`; 7-seg and alphanumeric `{"text": "12.345", "blank": false, "blink": false}`; bar `{"v": 0..1}`; LED matrix `{"rows": ["..g..", …]}` (one character per LED: g, a, r, w, `.` off); buzzer `{"on": bool}` | on change | 1, retained |
| `panel/<panel>/status` | the panel | `{"online": bool, "fw": str, "config": hash, "uptime": s}` (LWT `{"online": false}`) | 5 s | 1, retained |
| `tlm/time` | plant | `{"ut", "met", "warp", "paused"}` | 10 Hz | 0 |
| `tlm/flight` | plant | `{"alt", "radar", "vs", "hs", "speed", "q", "g", "lat", "lon", "vn", "ve"}` (vn, ve: surface velocity north and east) | 10–20 Hz | 0 |
| `tlm/vessel` | plant | `{"name", "mass", "thrust", "thrust_avail", "isp", "situation", "stage", "throttle", "sas", "rcs", "gear", "lights", "brakes", "sas_mode", "solar", "chute", "comm", "has_gear", "contact"}` (solar: panels deployed or null; chute: stowed/armed/deployed/cut or null; comm: a link to the ground exists; contact: landed, splashed, or a leg or wheel touches the ground) | 10 Hz | 0 |
| `tlm/attitude` | plant | `{"pitch", "heading", "roll", "prograde": {"pitch", "heading"} or null}` degrees against the local horizon; prograde is the surface velocity direction | 10 Hz | 0 |
| `tlm/orbit` | plant | `{"body", "apo", "peri", "a", "e", "i", "period", "t_apo", "t_peri", "t_soi", "nu", "argp"}` (degrees; t_soi: seconds to the next change of sphere of influence, or null) | 2–5 Hz | 0, retained |
| `tlm/target` | plant | `{"set": false, "ctrl_port"}` or `{"set", "name", "range", "closing", "los_rate" (°/min), "rel_v", "ctrl_port", "port": {"axial", "x", "z", "v_axial", "vx", "vz", "angle", "from_port", "right", "up", "fwd", "v_right", "v_up", "yaw", "pitch", "roll"}}` (axial … vz: in the targeted port's frame, y out of the port; angle: between our axis and the port's, 0 = aligned; right, up, fwd: where the target port is from ours, in the pilot's own axes, m; v_right, v_up: how fast those offsets change; yaw, pitch: the turn that would face the port squarely, + right and + up; roll: the target port's own "up" against ours, + = roll right; ctrl_port: the vessel is controlled from a docking port) | 5 Hz with a target, else 2 Hz | 0 |
| `tlm/engines` | plant | `{"engines": [{"x", "z", "stage", "on", "thrust", "max", "fuel"}], "limit", "gimbal_locked"}` (x, z: position across the vessel's axis, m; max: thrust available at full throttle; limit: mean thrust limiter of the lit engines, 0..1) | 2 Hz | 0 |
| `tlm/resources` | plant | `{"<name>": {"amount", "max"}}` for the current stage and the vessel: `{"stage": {...}, "total": {...}}` | 2 Hz | 0 |
| `tlm/node` | plant | `{"set": false}` or `{"set", "ut", "dv": [prograde, normal, radial], "att_err"}`: the first maneuver node in the game, whoever made it; att_err: degrees between the vessel's axis and the burn direction | 2 Hz | 0 |
| `tlm/thermal` | plant | `{"max"}`: the hottest part as a fraction of its temperature limit (skin of every part, core of the engines) | 2 Hz | 0 |
| `cmd/throttle` | cockpit logic | `{"v": 0..1}` | on change, ≤ 20 Hz | 0 |
| `cmd/stage` | cockpit logic | `{}` | event | 1 |
| `cmd/abort` | cockpit logic | `{}` | event | 1 |
| `cmd/sas`, `cmd/rcs`, `cmd/gear`, `cmd/lights`, `cmd/brakes` | cockpit logic | `{"on": bool}` | on change | 1 |
| `cmd/solar` | cockpit logic | `{"on": bool}` | on change | 1 |
| `cmd/chute` | cockpit logic | `{"deploy": true}` (needs CHUTE ARM) | event | 1 |
| `cmd/warp` | cockpit logic | `{"step": ±1}`, `{"stop": true}` (rails warp in vacuum, physics warp in the atmosphere) or `{"to_ut": s}` (rails warp until that UT; a step or stop cancels it) | event | 1 |
| `cmd/thrust_limit` | cockpit logic | `{"v": 0..1}`: thrust limiter of every lit engine that can be throttled | on change | 1 |
| `cmd/gimbal` | cockpit logic | `{"locked": bool}` | on change | 1 |
| `cmd/target` | cockpit logic | `{"step": ±1}` next / previous vessel around the same body, nearest first; `{"port": 1}` next free docking port of the target, then the vessel itself again; `{"clear": true}` | event | 1 |
| `cmd/control_from` | cockpit logic | `{"port": bool}`: control from the vessel's first free docking port, or from where it was controlled when bound | on change | 1 |
| `cmd/node` | cockpit logic | `{"ut": s, "dv": [prograde, normal, radial]}` replaces the maneuver node the plant made for the cockpit; `{"clear": true}` removes it. Only an attitude reference for SAS (mode `maneuver`): the PAD and the Δv counter stay in the cockpit | on change | 1 |
| `cmd/pause` | cockpit logic | `{"on": bool}` | on change | 1 |
| `cmd/game` | cockpit logic | `{"quicksave": true}` or `{"quickload": true}` (needs SAVE ARM) | event | 1 |
| `pad/uplink` | Mission Control | `{"tig_met": s, "dv": [prograde, normal, radial]}`: a PAD read up to the crew. The burn computer shows it blinking until the crew accepts it (`dsky/uplink` is the same message, kept for the DSKY) | event | 1 |
| `cmp/pad` | cockpit logic | `{"tig", "dv", "armed", "state": "idle"|"ready"|"armed"|"burn"|"done"}`: the PAD loaded in the burn computer | on change | 1, retained |
| `cmd/sas_mode` | cockpit logic | `{"mode": "stability"|"prograde"|"retrograde"|"normal"|"antinormal"|"radial"|"antiradial"|"target"|"antitarget"|"maneuver"}` | on change | 1 |
| `cw/state` | cockpit logic | `{"master_caution": bool, "master_alarm": bool, "active": ["LOW FUEL", …], "unacked": [...]}` | on change | 1, retained |
| `gateway/status` | plant (gateway or mock) | `{"connected", "plant": "ksp"|"mock", "scene", "vessel", "paused"}` (LWT `connected: false`) | on change + 5 s | 1, retained |
| `sim/reset` | instructor (or the panel's bench page) | `{}` | event | 1 |
| `sim/failures/<id>` | instructor | `{"on": bool}` | event | 1, retained |

## Rules
- Panels hold no logic: they publish raw inputs and draw what `panel/<panel>/out/*` says. Debounce and lamp test live
  in the cockpit logic for the prototype (the firmware will debounce locally).
- KSP is the authority on physical state. The cockpit never assumes a command worked: it compares the switch position
  with `tlm/vessel` and shows a "disagree" (blinking) lamp until they match. Policy per control: *panel wins* (the
  command is re-sent once a second while they disagree: SAS, RCS, lights) or *game wins* (only the lamp: gear).
- A knob or switch that sets something the craft's builder may have set (thrust limiter, gimbal lock, control point,
  pause) commands the plant only when it moves: its first reported position after a restart is not a command.
- Telemetry older than 2 s raises the `NO LINK` caution.
- Panel definitions: `protocol/panels/<panel>.json` (controls, outputs, legends). The virtual panel is drawn from it; the
  generic firmware will be generated from the same file.
