/* BOOSTER: propulsion. Each engine (what it gives against what it could), thrust, TWR, the stage's propellant,
   limiter and gimbal. A failed engine shows here as lit with no thrust, or as gone. */
import { create, box, figures, fixed } from '../ui.js';
import { store, vessel, orbit, flight } from '../bus.js';
import { bodyOf } from '../bodies.js';

let setFigure, engineTable;

export function mount(root) {
  setFigure = figures(box(root, 'VEHICLE'), [['stage', 'Stage'], ['throttle', 'Throttle'], ['thrust', 'Thrust'], ['twr', 'TWR'],
    ['isp', 'Specific impulse'], ['limit', 'Thrust limiter'], ['gimbal', 'Gimbals'], ['lf', 'Stage fuel'], ['ox', 'Stage oxidizer']]);
  const engines = box(root, 'ENGINES', 'wide');
  const table = create('table', 'mcc-table');
  table.innerHTML = '<thead><tr><th>Stage</th><th>Position (m)</th><th>State</th><th>Thrust</th><th>Of</th><th>Fuel</th></tr></thead>';
  engineTable = create('tbody');
  table.append(engineTable);
  engines.append(table);
}

const fraction = (resource) => (resource && resource.max ? `${Math.round((resource.amount / resource.max) * 100)} %` : '—');

export function update() {
  const craft = vessel(), engines = store['tlm/engines'] || {}, stageResources = store['tlm/resources']?.stage || {};
  const body = bodyOf(orbit().body);
  const gravity = body && flight().alt != null ? body.mu / (body.radius + flight().alt) ** 2 : null;
  setFigure('stage', craft.stage ?? '—');
  setFigure('throttle', fixed((craft.throttle || 0) * 100, 0, '%'));
  setFigure('thrust', `${fixed((craft.thrust || 0) / 1000, 1)} of ${fixed((craft.thrust_avail || 0) / 1000, 1, 'kN')}`);
  setFigure('twr', gravity && craft.mass ? fixed(craft.thrust_avail / (craft.mass * gravity), 2) : '—');
  setFigure('isp', fixed(craft.isp, 0, 's'));
  setFigure('limit', engines.limit == null ? '—' : fixed(engines.limit * 100, 0, '%'));
  setFigure('gimbal', engines.gimbal_locked == null ? '—' : engines.gimbal_locked ? 'LOCKED' : 'free', engines.gimbal_locked ? 'warn' : '');
  setFigure('lf', fraction(stageResources.LiquidFuel || stageResources.SolidFuel));
  setFigure('ox', fraction(stageResources.Oxidizer));

  const throttle = craft.throttle || 0;
  engineTable.replaceChildren(...(engines.engines || []).slice().sort((a, b) => a.stage - b.stage).map((engine) => {
    let state = 'off', tone = '';
    if (engine.on && !engine.fuel) { state = 'FLAMEOUT'; tone = 'bad'; }
    else if (engine.on && throttle > 0.05 && engine.thrust < 0.5 * (engine.max || 0) * throttle) { state = 'WEAK'; tone = 'warn'; }
    else if (engine.on) { state = engine.thrust > 0 ? 'burning' : 'lit'; tone = engine.thrust > 0 ? 'good' : ''; }
    const row = create('tr', tone);
    for (const text of [engine.stage, `${fixed(engine.x, 1)}, ${fixed(engine.z, 1)}`, state, fixed(engine.thrust / 1000, 1, 'kN'),
      fixed((engine.max || engine.rated || 0) / 1000, 1, 'kN'), engine.fuel ? 'yes' : 'NO']) row.append(create('td', '', String(text)));
    return row;
  }));
}
