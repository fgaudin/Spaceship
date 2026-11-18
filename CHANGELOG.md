# Changelog

What changed and why, in more detail than the commit messages. Newest first. Topic and panel names are those of
`protocol/topics.md` and `protocol/panels/`.

## 2026-11-18 — panel review: fewer repeats, ASCENT and ORBIT panels, power from the battery, LIGHTS

After flying the panels (NOTES.md): an instrument that repeats another, or needs a selector to be read, goes.

- **C&W:** PERI LOW and SOI CHANGE are gone (the ORBIT panel and the event timer show them); 0.05 G and CONTACT
  moved into the grid in their place, so the separate FLIGHT EVENTS box is gone too.
- **ASCENT replaces DISPLAYS:** DISP A and its selector are gone; altitude (km), surface speed and g have their own
  displays, next to MET and the thrust bar. **ORBIT** (new, on the SOLO module next to PAD REQUEST, `lab` bus):
  apoapsis, periapsis, and the inclination taken from NAVIGATION.
- **ENGINE:** THRUST LIMIT is a knob (new item type `knob`: 0 to 1 over 270°, drag, wheel or arrows); stage Δv and
  TWR moved here from PROPELLANT · STAGE (now PROPELLANT), and STAGE FUEL from DISPLAYS. Their maths
  (`cockpit/performance.py`) is shared with LANDING.
- **ABORT fires the abort group, and only that.** ABORT MODE and its four sequences (staging, forced SAS and RCS…)
  are gone: what happens is what the craft's builder wired to the abort group. MCC RETRO no longer advises a mode.
- **ATTITUDE:** the NAVBALL lamps are gone: SPEED REF has an LED (new: `led` on a rotary) that blinks while the
  game's reference is not the knob's. GEAR moved to LANDING, LIGHTS to the LIGHTS panel, CB MAIN BUS is gone.
- **Power follows the electric charge.** Out of charge, every lamp, display and cockpit light goes dark, the
  throttle is cut, the sticks released and the inputs ignored, as CB MAIN BUS off did; `cockpit/power` says so
  (flight dynamics now reads it instead of the breaker). The `cb_main` input still works, for a breaker that may
  come back on the hardware.
- **LIGHTS** (new, overhead): CABIN and BACKLIGHT are the cockpit's own lights (`cockpit/lighting`: on the console
  page the plates brighten and the legends glow, so the switches finally do something there); EXTERNAL is the
  craft's lights, as the old LIGHTS switch.
- **SYS:** FUEL CELL switch with its LED (gateway: the stock fuel cells' resource converters, `cmd/fuel_cell`,
  `tlm/vessel.fuel_cell`; the mock has one giving 1.5 EC/s); RECOVERY gets the ablator left (Ablator in
  `tlm/resources`) and the outside temperature (`tlm/thermal.outside`, °C); TIME WARP and GAME merged into one panel,
  and quick save and quick load no longer need SAVE ARM, which is gone.
- **LANDING:** TO GROUND, BRAKE HEIGHT and the BRAKE lamp are gone; HOVER TIME shows how long the stage can hold the
  craft still (its Δv over the local gravity; dashes when the engines cannot lift it). GEAR is here now.
- **RDV:** the RENDEZVOUS plate is gone with GATE, OVERSPEED and LOS RATE (the CLOSING caution still watches the
  braking gate). The docking plates are renamed for what they show and rearranged: ROTATION (was DOCK 1) shows the
  yaw, pitch and roll rates (°/s, the angles differentiated over game time, so their signs agree with the angles)
  instead of ALIGNED; TRANSLATION (DOCK 2) reads in docking terms, LATERAL, VERTICAL and RANGE (along the port's
  axis), each with its RATE: the range rate is now negative while closing (it was shown as a positive closing
  speed), so the three rates all say how fast the figure above them changes; DOCKING
  (DOCK 3, next to TARGET) the range (with the KM LED) and closing speed to the target vessel. The module is 2 × 2 U
  now. Only panel ids and titles changed: the controls and their topics are the same.
- Layout check: 0 issues (TARGET and DOCKING controls moved a few mm apart: the overlap seen now and then on TARGET
  was a real near miss). Cut templates: the C&W overlaps are gone; ASCENT's wider real digits are reported.
- Tests: the cockpit unit tests follow (63, new: power from charge, lights, fuel cell, outside temperature and
  ablator, docking rates, hover time, ORBIT); `tests/e2e_*` and the ascent rehearsal read the new displays; the KSP
  landing test brakes on its own computed height instead of the BRAKE lamp. Not run against KSP or the mock yet.

## 2026-11-17 — laser-cut templates of the faceplates

- **`panels/cut/make_templates.py`** makes the faceplates' cutting templates from the panel definitions, so the
  hardware follows the virtual console instead of being redrawn: one SVG per panel at its real size (99 × 99 mm for
  1×1 U) and one per module with its panels in their slots, in mm, layers in LightBurn's palette colours
  (legends orange, readable on a dark background too; holes blue; outline red; guides green and yellow with no
  output), set in `footprints.json`. Python 3 only.
