"""The vehicle's figures shown on several panels: local gravity, stage Δv, TWR, hover time, speeds, time to impact."""
import math

from . import settings as S


def local_gravity(cockpit):
    """m/s² at the vessel's altitude, or None for a body the cockpit does not know."""
    body = S.BODIES.get(cockpit.orbit.get('body'))
    altitude = cockpit.flight.get('alt')
    if body is None or altitude is None:
        return None
    gravitational_parameter, radius = body
    return gravitational_parameter / (radius + altitude) ** 2


def stage_delta_v(cockpit):
    """Δv left in the current stage, or before ignition in the next one: the rocket equation on its propellant
    (course TM-4). None when unknown."""
    stage = cockpit.resources.get('stage', {})
    units = sum(stage.get(name, {}).get('amount', 0.0) for name in ('LiquidFuel', 'Oxidizer', 'SolidFuel'))
    propellant_mass = S.PROPELLANT_KG_PER_UNIT * units
    mass, specific_impulse = cockpit.vessel.get('mass'), cockpit.propulsion()[1]
    if not (mass and specific_impulse) or mass <= propellant_mass:
        return None
    return specific_impulse * S.STANDARD_GRAVITY * math.log(mass / (mass - propellant_mass))


def thrust_to_weight(cockpit):
    """Available thrust over weight in the local gravity. None when the body or the altitude is unknown."""
    gravity, mass = local_gravity(cockpit), cockpit.vessel.get('mass')
    thrust = cockpit.propulsion()[0]
    if not (gravity and mass) or thrust is None:
        return None
    return thrust / (mass * gravity)


def hover_time(cockpit):
    """Seconds the stage can hold the vessel still against gravity: hovering spends Δv at the rate of the local
    gravity, so it is the stage's Δv over g. None when unknown, or when the engines cannot lift the vessel."""
    delta_v, gravity, ratio = stage_delta_v(cockpit), local_gravity(cockpit), thrust_to_weight(cockpit)
    if delta_v is None or not gravity or ratio is None or ratio < 1:
        return None
    return delta_v / gravity


def speeds_in_reference(cockpit):
    """(horizontal, vertical, total) m/s against what the SPEED REF knob selects: the orbit, or the surface (also for
    TGT: a speed against a target says nothing of the ground below). Turning with the planet only adds sideways
    speed, so the vertical speed is the same in both. Each is None when unknown."""
    flight = cockpit.flight
    vertical = flight.get('vs')
    if cockpit.selected('speed_ref', S.SPEED_MODES) != 'orbit':
        return flight.get('hs'), vertical, flight.get('speed')
    total = flight.get('v_orb')
    if total is None or vertical is None:
        return None, vertical, total
    return math.sqrt(max(total ** 2 - vertical ** 2, 0.0)), vertical, total


def time_to_impact(cockpit):
    """Seconds to the ground at the present sink rate (gravity and braking ignored). None when not sinking, or on an
    orbit that stays above the surface."""
    radar, vertical, periapsis = cockpit.flight.get('radar'), cockpit.flight.get('vs'), cockpit.orbit.get('peri')
    if radar is None or vertical is None or vertical >= -S.SINKING_ABOVE_M_S or (periapsis or 0) > 0:
        return None
    return radar / -vertical
