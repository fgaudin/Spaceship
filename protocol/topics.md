# Cockpit bus protocol (prototype v0)

One MQTT broker; every topic has exactly one writer. Payloads are JSON, SI units (m, s, kg, N, m/s, Pa, degrees for
attitude angles). Seeded from the KSP self-test (`selftest/interface.md`).

## Namespaces and writers

| Topic | Writer | Payload | Rate | QoS / retain |
|---|---|---|---|---|
| `panel/<panel>/in/<control>` | the panel | `{"v": <value>}`: switch 0/1 (3-pos: -1/0/1), button 0/1 (momentary), pot 0..1, rotary int | on change | 1, **retained** for switches/pots/rotaries, not for buttons |
| `panel/<panel>/out/<output>` | cockpit logic | lamp/LED `{"on": bool, "blink": bool}`; 7-seg and alphanumeric `{"text": "12.345", "blank": false, "blink": false}`; bar `{"v": 0..1}`; LED matrix `{"rows": ["..g..", …]}` (one character per LED: g, a, r, w, `.` off); buzzer `{"on": bool}` | on change | 1, retained |
| `panel/<panel>/status` | the panel | `{"online": bool, "fw": str, "config": hash, "uptime": s}` (LWT `{"online": false}`) | 5 s | 1, retained |
| `panel/<module>/io/status` | the I/O node of a module that also has a screen (virtual console: FDAI) | the same, while its page reports on `panel/<module>/status` | 5 s | 1, retained |
| `tlm/time` | plant | `{"ut", "met", "warp", "paused"}` | 10 Hz | 0 |
| `tlm/flight` | plant | `{"alt", "radar", "vs", "hs", "speed", "v_orb", "q", "g", "lat", "lon", "vn", "ve", "v_right", "v_fwd", "v_down", "p"}` (v_orb: speed along the orbit, against the body's centre; vn, ve: surface velocity north and east; v_right, v_fwd, v_down: the same velocity along the vessel's own axes; p: outside static pressure, Pa) | 10–20 Hz | 0 |
| `tlm/vessel` | plant | `{"name", "mass", "thrust", "thrust_avail", "isp", "situation", "stage", "throttle", "sas", "rcs", "gear", "lights", "brakes", "sas_mode", "speed_mode", "solar", "fuel_cell", "chute", "comm", "has_gear", "contact"}` (solar: panels deployed or null; fuel_cell: a fuel cell runs, or null without one; chute: stowed/armed/deployed/cut or null; comm: a link to the ground exists; contact: landed, splashed, or a leg or wheel touches the ground) | 10 Hz | 0 |
| `tlm/attitude` | plant | `{"pitch", "heading", "roll", "prograde": {"pitch", "heading"} or null}` degrees against the local horizon; prograde is the surface velocity direction | 10 Hz | 0 |
| `tlm/orbit` | plant | `{"body", "apo", "peri", "a", "e", "i", "period", "t_apo", "t_peri", "t_soi", "nu", "argp"}` (degrees; t_soi: seconds to the next change of sphere of influence, or null; also "lan", the longitude of the ascending node, and "ut", the time the elements hold at) | 2 Hz, 10 Hz while thrusting | 0, retained |
| `tlm/target` | plant | `{"set": false, "ctrl_port", "docked"}` or `{"set", "name", "range", "closing", "los_rate" (°/min), "rel_v", "ctrl_port", "docked" (a docking port of the vessel is docked), "port": {"axial", "x", "z", "v_axial", "vx", "vz", "angle", "from_port", "right", "up", "fwd", "v_right", "v_up", "yaw", "pitch", "roll"}}` (axial … vz: in the targeted port's frame, y out of the port; angle: between our axis and the port's, 0 = aligned; right, up, fwd: where the target port is from ours, in the pilot's own axes, m; v_right, v_up: how fast those offsets change; yaw, pitch: the turn that would face the port squarely, + right and + up; roll: the target port's own "up" against ours, + = roll right; ctrl_port: the vessel is controlled from a docking port) | 5 Hz with a target, else 2 Hz | 0 |
| `tlm/engines` | plant | `{"engines": [{"x", "z", "stage", "on", "thrust", "max", "fuel", "rated", "isp_vac", "isp_sl"}], "stage", "limit", "gimbal_locked"}` (x, z: position across the vessel's axis, m; max: thrust available at full throttle; rated: the same, also before the engine is lit; isp_vac, isp_sl: specific impulse in vacuum and at sea level; the outer stage: the vessel's stage number when this list was read, which `tlm/vessel` reports sooner; limit: mean thrust limiter of the lit engines, 0..1) | 2 Hz | 0 |
| `tlm/resources` | plant | `{"<name>": {"amount", "max"}}` for the current stage (propellant) and the vessel (ElectricCharge, LiquidFuel, Oxidizer, MonoPropellant, Ablator): `{"stage": {...}, "total": {...}}` | 2 Hz | 0 |
| `tlm/node` | plant | `{"set": false}` or `{"set", "ut", "dv": [prograde, normal, radial], "att_err", "yaw", "pitch"}`: the first maneuver node in the game, whoever made it; att_err: degrees between the vessel's axis and the burn direction; yaw, pitch: how to turn to face it (+ nose right, + nose up) | 2 Hz | 0 |
| `tlm/thermal` | plant | `{"max", "outside"}`: the hottest part as a fraction of its temperature limit (skin of every part, core of the engines); outside: the static air temperature, °C (about −270 in space) | 2 Hz | 0 |
| `tlm/comm` | plant | `{"link", "strength" (0..1), "hops", "via", "antenna"}`: the radio link to the ground; via: the first station or relay on the way, or null; antenna: deployable antennas out, or null when there is none | 2 Hz | 0 |
| `tlm/groups` | plant | `{"on": [bool × 10]}`: the craft's custom action groups 1 to 10 | 2 Hz | 0 |
| `cmd/throttle` | cockpit logic | `{"v": 0..1}` | on change, ≤ 20 Hz | 0 |
| `cmd/stage` | cockpit logic | `{}` | event | 1 |
| `cmd/abort` | cockpit logic | `{}` | event | 1 |
| `cmd/sas`, `cmd/rcs`, `cmd/gear`, `cmd/lights`, `cmd/brakes` | cockpit logic | `{"on": bool}` | on change | 1 |
| `cmd/solar` | cockpit logic | `{"on": bool}` | on change | 1 |
| `cmd/fuel_cell` | cockpit logic | `{"on": bool}`: start or stop every fuel cell | on change | 1 |
| `panel/hc/in/<axis>` | hand controllers (USB joysticks; tests) | `{"v": -1..1}` for rot_pitch (+ nose up), rot_yaw (+ nose right), rot_roll (+ right), trans_right, trans_up, trans_fwd | on change | 0 |
| `cmd/rotate` | cockpit logic | `{"pitch", "yaw", "roll"}` −1..1, after a 0.05 deadband. With SAS on, the cockpit switches SAS off while this is off centre and back on when centred (KSP does so for keyboard steering, not for kRPC inputs) | on change | 0 |
| `cmd/translate` | cockpit logic | `{"right", "up", "forward"}` −1..1 (RCS translation) | on change | 0 |
| `cmd/speed_mode` | cockpit logic | `{"mode": "orbit"|"surface"|"target"}`: the navball's speed reference, which SAS PRO and RETRO follow | on change | 1 |
| `cmd/antenna` | cockpit logic | `{"on": bool}`: deploy or retract every deployable antenna | on change | 1 |
| `cmd/action_group` | cockpit logic | `{"n": 1..10}`: toggle that custom action group | event | 1 |
| `cmd/chute` | cockpit logic | `{"deploy": true}` (needs CHUTE ARM) | event | 1 |
| `cmd/warp` | cockpit logic | `{"step": ±1}`, `{"stop": true}` (rails warp in vacuum, physics warp in the atmosphere) or `{"to_ut": s}` (rails warp until that UT; a step or stop cancels it) | event | 1 |
| `cmd/thrust_limit` | cockpit logic | `{"v": 0..1}`: thrust limiter of every lit engine that can be throttled | on change | 1 |
| `cmd/gimbal` | cockpit logic | `{"locked": bool}` | on change | 1 |
| `cmd/target` | cockpit logic | `{"step": ±1}` next / previous vessel around the same body, nearest first; `{"port": 1}` next free docking port of the target, then the vessel itself again; `{"clear": true}` | event | 1 |
| `cmd/undock` | cockpit logic | `{}`: undock the port the vessel is controlled from if it is docked, else the first docked port (needs UNDOCK ARM) | event | 1 |
| `cmd/control_from` | cockpit logic | `{"port": bool}`: control from the vessel's first free docking port, or from where it was controlled when bound | on change | 1 |
| `cmd/node` | cockpit logic | `{"ut": s, "dv": [prograde, normal, radial]}` replaces the maneuver node the plant made for the cockpit; `{"clear": true}` removes it. Only an attitude reference for SAS (mode `maneuver`): the PAD and the Δv counter stay in the cockpit | on change | 1 |
| `cmd/pause` | cockpit logic | `{"on": bool}` | on change | 1 |
| `cmd/game` | cockpit logic | `{"quicksave": true}` or `{"quickload": true}` | event | 1 |
| `pad/uplink` | Mission Control: the MCC's CAPCOM console, or the flight-dynamics service for a solo pilot (never both in one flight) | `{"tig_met": s, "dv": [prograde, normal, radial]}`: a PAD read up to the crew. The burn computer shows it blinking until the crew accepts it | event | 1 |
| `cmp/pad` | cockpit logic | `{"tig", "dv", "armed", "state": "idle"|"ready"|"armed"|"burn"|"done"}`: the PAD loaded in the burn computer | on change | 1, retained |
| `cmd/sas_mode` | cockpit logic | `{"mode": "stability"|"prograde"|"retrograde"|"normal"|"antinormal"|"radial"|"antiradial"|"target"|"antitarget"|"maneuver"}` | on change | 1 |
| `cam/list` | camera monitor | `{"cameras": [{"id", "name", "vessel", "kind"}]}`: the cameras the monitor can show (from the Kerbcast mod) | on change | 1, retained |
| `cam/status` | camera monitor | `{"online", "playing"}` (LWT `online: false`) | on change | 1, retained |
| `cam/select` | cockpit logic | `{"id"}`: the camera to show, or null | on change | 1, retained |
| `cw/state` | cockpit logic | `{"master_caution": bool, "master_alarm": bool, "active": ["LOW FUEL", …], "unacked": [...]}` | on change | 1, retained |
| `cockpit/power` | cockpit logic | `{"on": bool}`: the cockpit has power (electric charge left, and the breaker in); off, every panel is dark and its inputs dead | on change | 1, retained |
| `cockpit/lighting` | cockpit logic | `{"cabin": bool, "backlight": bool}`: the LIGHTS panel's cockpit lights, off without power (the console page brightens its plates and lights its legends) | on change | 1, retained |
| `panel/eng/out/fdai` | cockpit logic | `{"needles": "prograde"|"retrograde"|"off", "error_scale": 5|50, "markers": bool}`: how the FDAI page draws, from the FDAI controls on the ATTITUDE panel | on change | 1, retained |
| `gateway/status` | plant (gateway or mock) | `{"connected", "plant": "ksp"|"mock", "scene", "vessel", "paused"}` (LWT `connected: false`) | on change + 5 s | 1, retained |
| `sim/reset` | SimSup page (RESET SIM) | `{}` | event | 1 |
| `sim/failures/<id>` | SimSup | `{"on": bool, ...parameters}`: catalogue and who applies each in [simsup/README.md](../simsup/README.md) | on change | 1, retained |
| `sim/freeze` | SimSup | `{"on": bool}`: the instructor's pause (the gateway pauses KSP; the mock stops), apart from the crew's PAUSE | on change | 1, retained |
| `sim/load` | SimSup | `{"save": name}`: the gateway loads that KSP save | event | 1 |
| `fd/status` | flight-dynamics | `{"text", "ok"}`: what the last SOLO request gave ("CIRC APO 1004.2", "RDV: NO TARGET") | on change | 1, retained |
| `mcc/poll` | MCC, FLIGHT console | `{"open", "question", "met"}`: the go/no-go poll ([panels/virtual/mcc/README.md](../panels/virtual/mcc/README.md)) | on change | 1, retained |
| `mcc/poll/<role>` | MCC, that console | `{"go": bool, "met"}`: its answer | on change | 1, retained |
| `mcc/loop/<role>` | MCC, that console | `{"text", "met", "roles"}`: a note on the flight director's loop (roles: every console the laptop holds) | event | 1 |
| `sim/simsup/*` | SimSup and its page | the station's own state, log and requests (simsup/README.md) | | |

## Rules
- Panels hold no logic: they publish raw inputs and draw what `panel/<panel>/out/*` says. Debounce and lamp test live
  in the cockpit logic for the prototype (the firmware will debounce locally).
- KSP is the authority on physical state. The cockpit never assumes a command worked: it compares the switch position
  with `tlm/vessel` and shows a "disagree" (blinking) lamp until they match. Policy per control: *panel wins* (the
  command is re-sent once a second while they disagree: SAS, RCS, external lights) or *game wins* (only the lamp:
  gear, solar panels, brakes, fuel cells).
- A knob or switch that sets something the craft's builder may have set (thrust limiter, gimbal lock, control point,
  pause) commands the plant only when it moves: its first reported position after a restart is not a command.
- Telemetry older than 2 s raises the `NO LINK` caution.
- Module definitions: `protocol/panels/<module>.json` (its panels, each W×H U with its bus namespace; their controls,
  outputs, legends and mm positions), and `protocol/panels/console.json` (where the modules sit). The virtual console
  is drawn from them; the generic firmware will be generated from the module file. See
  [panels/README.md](panels/README.md).
