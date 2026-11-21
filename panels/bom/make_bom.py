"""A bill of materials for the console, from the module definitions (protocol/panels/*.json): every control and
indicator by kind and colour, the driver chips (placed as firmware/tools/gen_module.py places them), the boards,
screens and faceplates. An estimate to see the order of things, not a shopping list: parts are named by the
footprints of the laser-cut faceplates (panels/cut/footprints.json); wiring, connectors and frames are left out.

    python3 panels/bom/make_bom.py          # → panels/bom/BOM.md
"""
import collections
import json
import math
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PANELS = os.path.join(ROOT, 'protocol', 'panels')
sys.path.insert(0, os.path.join(ROOT, 'firmware', 'tools'))
import gen_module  # noqa: E402

FOOTPRINTS = json.load(open(os.path.join(ROOT, 'panels', 'cut', 'footprints.json')))['footprints']
HARDWARE = json.load(open(os.path.join(PANELS, 'hardware.json')))
PRICES = json.load(open(os.path.join(ROOT, 'panels', 'bom', 'prices.json')))['parts']
GROUPS = (('Displays', ('7-segment', 'alphanumeric', '10-segment', 'MAX7219', 'HT16K33')),
          ('Controls and lamps', ('rectangular', 'mini toggle', '12 mm toggle', '5 mm LED', 'annunciator', 'keypad',
                                  'rotary', 'single-turn', 'slide', 'knob', 'addressable', 'frosted', '12 mm piezo')),
          ('Expanders, ADC, drivers, wiring', ('MCP23017', 'ADS1115', 'ULN2803', 'module wiring')),
          ('Boards, screens, network', ('Olimex', 'Raspberry', 'screen', 'PoE switch', 'network cable')),
          ('Faceplates', ('acrylic',)))
U_MM, CLEARANCE_MM = 100, 0.5
COLOURLESS = 'unlit'


def modules():
    for name in sorted(os.listdir(PANELS)):
        if name.endswith('.json') and name not in ('console.json', 'hardware.json'):
            with open(os.path.join(PANELS, name), encoding='utf-8') as source:
                yield json.load(source)


def part(kind):
    return (FOOTPRINTS.get(kind) or {}).get('part', kind)


def count_items(module):
    """Counter of (line, detail) → quantity for one module's controls and indicators."""
    found = collections.Counter()
    for panel in module['panels']:
        for item in panel.get('items', []):
            kind = item['type']
            if item.get('led'):
                found[('5 mm LED (indicator above a switch)', item['led'].get('color', 'green'))] += 1
            if kind == 'toggle':
                found[(part('toggle'), '')] += 1
            elif kind == 'guarded_toggle':
                found[(part('guarded_toggle'), '')] += 1
            elif kind == 'button':
                found[(part('button'), COLOURLESS)] += 1
            elif kind == 'lamp_button':
                found[(part('lamp_button'), item.get('color', 'amber'))] += 1
            elif kind == 'led':
                found[(part('led'), item.get('color', 'green'))] += 1
            elif kind == 'annunciator':
                for cell in item.get('cells', []):
                    found[('annunciator cell (light box, ' + str(HARDWARE['lamps']['cell']['leds']) + ' LEDs, legend)',
                           cell.get('color', 'amber'))] += 1
            elif kind == 'seg7':
                found[('7-segment digit, 0.36 in', item.get('color', 'red'))] += item.get('digits', 1)
                found[('7-segment display (window)', f'{item.get("digits", 1)} digits')] += 1
            elif kind == 'bar':
                found[(part('bar'), '')] += math.ceil(item.get('segments', 10) / 10)
            elif kind == 'matrix':
                found[('3 mm LED (matrix)', '')] += item['rows'] * item['cols']
            elif kind == 'rosette':
                found[('addressable RGB LED (WS2812B / SK6812), engine rosette', '')] += 9
                found[('frosted acrylic disc, ' + str(item.get('lamp_mm', 10)) + ' mm', '')] += 9
            elif kind == 'alpha':
                found[('alphanumeric character (14-segment, HT16K33)', '')] += item.get('chars', 8)
                found[('alphanumeric display (window)', f'{item.get("chars", 8)} characters')] += 1
            elif kind == 'rotary':
                found[(part('rotary'), f'{len(item["positions"])} positions')] += 1
                found[('knob, about 15 mm', 'selector')] += 1
            elif kind == 'knob':
                found[(part('knob'), '')] += 1
                found[('knob, about 15 mm', 'potentiometer')] += 1
            elif kind == 'pot':
                found[(part('pot'), '')] += 1
            elif kind == 'keypad':
                keys = sum(1 for row in item['rows'] for key in row if key) + len(item.get('left') or []) + len(item.get('right') or [])
                found[('keypad key (tactile switch and cap)', '')] += keys
            elif kind == 'buzzer':
                found[(part('buzzer'), '')] += 1
        if panel.get('screen'):
            screen = panel['screen']
            size = f'{screen["inches"]} in' if screen.get('inches') else 'size from the panel'
            found[('screen', f'{size}, {screen["px"][0]} × {screen["px"][1]}' if screen.get('px') else size)] += 1
    return found


