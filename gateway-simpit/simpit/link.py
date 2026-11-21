"""The serial link to the Simpit plugin, as a device: handshake, channel registration, packets in and out.

`port` is anything with read(n) → bytes (returning what is there, or b'' after its timeout) and write(bytes): a
pyserial Serial in the gateway, a pty in the tests.
"""
import time

from . import protocol as P

HANDSHAKE_TIMEOUT_S = 2.0


class LinkError(RuntimeError):
    pass


class SimpitLink:
    def __init__(self, port):
        self.port = port
        self.deframer = P.Deframer()
        self.waiting = []               # packets read during the handshake that came after the SYNACK

    def handshake(self, channels, timeout=HANDSHAKE_TIMEOUT_S):
        """SYN, wait for the SYNACK, ACK, then register `channels`. LinkError when the plugin does not answer."""
        self.port.write(P.syn())
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            packets = self.deframer.feed(self.port.read(256))
            for index, (message_type, payload) in enumerate(packets):
                if P.is_synack(message_type, payload):
                    self.port.write(P.ack())
                    for channel in channels:
                        self.port.write(P.register(channel))
                    self.waiting = packets[index + 1:]
                    return
        raise LinkError('no SYNACK from the Simpit plugin (is its serial port this one, and started?)')

    def read(self):
        """The packets that came since the last call: [(type, payload)]."""
        packets, self.waiting = self.waiting, []
        return packets + self.deframer.feed(self.port.read(512))

    def send(self, packets):
        for packet in packets:
            self.port.write(packet)

    def answer_echo(self, message_type, payload):
        """The plugin's echo requests (a keep-alive) get their echo."""
        if message_type == P.ECHO_REQ:
            self.port.write(P.frame(P.ECHO_RESP, payload))
            return True
        return False

    def close(self):
        try:
            self.port.write(P.frame(P.CLOSE_SERIAL, b'\x00'))
        except OSError:
            pass
