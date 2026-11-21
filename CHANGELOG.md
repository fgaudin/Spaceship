# Changelog

What changed and why, in more detail than the commit messages. Newest first. Topic and panel names are those of
`protocol/topics.md` and `protocol/panels/`.

## 2026-11-21 — STATION moves the whole crew; the engines follow STATION; one mission clock

- **A bill of materials** (new `panels/bom/make_bom.py` → `panels/bom/BOM.md`), generated from the module definitions:
  every control and indicator by kind and colour with the modules it is on, the driver chips as the firmware places
  them, boards (an ESP32-POE2 also beside each glass module that has controls: cam, fdai), screens, PoE ports and the
  faceplates' acrylic. An estimate: no spares, wiring, connectors, frames or supplies. With a cost estimate, low
  (generic parts) and high (branded, EU distributors), from unit prices in `panels/bom/prices.json` to correct as
  real prices come in.

- **Engine rosette: no false ENG FAIL docked, and engines placed in the right frame** (gateway `parts_watch.py`, cockpit
  `engines.py`). Found in the docked stack (`full-extracted`, flown from the CM): the centre lamp red and ENG FAIL on,
  and the Cheetah on the ring's bottom lamp. The lander's Terrier, held shut down by engine sharing, had burned under
  the same vessel name and stage number, so the cockpit took it for an engine lost: `tlm/engines` now marks such an
  engine `held`, and the cockpit leaves it out (not shown, not lost). The positions were read once, when the part
  streams were built, in the frame of the part flown then; after a STATION switch they were in the wrong frame (the
  Cheetah 32 m off an axis it sits on): they are streamed now. Checked in KSP: the Cheetah white in the centre, no
  ENG FAIL.

- **The engine matrix became a rosette; BURNING is gone; STAGE and STAGE ARM swapped** (`protocol/panels/eng.json`,
  cockpit `engines.py`, `panels/engine_panel.py`; `eng_rosette` replaces `mx_eng` and `disp_eng_on`). A 9 × 9 matrix
  was hard to source and not pretty; one lamp per engine does not fit every rocket. Now 9 RGB lamps behind 10 mm
  frosted discs, a centre and a ring of 8: an engine on the axis (within 30 % of the outermost one's distance) lights
  the centre, the others the ring lamp nearest their angle; lamps shared by several engines show the worst state
  (red, amber, green, white). White, lit but idle or next to ignite, shows how many engines the stage has. The
  alarms count the engines themselves, not the lamps. BURNING was the count of green lamps. The faceplate tool
  (real part sizes, `panels/cut/`) needed the rows spread: STAGE at 73 mm, the rosette at 126, ABORT at 176. The
  console's budget counts addressable RGB LEDs (one GPIO; 20 mA a colour, 60 mA white), the firmware drives them
  with Adafruit NeoPixel (GPIO 33).

- **One command for the stack: `./capsule start [ksp|mock]`, `stop`, `restart`, `rebuild`, `status`, `logs`.** Starting
  a plant stops the other (both write `tlm/*`); the mock plant moved to a compose profile of its own (`mock`), so
  a plain `docker compose up` no longer starts it beside the KSP gateway.
- **The liftoff flight test is in the repository** (`tests/mission/liftoff.py`), its cutoff anticipation shortened
  (0.35 s of the apoapsis's rise cut 5 km short at TWR 11; 0.1 s now).
- **`firmware/tests/test_generated.py`**: fails when `firmware/generated/` no longer matches `protocol/panels/`.
- **A slow staging is broken down in the gateway's log** (activate_next_stage, settle, engine sharing), to find where
  the 0.7-0.8 s of GAPS C4 still go.

- **A draft of the panel modules' firmware** (new `firmware/`). One generic firmware for the ESP32-POE2 boards,
  the same node as a module of the virtual console: raw inputs out (debounced switches and buttons, selectors,
  levers on ADS1115, the keypad), outputs drawn from the cockpit's topics (lamps through MCP23017, 7-segment, bars and
  the matrix on a MAX7219 chain, alphanumerics on HT16K33, the buzzer), blinking locally, status and will as the
  console's. `tools/gen_module.py` places each control of `protocol/panels/<module>.json` on the module's chips and
  writes the header the build uses, a wiring table (`generated/<module>/WIRING.md`) and a PlatformIO environment per
  module. Its config hash is the console's (checked on two modules). It compiles for every module (PlatformIO,
  Arduino core 2.0.16); it has not run on a board: the pins and the colour matrix are to check (README).

- **A Simpit gateway, as a fallback plant** (new `gateway-simpit/`, proof of concept). If kRPC ever stops being
  usable, KSP can be reached through the Kerbal Simpit plugin (2.3.1, already in the stock install): the gateway plays
  the Arduino on its serial line (a tty0tty pair or two USB-serial adapters: KSP's Mono cannot open a socat pty,
  "Inappropriate ioctl for device", found in KSP) and publishes the same `tlm/*` and
  takes the same `cmd/*` for what Simpit carries: altitude, speeds, orbit, attitude, flight status, action groups,
  stage Δv, resources; throttle, stage, abort, the switches, SAS mode, rotation and translation, custom action groups,
  time warp. No UT or MET, parts, docking geometry or nodes. The protocol was taken from the Arduino library bundled
  with the mod (COBS framing, XOR checksum, SYN / SYNACK / ACK with the library version). Tested against a simulated
  plugin, also over a real pty through the gateway's own loop; not yet against KSP (Settings.cfg's PortName and a
  restart).

- **RDV TGT on the ground gives the liftoff** (GAPS C17; `flight-dynamics/planner.py`). From the Mun the liftoff time
  (the target's phase) and the launch azimuth (its plane) had been read from telemetry. Landed with a target in
  orbit, RDV TGT now reads up a PAD whose TIG is the liftoff, counted down by the EVENT TIMER on TIG, with the Δv of
  the ascent and the CIRC, and on the FLIGHT DYNAMICS display the azimuth for HEADING and the apoapsis to cut off on
  (`LIFT AZ088 AP 29`): no new control. A direct rendezvous: the apoapsis 1 km under the target's orbit, timed so the
  target is there when we are. The first version aimed at a parking orbit and a transfer: flown in KSP, the liftoff
  came out 9° off the phase it wanted, which beside a target at nearly the same height meant a 64 h wait for the
  transfer. The ascent model's constants come from that flight (cutoff 1.6 km above the site climbing 2.5°, 987 s
  and 138° from liftoff to the apoapsis); the model gives 986 s and 137°. RDV TGT in orbit within 25 km of the target
  now says CLOSE IN instead of such a wait. Airless bodies only. Unit tests in `flight-dynamics/tests/test_planner.py`.
