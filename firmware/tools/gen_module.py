"""Generate a module's firmware configuration from its definition, protocol/panels/<module>.json.

    python firmware/tools/gen_module.py eng            # → firmware/generated/eng/module_config.h and WIRING.md
    python firmware/tools/gen_module.py --all

Every control is given a place on the module's chips, in the order of the file, as panels/virtual/budget.js counts
them (protocol/panels/hardware.json):
- MCP23017 expanders (I2C 0x20..0x27, 16 pins each): switches, buttons, rotary positions (one pin each), the keypad's
  rows and columns, and every lamp, LED and annunciator cell (through a ULN2803 when its rail is above 5 V);
- ADS1115 (I2C 0x48..0x4B, 4 channels): levers and knobs;
- MAX7219 chain (SPI, 8 rows each): 7-segment digits (a display never straddles two chips), bar rows (8 segments a
  row), matrix rows;
- HT16K33 (I2C 0x70..0x77, 8 characters): alphanumeric displays;
- a GPIO for the buzzer, another for a chain of addressable RGB LEDs (WS2812B / SK6812: the engine rosette).
WIRING.md says where each control goes, for building the module; the header is what the firmware compiles.
The config hash is the virtual console's (FNV-1a of the definition's JSON), so the status shows the same fingerprint.
"""
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PANELS = os.path.join(ROOT, 'protocol', 'panels')
OUT = os.path.join(ROOT, 'firmware', 'generated')
FIRMWARE_BOARDS = ('olimex-esp32-poe2', 'olimex-esp32-poe')
FW_VERSION = 'fw-0.1'
MCP_BASE, ADS_BASE, HT_BASE = 0x20, 0x48, 0x70
MAX_MCP, MAX_ADS, MAX_HT = 8, 4, 8
BUZZER_GPIO = 4
RGB_GPIO = 33                   # the data line of the addressable RGB LEDs (engine rosette)


def fingerprint(text):
    """FNV-1a over UTF-16 code units, as panels/virtual/panel.js (charCodeAt)."""
    value = 2166136261
    data = text.encode('utf-16-le')
    for index in range(0, len(data), 2):
        value ^= data[index] | (data[index + 1] << 8)
        value = (value * 16777619) & 0xFFFFFFFF
    return format(value, 'x')


class Allocation:
    def __init__(self):
        self.next_pin = 0               # expander pins, 16 a chip
        self.next_ads = 0
        self.max_digits = []            # digits used on each MAX7219
        self.next_char = 0              # HT16K33 characters, 8 a chip
        self.wiring = []

    def pins(self, count):
        first = self.next_pin
        self.next_pin += count
        return first

    def analog(self):
        channel = self.next_ads
        self.next_ads += 1
        return channel

    def max_rows(self, count, keep_together):
        """(chip, first row) for `count` rows; a 7-segment display stays on one chip."""
        if keep_together:
            for chip, used in enumerate(self.max_digits):
                if used + count <= 8:
                    self.max_digits[chip] += count
                    return chip, used
        if count <= 8 or keep_together:
            self.max_digits.append(count)
            return len(self.max_digits) - 1, 0
        # longer than a chip (a matrix): from the start of a fresh chip, carrying over
        chip = len(self.max_digits)
        while count > 0:
            self.max_digits.append(min(8, count))
            count -= 8
        return chip, 0

    def chars(self, count):
        first = self.next_char
        self.next_char += count
        return first


def pin_name(pin):
    return f'MCP {pin // 16} (0x{MCP_BASE + pin // 16:02X}) {"GPA" if pin % 16 < 8 else "GPB"}{pin % 8}'