def chips(module):
    """The driver chips firmware/tools/gen_module.py places for the module's I/O (also on a glass module's I/O)."""
    keep = gen_module.OUT, gen_module.FIRMWARE_BOARDS
    with tempfile.TemporaryDirectory() as scratch:
        gen_module.OUT = scratch
        gen_module.FIRMWARE_BOARDS = (module['board'],)
        try:
            counts, _ = gen_module.generate(module['id'])
        finally:
            gen_module.OUT, gen_module.FIRMWARE_BOARDS = keep
    lamps_12v = sum(1 for panel in module['panels'] for item in panel.get('items', []) if item['type'] == 'lamp_button')
    if HARDWARE['lamps']['lamp']['v'] > 5:
        counts['uln2803'] = math.ceil(lamps_12v / HARDWARE['chips']['uln2803']['channels'])
    return counts


def has_io(module):
    return any(item['type'] not in ('screen',) for panel in module['panels'] for item in panel.get('items', []))


def price_of(line, detail):
    for entry in PRICES:
        name, _, detail_start = entry['match'].partition('|')
        if line.startswith(name) and detail.startswith(detail_start):
            return entry
    return None


def group_of(line):
    return next((group for group, starts in GROUPS if line.startswith(starts)), 'Other')


def cost_section(lines):
    """lines: [(part, detail, qty)] → the markdown of the cost estimate."""
    groups, unpriced = collections.defaultdict(lambda: [0.0, 0.0]), []
    table = ['| Part | Detail | Qty | Unit (EUR) | Total (EUR) |', '|---|---|---|---|---|']
    for line, detail, quantity in lines:
        price = price_of(line, detail)
        if price is None:
            unpriced.append(line)
            continue
        low, high = quantity * price['low'], quantity * price['high']
        group = groups[group_of(line)]
        group[0] += low
        group[1] += high
        table.append(f'| {line} | {detail} | {quantity:g} | {price["low"]:g} – {price["high"]:g} | {low:.0f} – {high:.0f} |')
    total = [sum(g[0] for g in groups.values()), sum(g[1] for g in groups.values())]
    out = ['## Cost estimate', '',
           'Unit prices from `panels/bom/prices.json`: low = generic parts (AliExpress-type sellers), high = branded '
           'parts from EU distributors. Estimates, not quotes: correct that file and run this again. No spares, '
           'shipping, tools, the console\'s structure, the hand controllers or the throttle controller.', '',
           '| Group | Low (EUR) | High (EUR) |', '|---|---|---|']
    out += [f'| {name} | {groups[name][0]:.0f} | {groups[name][1]:.0f} |' for name, _ in GROUPS if name in groups]
    out += [f'| **Total** | **{total[0]:.0f}** | **{total[1]:.0f}** |', '']
    if unpriced:
        out += ['Not priced: ' + ', '.join(sorted(set(unpriced))), '']
    return out + ['<details><summary>Line by line</summary>', ''] + table + ['', '</details>', '']


def faceplates(module):
    plates = []
    for panel in module['panels']:
        if panel.get('bare'):
            continue
        width, height = panel['size']
        plates.append(((width * U_MM - 2 * CLEARANCE_MM) * (height * U_MM - 2 * CLEARANCE_MM) / 1e6, f'{width}×{height} U'))
    return plates