- **The throttle lever is its own controller; THRUST % and TWR MAX on ENGINE** (GAPS C17; `protocol/panels/thr.json`,
  `eng.json`, `console.json`; cockpit `panels/engine_panel.py`). The lever will be built separately (USB, like the
  hand controllers): the virtual one moved to a THROTTLE module in a CONTROLLERS zone under the left window, against
  MAIN (a new `"align": "inner"` for side zones), on the same bus and topic. In its place on ENGINE, THRUST %: the
  thrust now of the lit engines' rated thrust, so the lever and THRUST LIMIT together (lever up, limit 80 %: 80); an
  engine giving less than it should reads low. TWR MAX beside TWR: the TWR at full throttle, also
  with the engines off (the braking a landing can count on; TWR reads 0 then). GIMBAL LOCK moved to the top row.
  The lever also stuck short of 100 % on a fast move: a position skipped by the 50 ms publish limit was only sent
  if the browser fired `change`; it is now sent when the 50 ms are up.

- **Staging no longer pauses telemetry** (GAPS C4; gateway `ksp/parts_watch.py`). After a staging every part stream
  was rebuilt on the main loop, during which nothing went out (0.7 s on the asparagus rocket, 0.1–0.2 s on the
  50-part Acapello). A fresh PartsWatch is now built on another thread (kRPC's client serialises the two threads'
  calls) and swapped in between two cycles; meanwhile the old streams are read, those of the parts that left reading
  0 or nothing (the solar panel and parachute readers now guard them like the others). A staging during a rebuild
  drops it and starts another. The first read after a bind no longer reads the parts twice. Measured in KSP on the
  Acapello without staging: swapped after 0.2 s, the slowest read meanwhile 18 ms. Unit tests in
  `gateway-ksp/tests/test_stage_propellant.py`.

- **Mission Control's text loop removed** (GAPS C9; `panels/virtual/mcc/`): it would not be used (a voice loop comes
  later). The footer's line, FLIGHT's LOOP box, CAPCOM's "PAD read up" note and the `mcc/loop/<role>` topic are gone;
  FLIGHT's alarms and poll take the freed column.

- **RDV: ROTATION above TRANSLATION** (`protocol/panels/rdv.json`): the two docking panels swapped places, at the
  user's request; ROTATION is now top left, TRANSLATION under it.

- **SPEED on TGT is the speed relative to the target** (GAPS C17; cockpit `performance.py`). With SPEED REF on TGT, the
  total speed in FLIGHT DATA read the surface's, so the relative speed (to null before closing) was on no display; the
  RDV panel's CLOSING is only its part along the line of sight. SPEED now reads `tlm/target.rel_v` on TGT, as KSP's
  navball does, and the surface's without a target; H/S and V/S stay the surface's.

- **SAS PRO and RETRO bring the speed reference back to the knob's** (GAPS C19; cockpit `panels/engine_panel.py`). KSP
  changes the navball's reference by itself, and a retained knob cannot re-send the position it is on: in the Mun
  descent the knob was on SURF, the game on ORBIT, and SAS RETRO would have held the orbit's retrograde. The cockpit
  does not re-send it on its own (it would fight KSP's switching); the press on PRO or RETRO, the moment it matters,
  sends `cmd/speed_mode` with the knob's reference before `cmd/sas_mode`, when the game's is another. Otherwise, and
  for STATION, the crew turns the knob away and back. Unit test in `cockpit-logic/tests/test_logic.py`.

- **Stage Δv no longer sticks at 0** (GAPS C22; gateway `ksp/parts_watch.py`). The tanks of the stage were chosen only
  when the stage number changed, from the engines lit at that moment. Chosen while none read lit (a bind or a staging
  read before KSP reports the engine on), the list stayed empty: no stage propellant, and stage Δv read 0 through the
  whole second Mun ascent. Reproduced in KSP by binding with the lander's engine shut down and lighting it after (0 m/s;
  628 m/s with the fix). The tanks are now chosen again whenever the set of lit engines changes (their `active` is
  already streamed: no extra calls). It was not the save load: three loads of `full-landed` in a row, and a reload
  between two burns, all read right. Unit test `gateway-ksp/tests/test_stage_propellant.py`.

- **One mission clock for the flight** (GAPS C12; gateway, new `ksp/mission_clock.py`). KSP keeps a mission time per
  vessel and starts a vessel made by an undocking at 0: in the Mun mission the lander's MET went from 08:33 to 00:00,
  so PADs keyed in MET, the event timer and Mission Control's history (which starts a new flight when MET goes back to
  0) followed whichever vessel was flown. The gateway now keeps the launch's UT and sends `tlm/time.met` = UT − it,
  with the game's own as `vessel_met`. On the pad the clock follows the vessel; each vessel bound afterwards carries on
  the flight when it is a fragment of it (bound just after our own undock, staging or STATION switch, or named in the
  flight, and started after the launch) or the same vessel; anything else starts a new flight. The other capsule's
  vessel is adopted into the flight as soon as it is apart, so its own save keeps the mission's MET even if it was
  never flown. The record is retained on `mission/clock` (a restarted gateway, or KSP restarted, carries on);
  mcc-data starts a new flight when its launch moves. Checked in KSP: undocking into the lander, MET 13.32.51 carried
  on (the vessel's own: 6 s); the lander's own save, MET 09.48.19 from the launch (its own: 4493 s). Unit tests
  `gateway-ksp/tests/test_mission_clock.py`, `mcc-data` recorder test.
- **MET RESET** (CAM panel, beside MET, `cmd/met_reset`): held 2 s, the mission clock starts again from the vessel
  flown, for the case the rules get wrong (a save of another flight whose vessel has a name of this one). A short press
  does nothing: the guard without a second control. It does not zero MET: MET becomes the flown vessel's own mission
  time, so a second reset on the same vessel shows no change. The button sits at 174.3 mm, 2.7 mm above MET's `at`,
  so that it lines up with the digits rather than with the block of digits and legend. A PAD keeps its moment in UT when the clock is set again: the
  burn computer moves its MET TIG by the clock's change.
- **A gateway restart no longer runs commands before a vessel is bound** (found while adding the clock: a waiting
  `cmd/*` with no vessel took the link down); only the retained `mission/clock` is read first.

- **Docked, the engine controls drive the flown capsule's engines only** (gateway, new `ksp/engine_sharing.py`). After
  docking, KSP rebuilt the staging and put the CSM's Cheetah and the lander's Terrier, which face opposite ways, in one
  stage, and ENG ARM and the throttle reach every engine: in the Mun mission the Cheetah had to be lit alone through
  kRPC (GAPS C10). Now, while the two capsules are docked, the engines on the side of the capsule not flown are shut
  down and remembered; STATION flying the other capsule swaps them, and undocked they are lit again. A capsule's side
  is found in the part tree: the docking joint is the docked port whose parent is the other port, and the parts under
  it are one capsule's. Checked on the slow telemetry cycle, at once after STAGE (an engine a staging lit goes out
  before the throttle reaches it) and after a STATION move; an engine SimSup failed is never relit. NEXT STAGE leaves
  the other capsule's engines out; `tlm/station` gains `held`. Unit tests `gateway-ksp/tests/test_engine_sharing.py`;
  checked in KSP on the docked CSM and lander: CM flown, Cheetah lit and Terrier held; STATION LM, the reverse; back.
