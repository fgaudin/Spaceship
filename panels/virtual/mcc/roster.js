/* The consoles of the MCC, in tab order. Each module exports mount(root) and update(). */
import * as flight from './consoles/flight.js';
import * as fido from './consoles/fido.js';
import * as retro from './consoles/retro.js';
import * as guido from './consoles/guido.js';
import * as booster from './consoles/booster.js';
import * as eecom from './consoles/eecom.js';
import * as capcom from './consoles/capcom.js';

export const CONSOLES = [
  { id: 'flight', name: 'FLIGHT', title: 'Flight director', module: flight },
  { id: 'fido', name: 'FIDO', title: 'Flight dynamics: the trajectory', module: fido },
  { id: 'retro', name: 'RETRO', title: 'Retrofire: the way home and the aborts', module: retro },
  { id: 'guido', name: 'GUIDO', title: 'Guidance: the burn computer and the attitude', module: guido },
  { id: 'booster', name: 'BOOSTER', title: 'Propulsion: engines and propellant', module: booster },
  { id: 'eecom', name: 'EECOM', title: 'Electrical, thermal and communications', module: eecom },
  { id: 'capcom', name: 'CAPCOM', title: 'Capsule communicator: PADs to the crew', module: capcom },
];
