"""Kerbal Simpit's serial protocol, as the bundled Arduino library speaks it (KerbalSimpitRevamped 2.3.1, library
1.3.0: GameData/KerbalSimpit/KerbalSimpitRevamped-Arduino/src). This side plays the device.

A packet is [type, payload..., checksum] (checksum: XOR of the type and every payload byte), COBS-encoded, then a 0
byte. Handshake: the device sends SYNC [0x00 SYN, version, NUL]; the plugin answers SYNC [0x01 SYNACK, ...]; the
device sends SYNC [0x02 ACK, version, NUL]. The device then registers the channels it wants (REGISTER, one byte); the
plugin sends those messages as the game changes. Payloads are packed little-endian C structs.
"""
import struct

LIBRARY_VERSION = b'1.3.0'          # KERBALSIMPIT_VERSION of the bundled library: what the plugin checks

# common
SYNC, ECHO_REQ, ECHO_RESP = 0, 1, 2
SYN, SYNACK, ACK = 0x00, 0x01, 0x02

# from the game (channels a device registers)
SCENE_CHANGE = 3
ALTITUDE, APSIDES = 8, 9
LF, LF_STAGE, OX, OX_STAGE, SF, SF_STAGE, MONO, ELECTRIC = 10, 11, 12, 13, 14, 15, 16, 17
VELOCITY, APSIDES_TIME, TARGET_INFO, SOI = 22, 24, 25, 26
ACTION_STATUS, DELTAV, ORBIT, FLIGHT_STATUS, ROTATION_DATA, VESSEL_NAME = 37, 38, 36, 43, 45, 46
SAS_MODE_INFO, VESSEL_CHANGE = 35, 51

# to the game
CLOSE_SERIAL, REGISTER, DEREGISTER, REQUEST = 7, 8, 9, 29
CAG_TOGGLE, AG_ACTIVATE, AG_DEACTIVATE = 12, 13, 14
ROTATION, TRANSLATION, THROTTLE, SAS_MODE, TIMEWARP, CUSTOM_LOG, NAVBALL_MODE = 16, 17, 19, 20, 24, 25, 28

# ACTION_STATUS bits, and the action groups AG_ACTIVATE / AG_DEACTIVATE take
STAGE_ACTION, GEAR_ACTION, LIGHT_ACTION, RCS_ACTION, SAS_ACTION, BRAKES_ACTION, ABORT_ACTION = 1, 2, 4, 8, 16, 32, 64

AUTOPILOT_MODES = {'stability': 0, 'prograde': 1, 'retrograde': 2, 'normal': 3, 'antinormal': 4, 'radial': 5,
                   'antiradial': 6, 'target': 7, 'antitarget': 8, 'maneuver': 9}
TIMEWARP_X1, TIMEWARP_UP, TIMEWARP_DOWN = 0, 12, 13

# Vessel.Situations of the KSP API (FLIGHT_STATUS), in the names tlm/vessel uses (kRPC's)
SITUATIONS = {1: 'landed', 2: 'splashed', 4: 'pre_launch', 8: 'flying', 16: 'sub_orbital', 32: 'orbiting',
              64: 'escaping', 128: 'docked'}
FLIGHT_IN_FLIGHT, FLIGHT_HAS_TARGET = 1, 64

AXIS_FULL = 32767                   # INT16_MAX: the library's full deflection

# payloads from the game: struct layout and field names (PayloadStructs.h)
PAYLOADS = {
    ALTITUDE: ('<2f', ('sealevel', 'surface')),
    APSIDES: ('<2f', ('periapsis', 'apoapsis')),
    APSIDES_TIME: ('<2i', ('periapsis', 'apoapsis')),
    VELOCITY: ('<3f', ('orbital', 'surface', 'vertical')),
    ORBIT: ('<8f', ('eccentricity', 'semi_major_axis', 'inclination', 'lan', 'arg_periapsis', 'true_anomaly',
                    'mean_anomaly', 'period')),
    ROTATION_DATA: ('<7f', ('heading', 'pitch', 'roll', 'orbital_heading', 'orbital_pitch', 'surface_heading',
                            'surface_pitch')),
    FLIGHT_STATUS: ('<8B', ('flags', 'situation', 'warp_index', 'crew_capacity', 'crew', 'comm_percent', 'stage',
                            'vessel_type')),
    DELTAV: ('<2f', ('stage', 'total')),
    TARGET_INFO: ('<6f', ('distance', 'velocity', 'heading', 'pitch', 'velocity_heading', 'velocity_pitch')),
    **{channel: ('<2f', ('total', 'available')) for channel in (LF, LF_STAGE, OX, OX_STAGE, SF, SF_STAGE, MONO,
                                                                 ELECTRIC)},
}
TEXT_PAYLOADS = (SOI, VESSEL_NAME)
BYTE_PAYLOADS = (SCENE_CHANGE, ACTION_STATUS, SAS_MODE_INFO, VESSEL_CHANGE)