- **NEXT STAGE shows every separation** (GAPS C11): DECOUPLE also lights for a docking port whose decouple node is in
  the stage (the launch escape tower on the CM's nose port showed SOLIDS alone), and FAIRING for covers thrown off by
  parts other than engines (`ModuleJettison`: the SM-25's doors showed a dark stage). Engine shrouds are left out: they
  do not come off when the engine is staged. Checked in KSP: the tower's stage SOLIDS + DECOUPLE, the SM-25's FAIRING.
- **EC/s is measured over UT** (GAPS C13): over mission time it froze, since MET stands still on the pad and starts
  again at 0 for an undocked vessel (−198.9 EC/s on the pad with the charge not moving), and jumped on a vessel change.
  It now starts again on another vessel or a clock going back. Test `test_charge_rate_over_universal_time_and_per_vessel`.
- **A burn computer field button always selects its field** (GAPS C14). ENTR moves on to the next field, and pressing
  that field's button, as a crew does, toggled it off: the next keys went into TIG (keying a DOI gave TIG 00.01.30 and
  Δv 0, with no ERR). Pressing the selected field's button now starts its entry again; CLR leaves a field.
  Test `test_the_field_entr_moved_to_can_be_pressed`.
- **STATION took only one kerbal across per move**, whatever the seats: turning it to LM with two in the CM left one
  behind, and turning it back could never empty the lander (it only swapped one kerbal each time). The gateway asked
  kRPC for every transfer from one crew list read before the first: after a transfer those crew objects are stale,
  the next `transfer_crew` failed inside kRPC (NullReferenceException) and the error was lost. The gateway now reads
  the source capsule's crew again before each kerbal, waits 0.5 s between two, tries once more on a failure and logs
  it. Found by the full Mun mission flown from the panels; checked in KSP: two kerbals CM → LM in one move, and back.
- **The Mun was mapped over and over** (the wall's MAPPING reached 100 % and started again: 41 times in a day) once
  maps of two installs sat in `maps/`, a JNSQ Mun of 400 km next to stock's of 200 km. mcc-data listed the maps by
  body name only, so the JNSQ file, sorted last, hid the stock one, and the stock Mun's was always "missing". Each body
  now gets only the map of its radius in the game flown (none when that one is not made yet), the check for a missing
  map looks at the files on disk, and `mcc/maps` is published once the bodies are read. The wall gets the stock Mun's
  map again instead of the JNSQ one. Unit test `mcc-data/tests/test_maps.py`; checked on the running stack: stock
  Kerbin and Mun on `mcc/maps`, stock Minmus mapped once.

## 2026-11-20 — the game's bodies everywhere (JNSQ), ice and deserts on the wall's maps

- **MAIN's row 5 centred:** REENTRY · RECOVERY and SCI (SCIENCE · ACTION GROUPS) move half a U left, to [0.5, 5]
  and [2.5, 5], a 5 U row in the middle of the 6 U zone instead of a hole at [0, 5]. With STAGING · ABORT in [4, 2],
  MAIN has no free place left.
- **New: NEXT STAGE, on a new STAGING · ABORT panel** (1 × 2, `eng` bus, panel id `staging_abort`, filling MAIN's
  free place right of C&W). Six cells lit for what pressing STAGE does: ENGINES and SOLIDS it lights (solids in
  amber: they cannot be stopped), DECOUPLE, CLAMPS, CHUTES, FAIRING; all dark with no stage left. The gateway reads it
  when it rebuilds the part list after each staging (the parts of stage current − 1: engines, decouplers, launch
  clamps, parachutes, fairings) and sends it as `tlm/vessel.next_stage`; the mock from its three stages. Checked in
  KSP on an orbiting ship: stage 1, DECOUPLE alone, as the game has it.
- **ENGINE and ENGINES · ABORT regrouped** around it: STAGING · ABORT reads top to bottom NEXT STAGE, the stage
  number, STAGE ARM and STAGE, then the engine status matrix, BURNING and THRUST, ABORT ARM and ABORT (two arm-then-press
  pairs, one above the other); ENGINE (2 × 1) keeps the thrust (ENG ARM, throttle, CUTOFF, THRUST LIMIT, GIMBAL LOCK,
  stage Δv, stage fuel, TWR), spread over the room STAGE left. ENG is now a plain 3 × 2; same inputs and outputs. The
  cut templates lose three issues (the matrix in the title band, ABORT ARM off the plate, ENG ARM in ENGINE's title
  band). C&W unchanged.
- **SAS MODE follows the game instead of fighting it.** A button asks for a mode; it blinks until the game takes it,
  is asked again up to five times (KSP falls back to stability when SAS comes on, and can drop a mode set in the very
  frame its node or target appears), and then the game's mode is lit. A mode changed in the game afterwards (KSP's
  own buttons, the node deleted at the end of a burn, a target lost) is followed: before, the cockpit sent the last
  button's mode five more times and left its lamp blinking. With SAS off the lamp shows the mode SAS will take, the
  last one the game held, and SAS coming on asks for it again. The gateway remembers the game's mode too, not the
  last command, so SAS coming on does not bring back an old mode (`follow_sas_mode`, after each telemetry read).
- **WHEELS on ELECTRICAL** (`sys` bus, `wheels`, LED `led_wheels`): switches every reaction wheel on or off, the
  pods' own included, so SAS has only RCS to turn with (`cmd/wheels`, new; `tlm/vessel.wheels`, null with no wheel on
  board). The game wins, as with FUEL CELL: the LED blinks while the switch and the game disagree, and since KSP starts
  with the wheels on, it blinks until WHEELS is switched on. ELECTRICAL is laid out again around the three switches:
  SOLAR, FUEL CELL and WHEELS 30 mm apart along the bottom (x 18, 48, 78; 80 put WHEELS on the mounting screw),
  CHARGE above SOLAR and raised to the displays' middle (y 35), EC and EC/S centred over the two right switches.
  No authority knob and no saturation lamp: kRPC 0.7 has neither, and stock wheels do not saturate. The mock
  plant keeps the state but draws no charge for it. Not yet checked in KSP.
