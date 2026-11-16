# Panels, controls and displays for a Mun trip and back (draft)

Draft list, to compare with your own research. Source: what the self-test needed to fly Kerbin → Mun landing → Kerbin
and an orbital rendezvous (see [selftest/interface.md](selftest/interface.md) and [selftest/gaps.md](selftest/gaps.md)),
plus the panel kinds in [PLAN.md](PLAN.md) §2. Vanilla KSP, two seats (CDR left, LMP right).

Priority: **A** = cannot fly the mission without it, **B** = needed to fly it by hand with the course's methods,
**C** = immersion or comfort. Kind: I/O (ESP32 panel), glass (Pi + screen), HID (USB joystick).

## 0. Layout decided (2026-11-15)

- **One centre console between the two seats** carries most panels, so the vessel is flyable from either seat. The
  Seat column below predates this: read CDR, LMP and centre as "centre console" unless a panel is per seat.
- **Per seat:** hand controllers (rotation, translation, throttle) and an attitude display in the pilot's line of sight.
- **Glass kept to a minimum.** Everything that can be digits, bars, lamps or LEDs is. Three non-glass display types
  cover what looked like it needed a screen: 7-segment digits, an alphanumeric LED row (target name) and an LED matrix
  (engine status). Glass remains for the attitude ball, and optionally one shared screen for the orbit drawing.
- **The DSKY is gone** (removed 2026-11-16; the sections below that mention it are the original plan). The burn computer (CMP: one display per PAD field, a numeric keypad, UPLINK ACCEPT) replaces it.

Built as virtual panels so far: 4 to 8 and 13 to 16 (ENG, SYS), 1 as the burn computer (CMP), the I/O part of 12 (RDV),
2 and 9 to 12 on glass (FDAI, MFD). The glass versions of 9 to 12 are candidates to drop once the I/O panels are flown.

## 1. Summary

| # | Panel | Kind | Seat | Priority | Used in |
|---|---|---|---|---|---|
| 1 | Flight computer (DSKY) | I/O | centre | A | every burn |
| 2 | Attitude display (FDAI) | glass | CDR | A | every burn, landing, entry |
| 3 | Hand controllers: rotation, translation, throttle | HID | CDR | A | landing, docking, manual burns |
| 4 | Engine and staging | I/O | CDR | A | ascent, every burn |
| 5 | Abort | I/O | CDR | A | ascent, descent |
| 6 | Attitude control: SAS, RCS, control mode | I/O | CDR | A | all |
| 7 | Caution and warning | I/O | centre top | A | all |
| 8 | Mission timers | I/O | centre | A | all |
| 9 | Orbit and trajectory display | glass | LMP | B | planning, MCC, LOI, TKI |
| 10 | Ascent and entry tapes | I/O or glass | CDR | B | ascent, entry |
| 11 | Landing display | glass + I/O | CDR | B | Mun descent |
| 12 | Rendezvous and docking display | glass | CDR | B | rendezvous, docking |
| 13 | Propellant and stages | I/O | LMP | B | all |
| 14 | Electrical and breakers | I/O | LMP | B | all |
| 15 | Landing gear, parachutes, lights | I/O | LMP | A (small) | landing, entry |
| 16 | Time warp and game | I/O | LMP or instructor | B | coasts |
| 17 | Environment and crew | I/O | LMP | C | all |
| 18 | Comms and science | I/O | LMP | C | Mun surface, coasts |
| 19 | Camera and window selector | I/O | CDR | C | landing, docking |
| 20 | Cabin lighting and audio | I/O | overhead | C | all |

## 2. The panels

### 1. Flight computer (DSKY) — A
The self-test's biggest finding: KSP has no PAD, no Δv counter and no TIG countdown; the cockpit must own them.
- Controls: 19-key keypad (0–9, +, −, VERB, NOUN, ENTER, CLEAR, PROCEED, KEY RELEASE, RESET).
- Displays: PROG, VERB, NOUN (2 digits each); three signed 5-digit registers; status lamps (COMP ACTY, OPR ERR,
  KEY REL, PROG alarm, NO ATT, TEMP, GIMBAL LOCK, STBY).
- Functions it must offer: load a PAD (TIG, Δv prograde/normal/radial, burn time); countdown to TIG; attitude error to
  the burn attitude; Δv counter (accumulated ∫F/m dt) with residuals after cutoff; AUTO burn (executor) or needles for
  a manual burn; programs for ascent, burn, landing, rendezvous, entry.
- Lessons to build in: re-arm the Δv counter after a staging event (G4); pre-launch TWR check against the plan (G8).

