# Mission Control (MCC)

One web page with a tab per flight controller's console. Each controller opens it on their own laptop and picks the
consoles they hold: one, or several when there are fewer people than roles. The tabs are toggles, and the page
remembers them on that laptop.

Every console is one **standard screen of 1200 × 800** (16:10), its boxes on a fixed grid of **3 × 2 tiles**: each
box has a place and a size in tiles (`box(root, title, { at: [column, row], size: [w, h] })` in `ui.js`), and
nothing reflows. A box whose content is longer scrolls inside it. The consoles held sit side by side, in as many
columns as lets them be drawn biggest, all at the same zoom (`fitConsoles` in `mcc.js`): one console on a laptop
fills the window; three are smaller, but each keeps its layout.

- Open: `http://<cockpit machine>:8650/mcc.html`, or `mcc.html#fido` for one console, `mcc.html#fido+retro` for two.
- A laptop holding several consoles answers a poll once for all of them (FLIGHT's board shows each). Holding FLIGHT
  with others: it runs the poll and answers for the others.
- The laptops must reach the cockpit machine on ports 8650 (the pages) and 9001 (the bus, MQTT over WebSockets).
  Docker publishes both on every interface; a firewall on the cockpit machine may still need to let them through.

## How it fits in

```
  laptop: FLIGHT ─┐                                    ┌─ tlm/*, cw/state, cmp/pad, panel/*/in  (read only)
  laptop: FIDO   ─┤                                    │
  laptop: RETRO  ─┼── MQTT broker (ws://…:9001) ───────┼─ mcc/poll, mcc/poll/<role>  (MCC's own)
  laptop: …      ─┤                                    │
  laptop: CAPCOM ─┘                                    └─ pad/uplink  (CAPCOM only: a PAD read up to the crew)
```

There is no MCC server: every console reads the bus directly, and the little state the consoles share is kept on the
broker as retained messages, so a laptop that joins late sees the poll and the answers at once.

| Topic | Writer | Payload |
|---|---|---|
| `mcc/poll` | FLIGHT | `{"open", "question", "met"}`, retained: the go/no-go poll |
| `mcc/poll/<role>` | that console | `{"go": true \| false, "met"}`, retained: its answer (FLIGHT clears them all when it opens a poll) |
| `pad/uplink` | CAPCOM | `{"tig_met", "dv": [prograde, normal, radial]}`: the burn computer shows it until the crew accepts it |

MCC never reads `sim/*`. As in Apollo, flight controllers find a failure from what the vehicle does; only the
instructor (SimSup, a separate page) knows what was injected.

## The consoles

| Tab | Role | Shows |
|---|---|---|
| FLIGHT | Flight director | Mission phase, vessel, MET, link, telemetry and cockpit health; the crew's alarms; the go/no-go poll board (open, close, each console's answer). |
| FIDO | Flight dynamics | Orbit elements and a drawing; time to apsides and to the next SOI change; the target (range, closing speed, line-of-sight rate); latitude, longitude, altitude. |
| RETRO | Retrofire | Periapsis against the entry corridor, 36 to 64 % of the atmosphere's height (25–45 km on stock Kerbin, 29–51 km on JNSQ's), the Δv at apoapsis to bring it to the middle, time to the atmosphere, load, dynamic pressure, heat, and KSP's verdict on opening the chutes. |
| GUIDO | Guidance | The burn computer's PAD and state, time to TIG, burn time at full thrust, a read-up waiting for the crew; how far the nose is from the burn direction; attitude, SAS mode, navball reference. |
| BOOSTER | Propulsion | Stage, throttle, thrust, TWR, specific impulse, limiter, gimbals, stage propellant; every engine with its state (burning, lit, weak, flameout, off). |
| EECOM | Electrical, thermal, comms | Charge, its trend and how long it lasts, solar panels, lights; the hottest part; monopropellant, fuel, oxidizer, xenon, ablator; life support (crew, and food, water and oxygen with the hours each lasts, recyclers not counted); science (experiments, ready, holding data, its value, biome); the radio link (signal, first relay, hops, antennas). |
| CAPCOM | Capsule communicator | The PAD form: read-up only with a radio link (AOS); the readback (waiting on the burn computer, loaded); a feed of the crew's actions on the panels. |

