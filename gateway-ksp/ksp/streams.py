"""kRPC streams. A stream is computed by KSP and pushed to the gateway, which then reads it locally at no cost.

The cost is inside the game: KSP computes every stream on every game update unless the stream has a rate, about
0.05 to 0.5 ms each (measured on a 16-part vessel: 63 streams took 4.4 ms per update unlimited and 0.2 ms at
2 Hz). So every stream here has the lowest rate its use allows."""

UNLIMITED = 0           # computed on every game update: only for what the burn computer counts with
FAST_HZ = 20            # published on every telemetry cycle (10 Hz)
SLOW_HZ = 4             # published on the slow cycle (2 Hz), or hardly ever changing


class StreamGroup:
    """A set of streams that live and die together (all those of a vessel, or of its parts in one stage)."""

    def __init__(self, connection):
        self.connection = connection
        self.streams = []

    def attribute(self, kerbal_object, attribute_name, rate_hz):
        """A stream of `kerbal_object.attribute_name`; call the result to read the latest value."""
        return self._keep(self.connection.add_stream(getattr, kerbal_object, attribute_name), rate_hz)

    def call(self, rate_hz, method, *arguments):
        """A stream of `method(*arguments)`."""
        return self._keep(self.connection.add_stream(method, *arguments), rate_hz)

    def _keep(self, stream, rate_hz):
        if rate_hz != UNLIMITED:
            stream.rate = rate_hz
        self.streams.append(stream)
        return stream

    def close(self):
        for stream in self.streams:
            try:
                stream.remove()
            except Exception:       # the object behind it is already gone (staged away, scene changed)
                pass
        self.streams = []


def read_or(default, stream):
    """The stream's value, or `default` when the part behind it no longer exists."""
    try:
        return stream()
    except Exception:
        return default
