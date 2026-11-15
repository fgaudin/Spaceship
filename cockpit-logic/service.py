"""MQTT shell around the pure cockpit logic (logic.py): subscribe, feed messages with the time, publish what it returns."""
import json, os, queue, time
import paho.mqtt.client as mqtt
from logic import Cockpit

HOST = os.environ.get('MQTT_HOST', 'localhost')
PORT = int(os.environ.get('MQTT_PORT', '1883'))
SUBS = ['panel/+/in/#', 'tlm/#', 'gateway/status', 'sim/reset', 'dsky/uplink', 'pad/uplink']


def main():
    inbox = queue.Queue()
    cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id='cockpit-logic')
    cli.will_set('cockpit/status', json.dumps({'online': False}), qos=1, retain=True)

    def on_connect(c, u, flags, rc, props=None):
        for s in SUBS:
            c.subscribe(s, qos=1)
        c.publish('cockpit/status', json.dumps({'online': True}), qos=1, retain=True)
        print('connected, subscribed', SUBS, flush=True)

    def on_message(c, u, m):
        try:
            inbox.put((m.topic, json.loads(m.payload or b'{}')))
        except ValueError:
            print('bad payload on', m.topic, m.payload[:80], flush=True)

    cli.on_connect, cli.on_message = on_connect, on_message
    while True:
        try:
            cli.connect(HOST, PORT, keepalive=10)
            break
        except OSError as e:
            print('broker not ready:', e, flush=True)
            time.sleep(1)
    cli.loop_start()
    cockpit = Cockpit()
    next_tick = 0.0
    while True:
        try:
            topic, payload = inbox.get(timeout=0.05)
            if topic == 'sim/reset':
                out = cockpit.reset()
            else:
                out = cockpit.handle(topic, payload, time.monotonic())
        except queue.Empty:
            out = []
        now = time.monotonic()
        if now >= next_tick:
            out += cockpit.tick(now)
            next_tick = now + 0.25
        for m in out:
            cli.publish(m.topic, json.dumps(m.payload), qos=m.qos, retain=m.retain)


if __name__ == '__main__':
    main()
