/* The flight so far, for charts and tracks: one sample a second of the telemetry, as columns (`t` is the MET), the
   flight's events and where it lifted off. A page asks mcc-data's recorder for the whole flight when it connects
   (mcc/history/get), then adds its own samples; without the recorder it has what it saw since it was opened.

   The same rules as the recorder (mcc-data/recorder.py): the clock back to zero is a new flight, back to an
   earlier moment a quickload (what came after goes). */
import { store, onMessage, onConnect, publish } from './bus.js';

export const COLUMN_NAMES = ['t', 'ut', 'alt', 'radar', 'apo', 'peri', 'spd', 'vorb', 'vs', 'q', 'g', 'lat', 'lon',
  'thr', 'thrust', 'mass', 'heat', 'ec', 'body'];
const SAMPLE_EVERY_MS = 1000;
const ASK_AGAIN_MS = 5000;
const MAX_POINTS = 7200;
const NEW_FLIGHT_MET_S = 1;
const MAX_EVENTS = 400;

const pageId = `page-${Math.random().toString(36).slice(2, 10)}`;
const listeners = [];
let columns = emptyColumns();
let events = [];
let launch = null;
let fromRecorder = false;
let lastSituation = null;

function emptyColumns() { return Object.fromEntries(COLUMN_NAMES.map((name) => [name, []])); }

export const history = () => ({ columns, events, launch, fromRecorder });
export const recorderOnline = () => Boolean(store['mcc/data/status']?.online);

/* listener() whenever the history changes (about once a second). */
export function onHistory(listener) { listeners.push(listener); }
const changed = () => { for (const listener of listeners) listener(); };

function cut(keep) {
  for (const name of COLUMN_NAMES) columns[name] = columns[name].slice(0, keep);
}

function sample() {
  const time = store['tlm/time'], flight = store['tlm/flight'];
  if (!time || !flight || time.met == null) return;
  const met = time.met, times = columns.t;
  if (times.length && met < times[times.length - 1] - NEW_FLIGHT_MET_S) {
    if (met < NEW_FLIGHT_MET_S) { columns = emptyColumns(); events = []; launch = null; }
    else { cut(times.findIndex((t) => t > met)); events = events.filter((event) => event.t <= met); }
  }
  if (columns.t.length && met <= columns.t[columns.t.length - 1]) return;
  const orbit = store['tlm/orbit'] || {}, vessel = store['tlm/vessel'] || {}, thermal = store['tlm/thermal'] || {};
  const charge = store['tlm/resources']?.total?.ElectricCharge;
  const row = { t: met, ut: time.ut, alt: flight.alt, radar: flight.radar, apo: orbit.apo, peri: orbit.peri,
    spd: flight.speed, vorb: flight.v_orb, vs: flight.vs, q: flight.q, g: flight.g, lat: flight.lat, lon: flight.lon,
    thr: vessel.throttle, thrust: vessel.thrust, mass: vessel.mass, heat: thermal.max,
    ec: charge?.max ? charge.amount / charge.max : null, body: orbit.body };
  // the lift-off, when the recorder is not there to say
  const grounded = ['pre_launch', 'landed', 'splashed'];
  if (!launch && grounded.includes(lastSituation) && vessel.situation && !grounded.includes(vessel.situation)) {
    launch = launchPoint(row.body, row, met);
  }
  lastSituation = vessel.situation || lastSituation;
  for (const name of COLUMN_NAMES) columns[name].push(row[name] ?? null);
  if (columns.t.length > MAX_POINTS) {
    const keep = columns.t.map((_, index) => index % 2 === 0 || index === columns.t.length - 1);
    for (const name of COLUMN_NAMES) columns[name] = columns[name].filter((_, index) => keep[index]);
  }
  changed();
}

/* Where it left the ground: the last sample on the body it climbs from (one from before a revert can name another
   body), else `fallback` (the sample being taken). As the recorder's launch_point. */
function launchPoint(body, fallback, t) {
  for (let index = columns.t.length - 1; index >= 0; index--) {
    if (columns.body[index] === body && columns.lat[index] != null) {
      return { lat: columns.lat[index], lon: columns.lon[index], body, t };
    }
  }
  return fallback && fallback.lat != null ? { lat: fallback.lat, lon: fallback.lon, body, t } : null;
}

function askRecorder() {
  if (!fromRecorder) publish('mcc/history/get', { id: pageId });
}

onMessage((topic, payload) => {
  if (topic === `mcc/history/${pageId}` && payload.columns) {
    const recorded = payload.columns;
    const lastRecorded = recorded.t[recorded.t.length - 1] ?? -Infinity;
    const newer = columns.t.findIndex((t) => t > lastRecorded);
    const mine = newer < 0 ? emptyColumns() : Object.fromEntries(COLUMN_NAMES.map((name) => [name, columns[name].slice(newer)]));
    columns = Object.fromEntries(COLUMN_NAMES.map((name) => [name, [...(recorded[name] || []), ...mine[name]]]));
    events = payload.events || [];
    launch = payload.launch || launch;
    fromRecorder = true;
    changed();
  } else if (topic === 'mcc/events') {
    if (!events.some((event) => event.t === payload.t && event.text === payload.text)) {
      events = [...events, payload].slice(-MAX_EVENTS);
      if (payload.text === 'LIFTOFF' && !launch && columns.t.length) {
        const last = columns.t.length - 1;
        launch = launchPoint(columns.body[last], null, payload.t);
      }
      changed();
    }
  }
});

onConnect(() => { fromRecorder = false; askRecorder(); });
setInterval(sample, SAMPLE_EVERY_MS);
setInterval(askRecorder, ASK_AGAIN_MS);
