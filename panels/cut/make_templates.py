#!/usr/bin/env python3
"""Laser-cut templates of the faceplates, from the panel definitions (protocol/panels/*.json) and the component
footprints (footprints.json), as SVG in mm for LightBurn.

    python3 panels/cut/make_templates.py [--out DIR] [--strict] [module ...]

One SVG per panel (out/<module>/<panel>.svg) and one per module with its panels in their slots (out/<module>.svg).
The layers use LightBurn's palette colours, so they import as separate layers:

    05 orange  legends and titles: single-stroke lines to score (or text, with "text": {"mode": "font"})
    01 blue    cutouts: holes and windows (cut them first)
    02 red     the faceplate's outline (cut it last)
    03 green   guide, no output: what shows on the face (caps, bezels, covers), with the cap legends
    04 yellow  guide, no output: the bodies behind the plate

A control's `at` is the centre of its block (LED, component, legend), as in the virtual console; the component's
place in the block comes from the footprints, so a bigger footprint moves its hole but keeps the block centred.
The checks report a block out of the faceplate or in the title band, two blocks overlapping on the face or behind
it, and a block on a mounting screw. Exit 0, or 1 with --strict when there is an issue."""

import argparse
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFINITIONS = HERE.parent.parent / 'protocol' / 'panels'
U_MM = 100                  # protocol/panels/README.md: 1 U is the slot
PANEL_CLEARANCE_MM = 0.5    # the faceplate is that much smaller on each side (panel.js: PANEL_CLEARANCE_MM)

LAYERS = [  # id, default colour (LightBurn's palette; footprints.json "layer_colours" overrides), what
    ('legends', '#FF8000', 'legends: score or engrave'),
    ('cut', '#0000FF', 'cutouts: cut first'),
    ('outline', '#FF0000', 'outline: cut last'),
    ('front', '#00E000', 'guide, no output: on the face'),
    ('behind', '#D0D000', 'guide, no output: behind the plate'),
]

