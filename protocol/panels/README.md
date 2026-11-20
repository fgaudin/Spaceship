# Modules, panels and the console

The I/O hardware of the capsule, described so that the virtual console draws it at its real size and the generic
firmware can be generated from the same files.

## Words

- **U**: the grid unit, **100 mm**: the slot. Every panel is a whole number of U wide and high, and its faceplate
  is built 0.5 mm smaller on each side for clearance (a 1×1 U panel is 99 × 99 mm). Modules fill their slots exactly.
- **Panel**: one plate of acrylic, W×H U (mostly 1×1, a few 2×1 or 1×2), with its controls at fixed places.
- **Module**: one board (an Olimex ESP32-POE), one PoE cable, one definition file. It carries one or more panels,
  held side by side by a frame adapter, so the same panels can make a 3×1, a 1×3 or an L. It is the unit that is
  plugged in, swapped, or taken to the bench. Two modules of the same shape can trade places.
- **Console**: where the modules sit in the capsule, in zones (overhead, main).

A panel's controls publish into the panel's own **bus namespace** (`"bus": "eng"` → `panel/eng/in/<control>`,
`panel/eng/out/<output>`), not the module's. A panel moved to another module keeps its topics, so the cockpit logic
does not notice. A module's heartbeat is `panel/<module>/status`.

## `<module>.json`: one module

```json
{
  "id": "eng", "title": "PROPULSION · FLIGHT CONTROL", "fw": "virtual-0.1", "board": "olimex-esp32-poe",
  "panels": [
    { "id": "engines_abort", "title": "ENGINES · ABORT", "size": [1, 1], "at": [2, 1], "bus": "eng",
      "items": [ { "type": "guarded_toggle", "id": "abort_arm", "label": "ABORT ARM", "in": "abort_arm", "at": [56, 78] } ] }
  ]
}
```

| Field | Meaning |
|---|---|
| panel `size` | `[width, height]` in U |
| panel `at` | where the panel sits on the module, in U from the module's top-left corner (`[column, row]`) |
| panel `bus` | the topic namespace of its controls |
| item `at` | the centre of the control block (indicator LED, component and legend), in mm from the faceplate's top-left corner. The panel title takes the top 12 mm. |
| item `type`, `in`, `out`, … | the control: `toggle`, `guarded_toggle`, `button`, `lamp_button`, `led`, `annunciator`, `seg7`, `bar`, `rotary`, `pot` (a lever), `knob` (a continuous knob, 0 to 1 over 270°; optional `scale` labels spread over the sweep, `steps` its resolution, `nudge` a wheel notch, `readout: false` without the percentage), `keypad`, `matrix`, `alpha`, `buzzer` (see `panels/virtual/widgets.js`). `toggle`, `guarded_toggle` and `rotary` take an indicator LED above them: `"led": {"out", "color"}`. A `toggle` can name its positions, `"positions": ["RADAR", "SEA"]` (up, down); a `bar` can stand up with `"vertical": true` |

Not there yet: a `pin` per control, for when the boards are designed.

The same files make the laser-cut templates of the faceplates (SVG for LightBurn, with the components' cutouts
from `panels/cut/footprints.json`): [panels/cut/README.md](../../panels/cut/README.md).

A **glass module** (a Raspberry Pi and a screen: FDAI, CAM) has a panel with a `screen` instead of controls:

```json
{ "id": "fdai", "title": "FDAI", "size": [2, 2], "at": [0, 0], "items": [],
  "screen": { "page": "fdai.html", "inches": 8, "mm": [162, 122], "px": [1024, 768] } }
```

The console shows the page (`fdai.html?embed=1`: no top bar, fitted to the screen; a page may carry its own query, as the windows' `cam.html?window=left`) at the screen's resolution
(`px`), scaled to its visible size (`mm`), centred under the panel's title. The page publishes its own status
(`panel/fdai/status`, `cam/status`); a module made only of glass has no I/O node of its own. The wheel and Esc over
the page act on the console, as everywhere else on it.

A glass panel may also carry controls (`items`, with the panel's `bus`), placed around the screen like on any panel:
the FDAI module's ATTITUDE panel has pitch, heading, roll and their rates beside the ball, the FDAI's own controls (NEEDLES, ERROR SCALE, MARKERS) in
the corners around it, and SAS, RCS, RCS FINE and SPEED REF under it (the SAS modes are the SAS MODE module's buttons), on the `eng` bus. Optional
`screen` fields: `at` (its centre on the faceplate, in mm; by default centred under the title), `round` (a circular
window) and `module_mm` (the display's body behind the plate, a circle on a round screen, for the cut templates' collision check). A glass page has no keys of its own:
what it would set on its bezel comes from panel controls through the cockpit.
The module then has an I/O node too (on the hardware: the Pi's GPIO, or a small I/O board on it); in the virtual
console it reports on `panel/<module>/io/status`, since the page already reports on `panel/<module>/status`. Both layout checks
treat the screen as an obstacle: a control on it is an issue (a round screen is a circle, so its corners are free).

Components are drawn at about their real size: 0.36" 7-segment digits (9 mm high), 18 × 12 mm lit push buttons,
14 mm keypad keys, 5 mm LEDs, bat-handle toggles.

## `console.json`: the capsule

```json
{ "title": "CENTRE CONSOLE",
  "zones": [ { "id": "main", "title": "MAIN", "modules": [ { "module": "eng", "at": [0, 0] } ] } ] }
```

Each zone is a grid of U; a module's `at` is its top-left corner on it. A zone's optional `size` ([width, height]
in U) makes it bigger than what it holds, so that its free places show. The zones are drawn one under the other, flat.
`"align": "center"` centres a zone over the others. `"side": "left"` (or `"right"`) draws a zone beside that
column instead, its top at the column's top, or `top` U lower; `"flush": true` puts it against the column with no
title: the windows, alongside OVERHEAD and MAIN. A panel with `"bare": true` is glass set straight into the console
board, drawn without faceplate, title or screws, and not cut. A screen's `"frame": {"width", "rivet", "rivet_every", "corner"}` (mm)
draws a riveted metal ring that wide around its glass, rivets along its middle about `rivet_every` apart, its outer
corners rounded to `corner`. `outline` (corners in U, clockwise) gives a zone a shape of its own: its grid is
cut to that shape and the outline drawn around it, as MAIN's taper down to the burn computer. A module's `at` may be fractional.
The firmware never reads this file.

## Changing the layout

Edit the numbers and reload the console page (`index.html`). It never reflows: what moves is what you moved. The
wheel zooms around the pointer, dragging pans, double-click fits a module, Esc fits everything.

- The **grid** checkbox draws a 10 mm grid on every panel; empty U places of a zone show faintly.
- Anything misplaced is outlined in red and counted in the top bar (`layout: n issues`, the list in its tooltip and
  in the browser console): a control sticking out of its panel, two controls overlapping, two panels or two modules
  on the same place, the same input on two panels, a module in `console.json` without a file.
- A new module, for example the C&W panel and the COM panel together: write `<new>.json` with both panel blocks
  (positions on each panel stay as they are; the panels' `bus` stays `eng` and `com`), give each panel its `at` on
  the new module, remove them from their old modules, and place the module in `console.json`.
