"""Mission Control's data: what the MCC consoles and the wall display need besides the live telemetry.

    flight recorder (recorder.py)   one sample a second and the flight's events; a page asks for the flight so far
                                    with mcc/history/get {"id"} and gets it on mcc/history/<id>; events also go out
                                    live on mcc/events
    bodies (kRPC)                   mcc/bodies, retained: every body's radius, μ, rotation, atmosphere, sphere of
                                    influence, orbit around its parent, and where its sun is overhead, read from the
                                    game (JNSQ's are not stock's); "highest", its highest terrain (m), once mapped
    relief maps (relief.py)         the terrain of the body being flown, and of its moons, sampled from the game with
                                    its biomes (ice, desert) into MAPS_DIR/<body>-<radius>-<version>.png, listed on
                                    mcc/maps (retained)

    mcc/data/status (retained)      {"online", "krpc", "mapping": {"body", "progress"} or null}

The flight is saved to STATE_FILE every 30 s and restored on start: a restart mid-flight keeps it.

Without kRPC (the mock plant) the recorder still runs; the pages draw the bodies from their own table, without maps.
"""
import json
import math
import os
import struct
import threading
import time
import zlib

import paho.mqtt.client as mqtt

import relief
from recorder import Recorder

MQTT_HOST = os.environ.get('MQTT_HOST', 'localhost')
MQTT_PORT = int(os.environ.get('MQTT_PORT', '1883'))
KRPC_HOST = os.environ.get('KRPC_HOST', '127.0.0.1')
MAPS_DIR = os.environ.get('MAPS_DIR', 'maps')
STATE_FILE = os.environ.get('STATE_FILE', 'state/flight.json')       # the flight so far, kept across a restart
SAVE_EVERY_S = 30.0
SAMPLE_EVERY_S = 1.0
BODIES_EVERY_S = 60.0
KRPC_RETRY_S = 10.0
ROW_PAUSE_S = 0.01              # between map rows: kRPC shares the game's frame with the gateway
SUBSCRIPTIONS = [('tlm/time', 0), ('tlm/flight', 0), ('tlm/orbit', 0), ('tlm/vessel', 0), ('tlm/thermal', 0),
                 ('tlm/resources', 0), ('tlm/comm', 0), ('tlm/target', 0), ('cw/state', 1), ('mcc/history/get', 1)]

lock = threading.Lock()
recorder = Recorder()
status = {'online': True, 'krpc': False, 'mapping': None}


def publish(client, topic, payload, retain=False):
    client.publish(topic, json.dumps(payload, separators=(',', ':')), qos=1, retain=retain)


def publish_status(client):
    publish(client, 'mcc/data/status', status, retain=True)


# ---------- the recorder ----------
def on_message(client, userdata, message):
    try:
        payload = json.loads(message.payload or b'{}')
    except ValueError:
        return
    if message.topic == 'mcc/history/get':
        asker = str(payload.get('id', ''))[:40]
        if asker:
            with lock:
                history = recorder.history()
            publish(client, f'mcc/history/{asker}', history)
        return
    with lock:
        events = recorder.on_message(message.topic, payload)
    for event in events:
        publish(client, 'mcc/events', event.payload())


def keep_sampling(client):
    saved_at = time.monotonic()
    while True:
        time.sleep(SAMPLE_EVERY_S)
        with lock:
            events = recorder.sample()
        for event in events:
            publish(client, 'mcc/events', event.payload())
        if time.monotonic() - saved_at > SAVE_EVERY_S:
            save_flight()
            saved_at = time.monotonic()


def save_flight():
    with lock:
        state = recorder.state()
    try:
        os.makedirs(os.path.dirname(STATE_FILE) or '.', exist_ok=True)
        with open(STATE_FILE + '.new', 'w') as handle:
            json.dump(state, handle, separators=(',', ':'))
        os.replace(STATE_FILE + '.new', STATE_FILE)
    except OSError as error:
        print('cannot save the flight:', error, flush=True)