def main():
    totals, per_module, rows = collections.Counter(), collections.defaultdict(collections.Counter), []
    chip_totals, boards, plates = collections.Counter(), collections.Counter(), []
    for module in modules():
        found = count_items(module)
        totals.update(found)
        for line, quantity in found.items():
            per_module[line][module['id']] += quantity
        board = module['board']
        if board in gen_module.FIRMWARE_BOARDS:
            boards['Olimex ESP32-POE2 (an I/O module)'] += 1
        elif board == 'raspberry-pi':
            boards['Raspberry Pi (a glass module: its screen)'] += 1
            if has_io(module):
                boards['Olimex ESP32-POE2 (the I/O beside a glass module)'] += 1
        else:
            boards[f'{board} ({module["id"]})'] += 1
        module_chips = chips(module) if has_io(module) and board != 'usb-stand-in' else {}
        chip_totals.update({name: n for name, n in module_chips.items() if n})
        module_plates = faceplates(module)
        plates += module_plates
        rows.append((module, found, module_chips, module_plates))

    out = ['# Bill of materials (estimate)', '',
           'Generated by `panels/bom/make_bom.py` from `protocol/panels/*.json`: run it again after a panel changes. Parts '
           'are named after the faceplate footprints (`panels/cut/footprints.json`); quantities are what the panels '
           'hold, with no spares. Wiring, connectors, frames, standoffs, knob caps beyond the count, the power supply '
           'and the PoE switch are left out.', '']
    out += ['## Boards and network', '', '| Item | Qty |', '|---|---|']
    out += [f'| {name} | {n} |' for name, n in sorted(boards.items())]
    poe = boards['Olimex ESP32-POE2 (an I/O module)'] + boards['Olimex ESP32-POE2 (the I/O beside a glass module)']
    out += [f'| PoE switch ports (802.3at for the ESP32-POE2 boards; the Pis on their own supply) | {poe} |', '']

    out += ['## Controls and indicators', '', '| Part | Detail | Qty | Where |', '|---|---|---|---|']
    for (line, detail), n in sorted(totals.items(), key=lambda entry: (entry[0][0], entry[0][1])):
        where = ', '.join(f'{module} {count}' for module, count in sorted(per_module[(line, detail)].items()))
        out.append(f'| {line} | {detail} | {n} | {where} |')
    out.append('')

    out += ['## Driver chips', '', 'As the firmware places them (MAX7219: a display never straddles two chips).', '',
            '| Chip | What for | Qty |', '|---|---|---|']
    notes = {'mcp': 'MCP23017 I2C expander (switches, buttons, lamps, LEDs, cells)', 'ads': 'ADS1115 I2C ADC (levers, knobs)',
             'max7219': 'MAX7219 driver (7-segment digits, bars)', 'ht16k33': 'HT16K33 driver (alphanumerics)',
             'uln2803': 'ULN2803 (12 V lamps of the lit buttons)', 'rgb': 'addressable RGB LEDs (counted above)'}
    for name in ('mcp', 'ads', 'max7219', 'ht16k33', 'uln2803'):
        if chip_totals.get(name):
            label, purpose = notes[name].split(' ', 1)
            out.append(f'| {label} | {purpose} | {chip_totals[name]} |')
    out.append('')

    area = sum(a for a, _ in plates)
    io_modules = poe
    priced = [(line, detail, n) for (line, detail), n in sorted(totals.items())
              if 'window' not in line]
    chip_names = {'mcp': 'MCP23017', 'ads': 'ADS1115', 'max7219': 'MAX7219', 'ht16k33': 'HT16K33', 'uln2803': 'ULN2803'}
    priced += [(chip_names[name], '', n) for name, n in sorted(chip_totals.items()) if name in chip_names]
    priced += [(name.split(' (')[0], '', n) for name, n in sorted(boards.items()) if not name.startswith('usb')]
    priced += [('PoE switch (16 ports, 802.3at)', '', 1),
               ('network cable', '', poe + boards['Raspberry Pi (a glass module: its screen)']),
               ('module wiring (per I/O module)', '', io_modules),
               ('acrylic, 3 mm (m²)', '', round(area * 1.2, 2))]          # a fifth more for the offcuts
    sizes = collections.Counter(size for _, size in plates)
    out += ['## Faceplates', '', f'{len(plates)} acrylic faceplates, {area:.2f} m² in all '
            f'({", ".join(f"{n} × {size}" for size, n in sorted(sizes.items()))}); the cut files: `panels/cut/`.', '']

    out += cost_section(priced)

    out += ['## By module', '', '| Module | Board | Controls and indicators | Chips |', '|---|---|---|---|']
    for module, found, module_chips, _ in rows:
        things = collections.Counter()
        for (line, detail), n in found.items():
            key = line.split(' (')[0].split(',')[0]
            if 'window' in line or line.startswith('knob') or line.startswith('frosted'):
                continue
            things[key] += n
        chip_text = ', '.join(f'{n} {name.upper()}' for name, n in module_chips.items() if n and name != 'rgb') or '—'
        out.append(f'| {module["id"]}: {module.get("title", "")} | {module["board"]} | '
                   f'{", ".join(f"{n} {k}" for k, n in sorted(things.items()))} | {chip_text} |')
    out.append('')
    path = os.path.join(ROOT, 'panels', 'bom', 'BOM.md')
    with open(path, 'w', encoding='utf-8') as target:
        target.write('\n'.join(out))
    print(f'wrote {os.path.relpath(path, ROOT)}')


if __name__ == '__main__':
    main()
