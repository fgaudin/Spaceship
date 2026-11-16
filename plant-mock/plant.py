"""Mock plant service: runs the simulation (simulation.py) in real time and puts it on the bus in place of KSP.
It publishes the same tlm/* as the KSP gateway and obeys the same cmd/*, plus sim/reset and sim/failures/<name> from
the instructor. Only one plant may run at a time: the mock and the gateway write the same topics."""
import json
import os
import threading
import time

import paho.mqtt.client as mqtt

from simulation import Plant

MQTT_HOST = os.environ.get('MQTT_HOST', 'localhost')
MQTT_PORT = int(os.environ.get('MQTT_PORT', '1883'))
TIME_STEP_S = 0.02
PUBLISH_EVERY_STEPS = 5             # telemetry at 10 Hz
STATUS_EVERY_STEPS = 250            # gateway/status every 5 s
MAX_STEPS_PER_LOOP = 5000           # cap on catching up under high warp
STATUS = {'connected': True, 'plant': 'mock', 'scene': 'flight', 'vessel': 'Mock X', 'paused': False}


def main():
    plant = Plant()
    plant_lock = threading.Lock()       # commands arrive on the MQTT thread
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id='plant-mock')
    client.will_set('gateway/status', json.dumps({'connected': False, 'plant': 'mock'}), qos=1, retain=True)

    def publish_status():
        client.publish('gateway/status', json.dumps(STATUS), qos=1, retain=True)

    def on_connect(client, userdata, flags, reason, properties=None):
        client.subscribe('cmd/#', qos=1)
        client.subscribe('sim/#', qos=1)
        publish_status()
        print('mock plant connected', flush=True)

    def on_message(client, userdata, message):
        try:
            request = json.loads(message.payload or b'{}')
        except ValueError:
            return
        with plant_lock:
            plant.command(message.topic, request)

    client.on_connect, client.on_message = on_connect, on_message
    while True:
        try:
            client.connect(MQTT_HOST, MQTT_PORT, keepalive=10)
            break
        except OSError as error:
            print('broker not ready:', error, flush=True)
            time.sleep(1)
    client.loop_start()

    loop_count = 0
    simulated_until = time.monotonic()      # wall-clock time the simulation has caught up with
    while True:
        elapsed_steps = max(1, int((time.monotonic() - simulated_until) / TIME_STEP_S))
        simulated_until += elapsed_steps * TIME_STEP_S
        with plant_lock:
            steps = 0 if plant.paused else min(elapsed_steps * plant.warp_rate(), MAX_STEPS_PER_LOOP)
            for _ in range(steps):
                plant.step(TIME_STEP_S)
            loop_count += 1
            frozen = 'telemetry_freeze' in plant.failures
            telemetry = plant.telemetry() if loop_count % PUBLISH_EVERY_STEPS == 0 and not frozen else None
        if loop_count % STATUS_EVERY_STEPS == 0:
            publish_status()
        if telemetry:
            for topic, payload in telemetry.items():
                client.publish(topic, json.dumps(payload), qos=0, retain=(topic == 'tlm/orbit'))
        time.sleep(max(0.0, simulated_until + TIME_STEP_S - time.monotonic()))


if __name__ == '__main__':
    main()