# ---------- a single-stroke font: caps height 6 units, x from 0 to the glyph's width, y down ----------
GLYPHS = {
    'A': '0,6 2,0 4,6; 0.67,4 3.33,4', 'B': '0,6 0,0 2.8,0 3.8,0.8 3.8,2.2 2.8,3 0,3; 2.8,3 4,3.8 4,5.2 3,6 0,6',
    'C': '4,1 3,0 1,0 0,1 0,5 1,6 3,6 4,5', 'D': '0,0 0,6 2.5,6 4,4.5 4,1.5 2.5,0 0,0', 'E': '4,0 0,0 0,6 4,6; 0,3 3,3',
    'F': '4,0 0,0 0,6; 0,3 3,3', 'G': '4,1 3,0 1,0 0,1 0,5 1,6 3,6 4,5 4,3.5 2.5,3.5', 'H': '0,0 0,6; 4,0 4,6; 0,3 4,3',
    'I': '2|0,0 2,0; 1,0 1,6; 0,6 2,6', 'J': '4,0 4,5 3,6 1,6 0,5', 'K': '0,0 0,6; 4,0 0,4; 1.5,2.5 4,6', 'L': '0,0 0,6 4,6',
    'M': '0,6 0,0 2,3.5 4,0 4,6', 'N': '0,6 0,0 4,6 4,0', 'O': '1,0 3,0 4,1 4,5 3,6 1,6 0,5 0,1 1,0',
    'P': '0,6 0,0 3,0 4,1 4,2.2 3,3.2 0,3.2', 'Q': '1,0 3,0 4,1 4,5 3,6 1,6 0,5 0,1 1,0; 2.5,4.5 4,6',
    'R': '0,6 0,0 3,0 4,1 4,2.2 3,3.2 0,3.2; 2,3.2 4,6', 'S': '4,1 3,0 1,0 0,1 0,2 1,3 3,3 4,4 4,5 3,6 1,6 0,5',
    'T': '0,0 4,0; 2,0 2,6', 'U': '0,0 0,5 1,6 3,6 4,5 4,0', 'V': '0,0 2,6 4,0', 'W': '5|0,0 1.25,6 2.5,2.5 3.75,6 5,0',
    'X': '0,0 4,6; 4,0 0,6', 'Y': '0,0 2,3 4,0; 2,3 2,6', 'Z': '0,0 4,0 0,6 4,6',
    '0': '1,0 3,0 4,1 4,5 3,6 1,6 0,5 0,1 1,0', '1': '1,1 2,0 2,6; 1,6 3,6', '2': '0,1 1,0 3,0 4,1 4,2 0,6 4,6',
    '3': '0,1 1,0 3,0 4,1 4,2 3,3 1.5,3; 3,3 4,4 4,5 3,6 1,6 0,5', '4': '3,6 3,0 0,4 4,4',
    '5': '4,0 0,0 0,2.6 3,2.6 4,3.6 4,5 3,6 1,6 0,5', '6': '3.5,0 1.5,0 0,1.5 0,5 1,6 3,6 4,5 4,3.8 3,2.8 1,2.8 0,3.8',
    '7': '0,0 4,0 1.5,6', '8': '1,3 0,2 0,1 1,0 3,0 4,1 4,2 3,3 1,3 0,4 0,5 1,6 3,6 4,5 4,4 3,3',
    '9': '4,2.2 3,3.2 1,3.2 0,2.2 0,1 1,0 3,0 4,1 4,4.5 2.5,6 0.5,6',
    ' ': '3|', '&': '4,6 1,2 1,1 1.7,0 2.6,0 3.2,1 3.2,1.6 0,4 0,5 1,6 2.2,6 4,3.5', '(': '2|2,0 1,1.2 1,4.8 2,6',
    ')': '2|0,0 1,1.2 1,4.8 0,6', '+': '2,1.5 2,4.5; 0.5,3 3.5,3', '-': '3|0.4,3 2.6,3', '−': '0.5,3 3.5,3',
    '.': '1|0.5,5.6 0.5,6', '/': '0,6 4,0', '°': '2.5|0.8,0 1.7,0 2.5,0.8 2.5,1.7 1.7,2.5 0.8,2.5 0,1.7 0,0.8 0.8,0',
    '·': '1|0.5,2.8 0.5,3.2', '×': '0.8,1.8 3.2,4.2; 3.2,1.8 0.8,4.2', 'Δ': '2,0 4,6 0,6 2,0',
    '▸': '1,1.5 3.5,3 1,4.5 1,1.5', '◂': '3,1.5 0.5,3 3,4.5 3,1.5',
}
GLYPH_SPACING = 1.6         # units between glyphs


def parse_glyph(code):
    width, _, strokes = code.rpartition('|') if '|' in code else ('4', '', code)
    lines = [[tuple(float(v) for v in point.split(',')) for point in stroke.split()] for stroke in strokes.split(';')]
    return float(width), [line for line in lines if line]


FONT = {char: parse_glyph(code) for char, code in GLYPHS.items()}
missing_glyphs = set()


def glyph(char):
    if char not in FONT:
        missing_glyphs.add(char)
        return 4.0, [[(0, 0), (4, 0), (4, 6), (0, 6), (0, 0)]]
    return FONT[char]


def text_width(text, size):
    if not text:
        return 0.0
    return (sum(glyph(char)[0] for char in text) + GLYPH_SPACING * (len(text) - 1)) * size / 6


# ---------- shapes: plain dicts, in mm ----------
def circle(x, y, diameter):
    return {'kind': 'circle', 'x': x, 'y': y, 'd': diameter}


def rect(x, y, w, h, r=0.0):
    return {'kind': 'rect', 'x': x, 'y': y, 'w': w, 'h': h, 'r': min(r, w / 2, h / 2)}


def text(x, y, string, size, anchor='middle'):
    """A legend centred vertically on y, its caps `size` mm high."""
    return {'kind': 'text', 'x': x, 'y': y, 't': string, 's': size, 'anchor': anchor}


def size_shape(x, y, size, r=0.0):
    """A footprint size: a number is a circle's diameter, [w, h] a rectangle."""
    return circle(x, y, size) if isinstance(size, (int, float)) else rect(x, y, size[0], size[1], r)


