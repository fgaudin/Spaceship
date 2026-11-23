# Instructor manual (draft)

How to run the Moonshot + KSP campaign with a class: the course modules in Moonshot, a probe flight after each
one, then crewed flights in the cockpit with a full Mission Control. This is a first outline: the flights listed
here have not all been flown yet, and the parts marked **TODO** or **Open** need a decision or a build.

## 1. The campaign at a glance

| Era | Where the students sit | What they fly | Stations open |
|---|---|---|---|
| **Probes** (TM-1 to TM-18) | One shared screen, the probe control room | An uncrewed probe after each module, from a stored program | PROBE |
| **Mission Control** (TM-19) | MCC consoles on laptops, one or two roles each | Sims, then the precursor flights | PROBE, MCC, WALL |
| **Crew** (after the course) | Cockpit (crew) + MCC (ground) | Suborbital, orbit, rendezvous and docking, Mun flyby, Mun landing | All |

Each flight follows the same loop:

1. **Briefing**: the story, the goal, the data the students are given.
2. **Predict**: the students work out the flight in their spreadsheet before the launch, and write the program.
3. **Fly**: uplink, GO, watch. The students do not touch KSP.
4. **Debrief**: predicted against measured (CSV export), and an explanation of every gap. This is where they learn.

### Rules of the campaign

- **No oracle.** Nothing on the students' side computes an answer: no SOLO panel, no map view, no maneuver node
  readout, no KSP Δv. A check comes from flying and comparing, never from a computer that already knows.
- **Rows are cleared, not given.** A telemetry row that is worked out from others (apoapsis, Δv, TWR, time to
  apoapsis) is cleared only once the students have worked it out by hand from the raw rows.
- **Probes may fail.** A lost probe is a lesson and costs a rebuild. Crews are a different matter (section 5).
- **Everything measured goes into the Kerbin data sheet**, a page the class keeps and grows from flight to flight
  (Kerbin's radius, μ, rotation period, atmosphere; the Mun's distance, period, μ). Later flights use the class's
  own numbers, not the wiki's.

## 2. Before the first class

**The KSP machine**
- Uninstall MechJeb and Kerbal Engineer.
- Flight scene in F2 (no UI) on the students' screen. Keep the keyboard with you: M (map view) works even with the
  UI hidden.
- **Open**: the VAB shows the stage Δv in the staging stack. Find out if it can be hidden, or keep the students away
  from it until TM-4's hand proof.
- One save per flight, so that a bad flight does not end the campaign (pre-built craft, target vessel in place).

**The rooms**
- `./capsule start ksp`, then the probe room at `http://<host>:8650/probe.html` on the shared 2560 × 1440 screen, in
  full screen (F11).
- SimSup (`/simsup.html`, password-protected, user `simsup`; see `panels/auth/README.md`) on your own screen. Its
  drawer (STATIONS) holds:
  - the stations the students may open (WALL, MCC, CONSOLE; PROBE is always open),
  - probe mode (on for the whole probe era),
  - the clearances: one checkbox per group of telemetry rows and per kind of program step.
- How the probe room works: `panels/virtual/probe/README.md`.

## 3. The briefing (first session)

### Backstory

> **TODO (placeholder).** Why the Kerbals go to the Mun, who the students are in the story, and why the course
> they study tells of another world (Earth, Apollo) while they fly on Kerbin. Whatever the story, it has to explain:
> - why the numbers in the course (Earth, Saturn V, 384 400 km) are not Kerbin's, so every number has to be
>   measured or worked out again;
> - why the program starts with probes and only flies crews at the end;
> - why the students get almost no instruments at first, and earn them.

### What the students are told

- Who they are and what the program is for (backstory).
- The loop: briefing, predict, fly, debrief.
- The rules: no oracle, rows are earned, a lost probe is part of the work, a crew is not.
- The probe room: telemetry boxes (dark for now), the program builder, UPLINK, GO, STOP, CLEAR, the event list and
  the CSV export. The uplink needs the radio link.
- The VAB: they may build and change their craft there. You run KSP.
- Their callsigns (Moonshot asks for one) and the patch board: a Moonshot patch per module, a flight patch per
  flight.

### First contact

A short flight before any theory: a pre-built rocket, a program of one STAGE step at T+0 and CHUTES later. No rows
cleared except perhaps charge. The point is the room and the drill (write, uplink, GO), and seeing how little they
know about what just happened.

## 4. Chapters: the probe era

