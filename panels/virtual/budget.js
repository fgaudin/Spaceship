/* What a module's panels ask of its board: inputs, lamps, displays, the driver chips they imply, the ESP32 pins those
   chips use, and the power, in flight and at lamp test (everything lit). The figures are in protocol/panels/hardware.json:
   rough, to compare groupings, not a design. Shown on the console while Left Alt is held. */

const ceil = (value, per) => Math.ceil(value / per);

/* The counts of one module. */
export function moduleNeeds(module) {
  const needs = { inputs: 0, analog: 0, leds: 0, lamps: 0, cells: 0, rows: 0, chars: 0, buzzer: 0 };
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
        case 'annunciator': needs.cells += (item.cells || []).length; break;
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

/* The chips, pins and power of a module, from its counts and the hardware assumptions. Power is per supply rail
   (volts → watts, in flight and at lamp test), each against the board's limit for that rail. */
export function moduleBudget(module, hardware) {
  const needs = moduleNeeds(module);
  const { chips, lamps, pins, boards } = hardware;
  const lampV = lamps.lamp.v, ledV = lamps.led.v, cellV = lamps.cell.v;
  // above 5 V: through a driver
  const driven = (lampV > 5 ? needs.lamps : 0) + (ledV > 5 ? needs.leds : 0) + (cellV > 5 ? needs.cells : 0);
  const count = {
    mcp23017: ceil(needs.inputs + needs.leds + needs.lamps + needs.cells, chips.mcp23017.io),
    uln2803: ceil(driven, chips.uln2803.channels),
    max7219: ceil(needs.rows, chips.max7219.rows),
    ht16k33: ceil(needs.chars, chips.ht16k33.chars),
    ads1115: ceil(needs.analog, chips.ads1115.channels),
  };
  const usesI2c = count.mcp23017 + count.ht16k33 + count.ads1115 > 0;
  const espPins = (usesI2c ? pins.i2c : 0) + (count.max7219 ? pins.spi : 0) + needs.buzzer * pins.buzzer;
  // watts on each rail: [in flight, at lamp test]
  const rails = {};
  const add = (volts, typicalMa, maxMa) => {
    const rail = rails[volts] || (rails[volts] = [0, 0]);
    rail[0] += (typicalMa * volts) / 1000;
    rail[1] += (maxMa * volts) / 1000;
  };
  const displays = (which) => count.max7219 * chips.max7219[which] + count.ht16k33 * chips.ht16k33[which];
  add(5, displays('typ_ma'), displays('max_ma'));
  add(ledV, needs.leds * lamps.led.ma * lamps.typical_on, needs.leds * lamps.led.ma);
  add(lampV, needs.lamps * lamps.lamp.ma * lamps.typical_on, needs.lamps * lamps.lamp.ma);
  const cellMa = needs.cells * lamps.cell.leds * lamps.cell.ma;
  add(cellV, cellMa * lamps.typical_on, cellMa);
  for (const volts of Object.keys(rails)) if (!rails[volts][1]) delete rails[volts];
  const board = boards[module.board] || {};
  const total = (index) => Object.values(rails).reduce((sum, rail) => sum + rail[index], 0) + (board.logic_w || 0);
  return { needs, count, espPins, board, rails, typicalW: total(0), lampTestW: total(1) };
}

/* The rails (and the board's total) over their limit at lamp test: e.g. ['5 V'], [] when it fits. */
export function overLimits(budget) {
  const { board, rails } = budget;
  if (!board.rails_w) return [];
  const over = Object.entries(rails).filter(([volts, [, test]]) => test > (board.rails_w[volts] ?? 0)).map(([volts]) => `${volts} V`);
  if (board.total_w && budget.lampTestW > board.total_w) over.push('total');
  return over;
}

export const overBudget = (budget) => overLimits(budget).length > 0;

/* Three short lines for the module's tag. */
export function describeBudget(budget) {
  const { needs, count, espPins, board, rails } = budget;
  const io = [[needs.inputs, 'in'], [needs.analog, 'analog'], [needs.leds, 'LEDs'], [needs.lamps, 'lamps'], [needs.cells, 'cells'],
    [needs.rows, 'display rows'], [needs.chars, 'chars']].filter(([n]) => n).map(([n, what]) => `${n} ${what}`);
  const parts = Object.entries(count).filter(([, n]) => n).map(([chip, n]) => `${n}× ${chip.toUpperCase()}`);
  const power = Object.entries(rails).map(([volts, [typical, test]]) => {
    const limit = board.rails_w ? ` / ${board.rails_w[volts] ?? 0}` : '';
    return `${volts} V ${typical.toFixed(1)} W, ${test.toFixed(1)} test${limit}`;
  }).join(' · ');
  return [io.join(' · ') || 'no I/O', `${parts.join(' · ') || 'no chips'} · ${espPins} pins`,
    `${power || 'no load'}${board.rails_w ? '' : ' (own supply)'}`];
}
