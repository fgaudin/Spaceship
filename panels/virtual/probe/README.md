# Probe control room

The students' station for the probe era of the Moonshot + KSP campaign. Every course module ends with an uncrewed
flight flown from here. The crewed flights come after the last module, with the full MCC and the cockpit.

The room starts almost dark. The instructor clears rows of telemetry and kinds of program steps as the students
progress (SimSup page, *Probe control room*). A row worked out from others (apoapsis, Δv, TWR) is cleared only
once the students have shown they can work it out by hand. Nothing in the room predicts: there is no map, no
trajectory after a burn and no node readout. The students predict in their spreadsheet, fly, and compare.

Page: **http://localhost:8650/probe.html** (PROBE in the top bar). Designed for one shared 2560 × 1440 screen in full
screen (F11). Below 1500 px wide it falls back to two columns and scrolls.

## How it fits in

```
  simsup.html ──sim/simsup/cmd──▶ simsup service ──▶ probe/mode, probe/clearance (retained)
                                                          │
  probe.html ──probe/program, probe/exec──▶ cockpit logic ┤ probe sequencer (cockpit/probe_sequencer.py)
       ▲                                       │          │   └─▶ cmd/stage, throttle, sas, sas_mode, rotate, node,
       └──── probe/sequencer, tlm/*, cmp/pad ──┘          │        chute, science ──▶ gateway ──▶ KSP
```

- **Probe mode** (`probe/mode`): the cockpit logic stops listening to the panels (their inputs are recorded but
  command nothing, and no switch is re-asserted), closes the throttle, and flies only the sequencer's program.
  Leaving probe mode stops a running program.
- **The program** is a list of steps, each at `T+` seconds after GO, at a mission time (MET), or `BURNOUT+` seconds
  after a burnout (below). They run in order; a step whose time has passed when its turn comes runs at once.
- **BURNOUT** (command group `cmd_burnout`): the engines the next staging will drop have run out of propellant. With
  boosters around a core that burns on, those are the boosters; under an upper stage, the core; when the next
  staging drops no engine, every lit engine. Short burners lit with the boosters (Sepratrons, ullage motors) do not
  fire it: it waits for everything the staging drops. The engines must read empty for 0.5 s. It follows the staging
  built in the VAB: a wrong staging gives a wrong burnout, and the students go back to their build. Staging on
  depletion is how real stages separated; it is meant as an unlock after a flight staged on computed burn times. The page saves drafts and named programs in the
  browser.
- **The uplink needs the radio link** (KSP's CommNet), and so do GO, STOP and CLEAR. A program already running
  carries on through a loss of signal, like a real stored sequence.

## Program steps

| Step | Settings | Always there? |
|---|---|---|
| STAGE | (often at BURNOUT+1 s once `cmd_burnout` is cleared) | yes |
| THROTTLE | % | yes |
| KICK | pitch, yaw, roll inputs (−1…1), for s seconds: SAS off meanwhile, then inputs centred and SAS on | yes |
| SAS ON/OFF | | yes |
| SAS MODE | stability; prograde/retrograde (`cmd_sas_pro`); normal, radial, target (`cmd_sas_all`); maneuver (`cmd_burn`) | stability only |
| CHUTES | | yes |
| BURN | Δv prograde, normal, radial; throttle %. At a MET (the TIG). Its PAD goes into the burn computer as soon as it is the next burn, so the node exists for SAS MANEUVER. The computer is armed at TIG and cuts off on accumulated Δv. Given up if no Δv is counted 10 s after TIG; ended as failed (Δv short logged, throttle closed) if the thrust stops for 3 s before the cutoff, so that the next step (a staging, another burn) can run. A burn across a staging is two burns: one per stage, the Δv split between them | `cmd_burn` |
| EXPERIMENTS | run every experiment that can run | `cmd_science` |

The KICK is the pitch-over of the course's gravity turn: a few seconds of stick, then SAS PROGRADE follows the
velocity. Its size and length are the students' free parameters. Which way a pitch or yaw input turns the rocket
depends on how it was built in the VAB: try it on the pad.

## Telemetry rows

From `catalogue.js`, by box: **trajectory** (altitude and vertical speed; radius, orbital speed and flight-path
angle; apsides; period, semi-major axis and eccentricity; latitude and longitude; time to the apsides;
inclination and node; body and time to SOI; radar altitude and horizontal speed), **vehicle** (stage, mass,
thrust and throttle; stage propellant and Isp; stage Δv and TWR; attitude and SAS; the burn computer; charge),
**environment** (static pressure and outside temperature; dynamic pressure and g; hottest part; target).
Each group has the course module it is meant for.

The charts and the CSV export (EVENTS, EXPORT CSV: the flight so far, one sample a second, for the spreadsheet)
carry only the cleared series. The event list shows what the room would see happen: liftoff, staging, engine on and
off, AOS and LOS, touchdown, splashdown, docking. It never names the trajectory (ORBIT, SUBORBITAL, ESCAPE): that
is the students' to work out. SOI changes show once `soi` is cleared.

## Not covered (yet)

- Nothing in the program reacts to the vehicle: every step is on time. A rocket held by a clamp staged on the pad
  carried on with its program (found in KSP with a craft whose staging the VAB had reset). For a student that is a
  lesson; the room could show a NEXT STAGE row (what it lights and releases: `tlm/vessel` `next_stage`), a
  measurement of the configuration, not an answer.
- The sequencer's log runs on across programs and flights (useful for a debrief, noisy for the next flight).

- The room only enforces clearances in the page. A student with an MQTT client could send any step; the
  sequencer does not check `probe/clearance`.
- KSP's own screen gives answers away: map view, the navball's burn time, the stage Δv. Keep the KSP machine's
  keyboard with the instructor and the flight scene in F2. MechJeb (installed) has its own windows, and Δv in the
  VAB: hide or remove it for the campaign.
- No phase angle to the Mun or to a target (the rendezvous breakpoints need it, or the students read it some
  other way).
- No attitude hold (kRPC autopilot) step. It is planned as a later "guidance computer" unlock, for the launch
  azimuth and the Mun ascent.
- The mock plant ignores the KICK (`cmd/rotate`) and the experiments.