def bounds(shape):
    if shape['kind'] == 'circle':
        r = shape['d'] / 2
        return (shape['x'] - r, shape['y'] - r, shape['x'] + r, shape['y'] + r)
    if shape['kind'] == 'rect':
        return (shape['x'] - shape['w'] / 2, shape['y'] - shape['h'] / 2, shape['x'] + shape['w'] / 2, shape['y'] + shape['h'] / 2)
    width = text_width(shape['t'], shape['s'])
    left = {'start': shape['x'], 'end': shape['x'] - width}.get(shape['anchor'], shape['x'] - width / 2)
    return (left, shape['y'] - shape['s'] / 2, left + width, shape['y'] + shape['s'] / 2)


def union(boxes):
    boxes = list(boxes)
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def moved(shape, dx, dy):
    return {**shape, 'x': shape['x'] + dx, 'y': shape['y'] + dy}


def extra_shapes(footprint):
    shapes = []
    for extra in footprint.get('extra', []):
        x, y = extra.get('at', (0, 0))
        shapes.append(circle(x, y, extra['circle']) if 'circle' in extra else rect(x, y, *extra['rect'], extra.get('r', 0)))
    return shapes


# ---------- components: what each control cuts and covers, around its own centre ----------
def grid_cells(columns, rows, pitch_x, pitch_y):
    """The centres of a columns × rows grid centred on 0, 0, row by row."""
    return [((c - (columns - 1) / 2) * pitch_x, (r - (rows - 1) / 2) * pitch_y) for r in range(rows) for c in range(columns)]