One row per module, in the course's order. **Flight** is the probe flight after the module; **Compute** is what
the students work out before it; **Clear** is what you clear in SimSup after the flight (or after the hand proof,
for a derived row). The group ids are those of `panels/virtual/probe/catalogue.js`.

| TM | Module | Flight | Compute | Clear after |
|---|---|---|---|---|
| 1 | Falling Around the World | Sounding rocket straight up, chutes | Apoapsis without drag from the burnout speed (v²/2g, then with g falling off). The shortfall says drag exists | `altitude` |
| 2 | Reading the Ellipse | Suborbital hop with a kick | μ of Kerbin from the Mun's period and distance (Kepler III; you read them from the tracking station). Apoapsis of the hop from the burnout state (vis-viva) | `state` |
| 3 | Where Are We? | Same hop, or higher | Apsides from radius, speed and flight-path angle, by hand; time to apoapsis | `apsides`, `elements`, `position`, `apsis_times` (each after its hand proof) |
| 4 | The Rocket Equation | Their own staged rocket, staging on computed burn times | Stage Δv and burn time from part masses and Isp | `mass`, `propellant`; `performance` after the hand proof; `cmd_burnout` after a flight staged on time |
| 5 | Measuring an Atmosphere | Barometer flight with the experiments | Scale height and surface pressure fitted from p(h); the residuals (one exponential does not fit, gap G2) | `air`, `cmd_science` |
| 6 | Riding the Saturn V | First orbit: kick, SAS prograde, BURNOUT staging, circularisation | Kick size and length; circularisation Δv at apoapsis (Δv_circ of section 6.3); burn time | `attitude`, `loads`, `cmd_sas_pro` |
| 7 | Your Own Launcher | Their own launcher to orbit, max Q under a limit | Δv budget with losses, TWR at liftoff | (nothing new) |
| 8 | Changing Orbits | No flight: Hohmann and plane change on paper, flown in TM-9 | Hohmann Δv to a higher orbit | |
| 9 | When, How Much, Which Way | Raise the orbit with a Hohmann transfer | PAD (TIG, Δv); burn time | `burn`, `cmd_burn` |
| 10 | When to Burn | Rendezvous with a pre-placed target, to a closest approach | Phase angle, wait time, TIG | `target` |
| 11 | Plane Changes | Launch into a target plane; a plane change at the node | Launch azimuth; plane change Δv at the node | `plane`, `cmd_sas_all` |
| 12 | Two Ships, One Line | **Open** (see below) | Terminal phase braking gates | |
| 13 | Translunar Navigation | Mun flyby, then Mun orbit | TMI phase angle and Δv, SOI radius, capture Δv at periapsis | `soi` |
| 14 | Free Return | A flyby that comes back into Kerbin's atmosphere | Free return periapsis, a midcourse correction | |
| 15 | Planning a Powered Descent | **Open** (see below) | Descent orbit, braking Δv | `landing` |
| 16 | The Last 500 Metres | **Open** (see below) | | |
| 17 | Planning the Return | Probe back from Mun orbit (sample return) | Return burn Δv at the SOI radius (gap G7) | |
| 18 | Threading the Corridor | Deorbit from Kerbin orbit, splash down near a point | Deorbit burn and lead angle; the corridor | `thermal` |

`power` (charge) can be cleared at any time: a flight with a flat battery teaches it fast.

### Holes in this table