def generate(module_id):
    path = os.path.join(PANELS, f'{module_id}.json')
    with open(path, encoding='utf-8') as source:
        definition = json.load(source)
    if definition.get('board') not in FIRMWARE_BOARDS:
        return None
    text = json.dumps(definition, separators=(',', ':'), ensure_ascii=False)
    alloc = Allocation()
    switches, rotaries, analogs, keypads, lamps, seg7s, bars, matrices, alphas, buzzers, rosettes = ([] for _ in range(11))
    rgb_leds = [0]
    has_screen = any(panel.get('screen') for panel in definition['panels'])

    for panel in definition['panels']:
        bus = panel['bus']
        topic_in = lambda name: f'panel/{bus}/in/{name}'
        topic_out = lambda name: f'panel/{bus}/out/{name}'

        def lamp(out, label):
            pin = alloc.pins(1)
            lamps.append((topic_out(out), pin))
            alloc.wiring.append((panel['title'], label, 'lamp', pin_name(pin) + ' → ULN2803 if 12 V'))

        for item in panel.get('items', []):
            kind, label = item['type'], item.get('label') or item['id']
            if item.get('led'):
                lamp(item['led']['out'], f'{label} (LED)')
            if kind in ('toggle', 'guarded_toggle', 'button', 'lamp_button'):
                pin = alloc.pins(1)
                momentary = kind in ('button', 'lamp_button')
                switches.append((topic_in(item['in']), pin, momentary))
                alloc.wiring.append((panel['title'], label, 'button' if momentary else 'switch', pin_name(pin) + ' to GND'))
                if kind == 'lamp_button' and item.get('out'):
                    lamp(item['out'], f'{label} (lamp)')
            elif kind == 'rotary':
                count = len(item['positions'])
                first = alloc.pins(count)
                rotaries.append((topic_in(item['in']), first, count))
                for index, position in enumerate(item['positions']):
                    alloc.wiring.append((panel['title'], f'{label} {position}', 'rotary position',
                                         pin_name(first + index) + ' to GND'))
            elif kind in ('pot', 'knob'):
                channel = alloc.analog()
                analogs.append((topic_in(item['in']), channel // 4, channel % 4, item.get('steps', 100)))
                alloc.wiring.append((panel['title'], label, 'analog',
                                     f'ADS1115 {channel // 4} (0x{ADS_BASE + channel // 4:02X}) A{channel % 4}, ends to 3.3 V and GND'))
            elif kind == 'keypad':
                rows = [list(row) for row in item['rows']]
                columns = max(len(row) for row in rows)
                left, right = item.get('left') or [], item.get('right') or []
                # the side keys: one more column each, their keys on the first rows
                grid = [([left[r]] if left and r < len(left) else ([''] if left else [])) + row + [''] * (columns - len(row))
                        + ([right[r]] if right and r < len(right) else ([''] if right else [])) for r, row in enumerate(rows)]
                row_first = alloc.pins(len(grid))
                col_first = alloc.pins(len(grid[0]))
                keypads.append((topic_in(item['in']), row_first, len(grid), col_first, len(grid[0]), grid))
                alloc.wiring.append((panel['title'], label, 'keypad', f'rows {pin_name(row_first)} +{len(grid) - 1}, '
                                                                     f'columns {pin_name(col_first)} +{len(grid[0]) - 1}'))
            elif kind == 'led':
                lamp(item['out'], label)
            elif kind == 'annunciator':
                for cell in item.get('cells', []):
                    lamp(cell['out'], cell.get('label', cell['out']))
            elif kind == 'seg7':
                chip, digit = alloc.max_rows(item['digits'], keep_together=True)
                seg7s.append((topic_out(item['out']), chip, digit, item['digits']))
                alloc.wiring.append((panel['title'], label, '7-segment', f'MAX7219 {chip} digits {digit}..{digit + item["digits"] - 1}'))
            elif kind == 'bar':
                rows = math.ceil(item.get('segments', 10) / 8)
                chip, row = alloc.max_rows(rows, keep_together=True)
                bars.append((topic_out(item['out']), chip, row, item.get('segments', 10)))
                alloc.wiring.append((panel['title'], label, 'bar', f'MAX7219 {chip} rows {row}..{row + rows - 1}'))
            elif kind == 'matrix':
                leds = item['rows'] * item['cols']
                chip, row = alloc.max_rows(math.ceil(leds / 8), keep_together=False)
                matrices.append((topic_out(item['out']), chip, row, item['rows'], item['cols']))
                alloc.wiring.append((panel['title'], label, 'LED matrix', f'MAX7219 {chip}.. rows from {row}, '
                                                                         f'{leds} LEDs in reading order'))
            elif kind == 'alpha':
                first = alloc.chars(item['chars'])
                alphas.append((topic_out(item['out']), first, item['chars']))
                alloc.wiring.append((panel['title'], label, 'alphanumeric', f'HT16K33 {first // 8} (0x{HT_BASE + first // 8:02X}) '
                                                                           f'characters {first % 8}..'))
            elif kind == 'rosette':
                rosettes.append((topic_out(item['out']), rgb_leds[0], 9))
                alloc.wiring.append((panel['title'], label, 'RGB rosette', f'GPIO {RGB_GPIO} data → LEDs {rgb_leds[0]}..'
                                                                         f'{rgb_leds[0] + 8} of the chain: centre, then the ring clockwise from the top'))
                rgb_leds[0] += 9
            elif kind == 'buzzer':
                buzzers.append((topic_out(item['out']), BUZZER_GPIO))
                alloc.wiring.append((panel['title'], label, 'buzzer', f'GPIO {BUZZER_GPIO} → transistor → piezo'))

    counts = {'mcp': math.ceil(alloc.next_pin / 16), 'ads': math.ceil(alloc.next_ads / 4),
              'max7219': len(alloc.max_digits), 'ht16k33': math.ceil(alloc.next_char / 8)}
    problems = [f'{name}: {count} chips, the bus has room for {limit}'
                for name, count, limit in (('MCP23017', counts['mcp'], MAX_MCP), ('ADS1115', counts['ads'], MAX_ADS),
                                           ('HT16K33', counts['ht16k33'], MAX_HT)) if count > limit]
    status_topic = f'panel/{definition["id"]}/{"io/" if has_screen else ""}status'
    buses = sorted({panel['bus'] for panel in definition['panels']})
    counts['rgb'] = rgb_leds[0]
    header = render_header(definition, fingerprint(text), status_topic, buses, counts, switches, rotaries, analogs,
                           keypads, lamps, seg7s, bars, matrices, alphas, buzzers, rosettes)
    out_dir = os.path.join(OUT, definition['id'])
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, 'module_config.h'), 'w', encoding='utf-8') as out:
        out.write(header)
    with open(os.path.join(out_dir, 'WIRING.md'), 'w', encoding='utf-8') as out:
        out.write(render_wiring(definition, counts, alloc.wiring, problems))
    return counts, problems