- **The solo pilot's PADs use the game's bodies:** the flight-dynamics planner took stock's Kerbin (600 km, μ 3.53e12)
  and stock's moons, so in JNSQ every PAD was wrong and INJECT aimed at a Mun 12,000 km out instead of 91,000. It now
  takes the body flown from `tlm/orbit` and the moons' orbits from `mcc/bodies` (checked in KSP: the Mun and Minmus
  where the game has them, to 0.001°). The safe periapsis is the atmosphere's top, or for an airless body the highest
  terrain mcc-data mapped plus a tenth (`"highest"` in `mcc/bodies`). INJECT works from whichever planet the moon
  orbits. Stock's figures stay for the mock plant.
- **`tlm/orbit` carries the body's `mu` and `radius`** (gateway and mock plant): the cockpit's local gravity, so TWR,
  hover time and the like, no longer come from stock's table.
- **GAME in the console's side column:** how fast KSP runs, game seconds per real second with the warp taken out,
  over the last 3 s of `tlm/time`: green from 0.95×, amber from 0.8×, red under (KSP's frame rate itself is not
  available through kRPC). Checked against kRPC's own clock: 0.67× and 0.68× with the two windows streaming.
- **The console page takes half the CPU it did:** the FDAI ball, drawn pixel by pixel, was redrawn on every screen
  refresh whenever the smoothed attitude moved by a hundredth of a degree, most of a core on its own. It is now
  redrawn at most 20 times a second and for a change of a tenth of a degree (a third of a pixel), and what never
  changes per pixel (its place on the ball, shading, edge) is computed once. Measured in Chromium over 10 s with the
  ship turning: 9.1 s of work before, 4.8 s after.
- **Left Alt shows what each module asks of its board**: inputs, analog inputs, lamps, display rows and characters,
  the driver chips (MCP23017, MAX7219, HT16K33, ADS1115), the ESP32 pins and the power in flight and at lamp test,
  against the ESP32-POE's 4 W (red when over); the total PoE power at the top left. Assumptions in
  `protocol/panels/hardware.json`, sums in `panels/virtual/budget.js`. SimSup and the cut templates now skip JSON
  files in `protocol/panels/` that are not modules. The I/O modules are now ESP32-POE2 boards (on the bench: a PoE
  injector): their 5 V rail gives 7.5 W to the displays and lamps, the ESP32 and Ethernet having a 3.3 V rail of their
  own. Lit buttons are taken as 12 V lamps on the board's 12 V rail (18 W), through ULN2803 drivers; annunciator
  cells as light boxes with two plain 15 mA LEDs, on 5 V; each rail is checked against its own limit. Every module fits in flight; at lamp test only RENDEZVOUS ·
  DOCKING goes over, on the 5 V rail (its 65 display rows).
- **Left Alt also counts the modules** (top left of the console): the boards to build, the windows (bare glass)
  left out, split into I/O and glass. Today: 13 modules, 11 I/O and 2 glass.
- **New panel: ATTITUDE HOLD** (1 × 1, `eng` bus): a pitch and a heading on two knobs (whole degrees, shown on PITCH °
  and HDG °) and a HOLD switch; with HOLD on, kRPC's autopilot holds that attitude, roll free (`cmd/hold`, new; the
  gateway reports `hold` in `tlm/vessel`, and the cockpit sends the command again if a restarted gateway forgot it).
  It holds only with SAS off and lets go while the rotation stick is off centre. HOLD's LED is steady within 3° of the
  set attitude, blinking while turning there or unable to hold. Knobs take new options (`scale`, `steps`, `nudge`,
  `readout`), in the virtual console and the cut templates. Checked in KSP on the pad (engaged, targets set, LED
  blinking 5° off target); not yet flown. A hold the game refuses is logged and reported, never a lost link (the first
  version called `engage()`, which kRPC 0.7 does not have: `engaged` is a property, and the error dropped the link).
- **FDAI, SAS MODE and ATTITUDE HOLD are one module** (FDAI, 2 × 3): ATTITUDE on top, SAS MODE and ATTITUDE HOLD under
  it, at MAIN [0, 4] and [1, 4]. FLIGHT DATA · LANDING moves one place right, to [2, 4]. MAIN's free places: [4, 2]
  and [0, 5].
- **ACTION GROUPS moves right of SCIENCE**, onto its module (SCI: SCIENCE · ACTION GROUPS, 3 × 1). MAIN's sides now
  go straight down to row 6 before the taper. ENG is an L (C&W, ENGINE, ENGINES · ABORT). MAIN's free places:
  [4, 2] right of C&W, [4, 4] right of FLIGHT DATA · LANDING, [0, 5] left of REENTRY · RECOVERY.
- **FLIGHT DATA · LANDING: one 3 × 1 panel on its own module** (`lnd`, at MAIN [1, 4], panel id `landing`), merging
  LANDING and ASCENT · DESCENT. What a landing needs is on the left (ALT and ALT REF, V and H SPEED, TIME TO IMPACT,
  HOVER TIME, the drifts, the touchdown lamps, CONTACT, GEAR), the climb's figures on the right (SPEED, G, Q). ENG is
  now a plain 3 × 2 (C&W, ENGINE, ACTION GROUPS, ENGINES · ABORT). Same inputs and outputs on the `eng` bus; SimSup's
  "panel dark" takes `landing` for the merged panel.
- **LANDING AID is now LANDING, and GEAR moves there**, from ASCENT · DESCENT, on its right beside the touchdown lamps, which now stand
  over CONTACT on the left. Same input and LED (`eng` bus).