def load_flight():
    try:
        with open(STATE_FILE) as handle:
            recorder.restore(json.load(handle))
        print(f'flight restored: {len(recorder.points)} samples, {len(recorder.events)} events', flush=True)
    except (OSError, ValueError, KeyError) as error:
        print('no flight to restore:', error, flush=True)


# ---------- kRPC: bodies and maps ----------
def read_bodies(space_center):
    sun = next((body for body in space_center.bodies.values() if body.orbit is None), None)
    bodies = {}
    for name, body in space_center.bodies.items():
        orbit = body.orbit
        entry = {'radius': body.equatorial_radius, 'mu': body.gravitational_parameter,
                 'rotation_period': body.rotational_period,
                 'atmosphere': body.atmosphere_depth if body.has_atmosphere else 0.0,
                 'soi': body.sphere_of_influence if math.isfinite(body.sphere_of_influence) else None,
                 'parent': orbit.body.name if orbit else None, 'orbit': None, 'subsolar': None}
        if orbit:
            entry['orbit'] = {'a': orbit.semi_major_axis, 'e': orbit.eccentricity,
                              'i': math.degrees(orbit.inclination), 'lan': math.degrees(orbit.longitude_of_ascending_node),
                              'argp': math.degrees(orbit.argument_of_periapsis), 'm0': orbit.mean_anomaly_at_epoch,
                              'epoch': orbit.epoch, 'period': orbit.period}
        if sun is not None and body is not sun:
            frame = body.reference_frame
            position = sun.position(frame)
            entry['subsolar'] = {'lat': body.latitude_at_position(position, frame),
                                 'lon': body.longitude_at_position(position, frame)}
        bodies[name] = entry
    return {'ut': space_center.ut, 'bodies': bodies}


MAP_VERSION = 'r3'          # in the file names: a new colouring makes new maps (older files are left, unused)


def map_file(name, radius):
    return f'{name}-{int(radius)}-{MAP_VERSION}.png'


def list_maps():
    maps = {}
    for file in sorted(os.listdir(MAPS_DIR)) if os.path.isdir(MAPS_DIR) else []:
        if file.endswith(f'-{MAP_VERSION}.json'):
            try:
                with open(os.path.join(MAPS_DIR, file)) as handle:
                    info = json.load(handle)
                maps[info['body']] = info
            except (OSError, ValueError, KeyError):
                continue
    return maps


BIOME_STEP = 2             # the biomes at half the map's resolution: their borders are coarse, and each read costs


