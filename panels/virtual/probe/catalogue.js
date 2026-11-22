/* What the probe control room can be cleared for, row by row: read by the room (probe.js) and by the instructor's
   page (simsup.js), which clears groups through the SimSup service (probe/clearance).

   A telemetry group is a few rows of one box. A row shows a measurement (what an instrument reads: altitude, speed,
   pressure, mass) or something worked out from them (apoapsis, Δv, TWR): the rule of the campaign is that a
   derived row is cleared only once the students have shown they can work it out by hand.
   A command group adds steps (or SAS modes) to the program builder. Staging, throttle, a kick, SAS on/off and the
   parachutes are always there: the first flight needs them.

   `module` is the course module after which the group is meant to be cleared (a hint for the instructor). */

export const BOXES = [
  ['trajectory', 'TRAJECTORY'],
  ['vehicle', 'VEHICLE'],
  ['environment', 'ENVIRONMENT'],
];

export const GROUPS = [
  // ---------- trajectory ----------
  { id: 'altitude', box: 'trajectory', title: 'Altitude and vertical speed', module: 'Newton & Gravity',
    rows: [['alt', 'ALTITUDE'], ['vs', 'VERTICAL SPEED']] },
  { id: 'state', box: 'trajectory', title: 'Radius, orbital speed, flight-path angle', module: 'Orbits',
    rows: [['radius', 'RADIUS'], ['v_orb', 'ORBITAL SPEED'], ['fpa', 'FLIGHT-PATH ANGLE']] },
  { id: 'apsides', box: 'trajectory', title: 'Apoapsis and periapsis (derived)', module: 'Orbits, after the hand proof',
    rows: [['apo', 'APOAPSIS'], ['peri', 'PERIAPSIS']] },
  { id: 'elements', box: 'trajectory', title: 'Period, semi-major axis, eccentricity (derived)', module: 'Orbits',
    rows: [['period', 'PERIOD'], ['sma', 'SEMI-MAJOR AXIS'], ['ecc', 'ECCENTRICITY']] },
  { id: 'position', box: 'trajectory', title: 'Latitude and longitude', module: 'Navigation',
    rows: [['lat', 'LATITUDE'], ['lon', 'LONGITUDE']] },
  { id: 'apsis_times', box: 'trajectory', title: 'Time to the apsides (derived)', module: 'When to Burn',
    rows: [['t_apo', 'TIME TO APOAPSIS'], ['t_peri', 'TIME TO PERIAPSIS']] },
  { id: 'plane', box: 'trajectory', title: 'Inclination and ascending node (derived)', module: 'Planes',
    rows: [['inc', 'INCLINATION'], ['lan', 'ASCENDING NODE']] },
  { id: 'soi', box: 'trajectory', title: 'Body and time to the next SOI change', module: 'Going to the Moon',
    rows: [['body', 'BODY'], ['t_soi', 'TIME TO SOI CHANGE']] },
  { id: 'landing', box: 'trajectory', title: 'Radar altitude and horizontal speed', module: 'Landing on the Moon',
    rows: [['radar', 'RADAR ALTITUDE'], ['hs', 'HORIZONTAL SPEED']] },
  // ---------- vehicle ----------
  { id: 'mass', box: 'vehicle', title: 'Stage, mass, thrust, throttle', module: 'Rocket Science',
    rows: [['stage', 'STAGE'], ['mass', 'MASS'], ['thrust', 'THRUST'], ['throttle', 'THROTTLE']] },
  { id: 'propellant', box: 'vehicle', title: 'Stage propellant and specific impulse', module: 'Rocket Science',
    rows: [['prop', 'STAGE PROPELLANT'], ['isp', 'SPECIFIC IMPULSE']] },
  { id: 'performance', box: 'vehicle', title: 'Stage Δv and TWR (derived)', module: 'Rocket Science, after the hand proof',
    rows: [['dv', 'STAGE Δv'], ['twr', 'TWR']] },
  { id: 'attitude', box: 'vehicle', title: 'Pitch, heading, prograde, SAS', module: 'Getting to Orbit',
    rows: [['pitch', 'PITCH'], ['heading', 'HEADING'], ['pro_pitch', 'PROGRADE PITCH'], ['sas', 'SAS']] },
  { id: 'burn', box: 'vehicle', title: 'Burn computer: Δv to go, burn time, pointing', module: 'Planning a Burn',
    rows: [['burn_state', 'BURN'], ['vg', 'Δv TO GO'], ['tb', 'BURN TIME'], ['att_err', 'POINTING ERROR']] },
  { id: 'power', box: 'vehicle', title: 'Electric charge', module: 'any',
    rows: [['charge', 'CHARGE']] },
  // ---------- environment ----------
  { id: 'air', box: 'environment', title: 'Static pressure and outside temperature', module: 'Measuring an Atmosphere',
    rows: [['p', 'STATIC PRESSURE'], ['temp', 'OUTSIDE TEMPERATURE']] },
  { id: 'loads', box: 'environment', title: 'Dynamic pressure and g load', module: 'Getting to Orbit',
    rows: [['q', 'DYNAMIC PRESSURE'], ['g', 'G LOAD']] },
  { id: 'thermal', box: 'environment', title: 'Hottest part', module: 'Coming Home',
    rows: [['heat', 'HOTTEST PART']] },
  { id: 'target', box: 'environment', title: 'Target: range, relative and closing speed', module: 'Docking',
    rows: [['tgt', 'TARGET'], ['range', 'RANGE'], ['rel_v', 'RELATIVE SPEED'], ['closing', 'CLOSING SPEED']] },
  // ---------- commands ----------
  { id: 'cmd_burnout', kind: 'cmd', title: 'BURNOUT trigger: when the engines the next staging drops are empty', module: 'Rocket Science, after a flight staged on computed times' },
  { id: 'cmd_sas_pro', kind: 'cmd', title: 'SAS prograde and retrograde', module: 'Getting to Orbit' },
  { id: 'cmd_sas_all', kind: 'cmd', title: 'SAS normal, radial and target', module: 'Planes, Docking' },
  { id: 'cmd_burn', kind: 'cmd', title: 'Burns (TIG, Δv) and SAS maneuver', module: 'Planning a Burn' },
  { id: 'cmd_science', kind: 'cmd', title: 'Run the experiments', module: 'Measuring an Atmosphere' },
];

/* The group a program step needs, or null for the steps always there. */
export const ACTION_NEEDS = { stage: null, throttle: null, kick: null, sas: null, chute: null,
  sas_mode: null, burn: 'cmd_burn', science: 'cmd_science' };

/* The group each SAS mode needs (stability needs none). */
export const SAS_MODE_NEEDS = { stability: null, prograde: 'cmd_sas_pro', retrograde: 'cmd_sas_pro',
  normal: 'cmd_sas_all', antinormal: 'cmd_sas_all', radial: 'cmd_sas_all', antiradial: 'cmd_sas_all',
  target: 'cmd_sas_all', antitarget: 'cmd_sas_all', maneuver: 'cmd_burn' };

/* The group each kind of trigger needs. */
export const TRIGGER_NEEDS = { t: null, met: null, burnout: 'cmd_burnout' };

export const telemetryGroups = () => GROUPS.filter((group) => group.kind !== 'cmd');
export const commandGroups = () => GROUPS.filter((group) => group.kind === 'cmd');