- **ASCENT · DESCENT regrouped** without GEAR, as a 3 × 3 grid: ALT, TIME TO IMPACT and HOVER TIME on the left;
  ALT REF, G and Q in the middle; H SPEED, V SPEED and SPEED on the right.
- **MAIN's right side rearranged:** the right column is now CAMERA, LINK · ANTENNA, LIFE SUPPORT, ELECTRICAL and
  PROPELLANT, top to bottom; ACTION GROUPS and ENGINES · ABORT sit right of C&W and ENGINE. Modules: AUX is CAMERA
  and LINK · ANTENNA, RES is LIFE SUPPORT, ELECTRICAL and PROPELLANT (1 × 3), ENG holds ACTION GROUPS instead of the
  link and propellant (an L, with MAIN's free place at [4, 4] in its corner). Every panel keeps its bus, so no topic
  changes.
- **SAS MODE: ten lit buttons instead of a knob** (new module `sas`, 1 × 1 U, in MAIN left of LANDING AID, under the
  FDAI; `eng` bus, inputs `sas_stab` … `sas_mnvr`, lamps `lamp_sas_*`): turning the knob from PRO to MNVR sent every
  mode in between to the game. The chosen mode is lit, steady once SAS holds it or while SAS is off, blinking while
  the game refuses it; before any choice the game's own mode is lit. The knob leaves the ATTITUDE panel, whose bottom row
  is regrouped: SAS, RCS and RCS FINE together on the left, SPEED REF on the right. MAIN's taper
  now starts a row lower (its sides straight down to row 5), which also leaves a free place at [5, 4]. The KSP
  end-to-end scripts press the buttons (not run).
- **Speeds right after a change of sphere of influence:** the gateway measured the vessel's speeds in the frames of
  the body it was bound at, so once at the Mun they were taken against Kerbin's turning surface (12,000 m/s instead
  of 750; altitude, latitude and longitude were right). It now opens its streams again when the body changes, by an
  SOI transition or the debug menu's teleport.
- **The ascent profile works after a revert:** the recorder's first sample of the new flight took the clock of the
  new flight and the orbit of the one before (at the Mun), so the lift-off point was put on the Mun and the profile,
  which draws only the launch body, stayed empty (with a false SOI KERBIN event). A new flight now forgets the
  telemetry heard before, and the lift-off point is the last sample on the body the climb starts from (recorder and
  pages alike). A flight saved with a wrong lift-off point is corrected when mcc-data restarts.
- **Wall display, easier to read:** in the orbit view, the part of an orbit behind the body (south of the equator,
  over the disc) is thin and dashed, the vessel there a hollow ring, the apsides there dimmed; the target's orbit
  likewise. On the ascent profile, events at the same place share one label (STAGE 2 · ENGINE CUTOFF), each label
  goes where it covers no other, on a dark backing, and the atmosphere's label moved to the right, out of the climb's
  way. The map's legend names the yellow dot: SUN OVERHEAD, the point where the sun is at the zenith.
- **The camera monitor and the windows recover from a revert:** a revert, a quickload or a scene change makes new
  cameras under the same JRTI ids, and JRTI leaves the old streams open but silent, so the pictures froze until the
  page was reloaded. The camera pages now also follow `tlm/time` and open their stream again 2 s after the mission
  clock goes back, or after the telemetry returns from a gap of more than 5 s.
- **RETRO's entry corridor scales with the atmosphere:** 36 to 64 % of its height (25–45 km on stock Kerbin, 29–51 km
  on JNSQ's 80 km), the deorbit target in the middle, on any body with an atmosphere. The range is shown.

- **The relief maps take the game's biomes:** where a biome's name says ice (Kerbin's IceCaps, Duna's polar caps),
  land and sea alike are white; where it says arid or desert (JNSQ Kerbin's two deserts), the land is sand and
  ochre; tundra is grey-green. The relief shading stays on top. Biomes are read at half the map's resolution, about
  40 s more per map. The maps are now `<body>-<radius>-r3.png`: they are made again on the next flight, and the
  `-r2` files can be deleted.

## 2026-11-19 — one console, two capsules: STATION and the windows

- **Mission Control's wall display** (`wall.html`, WALL in the top bar), for the room's TV: the ground track on a
  relief map of the body sampled from the game, with the night side, the next three orbits, apsides, the next burn,
  the impact point and the target; the orbit from above the pole with the moons and their spheres of influence;
  figures; charts of altitude and apsides, velocities, loads and heat, and the ascent profile; the flight's events.
  The ground track was checked in KSP: within 0.03° of longitude of where the vessel was 94 s later.
- **Charts on the MCC consoles** (RETRO, GUIDO, BOOSTER, EECOM), over the last 15 minutes. Drawn with uPlot
  (`panels/virtual/vendor/uPlot.*`, MIT).
- **New service `mcc-data`**: the flight recorder (one sample a second, events: lift-off, staging, engines, max Q,
  atmosphere, orbit, SOI, AOS/LOS, docking, alarms; kept on disk across a restart), the bodies read from KSP
  (`mcc/bodies`), and relief maps sampled from the game's terrain (`panels/virtual/maps/`, git-ignored, one set
  per KSP install). Topics in `protocol/topics.md`.
- **The MCC uses the game's bodies:** in JNSQ, Kerbin is 1,600 km across and turns in 43,082 s; FIDO, RETRO and
  BOOSTER drew and computed with stock's figures. They now take `mcc/bodies`, stock's only until it arrives.
- **No more `lab` bus:** ORBIT and NAVIGATION move to the `solo` bus of their module (`panel/solo/...`), CAMERA and
  ACTION GROUPS to a new `aux` bus (`panel/aux/...`). In the cockpit logic, `lab_panel.py` becomes `aux_panel.py`
  and ORBIT and NAVIGATION join `solo_panel.py`; the tests and KSP scripts read the new topics.
- **SOLO / MCC switch** (MODE, `mcc_mode`, at the bottom of NAVIGATION, whose rows moved up for it; starts on SOLO): on MCC, for a crew flying with Mission
  Control, PAD REQUEST, ORBIT and NAVIGATION go dark (lamp test still lights them) and the flight dynamics service
  ignores the PAD requests. The cockpit and the service both read the switch from `panel/solo/in/mcc_mode`.
- **EVENT TIMER and LIGHTS · FAN swapped** on OVERHEAD's SYS module, which now reads TIME WARP, EVENT TIMER,
  LIGHTS · FAN, SAVE: the timer sits next to TIME WARP.
