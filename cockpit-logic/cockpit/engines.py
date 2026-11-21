"""Engine status rosette: nine RGB lamps, one in the centre and a ring of eight, the engines placed by where they sit
across the vessel: an engine on the axis lights the centre, the others the ring lamp nearest their angle (clockwise
from the top, as seen on the panel). Engines that share a lamp show the worst of their states. It replaced a 9 × 9
LED matrix: hard to source, and not pretty.

Colours: g = giving thrust, w = lit but idle (or next to ignite, before any engine is lit): white shows how many
engines the stage has; a = has fuel but gives well under the thrust commanded; r = flamed out, or gone (it was
burning in this stage and is no longer listed); . = no engine there, dark.
"""
import math
from dataclasses import dataclass, field

from .settings import ENGINE_WEAK_BELOW, STANDARD_PRESSURE_PA, THROTTLE_UP_ABOVE

THRUSTING, IDLE, WEAK, DEAD, OFF = 'g', 'w', 'a', 'r', '.'
SAME_PLACE_M = 0.05         # a layout narrower than this is a single engine on the axis
ON_AXIS_SHARE = 0.3         # an engine this close to the axis, as a share of the outermost one's distance: the centre
LAMPS = 9                   # the centre, then the ring of 8 clockwise from the top
WORST_FIRST = (DEAD, WEAK, THRUSTING, IDLE)


@dataclass
class EngineSurvey:
    lamps: dict = field(default_factory=dict)       # lamp index → colour
    engine_lost: bool = False
    colours: list = field(default_factory=list)     # every engine's colour (lamps may share engines: the alarms count these)

    def count(self, colour):
        return self.colours.count(colour)

    def leds(self):
        """The rosette as the protocol wants it: one character per lamp, the centre first."""
        return ''.join(self.lamps.get(index, OFF) for index in range(LAMPS))


class EngineMonitor:
    """Remembers which engines have burned in the current stage, to notice one that disappears."""

    def __init__(self):
        self.flight_and_stage = None                # (vessel name, stage number) the memory belongs to
        self.positions_seen_burning = frozenset()

    def survey(self, engine_telemetry, vessel):
        """`engine_telemetry`: tlm/engines; `vessel`: tlm/vessel."""
        # an engine held shut down because its capsule is not the one flown (docked) is not this capsule's: left out,
        # or it would show as lost once it had burned in the same stage (a red lamp and ENG FAIL in the docked stack)
        engines = [engine for engine in engine_telemetry.get('engines') or [] if not engine.get('held')]
        # The stage the engine list was read in. tlm/vessel has the stage number sooner than tlm/engines has the new
        # list: just after staging, the vessel's number with the old list would make the dropped engines look lost.
        stage = engine_telemetry.get('stage', vessel.get('stage'))
        throttle = vessel.get('throttle') or 0.0
        switched_on = [engine for engine in engines if engine.get('on')]
        lit = still_in_use(switched_on)
        # Before ignition nothing is lit: show the engines of the next stage instead.
        shown = lit or [engine for engine in engines if stage is not None and engine.get('stage') == stage - 1]

        if self.flight_and_stage != (vessel.get('name'), stage):
            self.flight_and_stage, self.positions_seen_burning = (vessel.get('name'), stage), frozenset()
        lit_positions = frozenset(position_of(engine) for engine in lit)
        spent_positions = frozenset(position_of(engine) for engine in switched_on) - lit_positions
        self.positions_seen_burning = (self.positions_seen_burning | lit_positions) - spent_positions
        lost_positions = self.positions_seen_burning - lit_positions if lit else frozenset()

        points = [(position_of(engine), colour_of(engine, throttle)) for engine in shown]
        points += [(position, DEAD) for position in lost_positions]
        return EngineSurvey(lay_out(points), bool(lost_positions), [colour for _, colour in points])


def still_in_use(lit_engines):
    """The lit engines, less the spent ones: an engine out of fuel that is still attached while engines ignited in
    a later stage burn (KSP numbers stages downwards). It did its job; it is not a failure to stage away."""
    burning_stages = [engine.get('stage', 0) for engine in lit_engines if engine.get('fuel', True)]
    if not burning_stages:
        return lit_engines                          # everything is out of fuel: flameout, the cue to stage
    latest_stage = min(burning_stages)
    return [engine for engine in lit_engines
            if engine.get('fuel', True) or engine.get('stage', 0) <= latest_stage]


def position_of(engine):
    """Where the engine sits across the vessel's axis, rounded so that telemetry noise does not move it."""
    return round(engine['x'], 1), round(engine['z'], 1)


def colour_of(engine, throttle):
    if not engine.get('on'):
        return IDLE
    if not engine.get('fuel', True):
        return DEAD
    thrust, full_thrust = engine.get('thrust', 0), engine.get('max', 0)
    if throttle > THROTTLE_UP_ABOVE and full_thrust > 0 and thrust < ENGINE_WEAK_BELOW * full_thrust * throttle:
        return WEAK
    return THRUSTING if thrust > 0 else IDLE


def lamp_of(x, z, widest):
    """The rosette lamp for an engine at (x right, z down) across the vessel: 0 on the axis, else 1..8 clockwise from
    the top by its angle."""
    distance = math.hypot(x, z)
    if widest <= SAME_PLACE_M or distance <= ON_AXIS_SHARE * widest:
        return 0
    angle = math.degrees(math.atan2(x, -z)) % 360             # 0 at the top, clockwise
    return 1 + round(angle / 45) % 8


def lay_out(points):
    """{lamp: colour} for each ((x, z), colour); a lamp with several engines shows the worst of them."""
    widest = max([math.hypot(x, z) for (x, z), _ in points] or [0.0])
    lamps = {}
    for (x, z), colour in points:
        lamp = lamp_of(x, z, widest)
        shown = lamps.get(lamp)
        if shown is None or WORST_FIRST.index(colour) < WORST_FIRST.index(shown):
            lamps[lamp] = colour
    return lamps


def propulsion(engine_telemetry, vessel, flight):
    """(thrust at full throttle, specific impulse) of what pushes the vessel: the lit engines as KSP reports them, or,
    before any engine is lit, the engines the next staging lights (KSP numbers stages downwards: stage − 1).
    None for either when unknown."""
    thrust, specific_impulse = vessel.get('thrust_avail') or 0.0, vessel.get('isp') or 0.0
    if thrust > 0 and specific_impulse > 0:
        return thrust, specific_impulse
    stage = vessel.get('stage')
    engines = engine_telemetry.get('engines') or []
    if any(engine.get('on') for engine in engines) or stage is None:
        return None, None                           # lit but giving nothing: flamed out, not "before ignition"
    next_engines = [engine for engine in engines if engine.get('stage') == stage - 1 and engine.get('rated')]
    if not next_engines:
        return None, None
    # Specific impulse falls about linearly with the outside pressure between vacuum and one atmosphere.
    atmospheres = min(1.0, (flight.get('p') or 0.0) / STANDARD_PRESSURE_PA)
    total_thrust = sum(engine['rated'] for engine in next_engines)
    # Engines burning together: their propellant flows add up, so the specific impulse is thrust-weighted harmonic.
    propellant_flow = sum(engine['rated'] / (engine['isp_vac'] + (engine['isp_sl'] - engine['isp_vac']) * atmospheres)
                          for engine in next_engines)
    return total_thrust, total_thrust / propellant_flow if propellant_flow > 0 else None