def component(item, footprint, settings):
    """{cut, front, behind, guide_text, legends}: shapes around the component's centre; front is one box."""
    kind, fp, small = item['type'], footprint, settings['text']['small']
    cut, behind, guide_text, legends = [], [], [], []

    if kind in ('toggle', 'guarded_toggle', 'led', 'lamp_button', 'button', 'buzzer'):
        if kind == 'buzzer':
            cut += [circle(0, 0, fp['hole'])] + [circle(fp['pitch'] * math.cos(a * math.pi / 3), fp['pitch'] * math.sin(a * math.pi / 3), fp['hole'])
                                                 for a in range(6)]
        else:
            cut.append(size_shape(0, 0, fp['cut'], 0.5))
        front = bounds(size_shape(0, 0, fp['front']))
        if kind in ('lamp_button', 'button') and item.get('label'):
            guide_text.append(text(0, 0, item['label'], small))
        for index, position in enumerate(item.get('positions', fp.get('positions', []))[:2] if kind == 'toggle' else []):
            y = (front[1] + small / 2 + 0.5) if index == 0 else (front[3] - small / 2 - 0.5)
            legends.append(text(front[2] + 1, y, position, small, 'start'))

    elif kind == 'annunciator':
        columns = item.get('cols', 3)
        rows = math.ceil(len(item['cells']) / columns)
        for (x, y), cell in zip(grid_cells(columns, rows, *fp['pitch']), item['cells']):
            cut.append(rect(x, y, *fp['cell'], fp['corner_radius']))
            guide_text.append(text(x, y, cell.get('label', ''), small * 0.8))
        width = (columns - 1) * fp['pitch'][0] + fp['cell'][0] + 2 * fp['frame']
        height = (rows - 1) * fp['pitch'][1] + fp['cell'][1] + 2 * fp['frame']
        front = (-width / 2, -height / 2, width / 2, height / 2)

    elif kind in ('seg7', 'bar', 'alpha'):
        count, pitch = {'seg7': (item.get('digits', 1), fp.get('digit_pitch')), 'bar': (item.get('segments', 10), fp.get('segment_pitch')),
                        'alpha': (item.get('chars', 8), fp.get('char_pitch'))}[kind]
        length = count * pitch + 2 * fp['pad']
        width, height = (fp['height'], length) if item.get('vertical') else (length, fp['height'])
        window = rect(0, 0, width, height, fp['corner_radius'])
        cut.append(window)
        front = bounds(window)
        if kind == 'seg7':
            behind.append(rect(0, 0, window['w'], fp['behind_height']))

    elif kind == 'matrix':
        columns, rows = item['cols'], item['rows']
        if fp['mode'] == 'window':
            cut.append(rect(0, 0, (columns - 1) * fp['pitch'] + fp['hole'] + 2 * fp['pad'], (rows - 1) * fp['pitch'] + fp['hole'] + 2 * fp['pad'], 0.5))
        else:
            cut += [circle(x, y, fp['hole']) for x, y in grid_cells(columns, rows, fp['pitch'], fp['pitch'])]
        half_w, half_h = ((columns - 1) * fp['pitch'] + fp['hole']) / 2 + fp['pad'], ((rows - 1) * fp['pitch'] + fp['hole']) / 2 + fp['pad']
        front = (-half_w, -half_h, half_w, half_h)

    elif kind in ('rotary', 'knob'):
        # a selector's positions, or a continuous knob's scale over 270° (as the virtual console, widgets.js)
        positions = item['positions'] if kind == 'rotary' else fp['scale']
        count = len(positions)
        sweep = min(270, 45 * (count - 1)) if kind == 'rotary' else 270
        for index, position in enumerate(positions):
            angle = math.radians(-sweep / 2 + (sweep * index / (count - 1) if count > 1 else 0))
            sine = math.sin(angle)                     # legends read outward from the knob, as on a dial plate
            anchor = 'middle' if abs(sine) < 0.1 else ('start' if sine > 0 else 'end')
            legends.append(text(fp['legend_radius'] * sine, -fp['legend_radius'] * math.cos(angle), position, small, anchor))
        cut.append(circle(0, 0, fp['cut']))
        behind.append(circle(0, 0, fp['behind']))
        front = union([bounds(circle(0, 0, fp['knob']))] + [bounds(legend) for legend in legends])

    elif kind == 'pot':
        length = fp['travel'] + fp['slot_width']
        cut.append(rect(0, 0, fp['slot_width'], length, fp['slot_width'] / 2))
        cap_w, cap_h = fp['cap']
        front = (-cap_w / 2, -(fp['travel'] + cap_h) / 2, cap_w / 2, (fp['travel'] + cap_h) / 2)
        behind.append(size_shape(0, 0, fp['behind']))

    elif kind == 'keypad':
        key_w, key_h = fp['key']
        gap, rows = fp['gap'], item['rows']
        columns = len(rows[0])
        grid_w, grid_h = columns * key_w + (columns - 1) * gap, len(rows) * key_h + (len(rows) - 1) * gap
        sides = [(side, item.get(side) or []) for side in ('left', 'right')]
        total_w = grid_w + sum(fp['side_key_width'] + gap for _, keys in sides if keys)
        left = -total_w / 2
        labels = item.get('labels', {})

        def key(x, y, w, h, name):
            cut.append(rect(x, y, w, h, fp['corner_radius']))
            guide_text.append(text(x, y, labels.get(name, name), small))

        x = left
        for side, keys in sides:
            if side == 'right':
                x = left + total_w - fp['side_key_width']
            if not keys:
                continue
            slots = max(2, len(keys))                  # as the virtual console: a side column has 2 rows at least
            tall = (grid_h - (slots - 1) * gap) / slots
            for index, name in enumerate(keys):
                key(x + fp['side_key_width'] / 2, -grid_h / 2 + tall / 2 + index * (tall + gap), fp['side_key_width'], tall, name)
            if side == 'left':
                x += fp['side_key_width'] + gap
        grid_left = left + (fp['side_key_width'] + gap if item.get('left') else 0)
        for r, row in enumerate(rows):
            for c, name in enumerate(row):
                if name:
                    key(grid_left + c * (key_w + gap) + key_w / 2, -grid_h / 2 + r * (key_h + gap) + key_h / 2, key_w, key_h, name)
        front = (-total_w / 2, -grid_h / 2, total_w / 2, grid_h / 2)

    else:
        return None

    cut += extra_shapes(fp)
    if fp.get('behind') is not None and kind not in ('rotary', 'pot'):
        behind.append(size_shape(0, 0, fp['behind']))
    return {'cut': cut, 'front': front, 'behind': behind, 'guide_text': guide_text, 'legends': legends}