- **No alarm in the VAB or the SPH:** the gateway puts the game's scene in `gateway/status` when there is no ship to
  fly (`editor_vab`, `space_center`, ... from kRPC's `game_scene`), and the cockpit raises no alarm, NO LINK included,
  while it is an editor. At the Space Center or in the tracking station NO LINK still sounds.
- **MONITOR switch on the CAMERA panel** (`cam_power`, on by default): off, the cockpit sends
  `cam/select {"id": null, "off": true}`, the monitor goes black (no NO SIGNAL flag) and the panel reads MONITOR OFF.
  Back on, it returns to the camera it was on. The panel's rows moved up to make room.
- **The camera monitor leaves out the window cameras:** CAM ◂ ▸ skip `cm_left`, `cm_right`, `lm_left` and
  `lm_right` (numbered copies too), which belong to the windows. `cam/list` still has every camera.
- **Rolled window cameras:** `cam.html?rotate=90` (or −90, 180) turns the picture clockwise. The left window turns
  −90° and the right +90° (checked against the cameras in the game), for window cameras rolled a quarter turn on their parts in the VAB (opposite ways, for
  looks): a portrait window then gets the whole height of JRTI's landscape picture across its width instead of a
  strip from its middle.
- **The windows hold their cameras at 50°** (`cam.html?window=…`, `?fov=` to change it): set through JRTI's
  `/camera/<id>/settings` when a camera is shown and checked on every camera list (3 s), since JRTI does not keep it
  across a reload and its viewer can change it. In portrait the 16:9 stream is cropped to its middle.
- **Hand controllers on the keyboard** until the joysticks exist (`panels/virtual/hand_controllers.js`): the console
  page publishes `panel/hc/in/*` on KSP's keys, WSADQE for rotation and IJKLHN for translation, and draws both sticks
  in the side column. The keys reach it from the glass screens too (`shell.js` passes them on); losing the keyboard
  lets everything go. The throttle moves from the arrow keys to Left Shift / Left Ctrl held, as in KSP (0 to full in
  2 s).
- **RCS FINE switches KSP's precision mode** (`cmd/precision`, `precision` in `tlm/vessel`), so the keyboard is fine
  too; the panel wins (Caps Lock in the game is undone). The sticks keep the cockpit's own 30 %: measured in KSP,
  precision mode does not scale inputs sent through kRPC. (kRPC 0.7 has `precision_mode`; the README said it could not
  be reached.)
- **STATION** (new overhead module STN, 1 × 2 U, `sys` bus; OVERHEAD is now 5 × 2 U): a CM / LM selector. Turning it
  moves the crew into the other capsule while it has seats, pilots first, and flies the craft from it (`cmd/station`,
  carried out by the gateway). The console goes dark for 15 s with TRANSFER blinking (throttle cut, inputs dead), then
  powers up with a 3 s lamp test. CM and LM lamps (the capsule with the controls), TUNNEL (docked: the crew can go
  across), CM CREW and LM CREW. Turned back during the blackout, the crew goes back once it is over.
- **Two windows** (glass modules WNL and WNR, old 17" 5:4 monitors in portrait (270 × 338 mm), bare glass set into the board against MAIN's sides in a 22 mm riveted metal frame with 14 mm round corners (`screen.frame`), 3.15 × 3.83 U, their top level
  with MAIN's (`"top": 2.336` U below OVERHEAD's top): zones of their own, new `"side"`, `"top"` and `"flush"` in `console.json`, and `"bare"` panels, drawn
  without faceplate and not cut; MAIN keeps its 6 U Gemini outline): `cam.html?window=left|right` shows the camera the cockpit puts on `cam/window/left|right`, the current
  capsule's `cm_left`/`cm_right` or `lm_left`/`lm_right`, filling the glass; dark through the blackout. The window
  cameras are ordinary Hullcam cameras named in JRTI's part menu in the VAB; the gateway finds each capsule as the
  crewed part its window cameras are attached to.
- **The camera monitor uses JRTI instead of Kerbcast:** Kerbcast reports only the Hullcam part's built-in camera name
  (two NavCams are both "NavCam") and reads it once, so a camera cannot be told apart by a name set in the VAB. JRTI
  lists each camera under the name set in its part menu and streams it as MJPEG, shown in an `<img>`. The page reaches
  JRTI through the panel server's `/jrti/` (JRTI sends no CORS header); JRTI's "Auto-stream every camera" must be on.
- **The selector keeps the controls:** while the game flies the other capsule (a separation leaves it on the side
  with the original root part; "control from here" in the game), the cockpit sends `cmd/station` with
  `controls_only` every 2 s, switching vessels when the capsules are apart. Never to an empty capsule, nor during
  time warp.
  The windows follow the selector too, so they no longer flash the CM's view during that moment (the game's
  capsule only when the selector's is empty).
- **`tlm/station`** (gateway): crew and seats per capsule, the one flown from, docked or not. MCC EECOM shows it
  (CM · LM line in LIFE SUPPORT).
- **Gateway:** never moves a kerbal into a full part: kRPC's `transfer_crew` then drops the kerbal out of the vessel,
  back to the astronaut complex.
- **Cockpit:** `powered()` is now "has power and not in the blackout" (`has_power()` is the charge alone); the lamp test
  is `lamp_test()`, the switch or the power-up.

## 2026-11-19 — the console's final shape

- **LOW joins MAIN:** MAIN is 6 U wide for 4 U, then narrows through a 4 × 2 U block to the 3 U burn computer, inside one
  tapering outline (`outline` in `console.json`, replacing `taper`). The hand controllers stay outside the U grid.
- **OVERHEAD** is cut to its 4 × 2 U and centred (`"align": "center"`).

## 2026-11-19 — all 7-segment displays green

- **Every 7-segment display is green**, and so is every **LED bar**: red and amber are left to the warnings and cautions.
- **ENGINE:** six evenly spaced columns: CUTOFF over a vertical STAGE FUEL bar next to the throttle, the stage number above the STAGE button.
- **ABLATOR LOW** (a caution, under 20 %) replaces **ΔV RESID** on the annunciator; ΔV TO GO still shows the residual after a burn.

## 2026-11-19 — module names on the console

- **Holding Left Alt** dims the panels and shows every module's boundary and name, at one size whatever the zoom.

## 2026-11-19 — SimSup, MCC and the docs catch up with the console

