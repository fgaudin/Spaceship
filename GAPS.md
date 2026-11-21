# Cockpit gaps found by flying

What the scripted flights in KSP (`tests/e2e_ksp_*.py`, `tests/rehearsal_ksp_ascent.py`) showed the cockpit cannot
do yet, or did wrong. Open items first; closed ones keep a line on what fixed them (details in CHANGELOG.md).
Gaps in the Moonshot course itself are in `selftest/gaps.md`.

## Open

### C1. Mission Control's PADs reach the crew as a data uplink, not by voice
- Decided: students compute PADs and read them up; a solo pilot asks the SOLO panel (flight-dynamics service).
- Open: the radio (voice) between Mission Control and the crew, still to be built (the user's, later).

### C3. Stage Δv is misleading on an asparagus rocket
- Found by: the rehearsal. On the pad it reads 243 m/s: the propellant of the tanks that leave with the burning
  engines, so only the first pair of boosters. Correct by its definition, not what a pilot expects.
- Possible fix: show Δv to the next staging and total Δv, on a selector.

### C5. The burn computer's cutoff is 0.1 s of thrust
- 3.8 m/s short at 38 m/s², 1 m/s at 26 m/s². Inside the ΔV RESID allowance; trimming the residual at a low thrust
  limit is the procedure. Decided: that stays the procedure (trim the residual at a low thrust limit).

### C6. Hand controllers exist only as bus topics
- `panel/hc/in/*` works (the rehearsal kicks on it), but there is no USB service yet, no page to move them by hand,
  and the mock plant ignores them. Not a problem: enough for tests; a USB controller will come.

### C7. SimSup failures are all or nothing
- No partial failures (an engine at 50 %, a slow leak). Battery and heat failures exist only in the mock: kRPC cannot
  drain a resource or heat a part.
- An engine kept at part thrust (its own thrust limiter, held) is possible with kRPC, but the crew would need to see an
  engine underperforming: put aside, to think about again later.

### C9. RETRO's corridor and deorbit target are fixed numbers
- The entry corridor (25–45 km) and the deorbit target (35 km) are not computed for the vehicle (see C21).

### C15. STATION cannot reach a capsule beyond 2.5 km
- Found by: the CSM had to come down to the MEM (109 km apart). STATION only switches to a capsule KSP has loaded, so
  a far-away capsule cannot be flown without the game's own vessel switch.
- Possible fix: switch to the other capsule's vessel at any range (the game can, kRPC `active_vessel`).
- Left as is for now: not known yet whether it is needed.

### C17. The landing and the rendezvous need figures the panels do not show
- Found by: the descent and the Mun ascent. With the engine off TWR reads 0, so the available deceleration for the
  final braking was read from telemetry. The RDV panel shows the closing speed only, not the total relative speed
  (to kill before closing). The liftoff time (the target's phase angle) and the launch azimuth (its inclination)
  were read from telemetry.
- Possible fix: TWR MAX (or decel available) beside TWR; REL V on RDV; a liftoff countdown on SOLO with a target.
- Done: the total speed on SPEED REF TGT is the relative speed (rel_v), as on KSP's navball; TWR MAX on ENGINE.
- Done: RDV TGT pressed while landed reads up a PAD whose TIG is the liftoff (counted down by the EVENT TIMER on TIG),
  the azimuth in the FLIGHT DYNAMICS text; no new control (Mission Control computes them otherwise). Its ascent
  model is still to be checked against a flight in KSP.

### C18. Nothing warns that the craft cannot turn
- Found by: the MEM has no reaction wheel. With RCS off it has no torque: SAS MNVR stayed 140° off for minutes and the
  ascent's attitude oscillated (only the gimbal steered); with RCS on, holding attitude through a warp emptied its
  monoprop. Only ATT ERR showed it, indirectly.
- Possible fix: a NO TORQUE caution (SAS or HOLD engaged, no wheel and RCS off); RCS ΔV going down while coasting.
- Left as is for now.

### C21. RETRO's corridor middle gave 10 g from the Mun
- Found by: the entry from a 34 km periapsis (corridor 25–45 km): peak 10.2 g, hottest part 62 %. The corridor is a
  fixed share of the atmosphere, not worked out for the entry speed (C9).
- Possible fix: a corridor computed for the vehicle and the entry speed (shallower from the Mun).

### Notes for tests (not cockpit gaps)
- The Terrier fired once for about 6 s right after a save load, with switches retained from a run before (ENG ARM on);
  not seen with every input neutral before the load. Tests zero their inputs before loading.
- Mapping a body costs KSP: a map is about a million kRPC terrain samples. The wall "lag" on the KSP machine came with
  the Mun being mapped again and again (fixed below), probably the cause; the page alone takes about 20 % of one
  core in headless Chromium, 0.5 s of script in 15 s (`tmp/wall_profile.js`).
- Releasing the launch clamps at zero thrust drops the rocket onto the pad and can break the lowest engine.
- Every save load leaves a 2–4 s telemetry gap: NO LINK comes on for that moment.

## Closed (2026-11-21)
- C16, no TEI, DOI or mid-course PAD on SOLO: not needed; flown by hand (burn retrograde to the periapsis wanted).
- C4, staging paused telemetry (0.7 s on a big rocket): the part streams are rebuilt on another thread and swapped in.
- C9, the rest: the text loop was removed (it would not be used; the voice loop is the user's, later); Mission Control
  has its history (mcc-data) and was opened from another machine.
- C19, the SPEED REF knob could not assert the position it is on: SAS PRO and RETRO (the modes that follow it) send the
  knob's reference first when the game's is another; otherwise, and for STATION, turn away and back (the procedure).
- C2, pitch and heading only on glass: they are on 7-segment displays now.
- C8, the camera monitor only tried in Chrome: it works in Firefox.
- C20, the CM's power running out under the chutes: not a gap; the crew can work out the time left, and a design can
  carry a battery for the descent.
- C22, stage Δv read 0 through an ascent: the stage's tanks, chosen while no engine read lit, stayed empty; they are
  chosen again when the engines lit change.
- C12, MET started again for an undocked vessel: one mission clock, kept by the gateway (`mission/clock`); MET RESET.
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
