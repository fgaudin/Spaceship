"""Flight dynamics service: the solo pilot's Mission Control. On a press of the SOLO panel's buttons it works out
the PAD (planner.py) and reads it up to the burn computer on pad/uplink, exactly as CAPCOM would; the crew accepts
it there. fd/status says what it did, for the panel's display.

    panel/solo/in/fd_circ, fd_plane, fd_rdv, fd_inject (buttons), fd_body (knob: 0 MUN, 1 MINMUS),
    mcc_mode (the MODE switch on NAVIGATION, SOLO / MCC: on MCC, Mission Control is there and the buttons do nothing)
"""
import json
import os
import time

import paho.mqtt.client as mqtt

from planner import Pad, change_plane, circularise, inject, rendezvous

MQTT_HOST = os.environ.get('MQTT_HOST', 'localhost')
MQTT_PORT = int(os.environ.get('MQTT_PORT', '1883'))
MOONS = ['Mun', 'Minmus']
REQUESTS = {
    'fd_circ': lambda telemetry, moon: circularise(telemetry),
    'fd_plane': lambda telemetry, moon: change_plane(telemetry),
    'fd_rdv': lambda telemetry, moon: rendezvous(telemetry),
    'fd_inject': lambda telemetry, moon: inject(telemetry, moon),
}


def answer(control, telemetry, inputs, powered=True):
    """(uplink payload or None, status payload) for a request button. `powered`: cockpit/power, what the cockpit
    logic says (no electric charge, or the breaker out)."""
    if not powered or inputs.get('mcc_mode'):
        return None, {'text': '', 'ok': False}              # no power, or MCC flying: the panel is dead
    moon = MOONS[int(inputs.get('fd_body') or 0) % len(MOONS)]
    result = REQUESTS[control](telemetry, moon)
    if isinstance(result, Pad):
        return {'tig_met': result.tig_met, 'dv': list(result.dv)}, {'text': result.text, 'ok': True}
    return None, {'text': result.text, 'ok': False}


def main():
    telemetry, inputs, power = {}, {}, {'on': True}
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id='flight-dynamics')

    def on_connect(client, userdata, flags, reason, properties=None):
        client.subscribe([('tlm/#', 0), ('panel/solo/in/#', 1), ('cockpit/power', 1)])
        client.publish('fd/status', json.dumps({'text': 'READY', 'ok': True}), qos=1, retain=True)
        print('connected', flush=True)

    def on_message(client, userdata, message):
        try:
            payload = json.loads(message.payload or b'{}')
        except ValueError:
            return
        if message.topic.startswith('tlm/'):
            telemetry[message.topic] = payload
            return
        if message.topic == 'cockpit/power':
            power['on'] = bool(payload.get('on', True))
            return
        control = message.topic.rsplit('/', 1)[1]
        pressed = bool(payload.get('v')) and not inputs.get(control)
        inputs[control] = payload.get('v')
        if control in REQUESTS and pressed:
            uplink, status = answer(control, telemetry, inputs, power['on'])
            if uplink:
                client.publish('pad/uplink', json.dumps(uplink), qos=1)
            client.publish('fd/status', json.dumps(status), qos=1, retain=True)
            print(control, status, uplink, flush=True)

    client.on_connect, client.on_message = on_connect, on_message
    while True:
        try:
            client.connect(MQTT_HOST, MQTT_PORT, keepalive=10)
            break
        except OSError as error:
            print('broker not ready:', error, flush=True)
            time.sleep(1)
    client.loop_forever()


if __name__ == '__main__':
    main()