def c_string(text):
    return json.dumps(text, ensure_ascii=True)


def render_header(definition, config_hash, status_topic, buses, counts, switches, rotaries, analogs, keypads, lamps,
                  seg7s, bars, matrices, alphas, buzzers, rosettes):
    lines = [f'// Generated by firmware/tools/gen_module.py from protocol/panels/{definition["id"]}.json: do not edit.',
             '#pragma once', '#include "controls.h"', '',
             f'#define MODULE_ID {c_string(definition["id"])}',
             f'#define FW_VERSION {c_string(FW_VERSION)}',
             f'#define CONFIG_HASH {c_string(config_hash)}',
             f'#define STATUS_TOPIC {c_string(status_topic)}', '',
             f'static const char *const BUSES[] = {{{", ".join(c_string(bus) for bus in buses)}}};',
             f'static const uint8_t MCP_COUNT = {counts["mcp"]};',
             f'static const uint8_t ADS_COUNT = {counts["ads"]};',
             f'static const uint8_t MAX7219_COUNT = {counts["max7219"]};',
             f'static const uint8_t HT16K33_COUNT = {counts["ht16k33"]};',
             f'static const uint8_t RGB_LED_COUNT = {counts["rgb"]};',
             f'static const uint8_t RGB_GPIO = {RGB_GPIO};', '']

    def table(type_name, name, rows):
        lines.append(f'static const {type_name} {name}[] = {{')
        lines.extend(f'  {{{row}}},' for row in rows)
        if not rows:
            lines.append('  {}')                      # an empty table still compiles; its count is 0
        lines.append('};')
        lines.append(f'static const uint8_t {name}_COUNT = {len(rows)};')
        lines.append('')

    table('SwitchConfig', 'SWITCHES', [f'{c_string(t)}, {p}, {str(m).lower()}' for t, p, m in switches])
    table('RotaryConfig', 'ROTARIES', [f'{c_string(t)}, {f}, {n}' for t, f, n in rotaries])
    table('AnalogConfig', 'ANALOGS', [f'{c_string(t)}, {a}, {c}, {s}' for t, a, c, s in analogs])
    for index, (topic, row_first, rows, col_first, cols, grid) in enumerate(keypads):
        keys = ', '.join(c_string(key) for row in grid for key in row)
        lines.append(f'static const char *const KEYPAD_{index}_KEYS[] = {{{keys}}};')
    table('KeypadConfig', 'KEYPADS', [f'{c_string(t)}, {rf}, {r}, {cf}, {c}, KEYPAD_{i}_KEYS'
                                      for i, (t, rf, r, cf, c, _) in enumerate(keypads)])
    table('LampConfig', 'LAMPS', [f'{c_string(t)}, {p}' for t, p in lamps])
    table('Seg7Config', 'SEG7S', [f'{c_string(t)}, {c}, {d}, {n}' for t, c, d, n in seg7s])
    table('BarConfig', 'BARS', [f'{c_string(t)}, {c}, {r}, {s}' for t, c, r, s in bars])
    table('MatrixConfig', 'MATRICES', [f'{c_string(t)}, {c}, {r}, {rows}, {cols}' for t, c, r, rows, cols in matrices])
    table('AlphaConfig', 'ALPHAS', [f'{c_string(t)}, {f}, {n}' for t, f, n in alphas])
    table('BuzzerConfig', 'BUZZERS', [f'{c_string(t)}, {g}' for t, g in buzzers])
    table('RosetteConfig', 'ROSETTES', [f'{c_string(t)}, {f}, {n}' for t, f, n in rosettes])
    return '\n'.join(lines)


