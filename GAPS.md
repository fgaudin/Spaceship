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

### Notes for tests (not cockpit gaps)
- Releasing the launch clamps at zero thrust drops the rocket onto the pad and can break the lowest engine.
- Every save load leaves a 2–4 s telemetry gap: NO LINK comes on for that moment.

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
