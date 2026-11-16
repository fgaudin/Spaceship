/* The MCC's link to the bus: one MQTT connection, a store of the last payload per topic, and helpers.

   MCC topics (one writer each, retained so that a console opened late sees the state):
     mcc/poll          FLIGHT           {"open", "question", "met"}: the go/no-go poll
     mcc/poll/<role>   that console     {"go": true | false, "met"}: its answer
     mcc/loop/<role>   that console     {"text", "met"} (not retained): a note on the flight director's loop
   MCC never subscribes to sim/*: flight controllers find failures from what the vehicle does, as in Apollo. */

import { connectBus, parse } from '../bus.js';

const SUBSCRIPTIONS = ['tlm/#', 'cw/state', 'cmp/pad', 'gateway/status', 'cockpit/status', 'panel/+/status',
  'panel/cmp/out/lamp_uplink', 'panel/eng/in/abort_mode', 'panel/+/in/#', 'mcc/#'];

export const store = {};                // topic → last payload
export const receivedAt = {};           // topic → Date.now() of the last message
const listeners = [];

export const client = connectBus({
  name: 'mcc',
  onConnect: (connection) => connection.subscribe(SUBSCRIPTIONS, { qos: 0 }),
  onMessage: (topic, text, packet) => {
    const payload = parse(text);
    if (payload === undefined) return;
    store[topic] = payload;
    receivedAt[topic] = Date.now();
    for (const listener of listeners) listener(topic, payload, packet.retain);
  },
});

/* listener(topic, payload, retained) for every message: for consoles that keep their own history (events, feeds). */
export function onMessage(listener) { listeners.push(listener); }

export function publish(topic, payload, retain = false) {
  client.publish(topic, JSON.stringify(payload), { qos: 1, retain });
}

/* ---------- reading the flight ---------- */
const STALE_AFTER_MS = 2000;
export const telemetryLive = () => Date.now() - (receivedAt['tlm/time'] || 0) < STALE_AFTER_MS;
export const vessel = () => store['tlm/vessel'] || {};
export const flight = () => store['tlm/flight'] || {};
export const orbit = () => store['tlm/orbit'] || {};
export const clock = () => store['tlm/time'] || {};
export const met = () => clock().met;
export const linkUp = () => {
  const comm = store['tlm/comm'];
  return comm ? Boolean(comm.link) : vessel().comm !== false;
};