# ---------- a control block: LED, component, legend, stacked and centred on `at` ----------
def place_item(item, settings, issues, where):
    footprints, text_settings, gap = settings['footprints'], settings['text'], settings['block']['gap']
    footprint = footprints.get(item['type'])
    built = component(item, footprint, settings) if footprint else None
    if built is None:
        issues.append(f'{where}: no footprint for "{item["type"]}"')
        return None
    front = built['front']
    parts = []                                          # (name, height, width)
    if item.get('led'):
        parts.append(('led', footprints['led']['front'], footprints['led']['front']))
    parts.append(('component', front[3] - front[1], front[2] - front[0]))
    label = item.get('label') or ''
    if label and footprint.get('legend', True):
        parts.append(('legend', text_settings['legend'], text_width(label, text_settings['legend'])))

    x0, y0 = item['at']
    top = y0 - (sum(height for _, height, _ in parts) + gap * (len(parts) - 1)) / 2
    placed = {'cut': [], 'front': [], 'behind': [], 'legends': [], 'guide_text': []}
    for name, height, _ in parts:
        centre_y = top + height / 2
        if name == 'led':
            placed['cut'].append(circle(x0, centre_y, footprints['led']['cut']))
            placed['front'].append(circle(x0, centre_y, footprints['led']['front']))
        elif name == 'component':
            dx, dy = x0 - (front[0] + front[2]) / 2, centre_y - (front[1] + front[3]) / 2
            for layer in ('cut', 'behind', 'legends', 'guide_text'):
                placed[layer] += [moved(shape, dx, dy) for shape in built[layer]]
            placed['front'].append(rect(x0, centre_y, front[2] - front[0], front[3] - front[1]))
            placed['component_at'] = (dx, dy)
        else:
            placed['legends'].append(text(x0, centre_y, label, text_settings['legend']))
        top += height + gap
    placed['box'] = union([bounds(shape) for shape in placed['front'] + placed['legends']])
    placed['behind_box'] = union([bounds(shape) for shape in placed['behind']]) if placed['behind'] else None
    return placed


def touches_circle(box, shape):
    """A box against a circle: controls may sit in the corners around a round screen."""
    x, y = shape['x'], shape['y']
    return math.hypot(x - max(box[0], min(x, box[2])), y - max(box[1], min(y, box[3]))) < shape['d'] / 2


def shapes_touch(a, b):
    """Two circles or boxes, by their real outlines."""
    if a['kind'] == b['kind'] == 'circle':
        return math.hypot(a['x'] - b['x'], a['y'] - b['y']) < (a['d'] + b['d']) / 2
    if b['kind'] == 'circle':
        return touches_circle(bounds(a), b)
    if a['kind'] == 'circle':
        return touches_circle(bounds(b), a)
    return overlap(bounds(a), bounds(b))