- **Footprints in `panels/cut/footprints.json`**, one per item type: the cutout, what shows on the face, the body
  behind, and extra holes (anti-rotation tabs, mounting holes). Every value is a placeholder for a typical part
  (6 mm mini toggles, 12 mm toggles with flip covers, 18 × 12 mm push buttons, 0.36" digits, 3 mm LEDs on a
  4.5 mm grid, 3/8" rotary selectors, a 30 mm slide pot…), to be measured and replaced when the parts are in hand.
  An item's `at` stays the centre of its block (LED, component, legend), as in the console.
- **Legends in a single-stroke font** drawn by the script (scored lines, as on engraved panels), so they import
  into LightBurn as paths with no font to install; SVG text is an option. Push-button, annunciator and key legends
  go on the caps and lenses, so they are on a guide layer, not engraved.
- **Layout checks** with the real sizes: out of the faceplate or in the title band, overlaps on the face, bodies
  colliding behind, a control on a mounting screw. With the placeholders, 17 issues: the guarded toggles' covers,
  the wider 7-segment displays and the C&W grid do not fit where the virtual console draws them. Nothing is moved
  yet; that waits for the real parts.

## 2026-11-17 — panel clearance, module edges; the bench goes to SimSup; a side column on the console

- **1 U is a slot, not a panel.** A faceplate is built 0.5 mm smaller on each side for clearance (a 1×1 U panel is
  99 × 99 mm, neighbours 1 mm apart); control `at` positions are from the faceplate's corner. Every control still
  fits (layout check: 0 issues). `protocol/panels/README.md` updated.
- **Module edges.** A module fills its slots exactly and draws nothing outside them: its frame used to be drawn
  1.5 mm outside, so neighbouring modules overlapped and covered each other's panels (invisible while the frame was
  black). A thin light edge just inside each module, in the panels' clearance, shows which panels belong together.
- **The instructor bench is gone** from the console page: its failures (engine out, battery short, telemetry
  freeze) were already in SimSup, which logs them for the debrief; the bench published `sim/failures/*` behind its
  back. RESET SIM (`sim/reset`) moved to SimSup's Flight box, next to FREEZE, and asks for confirmation.
- **Side column.** The keys and mouse help and the bus sniffer were under the console, out of sight since the wheel
  zooms instead of scrolling. They are now in a column on the console's right: the help at the top, the sniffer
  filling the rest when "bus" is on. Its left edge drags to widen it (so bus lines stop wrapping); double-click
  restores the default width, which is kept in the browser. Under 900 px wide the column goes under the console.

## 2026-11-17 — glass modules in the console; MCC consoles of a standard size

- **FDAI, MFD and CAM in the console**, as glass modules (`board: raspberry-pi`): a panel with a `screen` (page,
  inches, visible size in mm, resolution in px). The console shows the live page at the screen's resolution, scaled
  to its size: FDAI and MFD 2×2 U with an 8" 4:3 screen (1024 × 768), CAM 3×2 U with a 10.1" 16:10 one
  (1280 × 800). `?embed=1` drops a page's top bar and notes and fits it to the screen; Esc inside it goes back.
- **Console layout:** MAIN is 8 × 5 U (FDAI and MFD left of ENG, CMP under ENG, RDV and CAM on the right, a free row
  at the bottom); OVERHEAD and LOW 8 × 2. A zone can now be given a `size`, so its free places show.
- **Fix:** the console's fixed plates had broken the FDAI, MFD and CAM pages' own plates (no padding, no title);
  the fixed geometry now applies to console panels only.
- **The console is one zoomable view**, replacing the overview and module view: the wheel zooms around the pointer
  (over a rotary knob, the wheel still turns the knob; over a glass screen, the page passes it on), dragging pans
  (middle button anywhere, left button off the controls), every control works at any zoom, so several modules can be
  flown at once. Double-click a module (or `#<module>`) fits it, Esc fits the whole console; Esc no longer clears
  the keypad (Backspace does).
- **MCC:** every console is one standard screen of 1200 × 800 with its boxes on a fixed 3 × 2 grid of tiles; a box
  longer than its tiles scrolls. A laptop holding several consoles shows them side by side, all at the same zoom,
  in the number of columns that draws them biggest. Checked: the multi-console poll and banner tests pass.

## 2026-11-16 — the console: modules and panels at their physical size

- **Units.** 1 U = 100 mm. A *panel* is one faceplate of W×H U; a *module* is one board (Olimex ESP32-POE, one PoE
  cable, one file) carrying one or more panels, swapped or taken to the bench as a unit. Format and how to change a
  layout: `protocol/panels/README.md`.
- **Definitions.** `protocol/panels/<module>.json` now lists `panels` (size and place in U, bus namespace) whose
  controls have fixed `at` positions in mm, instead of `sections` that flowed. Positions and sizes were measured from
  the old layout: every panel came out 1×1 or 2×1. Nearly empty sections were merged (ANTENNA into LINK, DOCKED into
  DOCK 3, ENGINES with ABORT), and the PAD displays lost their labels (the field buttons say the same).
  A panel's topics are its own (`"bus"`), so moving it to another module changes nothing on the bus.
- **One console page.** `protocol/panels/console.json` places the modules in three zones (overhead, main, low); the
  page draws them all, live, zoomed to fit; a click opens a module at real size with its controls usable, Esc goes
  back, `index.html#<module>` opens one directly (`?panel=<id>` still works). Nothing reflows: on a phone the same
  layout is just smaller. A grid checkbox draws 10 mm squares; misplaced controls, overlapping panels or modules
  are outlined in red and counted in the top bar. The seven I/O tabs became one CONSOLE link.
- Each virtual module has its own bus connection, heartbeat and will, as its board will.
- `PLAN.md` (mechanical: 100 mm U instead of the Dzus grid; panel and module) and `PANELS.md` updated.

## 2026-11-16 — shared top bar and bus connection for the web pages

- `panels/virtual/shell.js` builds every page's top bar (brand, bus light, navigation) from one list of pages; each
  page's HTML keeps only its own status items. Adding a page was editing five headers; now it is one line.
- `panels/virtual/bus.js` is the one MQTT connection helper (broker address, client id, reconnection, the light),
  used by the I/O panels, FDAI, MFD, the camera monitor, SimSup and MCC. FDAI and MFD became ES modules for it.
- Checked in a browser: every page loads without errors, with the navigation and the light; MCC's multi-console
  poll test passes.

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