### 2. Attitude display (FDAI) — A
- Displays: 3-axis ball (or a drawn one); pitch, yaw and roll error needles; rate needles; reference selector readout.
- Controls (bezel): reference frame (ORBIT / SURFACE / TARGET / INERTIAL), needle source (PAD attitude / target /
  velocity), scale (5° / 50°).
- Every burn in the self-test held a fixed inertial attitude from the PAD: the needles must show the error to it.

### 3. Hand controllers — A
- Rotational hand controller (3 axes, spring-centred), translational hand controller (3 axes; needed for docking and
  for fine Δv trims), throttle lever with a detent at 0 and a hard stop.
- Trim wheel or thumb switch for fine throttle; push-to-talk on the RHC.
- USB HID directly to KSP for latency; the gateway only reports them.

### 4. Engine and staging — A
- Controls: ENG ARM (guarded toggle), STAGE ARM (guarded) + STAGE (lit push button), throttle enable, engine cutoff
  (big red, unguarded), thrust limiter knob (the rendezvous needed 10–25 % for small burns), gimbal lock toggle.
- Displays: stage number (2 digits), thrust bar, throttle bar, TWR (3 digits), Δv remaining in the stage (4 digits),
  ENGINE ON / FLAMEOUT lamps.
- Rule to keep: the throttle is forced to the panel's value when a vessel is bound (KSP loads a save at 50 %: G11).

### 5. Abort — A
- Controls: ABORT ARM (guarded) + ABORT (lit, red); abort mode selector (PAD / ASCENT / ORBIT / DESCENT) to choose the
  action group or the program.
- Displays: mode lamps, ARMED lamp.

### 6. Attitude control — A
- Controls: SAS on/off; SAS mode rotary (stability, prograde, retrograde, normal, antinormal, radial in, radial out,
  target, anti-target, maneuver); RCS on/off; control mode MANUAL / AUTO (one owner per axis: sticks or the computer);
  fine controls toggle; "control from here" selector (pod / docking port) for docking.
- Displays: one lamp per switch showing the game's state, blinking on disagreement; speed mode lamps
  (ORBIT / SURFACE / TARGET).

### 7. Caution and warning — A
- Controls: MASTER ALARM and MASTER CAUTION (lit push buttons, press to acknowledge), LAMP TEST, tone volume.
- Annunciators (first list): NO LINK, LOW FUEL, LOW POWER, HIGH G, HIGH Q, SAS DISAGREE, FLAMEOUT, ATT ERROR at TIG,
  Δv RESIDUAL, PERIAPSIS LOW (in atmosphere or under ground), SOI CHANGE soon, RADAR ALT, DESCENT RATE, GEAR UP,
  CHUTE not armed, RCS LOW, OVERHEAT, COMM LOST, THROTTLE NOT ZERO (at load or switch), WARP ON.

### 8. Mission timers — A
- Displays: MET (hhh:mm:ss), event timer (counts to or from TIG, ±mm:ss), UT.
- Controls: event timer START / STOP / RESET, UP / DOWN, set minutes and seconds (two thumbwheels or encoders),
  source selector (MANUAL / PAD TIG / apoapsis / periapsis / SOI).