def overlap(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


# ---------- a panel ----------
def build_panel(module, panel, settings):
    plate, text_settings = settings['plate'], settings['text']
    width, height = (u * U_MM - 2 * PANEL_CLEARANCE_MM for u in panel['size'])
    where = f'{module["id"]}/{panel["id"]}'
    issues = []
    layers = {name: [] for name, _, _ in LAYERS}
    layers['outline'].append(rect(width / 2, height / 2, width, height, plate['corner_radius']))

    holes = plate['mounting_holes']
    screws = [(x, y) for x in (holes['inset'], width - holes['inset']) for y in (holes['inset'], height - holes['inset'])]
    layers['cut'] += [circle(x, y, holes['diameter']) for x, y in screws]
    layers['front'] += [circle(x, y, holes['head']) for x, y in screws]

    layers['legends'].append(text(width / 2, text_settings['title_baseline'] - text_settings['title'] / 2, panel['title'], text_settings['title']))
    rule = text_settings['title_rule']
    layers['legends'].append({'kind': 'line', 'points': [(width * (1 - rule['width']) / 2, rule['y']), (width * (1 + rule['width']) / 2, rule['y'])]})

    inside = (plate['edge_margin'], plate['title_band'], width - plate['edge_margin'], height - plate['edge_margin'])
    screen_box = module = window = None
    if panel.get('screen'):
        fp = settings['footprints']['screen']
        w, h = (v + 2 * fp['margin'] for v in panel['screen']['mm'])
        screen = panel['screen']
        x, y = screen.get('at', (width / 2, fp['top'] + h / 2))     # `at`: the screen's centre on the faceplate
        window = circle(x, y, w) if screen.get('round') else rect(x, y, w, h, fp['corner_radius'])
        layers['cut'] += [window] + [moved(shape, x, y) for shape in extra_shapes(fp)]
        box = screen_box = bounds(window)
        if screen.get('module_mm'):                                 # the display's body behind the plate
            size = screen['module_mm']
            module = circle(x, y, size[0]) if screen.get('round') else rect(x, y, *size)
            layers['behind'].append(module)
            for sx, sy in screws:
                if shapes_touch(circle(sx, sy, holes['head']), module):
                    issues.append(f'{where}: the screen module is on the mounting screw at {sx:.0f}, {sy:.0f}')
        if box[0] < 0 or box[3] > height - plate['edge_margin']:
            issues.append(f'{where}: the screen window does not fit the faceplate')

    blocks = []
    for item in panel.get('items', []):
        placed = place_item(item, settings, issues, f'{where}/{item["id"]}')
        if not placed:
            continue
        for layer in ('cut', 'front', 'behind', 'legends'):
            layers[layer] += placed[layer]
        layers['front'] += placed['guide_text']
        box = placed['box']
        if box[0] < inside[0] or box[2] > inside[2] or box[3] > inside[3]:
            issues.append(f'{where}/{item["id"]}: sticks out of the faceplate ({describe(box, width, height)})')
        elif box[1] < inside[1]:
            issues.append(f'{where}/{item["id"]}: in the title band (top at {box[1]:.1f} mm, the band ends at {inside[1]} mm)')
        if screen_box and (touches_circle(box, window) if window['kind'] == 'circle' else overlap(box, screen_box)):
            issues.append(f'{where}/{item["id"]}: on the screen window')
        if module and any(shapes_touch(shape, module) for shape in placed['behind']):
            issues.append(f'{where}/{item["id"]}: collides with the screen module behind the plate')
        for x, y in screws:
            if overlap(box, bounds(circle(x, y, holes['head']))):
                issues.append(f'{where}/{item["id"]}: on the mounting screw at {x:.0f}, {y:.0f}')
        for other_id, other in blocks:
            if overlap(box, other['box']):
                issues.append(f'{where}: {other_id} and {item["id"]} overlap on the face')
            if placed['behind_box'] and other['behind_box'] and overlap(placed['behind_box'], other['behind_box']):
                issues.append(f'{where}: {other_id} and {item["id"]} collide behind the plate')
        blocks.append((item['id'], placed))
    return (width, height), layers, issues


def describe(box, width, height):
    return f'{box[0]:.1f}..{box[2]:.1f} × {box[1]:.1f}..{box[3]:.1f} mm on {width:g} × {height:g}'


# ---------- SVG ----------
def number(value):
    return f'{value:.3f}'.rstrip('0').rstrip('.')


def stroke_text(shape):
    unit = shape['s'] / 6
    width = text_width(shape['t'], shape['s'])
    x = {'start': shape['x'], 'end': shape['x'] - width}.get(shape['anchor'], shape['x'] - width / 2)
    top = shape['y'] - shape['s'] / 2
    paths = []
    for char in shape['t']:
        advance, lines = glyph(char)
        for line in lines:
            points = ' '.join(f'{number(x + px * unit)},{number(top + py * unit)}' for px, py in line)
            paths.append(f'<polyline points="{points}"/>')
        x += (advance + GLYPH_SPACING) * unit
    return paths


def svg_shape(shape, text_mode, font, colour):
    kind = shape['kind']
    if kind == 'circle':
        return [f'<circle cx="{number(shape["x"])}" cy="{number(shape["y"])}" r="{number(shape["d"] / 2)}"/>']
    if kind == 'rect':
        radius = f' rx="{number(shape["r"])}"' if shape['r'] else ''
        return [f'<rect x="{number(shape["x"] - shape["w"] / 2)}" y="{number(shape["y"] - shape["h"] / 2)}" '
                f'width="{number(shape["w"])}" height="{number(shape["h"])}"{radius}/>']
    if kind == 'line':
        return [f'<polyline points="{" ".join(f"{number(x)},{number(y)}" for x, y in shape["points"])}"/>']
    if not shape['t']:
        return []
    if text_mode == 'font':
        return [f'<text x="{number(shape["x"])}" y="{number(shape["y"] + shape["s"] / 2)}" font-size="{number(shape["s"] / 0.72)}" '
                f'font-family="{font}" text-anchor="{shape["anchor"]}" fill="{colour}" stroke="none">{escape(shape["t"])}</text>']
    return stroke_text(shape)


def escape(string):
    return string.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def svg(width, height, placed_layers, settings, title):
    """placed_layers: [(dx, dy, layers)], drawn into one drawing of width × height mm."""
    text_mode, font = settings['text'].get('mode', 'stroke'), settings['text']['font']
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
           f'width="{number(width)}mm" height="{number(height)}mm" viewBox="0 0 {number(width)} {number(height)}">',
           f'<title>{escape(title)}</title>']
    for name, colour, what in LAYERS:
        colour = settings.get('layer_colours', {}).get(name, colour)
        out.append(f'<g id="{name}" inkscape:groupmode="layer" inkscape:label="{name}: {what}" fill="none" stroke="{colour}" '
                   f'stroke-width="0.1" stroke-linecap="round" stroke-linejoin="round">')
        for dx, dy, layers in placed_layers:
            for shape in layers[name]:
                shape = {**shape, 'points': [(x + dx, y + dy) for x, y in shape['points']]} if shape['kind'] == 'line' else moved(shape, dx, dy)
                out += svg_shape(shape, text_mode, font, colour)
        out.append('</g>')
    out.append('</svg>')
    return '\n'.join(out) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('modules', nargs='*', help='module ids (default: all)')
    parser.add_argument('--out', type=Path, default=HERE / 'out')
    parser.add_argument('--footprints', type=Path, default=HERE / 'footprints.json')
    parser.add_argument('--strict', action='store_true', help='exit 1 when there is an issue')
    args = parser.parse_args()

    settings = json.loads(args.footprints.read_text())
    files = sorted(path for path in DEFINITIONS.glob('*.json') if path.stem != 'console')
    modules = [json.loads(path.read_text()) for path in files]
    if args.modules:
        unknown = set(args.modules) - {module['id'] for module in modules}
        if unknown:
            sys.exit(f'no module {", ".join(sorted(unknown))}')
        modules = [module for module in modules if module['id'] in args.modules]

    all_issues, panel_count = [], 0
    for module in modules:
        folder = args.out / module['id']
        folder.mkdir(parents=True, exist_ok=True)
        on_module = []
        for panel in module['panels']:
            if panel.get('bare'):
                continue            # glass set straight into the console board: no faceplate to cut
            (width, height), layers, issues = build_panel(module, panel, settings)
            name = f'{module["id"]}-{panel["id"]}'
            (folder / f'{panel["id"]}.svg').write_text(svg(width, height, [(0, 0, layers)], settings, f'{name} · {width:g} × {height:g} mm'))
            on_module.append((panel['at'][0] * U_MM + PANEL_CLEARANCE_MM, panel['at'][1] * U_MM + PANEL_CLEARANCE_MM, layers))
            all_issues += issues
            panel_count += 1
        size_u = [max(panel['at'][axis] + panel['size'][axis] for panel in module['panels']) for axis in (0, 1)]
        (args.out / f'{module["id"]}.svg').write_text(
            svg(size_u[0] * U_MM, size_u[1] * U_MM, on_module, settings, f'module {module["id"]} · {size_u[0]}×{size_u[1]} U'))

    print(f'{panel_count} panels from {len(modules)} modules → {args.out}')
    if missing_glyphs:
        all_issues.append(f'no glyph in the stroke font for {"".join(sorted(missing_glyphs))!r} (drawn as a box)')
    for issue in all_issues:
        print(f'  {issue}')
    print(f'{len(all_issues)} issue{"s" if len(all_issues) != 1 else ""}')
    return 1 if args.strict and all_issues else 0


if __name__ == '__main__':
    sys.exit(main())