- **`panel_dark` darkens one real panel** (`panel`: its id, suggested on the page), and no longer a whole bus. SimSup reads the
  panel definitions (`PANELS_DIR`, mounted in `docker-compose.yml`) and sends the panel's outputs and inputs with the failure.
- **SimSup's failure parameters are lists** of their possible values (panels, alarms, displays, controls by their names on the console), no longer text to type.
- **New SimSup failures:** `ls_gauge`, `chute_gauge`, `science_dead`. A **revert** is logged as a flight event and clears the
  active failures; armed ones stay armed.
- **MCC:** EECOM gains LIFE SUPPORT and SCIENCE boxes, xenon and ablator; RETRO the time to the atmosphere and the chute verdict.
- **Docs:** the README's modules, alarms and camera text, the laser-cut issue count.

## 2026-11-19 — the annunciator holds alarms only

- **0.05 G** moves to REENTRY · RECOVERY, above the chute lamps (now `panel/sys/out/lamp_05g`), and **CONTACT** to LANDING AID,
  under the touchdown lamps: neither is an alarm.
  The annunciator is left with 20 cells, 5 × 4.

## 2026-11-19 — a FAN switch

- **LIGHTS becomes LIGHTS · FAN**, with a FAN toggle above the light switches (`panel/sys/in/fan`). It does nothing in the virtual cockpit.

## 2026-11-19 — LANDING AID

- **PROPELLANT and LIFE SUPPORT swap places:** PROPELLANT is now on the ENG module, LIFE SUPPORT on RES under ELECTRICAL.
- **ENGINE and ASCENT · DESCENT swap places**, which puts ASCENT · DESCENT beside LANDING AID.
- **A new 1 U panel left of ENGINE** (module LND, `eng` bus): DRIFT + R and DRIFT + UP, the sideways speed across the craft's
  axis, and the touchdown lamps SINK OK, DRIFT OK, UPRIGHT and GEAR DOWN, lit below 1000 m while each is within its limit.
- 7-segment displays no longer show `-0.0` for a tiny negative value.

## 2026-11-19 — REENTRY and SCIENCE panels