While a poll is open, a banner across the top takes the GO / NO-GO for every console held except FLIGHT.

## The code

| File | What it is |
|---|---|
| `../mcc.html`, `../mcc.css` | The page and its styles (colours from `panel.css`). |
| `mcc.js` | Tabs (toggles), the consoles held and remembered, the poll banner (answer), the update loop (twice a second). |
| `bus.js` | The MCC's store of the last payload per topic and small readers (`vessel()`, `orbit()`, `linkUp()`…), on the connection of the shared `../bus.js`. The top bar and the page navigation come from the shared `../shell.js`. |
| `roster.js` | The consoles in tab order. Adding one: write `consoles/<id>.js` with `mount(root)` and `update()`, add it here. |
| `consoles/*.js` | One module per console. |
| `ui.js` | Formatting and DOM helpers (`box()` places a box on the console's tiles). |
| `bodies.js` | The bodies as the game has them (mcc/bodies, read from KSP by mcc-data: JNSQ's Kerbin is not stock's), stock's figures until then. |
| `history.js` | The flight so far, one sample a second as columns: the recorder's (mcc/history) when the page connects, then its own samples. |
| `charts.js`, `consolechart.js` | Strip charts over the mission clock with uPlot (`../vendor/uPlot.*`, MIT); `chartBox()` puts one in a console's box, over the last 15 minutes. |
| `orbitmath.js` | Two-body orbits (as `flight-dynamics/orbits.py`), the ground track ahead, where a body's sun is overhead. |
| `../wall.html`, `../wall.js`, `../wall.css` | The wall display (below). |

## The wall display

`http://<cockpit machine>:8650/wall.html`, on the room's TV or projector, for everyone at once (F: full screen,
without the top bar). It fills the screen at any size.

- **Ground track** on a relief map of the body, sampled from the game by mcc-data (a quarter of a degree a pixel,
  shaded and coloured by height; made once per body the first time it is flown, its moons too; a plain map until
  then): the flight so far (amber), the next orbit (cyan) and two more (dashed), night where the body's sun has set,
  the apsides, the next burn (TIG), the impact point of a suborbital path, the target's track, the launch site.
  The track ahead comes from the orbit's elements pinned to the ground by the vessel's longitude; checked in KSP
  against where the vessel was 94 s later: within 0.03° of longitude.
- **Orbit** from above the pole: the orbit with its apsides, the moons on theirs with their spheres of influence,
  the target, the sun's direction and the body's night side; the zoom follows the orbit out to the moons.
- **Figures**: altitude, apsides, inclination, speeds, time to each apsis, period, dynamic pressure, TWR, mass.
- **Charts**: altitude and apsides, velocities, loads and heat over the whole flight, and the ascent profile
  (altitude against the distance from the launch site) with the events along it.
- **Events**: lift-off, staging, engine on and cutoff, max Q, out of the atmosphere and entry, orbit, SOI changes,
  AOS and LOS, docking, the crew's alarms, from the recorder.
- **Head**: vessel, phase, sphere of influence, the next burn's countdown and Δv, MET, AOS / LOS, time warp, master
  caution and alarm.

## Charts on the consoles

RETRO: periapsis and altitude, entry loads and heat. GUIDO: the apsides and the throttle through a burn. BOOSTER:
throttle and thrust. EECOM: charge and heat. Each over the last 15 minutes, from the same history as the wall.

## mcc-data: the recorder, the bodies, the maps

A service of its own ([mcc-data/](../../../mcc-data/), in Docker as `mcc-data`): it records the flight (one sample a
second, the events), answers a page's `mcc/history/get`, reads the bodies from KSP (`mcc/bodies`) and samples the
relief maps into `panels/virtual/maps/`. It keeps the flight on disk (`mcc-data/state/`) across a restart. Without
KSP (the mock plant) it still records; the pages use stock's bodies and draw the ground track on a plain map.

## Not done yet

- A voice loop (the text loop was removed: it would not be used).
- RETRO's corridor and deorbit target are fractions of the atmosphere for a small capsule, not computed for the vehicle.
