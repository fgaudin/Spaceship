"""MQTT shell around SimSup (simsup_core.py): feeds it the bus and publishes what it returns. No rules here."""
import glob
import json
import os
import queue
import time

import paho.mqtt.client as mqtt

from simsup_core import SimSup, panel_wiring, parameter_choices

MQTT_HOST = os.environ.get('MQTT_HOST', 'localhost')
MQTT_PORT = int(os.environ.get('MQTT_PORT', '1883'))
SCENARIOS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scenarios.json')
PANELS_DIR = os.environ.get('PANELS_DIR', os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'protocol', 'panels'))
SUBSCRIPTIONS = ['sim/simsup/cmd', 'tlm/#', 'panel/+/in/#', 'cmd/#', 'cw/state', 'probe/mode', 'probe/clearance']
TICK_EVERY_S = 1.0
INBOX_WAIT_S = 0.1


def publish(client, messages):
    for message in messages:
        client.publish(message.topic, json.dumps(message.payload), qos=message.qos, retain=message.retain)


def load_modules():
    modules = []
    for path in glob.glob(os.path.join(PANELS_DIR, '*.json')):
        with open(path, encoding='utf-8') as file:
            definition = json.load(file)
        if 'panels' in definition:          # a module (not console.json, nor hardware.json's assumptions)
            modules.append(definition)
    return modules


def main():
    with open(SCENARIOS_FILE) as file:
        scenarios = json.load(file)['scenarios']
    modules = load_modules()
    simsup = SimSup(scenarios=scenarios, panels=panel_wiring(modules), choices=parameter_choices(modules))
    inbox = queue.Queue()               # messages arrive on the MQTT thread; SimSup runs on this one
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id='simsup')

    def on_connect(client, userdata, flags, reason, properties=None):
        for subscription in SUBSCRIPTIONS:
            client.subscribe(subscription, qos=1)
        print('connected, subscribed', SUBSCRIPTIONS, flush=True)

    def on_message(client, userdata, message):
        try:
            inbox.put((message.topic, json.loads(message.payload or b'{}')))
        except ValueError:
            pass

    client.on_connect, client.on_message = on_connect, on_message
    while True:
        try:
            client.connect(MQTT_HOST, MQTT_PORT, keepalive=10)
            break
        except OSError as error:
            print('broker not ready:', error, flush=True)
            time.sleep(1)
    client.loop_start()
    publish(client, simsup.startup())
    next_tick_at = 0.0
    while True:
        try:
            topic, payload = inbox.get(timeout=INBOX_WAIT_S)
            to_publish = simsup.handle(topic, payload, time.monotonic())
        except queue.Empty:
            to_publish = []
        now = time.monotonic()
        if now >= next_tick_at:
            to_publish += simsup.tick(now)
            next_tick_at = now + TICK_EVERY_S
        publish(client, to_publish)


if __name__ == '__main__':
    main()
