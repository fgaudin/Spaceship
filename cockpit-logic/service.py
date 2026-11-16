"""MQTT shell around the cockpit logic (the cockpit package): it feeds every bus message to the Cockpit with the
current time and publishes what the Cockpit returns. All the rules are in the package; nothing here but plumbing."""
import json
import os
import queue
import time

import paho.mqtt.client as mqtt

from cockpit import Cockpit

MQTT_HOST = os.environ.get('MQTT_HOST', 'localhost')
MQTT_PORT = int(os.environ.get('MQTT_PORT', '1883'))
SUBSCRIPTIONS = ['panel/+/in/#', 'tlm/#', 'gateway/status', 'sim/reset', 'dsky/uplink', 'pad/uplink']
TICK_EVERY_S = 0.25             # periodic work of the cockpit: staleness, re-commands, displays
INBOX_WAIT_S = 0.05


def connect_to_broker(inbox):
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id='cockpit-logic')
    # If this service dies, the broker tells the panels the cockpit is offline.
    client.will_set('cockpit/status', json.dumps({'online': False}), qos=1, retain=True)

    def on_connect(client, userdata, flags, reason, properties=None):
        for subscription in SUBSCRIPTIONS:
            client.subscribe(subscription, qos=1)
        client.publish('cockpit/status', json.dumps({'online': True}), qos=1, retain=True)
        print('connected, subscribed', SUBSCRIPTIONS, flush=True)

    def on_message(client, userdata, message):
        try:
            inbox.put((message.topic, json.loads(message.payload or b'{}')))
        except ValueError:
            print('bad payload on', message.topic, message.payload[:80], flush=True)

    client.on_connect, client.on_message = on_connect, on_message
    while True:
        try:
            client.connect(MQTT_HOST, MQTT_PORT, keepalive=10)
            break
        except OSError as error:
            print('broker not ready:', error, flush=True)
            time.sleep(1)
    client.loop_start()
    return client


def main():
    inbox = queue.Queue()           # messages arrive on the MQTT thread; the cockpit runs on this one
    client = connect_to_broker(inbox)
    cockpit = Cockpit()
    next_tick_at = 0.0
    while True:
        try:
            topic, payload = inbox.get(timeout=INBOX_WAIT_S)
            if topic == 'sim/reset':
                to_publish = cockpit.reset()
            else:
                to_publish = cockpit.handle(topic, payload, time.monotonic())
        except queue.Empty:
            to_publish = []
        now = time.monotonic()
        if now >= next_tick_at:
            to_publish += cockpit.tick(now)
            next_tick_at = now + TICK_EVERY_S
        for message in to_publish:
            client.publish(message.topic, json.dumps(message.payload), qos=message.qos, retain=message.retain)


if __name__ == '__main__':
    main()
