"""What the cockpit logic publishes: messages for the bus, and the payloads of panel outputs."""
from dataclasses import dataclass


@dataclass
class Message:
    topic: str
    payload: dict
    retain: bool = False
    qos: int = 0


class PanelOutputs:
    """Collects the wanted state of one panel's outputs into `wanted` (topic → payload).
    The payload shapes are the protocol's (protocol/topics.md)."""

    def __init__(self, wanted, panel):
        self.wanted = wanted
        self.prefix = f'panel/{panel}/out/'

    def raw(self, name, payload):
        self.wanted[self.prefix + name] = payload

    def lamp(self, name, on, blink=False):
        """A lamp or LED. A lamp that is off never blinks."""
        self.raw(name, {'on': bool(on), 'blink': bool(on and blink)})

    def text(self, name, text, blink=False):
        """A 7-segment or alphanumeric display."""
        self.raw(name, {'text': text, 'blank': False, 'blink': bool(blink)})

    def blank(self, name):
        """A display with no power."""
        self.raw(name, {'text': '', 'blank': True, 'blink': False})

    def bar(self, name, fraction):
        """An LED bar graph, 0 to 1."""
        self.raw(name, {'v': round(max(0.0, min(1.0, fraction or 0.0)), 2)})

    def all_dark(self, lamps=(), displays=(), bars=()):
        """Main bus off."""
        for name in lamps:
            self.lamp(name, False)
        for name in displays:
            self.blank(name)
        for name in bars:
            self.bar(name, 0.0)

    def all_lit(self, lamps=(), displays=(), bars=()):
        """Lamp test: every lamp steady, every segment on."""
        for name in lamps:
            self.lamp(name, True)
        for name in displays:
            self.text(name, '8.8.8.8.8.8.8.')
        for name in bars:
            self.bar(name, 1.0)


def switch_lamp(game_state, switch_on):
    """(on, blink) for the indicator of a switch: lit when the game or the switch says on, blinking when they
    disagree. Dark when the game does not report that state."""
    if game_state is None:
        return False, False
    return bool(game_state) or switch_on, bool(game_state) != switch_on
