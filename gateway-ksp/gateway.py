"""KSP gateway: the only process that talks to KSP. kRPC → tlm/* on the bus; cmd/* from the bus → kRPC calls.

Same topics and payloads as the mock plant (protocol/topics.md). It survives KSP not running (retries), scene changes
and vessel switches (streams are rebuilt when the active vessel changes) and staging (part streams are rebuilt).
"""
import json
import os
import queue
import time

import paho.mqtt.client as mqtt

from ksp.commands import CommandHandler
from ksp.vessel_link import NEW_VESSEL, NO_VESSEL, VesselLink

MQTT_HOST = os.environ.get('MQTT_HOST', 'localhost')
MQTT_PORT = int(os.environ.get('MQTT_PORT', '1883'))
KRPC_HOST = os.environ.get('KRPC_HOST', '127.0.0.1')
TELEMETRY_RATE_HZ = float(os.environ.get('RATE_HZ', '10'))
SLOW_TELEMETRY_EVERY = 5        # orbit, resources, engines, heat, node: every 5th cycle (2 Hz)
TARGET_TELEMETRY_EVERY = 2      # the target, while one is set: every 2nd cycle (5 Hz)
STATUS_EVERY_S = 5
NO_VESSEL_STATUS_EVERY_S = 2
RETRY_KRPC_AFTER_S = 3
RECONNECT_AFTER_S = 2


def connect_to_broker(command_queue):
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id='gateway-ksp')
    # If the gateway dies, the broker tells everyone the plant is gone.
    client.will_set('gateway/status', json.dumps({'connected': False, 'plant': 'ksp'}), qos=1, retain=True)
    client.on_connect = lambda client, userdata, flags, reason, properties=None: client.subscribe('cmd/#', qos=1)
    client.on_message = lambda client, userdata, message: command_queue.put(
        (message.topic, json.loads(message.payload or b'{}')))
    while True:
        try:
            client.connect(MQTT_HOST, MQTT_PORT, keepalive=10)
            break
        except OSError as error:
            print('broker not ready:', error, flush=True)
            time.sleep(1)
    client.loop_start()
    return client


def run_commands(command_queue, commands, wait_until=None):
    """Run the queued commands. With `wait_until`, keep waiting for more until that time, so that a command (the
    burn computer's cutoff) acts at once and not at the next telemetry cycle."""
    while True:
        try:
            if wait_until is None:
                topic, request = command_queue.get_nowait()
            else:
                topic, request = command_queue.get(timeout=max(0.0, wait_until - time.monotonic()))
        except queue.Empty:
            return
        commands.run(topic, request)


def fly(link, client, command_queue, publish_status):
    """The telemetry loop for one kRPC connection. Returns only by raising (scene change, KSP quit, vessel gone)."""
    commands = CommandHandler(link)
    status_sent_at, cycle = 0.0, 0
    cycle_period = 1 / TELEMETRY_RATE_HZ
    next_cycle_at = time.monotonic()
    while True:
        binding = link.bind()
        if binding == NO_VESSEL:
            if time.monotonic() - status_sent_at > NO_VESSEL_STATUS_EVERY_S:
                status_sent_at = time.monotonic()
                publish_status(connected=False, scene='no vessel')
            time.sleep(0.5)
            continue
        if binding == NEW_VESSEL or time.monotonic() - status_sent_at > STATUS_EVERY_S:
            if binding == NEW_VESSEL:
                print('active vessel:', link.vessel.name, flush=True)
            status_sent_at = time.monotonic()
            publish_status(connected=True, scene='flight', vessel=link.vessel.name, paused=link.connection.krpc.paused)

        run_commands(command_queue, commands)
        if link.vessel is None:         # a command split the vessel (undock): bind again first
            continue
        commands.continue_warp_to()
        cycle += 1
        payloads = link.telemetry(include_slow=cycle % SLOW_TELEMETRY_EVERY == 1,
                                  include_target=cycle % TARGET_TELEMETRY_EVERY == 0)
        for topic, payload in payloads.items():
            client.publish(topic, json.dumps(payload), qos=0, retain=(topic == 'tlm/orbit'))
        # Cycles start on a fixed beat, whatever the work took; after a long stall the beat starts again from now.
        next_cycle_at = max(next_cycle_at + cycle_period, time.monotonic())
        run_commands(command_queue, commands, wait_until=next_cycle_at)


def main():
    command_queue = queue.Queue()
    client = connect_to_broker(command_queue)

    def publish_status(**fields):
        client.publish('gateway/status', json.dumps({'plant': 'ksp', **fields}), qos=1, retain=True)

    while True:
        try:
            link = VesselLink(KRPC_HOST)
        except Exception as error:
            publish_status(connected=False, error=str(error)[:200])
            print('kRPC not reachable:', error, flush=True)
            time.sleep(RETRY_KRPC_AFTER_S)
            continue
        print('connected to kRPC', link.connection.krpc.get_status().version, flush=True)
        try:
            fly(link, client, command_queue, publish_status)
        except Exception as error:
            print('link lost:', repr(error)[:300], flush=True)
            publish_status(connected=False, error=repr(error)[:200])
            link.close()
            time.sleep(RECONNECT_AFTER_S)


if __name__ == '__main__':
    main()