class BadPacket(ValueError):
    pass


# ---------- COBS ----------
def cobs_encode(data):
    """Consistent Overhead Byte Stuffing, as the library's cobsEncode (no trailing 0)."""
    out, block = bytearray(), bytearray()
    for byte in data:
        if byte == 0:
            out.append(len(block) + 1)
            out += block
            block = bytearray()
        else:
            block.append(byte)
            if len(block) == 254:
                out.append(255)
                out += block
                block = bytearray()
    out.append(len(block) + 1)
    out += block
    return bytes(out)


def cobs_decode(data):
    """The inverse; `data` without its trailing 0."""
    out, index = bytearray(), 0
    while index < len(data):
        code = data[index]
        if code == 0:
            raise BadPacket('zero inside a COBS frame')
        block = data[index + 1:index + code]
        if len(block) != code - 1:
            raise BadPacket('COBS block past the end')
        out += block
        index += code
        if code != 255 and index < len(data):
            out.append(0)
    return bytes(out)


# ---------- packets ----------
def frame(message_type, payload=b''):
    """The bytes on the wire for one packet, its 0 delimiter included."""
    checksum = message_type
    for byte in payload:
        checksum ^= byte
    return cobs_encode(bytes([message_type]) + bytes(payload) + bytes([checksum])) + b'\x00'


def unframe(encoded):
    """(type, payload) from one packet's bytes without its 0 delimiter; BadPacket when it does not check out."""
    decoded = cobs_decode(encoded)
    if len(decoded) < 2:
        raise BadPacket('packet too short')
    checksum = 0
    for byte in decoded[:-1]:
        checksum ^= byte
    if checksum != decoded[-1]:
        raise BadPacket('bad checksum')
    return decoded[0], decoded[1:-1]


class Deframer:
    """Bytes in as they come from the serial port; whole packets out."""
    def __init__(self):
        self.buffer = bytearray()
        self.dropped = 0

    def feed(self, data):
        packets = []
        for byte in data:
            if byte != 0:
                self.buffer.append(byte)
                continue
            if self.buffer:
                try:
                    packets.append(unframe(bytes(self.buffer)))
                except BadPacket:
                    self.dropped += 1
            self.buffer.clear()
        return packets


# ---------- handshake and channels ----------
def syn():
    return frame(SYNC, bytes([SYN]) + LIBRARY_VERSION + b'\x00')


def ack():
    return frame(SYNC, bytes([ACK]) + LIBRARY_VERSION + b'\x00')


def is_synack(message_type, payload):
    return message_type == SYNC and payload[:1] == bytes([SYNACK])


def register(channel):
    return frame(REGISTER, bytes([channel]))


# ---------- payloads ----------
def decode(message_type, payload):
    """A message from the game as a dict (or str, or int); None for a type this does not know or a wrong size."""
    if message_type in PAYLOADS:
        layout, names = PAYLOADS[message_type]
        if len(payload) != struct.calcsize(layout):
            return None
        return dict(zip(names, struct.unpack(layout, payload)))
    if message_type in TEXT_PAYLOADS:
        return payload.split(b'\x00', 1)[0].decode('ascii', 'replace')
    if message_type in BYTE_PAYLOADS:
        return payload[0] if payload else None
    return None


def axis(value):
    """−1..1 → the library's int16 range."""
    return int(round(max(-1.0, min(1.0, float(value))) * AXIS_FULL))


def throttle(value):
    return frame(THROTTLE, struct.pack('<h', int(round(max(0.0, min(1.0, float(value))) * AXIS_FULL))))


def rotation(pitch, roll, yaw):
    return frame(ROTATION, struct.pack('<3hB', axis(pitch), axis(roll), axis(yaw), 7))       # mask: all three


def translation(x, y, z):
    return frame(TRANSLATION, struct.pack('<3hB', axis(x), axis(y), axis(z), 7))


def action(bits, on):
    return frame(AG_ACTIVATE if on else AG_DEACTIVATE, bytes([bits]))
