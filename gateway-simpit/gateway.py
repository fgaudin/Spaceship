"""Simpit gateway: a fallback plant for when kRPC is not there. It talks to KSP through the Kerbal Simpit plugin's
serial protocol, playing the Arduino, and publishes the same tlm/* topics and takes the same cmd/* as gateway-ksp, for
the part Simpit can do (simpit/bridge.py). Run one plant at a time: this one, gateway-ksp or the mock.

    SIMPIT_PORT=/dev/ttyUSB0 python gateway.py       # a real serial port (a USB-serial cable looped to another)
    socat -d -d pty,raw,echo=0,link=/tmp/simpit-ksp pty,raw,echo=0,link=/tmp/simpit-gw   # or two linked ptys:
    SIMPIT_PORT=/tmp/simpit-gw python gateway.py     #   KSP's Settings.cfg PortName = /tmp/simpit-ksp
"""
import json
import os
import queue
import time

import paho.mqtt.client as mqtt
import serial

from simpit import protocol
from simpit.bridge import CHANNELS, Bridge, command
from simpit.link import LinkError, SimpitLink

MQTT_HOST = os.environ.get('MQTT_HOST', 'localhost')
MQTT_PORT = int(os.environ.get('MQTT_PORT', '1883'))
SIMPIT_PORT = os.environ.get('SIMPIT_PORT', '/tmp/simpit-gw')
BAUD_RATE = int(os.environ.get('SIMPIT_BAUD', '115200'))   # Settings.cfg BaudRate; a pty ignores it
PUBLISH_EVERY_S = 0.1           # telemetry at most 10 Hz, as gateway-ksp
STATUS_EVERY_S = 5
RETRY_AFTER_S = 3
ECHO_EVERY_S = 2                # an echo request: the plugin answers even out of the flight scene
SILENT_AFTER_S = 6              # nothing from the plugin this long (not even an echo): the link is gone, start again


def main():
    commands = queue.Queue()
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id='gateway-simpit')
    client.will_set('gateway/status', json.dumps({'connected': False, 'plant': 'simpit'}), qos=1, retain=True)
    client.on_connect = lambda client, userdata, flags, reason, properties=None: client.subscribe([('cmd/#', 1)])
    client.on_message = lambda client, userdata, message: commands.put(
        (message.topic, json.loads(message.payload or b'{}')))
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=10)
    client.loop_start()
    publish = lambda topic, payload, retain=False: client.publish(topic, json.dumps(payload), qos=1 if retain else 0,
                                                                  retain=retain)
    while True:
        try:
            with serial.Serial(SIMPIT_PORT, BAUD_RATE, timeout=0.02) as port:
                fly(SimpitLink(port), commands, publish)
        except (OSError, serial.SerialException, LinkError) as error:
            print('simpit:', error, flush=True)
        publish('gateway/status', {'connected': False, 'plant': 'simpit'}, retain=True)
        time.sleep(RETRY_AFTER_S)


def fly(link, commands, publish):
    link.handshake(CHANNELS)
    print('simpit: connected, channels registered', flush=True)
    bridge = Bridge()
    publish('gateway/status', bridge.status(True), retain=True)
    last_heard = last_publish = last_status = last_echo = time.monotonic()
    while True:
        now = time.monotonic()
        for message_type, payload in link.read():
            last_heard = now
            if not link.answer_echo(message_type, payload):
                bridge.on_message(message_type, payload)
        while not commands.empty():
            topic, request = commands.get_nowait()
            link.send(command(topic, request))
        if now - last_publish >= PUBLISH_EVERY_S:
            last_publish = now
            for topic, payload in bridge.topics().items():
                publish(topic, payload, retain=topic == 'gateway/status')
        if now - last_echo >= ECHO_EVERY_S:
            last_echo = now
            link.send([protocol.frame(protocol.ECHO_REQ, b'\x00')])
        if now - last_status >= STATUS_EVERY_S:
            last_status = now
            publish('gateway/status', bridge.status(True), retain=True)
        if now - last_heard > SILENT_AFTER_S:
            raise LinkError(f'nothing from the plugin for {SILENT_AFTER_S} s')


if __name__ == '__main__':
    main()