def make_map(client, body, name):
    """Sample the terrain of `body` row by row, and its biomes, and write its relief map."""
    radius = body.equatorial_radius
    has_biomes = bool(body.biomes)
    heights, ocean, surfaces, has_ocean = [], [], [], False
    for row in range(relief.HEIGHT):
        latitude = relief.latitude_of_row(row)
        line, wet = [], []
        for column in range(relief.WIDTH):
            longitude = relief.longitude_of_column(column)
            bedrock = body.bedrock_height(latitude, longitude)
            under_sea = bedrock < 0 and body.surface_height(latitude, longitude) > bedrock + 1.0
            has_ocean = has_ocean or under_sea
            line.append(bedrock)
            wet.append(under_sea)
        heights.append(line)
        ocean.append(wet)
        if row % BIOME_STEP == 0:
            middle = relief.latitude_of_row(row + 0.5 * (BIOME_STEP - 1))
            coarse = [relief.surface_of(body.biome_at(middle, relief.longitude_of_column(column + 0.5 * (BIOME_STEP - 1))))
                      if has_biomes else relief.PLAIN for column in range(0, relief.WIDTH, BIOME_STEP)]
            surface_line = [coarse[column // BIOME_STEP] for column in range(relief.WIDTH)]
        surfaces.append(surface_line)
        if row % 12 == 0:
            status['mapping'] = {'body': name, 'progress': round(row / relief.HEIGHT, 2)}
            publish_status(client)
        time.sleep(ROW_PAUSE_S)
    rows = relief.colour(name, heights, ocean if has_ocean else None, radius, surfaces if has_biomes else None)
    os.makedirs(MAPS_DIR, exist_ok=True)
    file = map_file(name, radius)
    with open(os.path.join(MAPS_DIR, file), 'wb') as handle:
        handle.write(relief.png(rows, relief.WIDTH, relief.HEIGHT))
    flat = [h for line in heights for h in line]
    with open(os.path.join(MAPS_DIR, file[:-4] + '.heights'), 'wb') as handle:      # to colour it again, without the game
        handle.write(zlib.compress(struct.pack(f'<{len(flat)}f', *flat) + bytes(wet for line in ocean for wet in line)
                                   + bytes(code for line in surfaces for code in line)))
    with open(os.path.join(MAPS_DIR, file[:-4] + '.json'), 'w') as handle:
        json.dump({'body': name, 'radius': radius, 'file': file, 'min': min(flat), 'max': max(flat),
                   'ocean': has_ocean, 'size': [relief.WIDTH, relief.HEIGHT]}, handle)
    print(f'map of {name}: {file}', flush=True)


def wanted_maps(bodies, current):
    """The body flown and its moons, the body first."""
    if current not in bodies:
        return []
    moons = [name for name, body in bodies.items() if body['parent'] == current]
    return [current, *moons]


def keep_krpc(client):
    import krpc
    while True:
        try:
            connection = krpc.connect(name='mcc-data', address=KRPC_HOST)
        except Exception as error:          # KSP not running
            if status['krpc']:
                print('kRPC lost:', error, flush=True)
            status['krpc'] = False
            publish_status(client)
            time.sleep(KRPC_RETRY_S)
            continue
        status['krpc'] = True
        publish_status(client)
        print('connected to kRPC', flush=True)
        try:
            serve_krpc(client, connection)
        except Exception as error:          # scene change (the VAB has no bodies), KSP quit
            print('kRPC:', repr(error)[:200], flush=True)
        finally:
            status['mapping'] = None
            connection.close()
        time.sleep(KRPC_RETRY_S)


def serve_krpc(client, connection):
    space_center = connection.space_center
    publish(client, 'mcc/maps', list_maps(), retain=True)
    bodies_read_at = 0.0
    bodies = {}
    while True:
        if time.monotonic() - bodies_read_at > BODIES_EVERY_S:
            reading = read_bodies(space_center)
            bodies = reading['bodies']
            for name, info in list_maps().items():          # the highest terrain, measured by the map
                if name in bodies and info.get('radius') == bodies[name]['radius']:
                    bodies[name]['highest'] = info['max']
            publish(client, 'mcc/bodies', reading, retain=True)
            bodies_read_at = time.monotonic()
        with lock:
            current = recorder.latest['tlm/orbit'].get('body')
        maps = list_maps()
        missing = [name for name in wanted_maps(bodies, current)
                   if map_file(name, bodies[name]['radius']) not in {info['file'] for info in maps.values()}]
        if missing:
            make_map(client, space_center.bodies[missing[0]], missing[0])
            status['mapping'] = None
            publish_status(client)
            publish(client, 'mcc/maps', list_maps(), retain=True)
            bodies_read_at = 0.0                            # again, with the new map's highest terrain
            continue
        time.sleep(2.0)


def main():
    load_flight()
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id='mcc-data')
    client.will_set('mcc/data/status', json.dumps({'online': False, 'krpc': False, 'mapping': None}), qos=1, retain=True)

    def on_connect(client, userdata, flags, reason, properties=None):
        client.subscribe(SUBSCRIPTIONS)
        publish_status(client)
        print('connected to the bus', flush=True)

    client.on_connect, client.on_message = on_connect, on_message
    while True:
        try:
            client.connect(MQTT_HOST, MQTT_PORT, keepalive=10)
            break
        except OSError as error:
            print('broker not ready:', error, flush=True)
            time.sleep(1)
    client.loop_start()
    threading.Thread(target=keep_krpc, args=(client,), daemon=True).start()
    keep_sampling(client)


if __name__ == '__main__':
    main()
