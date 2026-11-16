# Flight dynamics: PADs for a solo pilot

With a full crew, PADs (the numbers for a burn: ignition time and Δv) are worked out on the ground, by the students,
and read up over the radio by CAPCOM. A pilot flying alone has no ground: the SOLO panel asks this service instead.
It does the sums a flight dynamics officer would, and reads the PAD up to the burn computer exactly as CAPCOM does
(`pad/uplink`): it blinks there until the pilot accepts it, then is flown like any other.

```
  SOLO panel ── panel/solo/in/fd_* ──▶ flight-dynamics ── pad/uplink ──▶ cockpit (burn computer: blinking, ACCEPT)
                                            │  ▲
                                 fd/status  │  │ tlm/orbit, tlm/target (its orbit), tlm/vessel, tlm/time
                                            ▼  │
                       cockpit (SOLO display and lamps)   gateway-ksp
```

## The requests

| Button | PAD | How |
|---|---|---|
| CIRC | Circularise | At apoapsis when the periapsis is below the safe altitude (or on an escape path: at periapsis), else at the next apsis. Δv = circular speed − speed there (vis-viva), prograde or retrograde. |
| PLANE | Change plane | Into the target's plane (a vessel around the same body), or the equator's without a target, at the node where it is cheaper (the farther one). The velocity is turned into the new plane: mostly normal, a little retrograde. |
| RDV TGT | Rendezvous | A Hohmann transfer to the target's orbit, timed so that both arrive together: when the target leads by π − (the angle it covers during the transfer). Both orbits nearly circular (e < 0.05) and in the same plane (0.5°); otherwise it says CIRC FIRST or PLANE FIRST. |
| INJECT (knob MUN / MINMUS) | Injection | The same transfer from a parking orbit around Kerbin, with the moon as the target. Minmus is 6° off the equator: the PAD says so (PL 6DEG), to correct on the way. |

Every TIG is the ignition time, half the burn before the event, so that the burn is centred on it; the burn time
comes from the vessel's mass, thrust and specific impulse (rocket equation). An event less than 60 s away is moved to
its next occurrence (the next orbit, or the next transfer window).

## The code

| File | What it is |
|---|---|
| `orbits.py` | Two-body orbits: elements, Kepler's equation, positions, nodes, Hohmann transfers, phase angles. |
| `planner.py` | The four PADs, from the telemetry; the bodies' constants and the moons' orbits (KSP stock values, checked against the game). |
| `service.py` | The MQTT shell: reads the SOLO buttons and the telemetry, publishes `pad/uplink` and `fd/status`. |
| `tests/` | The sums, against hand calculations and a position read from KSP. |

In KSP: `tests/e2e_ksp_solo.py` requests each PAD on a matching save, flies it from the panels, and checks the
outcome (circular orbit, planes matched, close approach, Mun encounter).

## Flying the PADs

The burn computer cuts off within about 0.1 s of thrust. A small burn on a light, powerful vessel (a plane trim of
0.5 m/s on a lander pushing 24 m/s²) lasts 0.02 s at full thrust and overshoots several times over: set THRUST
LIMIT so that the burn lasts 10 s or more (the PAD's burn time on the CMP panel says how long it is at the current
setting).

## Limits

- Circular-orbit sums for the plane change, the rendezvous and the injection: fine for parking orbits, rough for
  eccentric ones.
- The injection aims at the moon's centre: the encounter is there, the periapsis at the moon is not chosen. A
  mid-course correction (a later PLANE or CIRC) finishes the job.
- The rendezvous PAD is the transfer burn only; matching speed at arrival is flown on the RDV panel.
