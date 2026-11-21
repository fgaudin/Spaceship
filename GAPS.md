# Cockpit gaps found by flying

What the scripted flights in KSP (`tests/e2e_ksp_*.py`, `tests/rehearsal_ksp_ascent.py`) showed the cockpit cannot
do yet, or did wrong. Open items first; closed ones keep a line on what fixed them (details in CHANGELOG.md).
Gaps in the Moonshot course itself are in `selftest/gaps.md`.

## Open

### C1. Mission Control's PADs reach the crew as a data uplink, not by voice
- Decided: students compute PADs and read them up; a solo pilot asks the SOLO panel (flight-dynamics service).
- Open: the radio (voice) between Mission Control and the crew, still to be built.

### C2. Pitch and heading are only on glass
- Found by: the rehearsal (the pilot reads `tlm/attitude`) and the stick kick (which way to push for east).
- The FDAI page shows them. Open: whether a non-glass attitude indicator (a physical ball, or LED rings) is wanted.

### C3. Stage Δv is misleading on an asparagus rocket
- Found by: the rehearsal. On the pad it reads 243 m/s: the propellant of the tanks that leave with the burning
  engines, so only the first pair of boosters. Correct by its definition, not what a pilot expects.
- Possible fix: show Δv to the next staging and total Δv, on a selector.

### C4. Staging pauses the gateway for 0.7 s
- Found by: the stall logging. Rebuilding the part streams after `cmd/stage` takes 0.7 s, during which telemetry
  stops. Under the 2 s NO LINK threshold, but a visible hitch on the displays at each staging.
- Possible fix: rebuild the streams in the background, or only those of the parts that left.

### C5. The burn computer's cutoff is 0.1 s of thrust
- 3.8 m/s short at 38 m/s², 1 m/s at 26 m/s². Inside the ΔV RESID allowance; trimming the residual at a low thrust
  limit is the procedure. Better would mean counting Δv in the gateway at game speed.

### C6. Hand controllers exist only as bus topics
- `panel/hc/in/*` works (the rehearsal kicks on it), but there is no USB service yet, no page to move them by hand,
  and the mock plant ignores them.

### C7. SimSup failures are all or nothing
- No partial failures (an engine at 50 %, a slow leak). Battery and heat failures exist only in the mock: kRPC cannot
  drain a resource or heat a part.

### C8. The camera monitor was only tried in Chrome

### C9. Mission Control has no voice and no history
- The loop is text; consoles show the present, with no plots over time. RETRO's entry corridor (25–45 km) and
  deorbit target (35 km) are fixed numbers, not computed for the vehicle.
- Laptops on the network need ports 8650 and 9001 open on the cockpit machine; not tried from another machine yet.

Found by the full Mun mission flown from the panels (2026-11-20/21, `tests/mission/`, craft AcapelloCams IU): C10–C22.

### C12. MET starts again at 0 for an undocked vessel
- Found by: undocking the MEM (MET 08:33 → 00:00). The gateway sends the active vessel's own mission time, and KSP
  gives a new vessel a new one. The burn computer's TIG is keyed in MET, so the LM's and the CSM's PADs are on
  different clocks, and the event timer and MCC follow whichever vessel is flown.
- Possible fix: a mission clock kept by the cockpit from the launch (UT − launch UT), carried across undocking.

### C15. STATION cannot reach a capsule beyond 2.5 km
- Found by: the CSM had to come down to the MEM (109 km apart). STATION only switches to a capsule KSP has loaded, so
  a far-away capsule cannot be flown without the game's own vessel switch.
- Possible fix: switch to the other capsule's vessel at any range (the game can, kRPC `active_vessel`).

### C16. SOLO has no return, descent or mid-course PAD
- Found by: TEI, DOI and the mid-course corrections were computed by a stand-in for Mission Control (kRPC node
  searches) and loaded as nodes; the DOI was keyed by hand. INJECT aims at the Mun's centre (impact course), so a
  mid-course is always needed.
