/* EECOM: electrical, environmental and communications. Charge and its trend, solar panels, heat, consumables,
   the radio link. */
import { box, figures, fixed } from '../ui.js';
import { store, vessel, met } from '../bus.js';

let setPower, setThermal, setComm, lastCharge = null, chargeRate = null;

export function mount(root) {
  setPower = figures(box(root, 'ELECTRICAL'), [['ec', 'Charge'], ['rate', 'Trend'], ['endurance', 'Lasts'], ['solar', 'Solar panels'], ['lights', 'Lights']]);
  setThermal = figures(box(root, 'THERMAL · CONSUMABLES'), [['heat', 'Hottest part'], ['mono', 'Monopropellant'], ['lf', 'Fuel (vessel)'], ['ox', 'Oxidizer (vessel)']]);
  setComm = figures(box(root, 'COMMUNICATIONS'), [['link', 'Link'], ['strength', 'Signal'], ['via', 'Via'], ['hops', 'Hops'], ['antenna', 'Antennas']]);
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
  const comm = store['tlm/comm'] || {};
  setComm('link', comm.link ? 'AOS' : 'LOS', comm.link ? 'good' : 'bad');
  setComm('strength', comm.link ? `${Math.round((comm.strength || 0) * 100)} %` : '—');
  setComm('via', comm.via || '—');
  setComm('hops', comm.hops ?? '—');
  setComm('antenna', comm.antenna == null ? 'fixed only' : comm.antenna ? 'deployed' : 'stowed');
}
