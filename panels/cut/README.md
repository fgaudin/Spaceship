# Laser-cut faceplates

Templates for cutting the faceplates in acrylic, made from the same panel definitions as the virtual console
(`protocol/panels/*.json`), so a control moved there moves here too.

```sh
python3 panels/cut/make_templates.py            # every module, into panels/cut/out/ (not committed)
python3 panels/cut/make_templates.py eng sys    # some modules
python3 panels/cut/make_templates.py --strict   # exit 1 when there is a layout issue
```

It writes one SVG per panel (`out/<module>/<panel>.svg`, the faceplate at its real size: 99 × 99 mm for 1×1 U) and
one per module with its panels in their slots (`out/<module>.svg`, to check against the frame adapter). Python 3
only, no packages.

## In LightBurn

Import the SVG (File → Import); it is in mm and lands at its real size. The layers come in by colour (change them in
`layer_colours` in `footprints.json`; LightBurn makes one layer per distinct colour):

| Layer | Colour | What | Suggested mode |
|---|---|---|---|
| 05 | orange | titles, legends, the rule under the title | Line, low power (scored); or Fill with `"mode": "font"` |
| 01 | blue | holes and windows | Cut, first |
| 02 | red | the faceplate's outline | Cut, last (so the plate does not move while the holes are cut) |
| 03 | green | guide: what shows on the face (caps, bezels, covers, mounting screw heads), with the legends that go on the caps and lenses | Output off |
| 04 | yellow | guide: the bodies behind the plate | Output off |

The sizes are nominal: set the kerf offset on the cut layers (LightBurn: Cut settings → Kerf offset) once measured
on a test piece, or fit the holes to the parts by editing `footprints.json`.

The legends are drawn by the script in a single-stroke font (lines, the way engraved panels were lettered), so they
import as paths with nothing to install. `"text": {"mode": "font"}` in `footprints.json` writes SVG text in
`"font"` instead, to engrave filled letters; LightBurn needs that font installed, and whether it keeps the
alignment of SVG text is not tested yet.

## Footprints: `footprints.json`

One entry per item type, in mm around the component's centre. **Every number is a placeholder** for the typical part
named in `part`: measure the real one when it is in hand, edit, and run the script again.

- `cut`: what goes through the plate. A number is a round hole's diameter, `[w, h]` a rectangle.
- `front`: what shows on the face (bezel, cap, nut, flip cover). It sets the control's place in its block and is
  what the overlap check uses.
- `behind`: the body behind the plate, checked for collisions between neighbours.
- `extra`, on any footprint: more shapes to cut, around the component's centre, for an anti-rotation tab or
  mounting holes: `{"circle": 3.2, "at": [0, -9]}`, `{"rect": [2, 4], "r": 0.5, "at": [8, 0]}`.
- Types with repeated cells have their own fields: `annunciator` (`cell`, `pitch`), `seg7` (`digit_pitch`),
  `bar` (`segment_pitch`), `matrix` (`mode` holes or window, `hole`, `pitch`), `alpha` (`char_pitch`), `keypad`
  (`key`, `gap`, `side_key_width`), `rotary` (`cut`, `knob`, `legend_radius`), `knob` (the same, with its `scale`), `pot` (`travel`, `slot_width`,
  `cap`), `screen` (`margin`, `top`, `extra` for the screen's mounting holes).
- `plate`: corner radius, the mounting holes (diameter, inset from the edges, screw head for the check; they must
  match the frame adapter), the title band, the margin kept free along the edges.
- `text`: the legend, small (toggle positions, dial positions) and title sizes, caps height in mm.

## The block, and how `at` is read

As in the virtual console, an item's `at` is the centre of its whole block: the indicator LED (toggles with `led`),
the component, then its legend, stacked with `block.gap` between them. The component's place is worked out from the
footprints, so a bigger footprint moves its hole slightly but keeps the block centred where the definition says.
Push buttons carry their legend on the cap (it is drawn on the green guide, not engraved); annunciator legends go on
the cells' lenses (same); the keypad's on its keys (same). Toggle positions (ON, OFF) are scored right of the toggle;
dial positions on a circle around the knob, reading outward.

## The checks

After writing, the script lists:

- a block sticking out of the faceplate (minus `edge_margin`), or in the title band;
- two blocks overlapping on the face, or two bodies colliding behind the plate;
- a block on a mounting screw head;
- a screen window that does not fit;
- an item type with no footprint, a character the stroke font has no glyph for (drawn as a box).

With the placeholder footprints some panels already report issues (2026-11-18: 14): the 12 mm guarded toggles'
covers are bigger than the virtual console draws them, and the real 7-segment digits are wider (ASCENT, PAD). That is the point of the check: when a part is chosen, put its size here, and move the controls in
`protocol/panels/<module>.json` until both the console page and this script report nothing.
