# Cockpit bus protocol (prototype v0)

One MQTT broker; every topic has exactly one writer. Payloads are JSON, SI units (m, s, kg, N, m/s, Pa, degrees for
attitude angles). Seeded from the KSP self-test (`selftest/interface.md`).

## Namespaces and writers

| Topic | Writer | Payload | Rate | QoS / retain |
|---|---|---|---|---|
| `panel/<panel>/in/<control>` | the panel | `{"v": <value>}`: switch 0/1 (3-pos: -1/0/1), button 0/1 (momentary), pot 0..1, rotary int | on change | 1, **retained** for switches/pots/rotaries, not for buttons |
| `panel/<panel>/out/<output>` | cockpit logic | lamp/LED `{"on": bool, "blink": bool}`; 7-seg and alphanumeric `{"text": "12.345", "blank": false, "blink": false}`; bar `{"v": 0..1}`; LED matrix `{"rows": ["..g..", …]}` (one character per LED: g, a, r, w, `.` off); engine rosette `{"leds": "g.w......"}` (the same characters, the centre lamp first, then the ring clockwise from the top); buzzer `{"on": bool}` | on change | 1, retained |
| `panel/<panel>/status` | the panel | `{"online": bool, "fw": str, "config": hash, "uptime": s}` (LWT `{"online": false}`) | 5 s | 1, retained |
| `panel/<module>/io/status` | the I/O node of a module that also has a screen (virtual console: FDAI) | the same, while its page reports on `panel/<module>/status` | 5 s | 1, retained |
| `tlm/time` | plant | `{"ut", "met", "vessel_met", "warp", "paused"}`: met is the mission's, from the launch across undockings (`mission/clock`); vessel_met the game's own for the vessel flown | 10 Hz | 0 |
| `tlm/flight` | plant | `{"alt", "radar", "vs", "hs", "speed", "v_orb", "q", "g", "lat", "lon", "vn", "ve", "v_right", "v_fwd", "v_down", "p"}` (v_orb: speed along the orbit, against the body's centre; vn, ve: surface velocity north and east; v_right, v_fwd, v_down: the same velocity along the vessel's own axes; p: outside static pressure, Pa) | 10–20 Hz | 0 |
| `tlm/vessel` | plant | `{"name", "crew", "mass", "thrust", "thrust_avail", "isp", "situation", "stage", "throttle", "sas", "rcs", "gear", "lights", "brakes", "precision", "hold", "sas_mode", "speed_mode", "solar", "fuel_cell", "wheels", "next_stage", "chute", "chute_safe", "comm", "has_gear", "contact"}` (solar: panels deployed or null; fuel_cell: a fuel cell runs, or null without one; wheels: a reaction wheel is on, or null without one; next_stage: what the next staging does, `{"stage", "engines", "solids", "decouple", "clamps", "chutes", "fairing"}` (engines and solids: how many it lights), or null with no stage left; chute: stowed/armed/deployed/cut or null; comm: a link to the ground exists; precision: KSP's precision mode; hold: the gateway's autopilot holds `cmd/hold`'s attitude (KSP plant only); contact: landed, splashed, or a leg or wheel touches the ground) | 10 Hz | 0 |
| `tlm/attitude` | plant | `{"pitch", "heading", "roll", "prograde": {"pitch", "heading"} or null}` degrees against the local horizon; prograde is the surface velocity direction | 10 Hz | 0 |
| `tlm/orbit` | plant | `{"body", "atm", "mu", "radius", "apo", "peri", "a", "e", "i", "period", "t_apo", "t_peri", "t_soi", "nu", "argp"}` (degrees; atm: top of the atmosphere, m, null without; mu, radius: the body's, as the game has them; t_soi: seconds to the next change of sphere of influence, or null; also "lan", the longitude of the ascending node, and "ut", the time the elements hold at) | 2 Hz, 10 Hz while thrusting | 0, retained |
| `tlm/target` | plant | `{"set": false, "ctrl_port", "docked"}` or `{"set", "name", "range", "closing", "los_rate" (°/min), "rel_v", "ctrl_port", "docked" (a docking port of the vessel is docked), "port": {"axial", "x", "z", "v_axial", "vx", "vz", "angle", "from_port", "right", "up", "fwd", "v_right", "v_up", "yaw", "pitch", "roll"}}` (axial … vz: in the targeted port's frame, y out of the port; angle: between our axis and the port's, 0 = aligned; right, up, fwd: where the target port is from ours, in the pilot's own axes, m; v_right, v_up: how fast those offsets change; yaw, pitch: the turn that would face the port squarely, + right and + up; roll: the target port's own "up" against ours, + = roll right; ctrl_port: the vessel is controlled from a docking port) | 5 Hz with a target, else 2 Hz | 0 |
| `tlm/engines` | plant | `{"engines": [{"x", "z", "stage", "on", "held", "thrust", "max", "fuel", "rated", "isp_vac", "isp_sl", "propellants"}], "stage", "limit", "gimbal_locked"}` (x, z: position across the vessel's axis, m, in the frame of the part the craft is controlled from; held: shut down because its capsule is not the one flown, docked; max: thrust available at full throttle; rated: the same, also before the engine is lit; isp_vac, isp_sl: specific impulse in vacuum and at sea level; propellants: the resources it burns; the outer stage: the vessel's stage number when this list was read, which `tlm/vessel` reports sooner; limit: mean thrust limiter of the lit engines, 0..1) | 2 Hz | 0 |
| `tlm/resources` | plant | `{"<name>": {"amount", "max"}}` for the current stage (propellant) and the vessel (ElectricCharge, LiquidFuel, Oxidizer, MonoPropellant, XenonGas, Ablator, and with TAC Life Support Food, Water, Oxygen): `{"stage": {...}, "total": {...}}` | 2 Hz | 0 |
| `tlm/node` | plant | `{"set": false}` or `{"set", "ut", "dv": [prograde, normal, radial], "att_err", "yaw", "pitch"}`: the first maneuver node in the game, whoever made it; att_err: degrees between the vessel's axis and the burn direction; yaw, pitch: how to turn to face it (+ nose right, + nose up) | 2 Hz | 0 |
| `tlm/thermal` | plant | `{"max", "outside"}`: the hottest part as a fraction of its temperature limit (skin of every part, core of the engines); outside: the static air temperature, °C (about −270 in space) | 2 Hz | 0 |
| `tlm/comm` | plant | `{"link", "strength" (0..1), "hops", "via", "antenna"}`: the radio link to the ground; via: the first station or relay on the way, or null; antenna: deployable antennas out, or null when there is none | 2 Hz | 0 |
| `tlm/science` | plant | `{"experiments": [{"title", "available", "data", "inoperable", "rerunnable", "value", "transmit"}], "biome"}`: value, transmit: the science of the data held, kept or sent | 2 Hz | 0 |
| `tlm/station` | plant | `{"at": "cm"/"lm"/null, "joined", "cm": {"crew", "seats", "here"} or null, "lm": {...} or null, "held"}`: the two capsules, found by their window cameras; at: the one the craft is flown from; here: in the active vessel; joined: both in it; held: engines of the capsule not flown held shut down while docked (the engine controls drive the flown capsule's only) (docked), so the crew can go across | 2 Hz | 0 |
| `tlm/groups` | plant | `{"on": [bool × 10]}`: the craft's custom action groups 1 to 10 | 2 Hz | 0 |
| `cmd/throttle` | cockpit logic | `{"v": 0..1}` | on change, ≤ 20 Hz | 0 |
| `cmd/stage` | cockpit logic | `{}` | event | 1 |
| `cmd/abort` | cockpit logic | `{}` | event | 1 |
| `cmd/sas`, `cmd/rcs`, `cmd/gear`, `cmd/lights`, `cmd/brakes`, `cmd/precision` (RCS FINE) | cockpit logic | `{"on": bool}` | on change | 1 |
| `cmd/solar` | cockpit logic | `{"on": bool}` | on change | 1 |
| `cmd/fuel_cell` | cockpit logic | `{"on": bool}`: start or stop every fuel cell | on change | 1 |
| `cmd/wheels` | cockpit logic | `{"on": bool}`: switch every reaction wheel on or off | on change | 1 |
| `panel/hc/in/<axis>` | hand controllers (USB joysticks; the console's keyboard for now; tests) | `{"v": -1..1}` for rot_pitch (+ nose up), rot_yaw (+ nose right), rot_roll (+ right), trans_right, trans_up, trans_fwd | on change | 0 |
| `cmd/rotate` | cockpit logic | `{"pitch", "yaw", "roll"}` −1..1, after a 0.05 deadband. With SAS on, the cockpit switches SAS off while this is off centre and back on when centred (KSP does so for keyboard steering, not for kRPC inputs) | on change | 0 |
| `cmd/translate` | cockpit logic | `{"right", "up", "forward"}` −1..1 (RCS translation) | on change | 0 |
| `cmd/speed_mode` | cockpit logic | `{"mode": "orbit"|"surface"|"target"}`: the navball's speed reference, which SAS PRO and RETRO follow | on change | 1 |
| `cmd/antenna` | cockpit logic | `{"on": bool}`: deploy or retract every deployable antenna | on change | 1 |
| `cmd/science` | cockpit logic | `{"index", "action": "run"/"transmit"/"dump"/"reset"}` or `{"all": true}` (run every experiment that can run) | event | 1 |
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
| `cmd/station` | cockpit logic | `{"to": "cm"/"lm"}`: the crew goes across into that capsule while it has seats (docked only), then the craft is flown from it, switching vessels when the capsules are apart. `{"to", "controls_only": true}`: the controls only, sent again while the game flies the other capsule (after a separation, or "control from here" in the game) | event | 1 |
| `cmd/met_reset` | cockpit logic | `{}`: MET RESET held 2 s: the mission clock starts again from the vessel flown: MET becomes its own mission time (`vessel_met`), not 0 | event | 1 |
| `cmd/game` | cockpit logic | `{"quicksave": true}`, `{"quickload": true}` or `{"revert": true}` (back to the launch, when the game allows it) | event | 1 |
| `pad/uplink` | Mission Control: the MCC's CAPCOM console, or the flight-dynamics service for a solo pilot (never both in one flight) | `{"tig_met": s, "dv": [prograde, normal, radial]}`: a PAD read up to the crew. The burn computer shows it blinking until the crew accepts it | event | 1 |
| `cmp/pad` | cockpit logic | `{"tig", "dv", "armed", "state": "idle"|"ready"|"armed"|"burn"|"done"}`: the PAD loaded in the burn computer | on change | 1, retained |
| `cmd/hold` | cockpit logic | `{"on": true, "pitch", "heading"}` (degrees, against the horizon) or `{"on": false}`: ATTITUDE HOLD, kRPC's autopilot holding that attitude, roll free. Sent only with SAS off and the stick centred. The mock plant ignores it | on change | 1 |
| `cmd/sas_mode` | cockpit logic | `{"mode": "stability"|"prograde"|"retrograde"|"normal"|"antinormal"|"radial"|"antiradial"|"target"|"antitarget"|"maneuver"}` | on change | 1 |
| `cam/list` | camera monitor | `{"cameras": [{"id", "name", "vessel"}]}`: the cameras the monitor can show (those the JRTI mod streams; name: the one set in its part menu) | on change | 1, retained |
| `cam/status` | camera monitor | `{"online", "playing"}` (LWT `online: false`) | on change | 1, retained |
| `cam/select` | cockpit logic | `{"id"}`: the camera to show, or null; `{"id": null, "off": true}` with the MONITOR switch off (black screen) | on change | 1, retained |
| `cam/window/left`, `cam/window/right` | cockpit logic | `{"id"}`: the camera each window shows (the current capsule's `cm_left`… camera on `cam/list`), or null through a move between the CM and the LM | on change | 1, retained |
| `cw/state` | cockpit logic | `{"master_caution": bool, "master_alarm": bool, "active": ["LOW FUEL", …], "unacked": [...]}` | on change | 1, retained |
| `cockpit/power` | cockpit logic | `{"on": bool}`: the cockpit has power (electric charge left, and the breaker in) and is not in the blackout of a move between the CM and the LM; off, every panel is dark and its inputs dead | on change | 1, retained |
| `cockpit/lighting` | cockpit logic | `{"cabin": bool, "backlight": bool}`: the LIGHTS panel's cockpit lights, off without power (the console page brightens its plates and lights its legends) | on change | 1, retained |
| `panel/eng/out/fdai` | cockpit logic | `{"needles": "prograde"|"retrograde"|"off", "error_scale": 5|50, "markers": bool}`: how the FDAI page draws, from the FDAI controls on the ATTITUDE panel | on change | 1, retained |
| `gateway/status` | plant (gateway or mock) | `{"connected", "plant": "ksp"|"mock", "scene", "vessel", "paused"}` (scene: `flight`, or the game's scene without a ship, `editor_vab`, `space_center`, ...: no alarm in `editor_*`) (LWT `connected: false`) | on change + 5 s | 1, retained |
| `sim/reset` | SimSup page (RESET SIM) | `{}` | event | 1 |
| `sim/failures/<id>` | SimSup | `{"on": bool, ...parameters}`: catalogue and who applies each in [simsup/README.md](../simsup/README.md) | on change | 1, retained |
| `sim/freeze` | SimSup | `{"on": bool}`: the instructor's pause (the gateway pauses KSP; the mock stops), apart from the crew's PAUSE | on change | 1, retained |
| `sim/load` | SimSup | `{"save": name}`: the gateway loads that KSP save | event | 1 |
| `fd/status` | flight-dynamics | `{"text", "ok"}`: what the last SOLO request gave ("CIRC APO 1004.2", "RDV: NO TARGET") | on change | 1, retained |
| `mcc/poll` | MCC, FLIGHT console | `{"open", "question", "met"}`: the go/no-go poll ([panels/virtual/mcc/README.md](../panels/virtual/mcc/README.md)) | on change | 1, retained |
| `mcc/poll/<role>` | MCC, that console | `{"go": bool, "met"}`: its answer | on change | 1, retained |
| `mcc/history/get` | an MCC page | `{"id"}`: asks the recorder for the flight so far | on connecting | 1 |
| `mcc/history/<id>` | mcc-data | `{"flight", "launch": {"lat", "lon", "body", "t"} or null, "columns": {"t", "ut", "alt", "radar", "apo", "peri", "spd", "vorb", "vs", "q", "g", "lat", "lon", "thr", "thrust", "mass", "heat", "ec", "body"}, "events": [...]}`: one sample a second (t: MET; ec: charge, 0..1), as columns | on request | 1 |
| `mcc/events` | mcc-data | `{"t", "text", "kind"}`: a flight event as it happens (kind: milestone, stage, engine, comm, alarm) | event | 1 |
| `mcc/bodies` | mcc-data, from KSP | `{"ut", "bodies": {"<name>": {"radius", "mu", "rotation_period", "atmosphere", "soi", "parent", "orbit": {"a", "e", "i", "lan", "argp", "m0", "epoch", "period"} or null, "subsolar": {"lat", "lon"} at ut, "highest": its highest terrain (m), once mapped}}}` | 60 s | 1, retained |
| `mcc/maps` | mcc-data | `{"<body>": {"file", "radius", "min", "max", "ocean", "size"}}`: the relief maps made of the bodies of the game flown (a body's map has its radius in this game; another install's map of the same name is left out), served as `maps/<file>` | on change | 1, retained |
| `mission/clock` | plant (gateway) | `{"launch_ut", "vessels": [names]}`: where MET starts and the vessels of this flight (a vessel made by an undocking, or a save of one, keeps the mission's MET); read back by a restarted gateway; mcc-data starts a new flight when launch_ut moves | on change | 1, retained |
| `mcc/data/status` | mcc-data | `{"online", "krpc", "mapping": {"body", "progress"} or null}` (LWT offline) | on change | 1, retained |
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
