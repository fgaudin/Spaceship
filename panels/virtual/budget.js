/* What a module's panels ask of its board: inputs, lamps, displays, the driver chips they imply, the ESP32 pins those
   chips use, and the power, in flight and at lamp test (everything lit). The figures are in protocol/panels/hardware.json:
   rough, to compare groupings, not a design. Shown on the console while Left Alt is held. */

const ceil = (value, per) => Math.ceil(value / per);

/* The counts of one module. */
export function moduleNeeds(module) {
  const needs = { inputs: 0, analog: 0, leds: 0, lamps: 0, rows: 0, chars: 0, buzzer: 0 };
  for (const panel of module.panels) {
    for (const item of panel.items || []) {
      if (item.led) needs.leds += 1;
      switch (item.type) {
        case 'toggle': case 'guarded_toggle': case 'button': needs.inputs += 1; break;
        case 'lamp_button': needs.inputs += 1; needs.lamps += 1; break;
        case 'rotary': needs.inputs += (item.positions || []).length; break;
        case 'keypad': {
          const columns = Math.max(...item.rows.map((row) => row.length)) + (item.left?.length ? 1 : 0) + (item.right?.length ? 1 : 0);
          needs.inputs += item.rows.length + columns;             // scanned as a matrix: one line per row and column
          break;
        }
        case 'pot': case 'knob': needs.analog += 1; break;
        case 'led': needs.leds += 1; break;
        case 'annunciator': needs.lamps += (item.cells || []).length; break;
        case 'seg7': needs.rows += item.digits || 0; break;
        case 'bar': needs.rows += ceil(item.segments || 0, 8); break;
        case 'matrix': needs.rows += ceil((item.rows || 0) * (item.cols || 0), 8); break;
        case 'alpha': needs.chars += item.chars || 0; break;
        case 'buzzer': needs.buzzer += 1; break;
        default: break;
      }
    }
  }
  return needs;
}

/* The chips, pins and power of a module, from its counts and the hardware assumptions. */
export function moduleBudget(module, hardware) {
  const needs = moduleNeeds(module);
  const { chips, lamps, pins, boards, supply_v: volts } = hardware;
  const count = {
    mcp23017: ceil(needs.inputs + needs.leds + needs.lamps, chips.mcp23017.io),
    max7219: ceil(needs.rows, chips.max7219.rows),
    ht16k33: ceil(needs.chars, chips.ht16k33.chars),
    ads1115: ceil(needs.analog, chips.ads1115.channels),
  };
  const usesI2c = count.mcp23017 + count.ht16k33 + count.ads1115 > 0;
  const espPins = (usesI2c ? pins.i2c : 0) + (count.max7219 ? pins.spi : 0) + needs.buzzer * pins.buzzer;
  const lampsMa = needs.leds * lamps.led_ma + needs.lamps * lamps.lamp_ma;
  const displaysMa = (which) => count.max7219 * chips.max7219[which] + count.ht16k33 * chips.ht16k33[which];
  const board = boards[module.board] || {};
  const base = board.base_w || 0;
  const watts = (milliamps) => (milliamps * volts) / 1000;
  return {
    needs, count, espPins, board,
    typicalW: base + watts(lampsMa * lamps.typical_on + displaysMa('typ_ma')),
    lampTestW: base + watts(lampsMa + displaysMa('max_ma')),
  };
}

/* Two short lines for the module's tag. */
export function describeBudget(budget) {
  const { needs, count, espPins, board } = budget;
  const io = [[needs.inputs, 'in'], [needs.analog, 'analog'], [needs.leds + needs.lamps, 'lamps'],
    [needs.rows, 'display rows'], [needs.chars, 'chars']].filter(([n]) => n).map(([n, what]) => `${n} ${what}`);
  const parts = Object.entries(count).filter(([, n]) => n).map(([chip, n]) => `${n}× ${chip.toUpperCase()}`);
  const power = `${budget.typicalW.toFixed(1)} W, ${budget.lampTestW.toFixed(1)} W lamp test`;
  const limit = board.budget_w ? ` / ${board.budget_w} W` : ' (own supply)';
  return [`${io.join(' · ') || 'no I/O'}`, `${parts.join(' · ') || 'no chips'} · ${espPins} pins · ${power}${limit}`];
}

export const overBudget = (budget) => Boolean(budget.board.budget_w) && budget.lampTestW > budget.board.budget_w;