- Possible fix: SOLO requests for TEI (to RETRO's corridor), DOI and MCC (moon periapsis).

### C17. The landing and the rendezvous need figures the panels do not show
- Found by: the descent and the Mun ascent. With the engine off TWR reads 0, so the available deceleration for the
  final braking was read from telemetry. The RDV panel shows the closing speed only, not the total relative speed
  (to kill before closing). The liftoff time (the target's phase angle) and the launch azimuth (its inclination)
  were read from telemetry.
- Possible fix: TWR MAX (or decel available) beside TWR; REL V on RDV; a liftoff countdown on SOLO with a target.

### C18. Nothing warns that the craft cannot turn
- Found by: the MEM has no reaction wheel. With RCS off it has no torque: SAS MNVR stayed 140° off for minutes and the
  ascent's attitude oscillated (only the gimbal steered); with RCS on, holding attitude through a warp emptied its
  monoprop. Only ATT ERR showed it, indirectly.
- Possible fix: a NO TORQUE caution (SAS or HOLD engaged, no wheel and RCS off); RCS ΔV going down while coasting.

### C19. The SPEED REF knob cannot assert the position it is on
- Found by: the descent. The knob (retained) was on SURF, the game on ORBIT: turning it "to SURF" sent nothing; the LED
  blinked (right) but the crew must turn away and back.
- Possible fix: a press on the knob, or re-sending the knob's position when the LED has blinked for a while.

### C20. The CM's power runs out under the chutes
- Found by: the entry. The fuel cells are in the SM: after its jettison the CM has 150 EC, and the console went dark
  at 2.9 km under the chutes (LOW POWER just before). Correct behaviour, but there is no time-to-empty figure and no
  procedure item.
- Possible fix: EC time left on ELECTRICAL; a checklist line (power down before the SM jettison).

### C21. RETRO's corridor middle gave 10 g from the Mun
- Found by: the entry from a 34 km periapsis (corridor 25–45 km): peak 10.2 g, hottest part 62 %. The corridor is a
  fixed share of the atmosphere, not worked out for the entry speed (C9).
- Possible fix: a corridor computed for the vehicle and the entry speed (shallower from the Mun).

### C22. Stage Δv read 0 on the MEM after a reload
- Found by: the second Mun ascent: stage Δv 0 through the whole climb from the same save that had shown 638 m/s.
  Not reproduced or explained yet.

### Notes for tests (not cockpit gaps)
- The Terrier fired once for about 6 s right after a save load, with switches retained from a run before (ENG ARM on);
  not seen with every input neutral before the load. Tests zero their inputs before loading.
- Mapping a body costs KSP: a map is about a million kRPC terrain samples. The wall "lag" on the KSP machine came with
  the Mun being mapped again and again (fixed below), probably the cause; the page alone takes about 20 % of one
  core in headless Chromium, 0.5 s of script in 15 s (`tmp/wall_profile.js`).
- Releasing the launch clamps at zero thrust drops the rocket onto the pad and can break the lowest engine.
- Every save load leaves a 2–4 s telemetry gap: NO LINK comes on for that moment.

## Closed (2026-11-21)
- C10, no per-engine control docked: the engine controls drive the flown capsule's engines; the other's are held.
- C11, NEXT STAGE missed separations: docking-port decouple nodes and jettisoned covers now light DECOUPLE and FAIRING.
- C13, the EC rate froze or jumped: measured over UT, started again on a new vessel.
- C14, a field button after ENTR deselected that field: it selects it.
- STATION took one kerbal across per move: the gateway reads the crew again before each transfer.
- The Mun mapped over and over with JNSQ and stock maps side by side: maps chosen by the body's radius.
- The stack tumbled after the CSM separation (no control on it): the craft got an Instrument Unit (RC-L01 and a
  reaction wheel on the Skiff stage, `selftest/craft/build_acapello_iu.py`); its SAS holds by itself.

## Closed (2026-11-16)
- Engine matrix kept staged-away engines red with ENG FAIL: stage number now sent with the engine list; spent engines
  still attached leave the matrix.
- TWR 0.00 and stage Δv blank before ignition: computed from the engines the next staging lights.
- Cutoff on the apoapsis display overshot by 1.7 km: orbit sent at 10 Hz while thrusting (0.5 km now).
- A field selected on the burn computer showed only a cursor: it keeps its value until the first key.
- No control for the navball's speed reference: SPEED REF knob and lamps on ENG.
- SAS fell back to STABILITY when switched on, or refused a mode while off: the gateway keeps and re-applies it.
- Cross-pointer wrong while the ship turned (a frame that turned with the ship): fixed frames; it had looked like a
  SAS that would not turn and made a landing test crash.
- SAS fought the hand controller: released while the stick is off centre.
- The engine would not restart after CUTOFF with no hint why: the CUTOFF lamp blinks until the lever is back at idle.
- A command KSP refused dropped the gateway's link (and zeroed the throttle): refusals are logged and the link stays.
- NO LINK in the coast: came from that link drop; since then gaps are only save loads.
- Electric charge showed dashes after a save load: vessel resources are read again.
- PERI LOW flashed at the end of the orbit insertion: not while thrusting.
- BRAKE lamp too late (a landing stopped 4 m up): margins 1.6 / 1.3.
- RCS had no fine mode: RCS FINE switch.
