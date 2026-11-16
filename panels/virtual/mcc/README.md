# Mission Control (MCC)

One web page with a tab per flight controller's console. Each controller opens it on their own laptop and picks the
consoles they hold: one, or several when there are fewer people than roles. The tabs are toggles; the consoles held
are shown one below the other, and the page remembers them on that laptop.

- Open: `http://<cockpit machine>:8650/mcc.html`, or `mcc.html#fido` for one console, `mcc.html#fido+retro` for two.
- A laptop holding several consoles answers a poll once for all of them (FLIGHT's board shows each), and its notes
  on the loop are signed with all of them (FIDO/RETRO). Holding FLIGHT with others: it runs the poll and answers for
  the others.
- The laptops must reach the cockpit machine on ports 8650 (the pages) and 9001 (the bus, MQTT over WebSockets).
  Docker publishes both on every interface; a firewall on the cockpit machine may still need to let them through.

## How it fits in

```
  laptop: FLIGHT ─┐                                    ┌─ tlm/*, cw/state, cmp/pad, panel/*/in  (read only)
  laptop: FIDO   ─┤                                    │
  laptop: RETRO  ─┼── MQTT broker (ws://…:9001) ───────┼─ mcc/poll, mcc/poll/<role>, mcc/loop/<role>  (MCC's own)
  laptop: …      ─┤                                    │
  laptop: CAPCOM ─┘                                    └─ pad/uplink  (CAPCOM only: a PAD read up to the crew)
```

There is no MCC server: every console reads the bus directly, and the little state the consoles share is kept on the
broker as retained messages, so a laptop that joins late sees the poll and the answers at once.

| Topic | Writer | Payload |
|---|---|---|
| `mcc/poll` | FLIGHT | `{"open", "question", "met"}`, retained: the go/no-go poll |
| `mcc/poll/<role>` | that console | `{"go": true \| false, "met"}`, retained: its answer (FLIGHT clears them all when it opens a poll) |
| `mcc/loop/<role>` | that console | `{"text", "met", "roles"}`: a note on the flight director's loop; `roles` lists every console the laptop holds |
| `pad/uplink` | CAPCOM | `{"tig_met", "dv": [prograde, normal, radial]}`: the burn computer shows it until the crew accepts it |

MCC never reads `sim/*`. As in Apollo, flight controllers find a failure from what the vehicle does; only the
instructor (SimSup, a separate page) knows what was injected.

## The consoles

| Tab | Role | Shows |
|---|---|---|
| FLIGHT | Flight director | Mission phase, vessel, MET, link, telemetry and cockpit health; the crew's alarms; the go/no-go poll board (open, close, each console's answer); the loop. |
| FIDO | Flight dynamics | Orbit elements and a drawing; time to apsides and to the next SOI change; the target (range, closing speed, line-of-sight rate); latitude, longitude, altitude. |
| RETRO | Retrofire | Periapsis against Kerbin's entry corridor (25–45 km), the Δv at apoapsis to bring it to 35 km, load, dynamic pressure, heat; the abort mode that fits the moment against the one selected on the crew's ABORT MODE knob. |
| GUIDO | Guidance | The burn computer's PAD and state, time to TIG, burn time at full thrust, a read-up waiting for the crew; how far the nose is from the burn direction; attitude, SAS mode, navball reference. |
| BOOSTER | Propulsion | Stage, throttle, thrust, TWR, specific impulse, limiter, gimbals, stage propellant; every engine with its state (burning, lit, weak, flameout, off). |
| EECOM | Electrical, thermal, comms | Charge, its trend and how long it lasts, solar panels, lights; the hottest part; monopropellant, fuel, oxidizer; the radio link (signal, first relay, hops, antennas). |
| CAPCOM | Capsule communicator | The PAD form: read-up only with a radio link (AOS); the readback (waiting on the burn computer, loaded); a feed of the crew's actions on the panels. |

Every console except FLIGHT has the same footer: GO / NO-GO for the open poll, and a line to the loop.

## The code

| File | What it is |
|---|---|
| `../mcc.html`, `../mcc.css` | The page and its styles (colours from `panel.css`). |
| `mcc.js` | Tabs (toggles), the consoles held and remembered, the poll banner and footer (answer, loop), the update loop (twice a second). |
| `bus.js` | The MCC's store of the last payload per topic and small readers (`vessel()`, `orbit()`, `linkUp()`…), on the connection of the shared `../bus.js`. The top bar and the page navigation come from the shared `../shell.js`. |
| `roster.js` | The consoles in tab order. Adding one: write `consoles/<id>.js` with `mount(root)` and `update()`, add it here. |
| `consoles/*.js` | One module per console. |
| `ui.js`, `bodies.js` | Formatting and DOM helpers; radius, atmosphere and μ of Kerbin, the Mun and Minmus. |

## Not done yet

- A voice loop. The text loop stands in.
- History: plots of altitude, speed or charge over time; every console shows the present only.
- RETRO's corridor and deorbit target are fixed numbers for a small capsule, not computed for the vehicle.