### 9. Orbit and trajectory display — B
- Displays: body, apoapsis, periapsis, period, inclination, eccentricity, time to apoapsis and periapsis, time to
  SOI change, next-patch periapsis (KSP's prediction, as a check only), phase angle to a target or to the Mun.
- Glass version: a top-down map like the course's planning desk; I/O version: one 7-segment display and a rotary
  (ALT, APO, PERI, PERIOD, INC, T-APO, T-PERI, T-SOI), as in the prototype.

### 10. Ascent and entry tapes — B
- Displays: altitude, vertical speed, speed (surface or orbital), dynamic pressure, g, flight-path angle or pitch,
  apoapsis (the ascent cuts off on it), downrange. Entry adds g peak, periapsis and heat lamp.
- Controls: speed reference SURFACE / ORBIT.

### 11. Landing display — B
- Displays: radar altitude of the lowest point (not of the centre of mass: G5), vertical speed, horizontal speed with
  a cross-pointer (forward / lateral drift), throttle and TWR, propellant time remaining (hover seconds), slope or
  landing-point cue if a camera is available.
- Controls: descent program PROCEED, rate-of-descent switch (click up / down, ±0.5 m/s, like the LM ROD), gear down.

### 12. Rendezvous and docking display — B
The rendezvous test used exactly these quantities.
- Displays: range, range rate (closing speed), line-of-sight rate, braking-gate speed for the current range (ρ/400 s)
  with an over-speed lamp, relative inclination, phase angle and time to the transfer TIG.
- Docking (under 100 m): axial distance, lateral offset (cross-pointer), closing speed, angle error, CAPTURE lamp;
  port camera or the course's COAS view on the glass.
- Controls: target select (next / previous vessel, port), reference TARGET, translation mode FULL / FINE / PULSE.

### 13. Propellant and stages — B
- Displays: bar per propellant for the current stage (liquid fuel, oxidizer, solid), monopropellant, total Δv,
  stage table (glass, optional). Low-level lamps feed panel 7.
- Controls: crossfeed enable, tank valves (optional), fuel-cell or drain switches if the craft has them.
- Lesson: the stage table must carry thrust limiters and which tank each engine drains (G8, G9).

### 14. Electrical and breakers — B
- Displays: electric charge bar and volts-style gauge, charge rate (+/−), source lamps (solar, fuel cell, RTG).
- Controls: MAIN BUS breaker (in the prototype), bus A / B, breakers per panel group (lamps, displays, computer,
  RCS, engine), solar panels extend / retract, battery isolate. Breakers are cockpit-owned rules, not KSP's.

### 15. Landing gear, parachutes, lights — A (small)
- Controls: GEAR up / down (lever-style toggle, game wins), CHUTE ARM (guarded) + DEPLOY, drogue / main, LIGHTS,
  BRAKES, ladder, cut chute.
- Displays: gear three-greens style lamp, chute state (STOWED / ARMED / SEMI / FULL).

### 16. Time warp and game — B
- Controls: warp − / +, WARP TO (TIG minus a lead), STOP WARP (big), physics / rails indicator; pause; quick save and
  quick load (guarded).
- Displays: warp rate (digits), WARP lamp. Rule from the test: no physics warp while RCS and the autopilot are both on (G12).

### 17. Environment and crew — C
- Displays: g meter (analog servo is nice), cabin temperature, crew count, situation lamp
  (PRELAUNCH / FLIGHT / ORBIT / LANDED / SPLASHED).

### 18. Comms and science — C
- Controls: antenna extend, transmit / store, experiment run buttons (4–6), EVA / board (if wanted).
- Displays: signal strength bar, science stored, biome (text display).

### 19. Camera and window selector — C
- Controls: view per window (FORWARD / DOWN / DOCKING / IVA / MAP), map view toggle, camera next / previous.

### 20. Cabin lighting and audio — C
- Controls: panel backlight dimmer, flood dimmer, intercom volume, master tone volume, voice loop push-to-talk.

## 3. Component count (rough, panels A and B)

| Component | Count | Where |
|---|---|---|
| Toggle switch (2 or 3 positions) | 40–50 | 4, 6, 13, 14, 15, 16 |
| Guarded toggle | 6–8 | ENG ARM, STAGE ARM, ABORT ARM, CHUTE ARM, save / load |
| Push button, lit | 25–30 | STAGE, ABORT, masters, DSKY keys, timers |
| Rotary selector | 8–10 | SAS mode, display select, abort mode, timer source, references |
| Encoder or thumbwheel | 4–6 | timers, limiter, dimmers |
| 7-segment digits | ~80 | DSKY 21, timers 20, orbit 8, stage / TWR / Δv 10, tapes 20 |
| LED bar graph (10 segments) | 8–10 | propellants, thrust, throttle, charge, signal |
| Annunciator cells | 20–24 | panel 7 |
| Indicator LED | 60–80 | one per switch plus status lamps |
| Analog gauge (servo) | 2–4 | g meter, charge, optional |
| Glass screens | 3–4 | FDAI, orbit, landing / docking, optional stage table |
| Hand controllers | 3 | RHC, THC, throttle |

## 4. Suggested build order
1. Panels 4, 5, 6, 7, 8, 15 on one or two ESP32 boards (the virtual `eng` panel already covers most of 4–7).
2. Throttle and the two hand controllers (HID).
3. FDAI on glass, then the DSKY with the burn program (PAD entry, countdown, Δv counter).
4. Orbit display and ascent tapes; fly ascent + circularisation + Mun flyby by hand.
5. Landing display, then rendezvous and docking display.
6. Electrical, propellant, warp; then the C panels.

## 5. Open questions
- One attitude display per seat, or one in the centre both can read?
- FDAI: glass only, or a physical ball later?
- Engine matrix: 8 × 8 (common part) or 9 × 9 (a centre engine sits on the centre LED)?
- How much of panels 9–12 is glass versus 7-segment? Glass is cheaper per value; segments read better and feel right.
- Mods: stock has no fuel cells, life support or comms failures worth a panel unless difficulty options are on.