def render_wiring(definition, counts, wiring, problems):
    lines = [f'# {definition["id"]}: {definition.get("title", "")}', '',
             f'Generated from `protocol/panels/{definition["id"]}.json` by `firmware/tools/gen_module.py`. Chips: '
             f'{counts["mcp"]} MCP23017, {counts["ads"]} ADS1115, {counts["max7219"]} MAX7219, {counts["ht16k33"]} HT16K33'
             + (f', {counts["rgb"]} addressable RGB LEDs.' if counts.get('rgb') else '.'),
             '']
    if problems:
        lines += ['**Does not fit one board:** ' + '; '.join(problems), '']
    lines += ['| Panel | Control | Kind | Where |', '|---|---|---|---|']
    lines += [f'| {panel} | {label} | {kind} | {where} |' for panel, label, kind, where in wiring]
    return '\n'.join(lines) + '\n'


def write_environments():
    """firmware/modules.ini: a PlatformIO environment for every module generated."""
    modules = sorted(name for name in os.listdir(OUT) if os.path.isfile(os.path.join(OUT, name, 'module_config.h')))
    lines = ['; Generated by tools/gen_module.py: one environment per module.']
    for module in modules:
        lines += ['', f'[env:{module}]', 'extends = module', f'build_flags = ${{module.build_flags}} -I generated/{module}']
    with open(os.path.join(ROOT, 'firmware', 'modules.ini'), 'w', encoding='utf-8') as out:
        out.write('\n'.join(lines) + '\n')


def main(arguments):
    names = ([name[:-5] for name in sorted(os.listdir(PANELS))
              if name.endswith('.json') and name not in ('console.json', 'hardware.json')]
             if arguments == ['--all'] else arguments)
    for name in names:
        result = generate(name)
        if result is None:
            print(f'{name}: not a firmware board (glass), skipped')
            continue
        counts, problems = result
        print(f'{name}: {counts}' + (f'  DOES NOT FIT: {problems}' if problems else ''))
    write_environments()


if __name__ == '__main__':
    main(sys.argv[1:] or ['--all'])
