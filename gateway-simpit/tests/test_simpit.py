"""The Simpit protocol as the bundled Arduino library speaks it, the translation to the bus, and the handshake."""
import os, random, struct, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from simpit import protocol as P  # noqa: E402
from simpit.bridge import CHANNELS, Bridge, command  # noqa: E402
from simpit.link import LinkError, SimpitLink  # noqa: E402


def library_cobs_encode(data):
    """KerbalSimpit::cobsEncode, line for line, to check ours against."""
    out = bytearray([0])
    code_index, code = 0, 1
    for index, byte in enumerate(data):
        remaining = len(data) - index - 1
        if byte:
            out.append(byte)
            code += 1
        if not byte or code == 0xff:
            out[code_index] = code
            code = 1
            code_index = len(out)
            if not byte or remaining:
                out.append(0)
    out[code_index] = code
    return bytes(out)


def test_cobs_matches_the_library_and_round_trips():
    rng = random.Random(1)
    for length in list(range(0, 40)) + [253, 254, 255, 300]:
        data = bytes(rng.choice([0, 0, 1, 7, 255, rng.randrange(256)]) for _ in range(length))
        assert P.cobs_encode(data) == library_cobs_encode(data)
        assert 0 not in P.cobs_encode(data)
        assert P.cobs_decode(P.cobs_encode(data)) == data


def test_a_frame_carries_its_type_payload_and_xor_checksum():
    packet = P.frame(P.REGISTER, bytes([P.ALTITUDE]))
    assert packet.endswith(b'\x00') and packet.count(0) == 1
    assert P.unframe(packet[:-1]) == (P.REGISTER, bytes([P.ALTITUDE]))
    assert P.cobs_decode(packet[:-1]) == bytes([8, 8, 8 ^ 8])            # type, channel, checksum


def test_the_deframer_splits_packets_and_drops_a_bad_one():
    good = P.frame(P.ALTITUDE, struct.pack('<2f', 1000.0, 120.0))
    corrupted = bytearray(P.frame(P.APSIDES, struct.pack('<2f', 1.0, 2.0)))
    corrupted[3] ^= 0x5a
    deframer = P.Deframer()
    stream = good + bytes(corrupted) + good
    packets = deframer.feed(stream[:7]) + deframer.feed(stream[7:])        # split anywhere
    assert [message_type for message_type, _ in packets] == [P.ALTITUDE, P.ALTITUDE] and deframer.dropped == 1


def test_the_handshake_bytes_are_the_librarys():
    # SYN: type 0, then 0x00 and the version with its NUL; the ACK the same with 0x02
    assert P.unframe(P.syn()[:-1]) == (P.SYNC, b'\x00' + b'1.3.0\x00')
    assert P.unframe(P.ack()[:-1]) == (P.SYNC, b'\x02' + b'1.3.0\x00')


class FakePlugin:
    """The game's end of the serial line: answers the SYN, records what the device sends, queues messages."""
    def __init__(self, answers=True):
        self.answers, self.outgoing, self.received = answers, bytearray(), []
        self.deframer = P.Deframer()

    def write(self, data):
        for message_type, payload in self.deframer.feed(data):
            self.received.append((message_type, payload))
            if self.answers and message_type == P.SYNC and payload[:1] == b'\x00':
                self.outgoing += P.frame(P.SYNC, b'\x01' + b'1.3.0\x00')

    def read(self, size):
        data, self.outgoing = bytes(self.outgoing[:size]), self.outgoing[size:]
        return data

    def send(self, message_type, payload):
        self.outgoing += P.frame(message_type, payload)


def test_handshake_then_channels_then_telemetry_to_topics():
    plugin = FakePlugin()
    link = SimpitLink(plugin)
    link.handshake(CHANNELS)
    kinds = [(message_type, payload[:1]) for message_type, payload in plugin.received]
    assert kinds[0] == (P.SYNC, b'\x00') and kinds[1] == (P.SYNC, b'\x02')
    assert [payload[0] for message_type, payload in plugin.received[2:]] == list(CHANNELS)
    plugin.send(P.ALTITUDE, struct.pack('<2f', 12000.0, 11500.0))
    plugin.send(P.VELOCITY, struct.pack('<3f', 2200.0, 500.0, 300.0))
    plugin.send(P.FLIGHT_STATUS, bytes([1, 32, 0, 3, 2, 100, 4, 7]))
    plugin.send(P.ACTION_STATUS, bytes([P.SAS_ACTION | P.GEAR_ACTION]))
    plugin.send(P.SOI, b'Mun\x00')
    bridge = Bridge()
    for message_type, payload in link.read():
        bridge.on_message(message_type, payload)
    topics = bridge.topics()
    assert topics['tlm/flight'] == {'alt': 12000.0, 'radar': 11500.0, 'v_orb': 2200.0, 'speed': 500.0, 'vs': 300.0,
                                    'hs': 400.0}
    assert topics['tlm/vessel']['situation'] == 'orbiting' and topics['tlm/vessel']['stage'] == 4
    assert topics['tlm/vessel']['sas'] and topics['tlm/vessel']['gear'] and not topics['tlm/vessel']['rcs']
    assert topics['tlm/orbit'] == {'body': 'Mun'} and topics['gateway/status']['scene'] == 'flight'
    assert bridge.topics() == {}                                            # nothing new


def test_no_answer_is_a_link_error():
    try:
        SimpitLink(FakePlugin(answers=False)).handshake(CHANNELS, timeout=0.2)
    except LinkError:
        return
    raise AssertionError('no LinkError')


def test_commands_to_packets():
    decode = lambda packets: [P.unframe(packet[:-1]) for packet in packets]
    assert decode(command('cmd/throttle', {'v': 1.0})) == [(P.THROTTLE, struct.pack('<h', 32767))]
    assert decode(command('cmd/stage', {})) == [(P.AG_ACTIVATE, bytes([P.STAGE_ACTION]))]
    assert decode(command('cmd/sas', {'on': False})) == [(P.AG_DEACTIVATE, bytes([P.SAS_ACTION]))]
    assert decode(command('cmd/sas_mode', {'mode': 'retrograde'})) == [(P.SAS_MODE, bytes([2]))]
    assert decode(command('cmd/rotate', {'pitch': -1.0, 'yaw': 0.5, 'roll': 0.0})) == [
        (P.ROTATION, struct.pack('<3hB', -32767, 0, 16384, 7))]
    assert decode(command('cmd/warp', {'step': 1})) == [(P.TIMEWARP, bytes([P.TIMEWARP_UP]))]
    assert command('cmd/node', {'ut': 1, 'dv': [1, 0, 0]}) == []                # not something Simpit does