- **REENTRY** (new module, `sys` bus, on MAIN's bottom row, SCIENCE beside it) takes ABLATOR, OUTSIDE °C and PRESSURE KPA from RECOVERY · BRAKES, and
  adds HOTTEST PART PCT, TIME TO ATM S (`atm` in `tlm/orbit`) and CHUTE SAFE / RISKY / UNSAFE (`chute_safe` in `tlm/vessel`).
- **RECOVERY · BRAKES merges into it**, as REENTRY · RECOVERY: the chute controls sit under the chute safety lamps.
- **SCIENCE** (new module, `sci` bus): one experiment shown at a time, with RUN, SEND, DUMP, RESET and RUN ALL, its state, the
  biome and the science of its data (`tlm/science`, `cmd/science`).
- **CAUTION & WARNING:** MASTER ALARM and MASTER CAUTION sit under the annunciator; the **MET** moves to the MONITOR panel.

## 2026-11-19 — OVERHEAD reordered

- **NAVIGATION joins the SOLO module** (still on the `lab` bus), and the LAB module, then empty, is gone.
- **OVERHEAD:** SOLO (PAD REQUEST, ORBIT, NAVIGATION) on the first row; TIME WARP, LIGHTS, EVENT TIMER and SAVE on the
  second. The burn computer is alone in LOW and moves to its first row.

## 2026-11-18 — SAVE gets its own panel, with REVERT TO LAUNCH

- **TIME WARP · GAME is split** into TIME WARP (with PAUSE) and **SAVE** (QUICK SAVE, QUICK LOAD).
- **REVERT TO LAUNCH** on SAVE acts only with the guarded **REVERT ARM** on, and is lit while armed. It sends
  `cmd/game {"revert": true}`, which the gateway passes on when KSP allows a revert.

## 2026-11-18 — TWR shows the present thrust

- **TWR** on ENGINE is now the thrust the engines give at this moment over the local weight, so it follows the throttle and
  reads 0.00 with the engines off. HOVER TIME still checks the full thrust available.

## 2026-11-18 — LIFE SUPPORT, with TAC Life Support

- **A LIFE SUPPORT panel** on the ENG module, under LINK · ANTENNA (`sys` bus): FOOD, WATER and O2 bars, how many hours each lasts for the crew
  aboard (TAC's own rates, recyclers not counted), and CREW. The gateway adds `Food`, `Water` and `Oxygen` to
  `tlm/resources` and `crew` to `tlm/vessel`.
- **LS LOW** (a caution, under 10 %) and **LS OUT** (a warning, one of them empty) join the annunciator, now 5 columns
  wide. Both need a crew aboard.

## 2026-11-18 — the PROPELLANT panel says what is left to do

- **The bars show the whole vessel** (FUEL, OXID, MONO and the new **XENON**, `XenonGas`); the current stage's fuel stays on
  ENGINE, which now follows the xenon of an ion stage, as does LOW FUEL.
- **BURN TIME S** (`disp_burn_time`): the stage's propellant at the present thrust, or at full thrust when not burning.
  **RCS ΔV M/S** (`disp_rcs_dv`): an estimate from the monopropellant and the stock thrusters' 240 s.
- **Stage figures count what the engines burn** (`propellants` in `tlm/engines`), at each resource's own density, so an
  ion stage ignores its rocket fuel. Solid fuel is now 7.5 kg per unit, its real value, instead of 5.

## 2026-11-18 — the console's zones get their target sizes

- **The ELECTRICAL and PROPELLANT bars stand vertical**, with those two panels rearranged around them.
- **The camera monitor goes to the top of MAIN's centre**, with the ENG module under it.
- **RECOVERY · BRAKES and LINK · ANTENNA** fill the ENG module's free column, above ENGINES · ABORT (still on the `sys` and
  `com` buses). The COM module is gone; SYS is one row, with SOLO under it.
- **ELECTRICAL and PROPELLANT** leave SYS for a new module, RES (still on the `sys` bus), in the right column of MAIN, under AUX.
  SYS closes up to 2 × 2 U, and COM and SOLO shift left in OVERHEAD.
- **LOW is centred under MAIN**, with an outline running from MAIN's bottom corners around it (`taper` in `console.json`),
  to show the console's shape. The 1 U between them is only a drawing distance.
- **OVERHEAD is 6 × 3 U, MAIN 6 × 6 U and LOW 3 × 3 U.** SOLO (PAD REQUEST and ORBIT) moves to OVERHEAD, the burn
  computer (CMP: PAD, ENTRY, BURN) to LOW under LAB, and the camera monitor next to the FDAI, inside MAIN's 6 U.
- **The centre of MAIN is a column:** CAUTION & WARNING, ASCENT · DESCENT, then ENGINE, with ENGINES · ABORT beside ENGINE
  and the camera monitor below. **CAMERA** and **ACTION GROUPS** form a new module, AUX (still on the `lab` bus), at the
  top of MAIN's right column, CAMERA first.

## 2026-11-18 — the cross-pointer goes

- **CROSS-POINTER is removed**, with its logic (`cross_pointer.py`), settings, the `xp_mode` input and its outputs.
  The landing end-to-end test now checks the alignment on retrograde from `tlm/flight`, and no longer tests the dot.
- **LOW zone:** LAB is one row (NAVIGATION, ACTION GROUPS, CAMERA) with SOLO under it, so the zone is 3 U wide.

## 2026-11-18 — the MFD goes, ASCENT · DESCENT grows

- **The MFD is removed** (page, module and top-bar link): the I/O panels now show what the crew used from it. What
  goes with it: the orbit drawing, the ascent tapes, and the docking gate and capture-envelope graphics.
- **ASCENT · DESCENT is 2 × 1 U**, so ENG is 4 U wide with a free slot under the panel. It gains **Q KPA**
  (`disp_q`, from `tlm/flight.q`) and **TIME TO IMPACT S** (`disp_impact`): radar altitude over the sink rate, as on the
  MFD, now with dashes when the orbit's periapsis is above sea level.
- **MAIN zone:** RDV moves to the top left, and the FDAI slides down into the MFD's place.

## 2026-11-18 — time to the apsides on ORBIT

- **TIME TO APO and TIME TO PERI** (`disp_t_apo`, `disp_t_peri`, from `tlm/orbit`) sit beside the apoapsis and periapsis,
  as hh.mm.ss with up to 999 hours; dashes on an escape orbit or once the periapsis is past. ORBIT grows to 2 × 1 U, so
  the SOLO module is 3 U wide, because a second column of 7-digit displays does not fit on 1 U.

## 2026-11-18 — ASCENT · DESCENT

- **ASCENT and LANDING are one panel** on the `eng` bus. The altitude is in metres on 8 digits, with **ALT REF**
  choosing the sea or the ground (RADAR). H SPEED, V SPEED and SPEED follow the **SPEED REF knob**: ORBIT uses the new
  `v_orb` of `tlm/flight`, SURF and TGT the surface. The vertical speed is the same against both. G, HOVER TIME and
  GEAR come along (`led_gear`, `disp_hover` and the `gear` input move from `lab` to `eng`); `disp_srf`, `disp_radar`,
  `disp_ld_vs` and `disp_ld_hs` are gone, for `disp_hs`, `disp_vs` and `disp_speed`.
- **MET** moves to CAUTION & WARNING, and **THRUST** to ENGINES · ABORT as a vertical bar (`"vertical": true`).
- **PRESSURE KPA** joins OUTSIDE °C on RECOVERY · BRAKES, from `tlm/flight.p`. Both displays have 4 digits, to fit.
- Toggles can name their positions (`"positions": ["RADAR", "SEA"]`), in the console and the cut templates.

## 2026-11-18 — the FDAI on a 4" round screen

- **A 4" round screen** (720 × 720, a 101.5 mm circle) replaces the 7": with only the ball and its roll ring on it, the
  ball grows from about 70 to about 83 mm, in a smaller opening. The screen view drops the readouts and rate scales.
- **Pitch, heading, roll and their rates** are 7-segment displays beside the screen, their right edges aligned. The cockpit formats them from
  `tlm/attitude` and differentiates them over game time (`angle_rates.py`, shared with the docking rates); the yaw rate
  is the heading's rate times the cosine of the pitch. Numbers need no scale, so **RATE SCALE is gone**.
- **Screens can be placed and round:** `screen.at`, `screen.round` and `screen.module_mm`, in the console and the cut
  templates (a circular window, the display's body checked behind the plate).
- **The FDAI controls use the corners around the circle** (MARKERS top left, NEEDLES bottom left, ERROR SCALE bottom
  right), which leaves the attitude controls alone under the screen, SAS MODE raised close to it; both layout checks now
  treat a round screen as a circle.
- **The display's body is a 126 mm circle** behind the plate, and the cut templates check the controls against that
  outline, so the corners around it are usable.

## 2026-11-18 — the FDAI's controls leave the glass

- **NEEDLES, ERROR SCALE, RATE SCALE and MARKERS** were keys drawn on the FDAI screen (and N, S, R, M on the
  keyboard), kept by each browser: nothing to click on a glass. They are now controls on the ATTITUDE panel, a row
  above the attitude switches: three knobs (prograde / retrograde / off; ±5° / ±50°; ±1 / ±5 / ±10 °/s) and a
  toggle. The cockpit sends the page its settings (`panel/eng/out/fdai`), and the page only draws.
- **A 7" 4:3 screen** (142 × 107 mm, 1024 × 768) instead of the 8", to make room for the second row on the 2 × 2 U
  faceplate; the ball is about 13 % smaller.
- **PITCH, HDG and ROLL in a column beside the ball** on the screen (`?embed=1`, the console's and a kiosk's view),
  so the ball takes the screen's full height: 736 px instead of 584 at 1024 × 768, which more than makes up for the
  smaller screen.

## 2026-11-18 — the attitude switches under the FDAI ball

- **ATTITUDE and FDAI are one panel:** the ball took a 2 × 2 U module on its own, with room to spare under its 8"
  screen. SAS, SAS MODE, SPEED REF, RCS and RCS FINE moved there from ENG (same controls, same `eng` bus, so the
  cockpit logic is unchanged); ENG is 3 × 2 U now and CMP moved up a row, which frees 2 U of the MAIN zone.
- **A glass panel can carry controls:** the console gives the FDAI module an I/O connection since it has items, and
  both layout checks (the console page's and the cut templates') now treat a screen as an obstacle. On the hardware
  the Pi would read the switches (GPIO, or a small I/O board): not decided. In the virtual console the module's I/O node reports on
  `panel/fdai/io/status`: the embedded page already reports on `panel/fdai/status`, and two clients with a last will
  on one retained topic would mark the module offline whenever either one closed.

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
