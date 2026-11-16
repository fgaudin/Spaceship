/* GUIDO, guidance officer: the burn computer, the maneuver node and how far the nose is from it, the attitude. */
import { box, figures, fixed, formatMet } from '../ui.js';
import { store, met, vessel } from '../bus.js';

const STANDARD_GRAVITY = 9.80665;
let setPad, setAttitude;

export function mount(root) {
  setPad = figures(box(root, 'BURN COMPUTER', { at: [0, 0] }), [['state', 'State'], ['tig', 'TIG'], ['to_tig', 'Time to TIG'], ['dv', 'Δv P / N / R'],
    ['total', 'Δv total'], ['burn', 'Burn time (full thrust)'], ['uplink', 'Uplink waiting']]);
  setAttitude = figures(box(root, 'ATTITUDE', { at: [1, 0] }), [['att_err', 'Off the burn'], ['pitch', 'Pitch'], ['heading', 'Heading'], ['roll', 'Roll'],
    ['sas', 'SAS'], ['ref', 'Navball reference']]);
}

export function update() {
  const pad = store['cmp/pad'] || {}, node = store['tlm/node'] || {}, craft = vessel();
  const delta = pad.dv || [0, 0, 0];
  const total = Math.hypot(...delta);
  setPad('state', (pad.state || 'idle').toUpperCase(), pad.state === 'burn' ? 'warn' : pad.state === 'armed' ? 'strong' : '');
  setPad('tig', pad.tig == null ? '—' : formatMet(pad.tig));
  setPad('to_tig', pad.tig == null || met() == null ? '—' : formatMet(met() - pad.tig));
  setPad('dv', delta.map((component) => fixed(component, 1)).join(' / '));
  setPad('total', fixed(total, 1, 'm/s'));
  let burnTime = null;
  if (craft.mass && craft.thrust_avail && craft.isp && total) {
    const exhaust = craft.isp * STANDARD_GRAVITY;
    burnTime = (craft.mass * exhaust / craft.thrust_avail) * (1 - Math.exp(-total / exhaust));
  }
  setPad('burn', fixed(burnTime, 1, 's'));
  setPad('uplink', store['panel/cmp/out/lamp_uplink']?.on ? 'YES: crew to accept' : 'no', store['panel/cmp/out/lamp_uplink']?.on ? 'warn' : '');

  const attitude = store['tlm/attitude'] || {};
  setAttitude('att_err', node.set ? fixed(node.att_err, 1, '°') : 'no node', node.set && node.att_err > 5 ? 'warn' : '');
  setAttitude('pitch', fixed(attitude.pitch, 1, '°'));
  setAttitude('heading', fixed(attitude.heading, 1, '°'));
  setAttitude('roll', fixed(attitude.roll, 1, '°'));
  setAttitude('sas', craft.sas ? (craft.sas_mode || 'on').toUpperCase() : 'off');
  setAttitude('ref', (craft.speed_mode || '—').toUpperCase());
}
