/* EECOM: electrical, environmental and communications. Charge and its trend, solar panels, heat, consumables,
   life support, science, the radio link. */
import { box, figures, fixed } from '../ui.js';
import { store, vessel, met } from '../bus.js';
import { chartBox } from '../consolechart.js';
import { GREEN, RED } from '../charts.js';

// TAC Life Support: units each kerbal uses per second, recyclers not counted
const LIFE_SUPPORT = [['food', 'Food', 1.6927083333e-05], ['water', 'Water', 1.1188078704e-05], ['oxygen', 'Oxygen', 0.001713537562385]];

let setLife, setScience, setPower, setThermal, setComm, lastCharge = null, chargeRate = null;

export function mount(root) {
  setPower = figures(box(root, 'ELECTRICAL', { at: [0, 0] }), [['ec', 'Charge'], ['rate', 'Trend'], ['endurance', 'Lasts'], ['solar', 'Solar panels'], ['lights', 'Lights']]);
  setThermal = figures(box(root, 'THERMAL · CONSUMABLES', { at: [1, 0] }), [['heat', 'Hottest part'], ['mono', 'Monopropellant'], ['lf', 'Fuel (vessel)'], ['ox', 'Oxidizer (vessel)'], ['xenon', 'Xenon'], ['ablator', 'Ablator']]);
  setComm = figures(box(root, 'COMMUNICATIONS', { at: [2, 0] }), [['link', 'Link'], ['strength', 'Signal'], ['via', 'Via'], ['hops', 'Hops'], ['antenna', 'Antennas']]);
  setLife = figures(box(root, 'LIFE SUPPORT', { at: [0, 1] }), [['crew', 'Crew'], ['station', 'CM · LM'], ...LIFE_SUPPORT.map(([id, name]) => [id, name])]);
  setScience = figures(box(root, 'SCIENCE', { at: [1, 1] }), [['count', 'Experiments'], ['ready', 'Ready'], ['data', 'Holding data'],
    ['value', 'Science held'], ['biome', 'Biome']]);
  chartBox(root, 'CHARGE · HEAT, % (of capacity, of the limit)', { at: [2, 1] }, {
    series: [
      { label: 'CHARGE', color: GREEN, unit: '%', decimals: 0, value: (c, i) => (c.ec[i] == null ? null : c.ec[i] * 100) },
      { label: 'HEAT', color: RED, unit: '%', decimals: 0, value: (c, i) => (c.heat[i] == null ? null : c.heat[i] * 100) },
    ],
    scales: { y: { range: [0, 100] } },
  });
}

function updateLifeSupport(totals, crew) {
  setLife('crew', crew ?? '—');
  setLife('station', stationText(store['tlm/station']));
  for (const [id, name, usePerSecond] of LIFE_SUPPORT) {
    const carried = totals[name];
    if (!carried || !carried.max) { setLife(id, store['tlm/resources'] ? 'not carried' : '—'); continue; }
    const fraction = carried.amount / carried.max;
    const hours = crew ? `, ${fixed(carried.amount / (usePerSecond * crew) / 3600, 1, 'h')}` : '';
    setLife(id, `${Math.round(fraction * 100)} %${hours}`, fraction <= 0 || fraction < 0.1 ? 'bad' : fraction < 0.2 ? 'warn' : '');
  }
}

/* tlm/station: the crew in each capsule, the one flown from, docked or not. */
function stationText(station) {
  if (!station || (!station.cm && !station.lm)) return '—';
  const count = (capsule) => (capsule ? `${capsule.crew}/${capsule.seats}` : '—');
  const flown = station.at ? `, flown from ${station.at.toUpperCase()}` : '';
  return `${count(station.cm)} · ${count(station.lm)}${station.joined ? ' docked' : ''}${flown}`;
}

function updateScience(science) {
  const experiments = science.experiments || [];
  const holding = experiments.filter((each) => each.data);
  setScience('count', science.experiments ? experiments.length : '—');
  const known = Boolean(science.experiments);
  setScience('ready', known ? experiments.filter((each) => each.available && !each.data && !each.inoperable).length : '—');
  setScience('data', known ? holding.length : '—');
  setScience('value', known ? fixed(holding.reduce((sum, each) => sum + (each.value || 0), 0), 1) : '—');
  setScience('biome', science.biome || '—');
}

const amount = (resource, unit = '') => (resource ? `${fixed(resource.amount, 0)} / ${fixed(resource.max, 0)}${unit}` : '—');

export function update() {
  const totals = store['tlm/resources']?.total || {}, craft = vessel();
  const charge = totals.ElectricCharge;
  if (charge && met() != null) {
    // a slow trend: units per second over game time, smoothed
    if (lastCharge && met() > lastCharge.met) {
      const rate = (charge.amount - lastCharge.amount) / (met() - lastCharge.met);
      chargeRate = chargeRate == null ? rate : chargeRate * 0.8 + rate * 0.2;
    }
    lastCharge = { amount: charge.amount, met: met() };
  }
  setPower('ec', amount(charge), charge && charge.amount / charge.max < 0.2 ? 'bad' : '');
  setPower('rate', chargeRate == null ? '—' : fixed(chargeRate, 2, 'EC/s'), chargeRate < -0.05 ? 'warn' : '');
  const hours = charge && chargeRate < -0.01 ? charge.amount / -chargeRate / 3600 : null;
  setPower('endurance', hours == null ? 'not draining' : fixed(hours, 1, 'h'), hours != null && hours < 1 ? 'bad' : '');
  setPower('solar', craft.solar == null ? 'none' : craft.solar ? 'deployed' : 'stowed');
  setPower('lights', craft.lights ? 'on' : 'off');
  const heat = store['tlm/thermal']?.max;
  setThermal('heat', heat == null ? '—' : `${Math.round(heat * 100)} % of limit`, heat > 0.8 ? 'bad' : heat > 0.6 ? 'warn' : '');
  setThermal('mono', amount(totals.MonoPropellant));
  setThermal('lf', amount(totals.LiquidFuel));
  setThermal('ox', amount(totals.Oxidizer));
  setThermal('xenon', amount(totals.XenonGas));
  const ablator = totals.Ablator;
  setThermal('ablator', amount(ablator), ablator && ablator.amount / ablator.max < 0.2 ? 'warn' : '');
  updateLifeSupport(totals, craft.crew);
  updateScience(store['tlm/science'] || {});
  const comm = store['tlm/comm'] || {};
  setComm('link', comm.link ? 'AOS' : 'LOS', comm.link ? 'good' : 'bad');
  setComm('strength', comm.link ? `${Math.round((comm.strength || 0) * 100)} %` : '—');
  setComm('via', comm.via || '—');
  setComm('hops', comm.hops ?? '—');
  setComm('antenna', comm.antenna == null ? 'fixed only' : comm.antenna ? 'deployed' : 'stowed');
}
