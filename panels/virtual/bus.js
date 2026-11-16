/* The connection to the bus, shared by every page: the broker's address (?broker=ws://host:9001, or the machine the
   page came from), a unique client id, reconnection, and the top bar's light (#conn-dot, #conn-text from shell.js).

     const client = connectBus({
       name: 'panel-fdai',                                  // the client id is this plus a random suffix
       will: { topic, payload },                            // optional: published by the broker if the page goes away
       onConnect: (client) => client.subscribe([...]),      // on every (re)connection
       onMessage: (topic, text, packet) => { ... },         // text: the payload as a string
     });

   `mqtt` is the global of vendor/mqtt.min.js, loaded by each page before its modules. */

export const brokerUrl = new URLSearchParams(location.search).get('broker') || `ws://${location.hostname || 'localhost'}:9001`;
const RECONNECT_EVERY_MS = 1000;
const CONNECT_TIMEOUT_MS = 4000;

function showConnection(state, text) {
  const light = document.getElementById('conn-dot');
  const label = document.getElementById('conn-text');
  if (light) light.className = `dot ${state}`;
  if (label) label.textContent = text;
}

export function connectBus({ name, will = null, onConnect = () => {}, onMessage = () => {} }) {
  const options = {
    clientId: `${name}-${Math.random().toString(16).slice(2, 8)}`,
    reconnectPeriod: RECONNECT_EVERY_MS, connectTimeout: CONNECT_TIMEOUT_MS,
  };
  if (will) options.will = { qos: 1, retain: true, ...will, payload: JSON.stringify(will.payload) };
  const client = mqtt.connect(brokerUrl, options);
  client.on('connect', () => {
    showConnection('up', `bus ${brokerUrl}`);
    onConnect(client);
  });
  client.on('close', () => showConnection('down', 'bus disconnected'));
  client.on('error', (error) => showConnection('down', `bus error: ${error.message}`));
  client.on('message', (topic, buffer, packet) => onMessage(topic, buffer.toString(), packet));
  return client;
}

/* For a page running without the bus (?demo=1). */
export function showDemo() {
  showConnection('up', 'demo (no bus)');
}

/* JSON from a message's text; undefined when it is not JSON. */
export function parse(text) {
  try { return text ? JSON.parse(text) : {}; } catch { return undefined; }
}