- **Rows by module.** The `module` hints in `catalogue.js` use old module names ("Newton & Gravity", "Getting to
  Orbit", "Planning a Burn", "Coming Home") and put `apsis_times` in When to Burn, while TM-3 already asks for the time
  to apoapsis. **TODO**: give the hints as TM codes and agree with this table.
- **TM-6 circularises before TM-9 teaches burns.** Either clear `cmd_burn` early (the students give the Δv, the burn
  computer cuts off on it), or circularise with two THROTTLE steps at METs from a burn time worked out with the rocket
  equation. The second is harder, uses only what they know, and its error is a good TM-9 debrief.
- **No phase angle row** (TM-10, TM-13). The students need the angle to the target or to the Mun, and nothing shows
  it. Either a measured row (the angle now, not the time to burn), or they work it out from positions, which the
  room does not show either. **TODO**.
- **TM-12, docking a probe**: the program builder has no RCS translation step, and docking by stored program with no
  feedback is close to impossible. Options: stop the probe at a closest approach (TM-10 again, tighter), or leave
  docking to the crewed rendezvous flight, flown in the cockpit.
- **TM-15 and TM-16, landing a probe**: every step is on time, and there is no radar altitude or speed trigger. A
  timed descent will crash unless the students predict it almost perfectly. Options: an impactor (Ranger) for TM-15
  and a soft landing only once a trigger exists; a radar trigger as an unlock (realistic: Surveyor's retro rocket
  was started by a radar altitude marking); or leave landing to the crew.
- **TM-17**: a return from Mun orbit needs an attitude hold to point the burn. SAS MANEUVER on a node does it
  if `cmd_burn` is cleared; check that the node mirror works in the Mun's SOI.
- **Steering**: no attitude hold step yet (planned as a later "guidance computer" unlock). Launch azimuth (TM-11)
  with a yaw kick only is crude.
- **The program is blind.** A step runs on time whatever the vehicle does (a clamp staged on the pad carried on
  with its program). Consider a NEXT STAGE row (what the next staging lights and drops): a measurement, not an answer.

## 5. Missions: the crewed era

### TM-19, Mission Control

The bridge between the eras. After the module:
- Open MCC and WALL in SimSup. Give each student one or two consoles (laptops). The full MCC is shown: every row is
  unlocked by then.
- Fly the next precursor (the uncrewed version of the first crewed mission) from the MCC instead of the probe room.
- Practise PAD readback with the crew-to-be, the go/no-go poll and the abort options.

**Open**: how the program builder of the probe room and the MCC share the work once the MCC is open (precursors
flown from the probe room, crewed flights from the cockpit).

### How each crewed mission runs

1. **Precursor**: the same profile, uncrewed, flown first (as Apollo 4 to 6 before Apollo 8).
2. **Sims**: the crew in the cockpit, the ground in the MCC, SimSup throwing failures. Revert is allowed. As many
   as needed.
3. **Flight readiness review**: the team shows the precursor's results, the plan with its Δv margins, and the abort
   options for each phase. You decide if they fly.
4. **Flight day**: one flight, no revert. Go/no-go poll before launch.
5. **Debrief**: predicted against flown, logged under the crew's names.

If a crew is lost, the next session is an **accident review board**: find the cause in the telemetry, fix the plan,
and fly again (with a new crew, or the same one in the story).

### The missions

| # | Mission | New for the class | Precursor | Course behind it |
|---|---|---|---|---|
| 1 | **Suborbital** | The cockpit, the crew, the ground team working together | TM-2/3 hop | TM-1 to TM-6, TM-18 (entry) |
| 2 | **Orbit** | A deorbit the crew lives through | TM-6/7 orbit | TM-6, TM-7, TM-9, TM-18 |
| 3 | **Rendezvous and docking** | Two vessels; docking by hand from the cockpit | TM-10 target flight | TM-8 to TM-12 |
| 4 | **Mun flyby** | Leaving Kerbin; LOS behind the Mun; free return | TM-13/14 flyby | TM-13, TM-14, TM-17, TM-18 |
| 5 | **Mun landing** | Descent, landing, ascent, docking in Mun orbit, return | TM-15/16/17 probe (whatever was flown) | All |

**TODO** per mission: the objective (for example orbit: periapsis above 70 km, deorbit and splash down within N km of
a point), the save it starts from, the craft (built by the class or given), the MCC roles that matter, the SimSup
failures for the sims, and the pass criteria.

### Flight day: making the real flight different

The real flight looks and flies like the sims (what the crew trained for must still hold). It differs in ritual and
stakes. Options, cheapest first:
- **Walkout and closeout**: badges with callsigns, the mission patch, a walk to the cockpit, you strapping the crew
  in and "closing the hatch".
- **Separation**: MCC in another room or behind a screen; voice is the only link.
- **Paper checklists** with the crew's names, signed and kept.
- **Quindar tones** on the radio, and **silence during LOS** behind the Mun.
- **Cabin lighting** that follows the flight (`cockpit/lighting` is only on/off today: colour or dimming needs a build).
- **A flight surgeon console** with heart-rate straps (opt-in only: it is personal data).
- **A flight record** and a certificate: the orbit, the Δv residuals, the landing distance.

Keep the effects away from the critical moments (burns, docking, landing).

## 6. Open questions

- The backstory (section 3).
- The pace: one module and its flight per session, or several modules per flight?
- Class size: one probe room screen for everyone, or teams taking turns at the program builder?
- Who owns a craft: one class rocket that grows, or each team's own?
- The Kerbin data sheet: a shared spreadsheet, a page in Moonshot, or paper on the wall?
- Grading, if any: the Moonshot objectives, the debrief, the flights?
