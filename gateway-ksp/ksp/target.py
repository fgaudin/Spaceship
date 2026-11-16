"""Rendezvous and docking: the state relative to the target, target selection, control point and undocking.

Reference frames used here (kRPC): the vessel frame is x right, y forward, z down, and follows the part the vessel
is controlled from; a docking port's frame has y pointing out of the port.
"""
import math
import time
from dataclasses import dataclass

NOT_A_TARGET = ('debris', 'flag')
OUT_OF_THE_PORT = (0.0, 1.0, 0.0)
INTO_THE_PORT = (0.0, -1.0, 0.0)
PORT_UP = (0.0, 0.0, -1.0)              # the port's own "up": opposite its z axis, by the same convention as a vessel


def subtract(a, b):
    return [x - y for x, y in zip(a, b)]


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def length(vector):
    return math.sqrt(dot(vector, vector))


def degrees_between(cosine):
    return round(math.degrees(math.acos(max(-1.0, min(1.0, cosine)))), 2)


@dataclass
class SlowFacts:
    """What the target telemetry needs and that hardly ever changes. Each is a kRPC call, and a call holds the game
    for about 0.1 ms, so they are read again only on the slow cycle or when the target changes."""
    target_vessel: object
    target_port: object
    target_name: str
    own_port: object            # the docking port the vessel is controlled from, or None
    inertial_frame: object      # does not turn with the planet or the vessel
    vessel_frame: object
    port_frame: object          # of the target port, or None

    @classmethod
    def read(cls, vessel, target_vessel, target_port):
        return cls(target_vessel, target_port,
                   target_name=target_vessel.name if target_vessel is not None else None,
                   own_port=vessel.parts.controlling.docking_port,
                   inertial_frame=vessel.orbit.body.non_rotating_reference_frame,
                   vessel_frame=vessel.reference_frame,
                   port_frame=target_port.reference_frame if target_port is not None else None)

    def are_about(self, target_vessel, target_port):
        return self.target_vessel == target_vessel and self.target_port == target_port


def target_telemetry(link, refresh_slow_facts):
    """tlm/target: range and closing speed to the target vessel and, when a docking port is targeted, the docking
    geometry. Also remembers on the link whether a target is set (it is then published more often)."""
    space_center, vessel = link.space_center, link.vessel
    target_port = space_center.target_docking_port
    target_vessel = space_center.target_vessel or (target_port.part.vessel if target_port is not None else None)
    facts = link.target_facts
    if refresh_slow_facts or facts is None or not facts.are_about(target_vessel, target_port):
        facts = link.target_facts = SlowFacts.read(vessel, target_vessel, target_port)
    link.has_target = target_vessel is not None
    state = {'set': link.has_target, 'ctrl_port': facts.own_port is not None, 'docked': link.parts.docked()}
    if target_vessel is None:
        return state

    to_target = subtract(target_vessel.position(facts.inertial_frame), vessel.position(facts.inertial_frame))
    relative_velocity = subtract(vessel.velocity(facts.inertial_frame), target_vessel.velocity(facts.inertial_frame))
    target_range = length(to_target)
    line_of_sight = [component / target_range for component in to_target] if target_range > 0 else [0, 0, 0]
    closing_speed = dot(relative_velocity, line_of_sight)
    across_line_of_sight = subtract(relative_velocity, [closing_speed * component for component in line_of_sight])
    line_of_sight_rate = None       # degrees per minute; meaningless at contact
    if target_range > 1:
        line_of_sight_rate = round(math.degrees(length(across_line_of_sight) / target_range) * 60, 4)
    state.update({'name': facts.target_name, 'range': round(target_range, 2), 'closing': round(closing_speed, 3),
                  'los_rate': line_of_sight_rate, 'rel_v': round(length(relative_velocity), 3)})
    if target_port is not None:
        state['port'] = docking_geometry(space_center, vessel, facts)
    return state


def docking_geometry(space_center, vessel, facts):
    """The "port" block of tlm/target, twice over.

    In the target port's frame (for a display centred on the port): axial distance, lateral offsets x and z, their
    speeds, and the angle between our axis and the port's.

    In the pilot's own axes (so that no roll is needed to read them): where the target port is (right, up, fwd), how
    fast those offsets change, and how to turn to face the port squarely (yaw, pitch) with the roll of its "up".
    """
    own_port, target_port = facts.own_port, facts.target_port
    port_frame, vessel_frame = facts.port_frame, facts.vessel_frame
    own_reference = own_port or vessel                      # our docking port if we are controlled from it
    our_position = own_reference.position(port_frame)
    our_velocity = vessel.velocity(port_frame)
    our_axis = own_reference.direction(port_frame)
    geometry = {
        'axial': round(our_position[1], 3), 'x': round(our_position[0], 3), 'z': round(our_position[2], 3),
        'v_axial': round(our_velocity[1], 4), 'vx': round(our_velocity[0], 4), 'vz': round(our_velocity[2], 4),
        'angle': degrees_between(-dot(our_axis, OUT_OF_THE_PORT)),      # 0 when facing straight into the port
        'from_port': own_port is not None,
    }

    to_vessel_frame = lambda direction: space_center.transform_direction(direction, port_frame, vessel_frame)
    own_port_position = own_port.position(vessel_frame) if own_port else (0.0, 0.0, 0.0)
    port_right, port_forward, port_down = subtract(target_port.position(vessel_frame), own_port_position)
    aim_right, aim_forward, aim_down = to_vessel_frame(INTO_THE_PORT)       # the way to point
    up_right, _, up_down = to_vessel_frame(PORT_UP)
    drift_right, _, drift_down = to_vessel_frame(our_velocity)              # our own motion, in our axes
    angle = lambda sideways, ahead: round(math.degrees(math.atan2(sideways, ahead)), 2)
    geometry.update({
        'right': round(port_right, 3), 'up': round(-port_down, 3), 'fwd': round(port_forward, 3),
        # we drift right → the port appears to move left: the offsets change by the opposite of our motion
        'v_right': round(-drift_right, 4), 'v_up': round(drift_down, 4),
        'yaw': angle(aim_right, aim_forward), 'pitch': angle(-aim_down, aim_forward),
        'roll': angle(up_right, -up_down),
    })
    return geometry


def select_target(link, request):
    """cmd/target: {'step': ±1} next / previous vessel around the same body, nearest first; {'port': 1} next free
    docking port of the target, then the vessel itself again; {'clear': true}."""
    space_center, vessel = link.space_center, link.vessel
    if request.get('clear'):
        space_center.clear_target()
        return
    target_port = space_center.target_docking_port
    target_vessel = space_center.target_vessel or (target_port.part.vessel if target_port is not None else None)
    if 'port' in request:
        if target_vessel is not None:
            _target_next_port(space_center, target_vessel, target_port)
        return
    inertial_frame = vessel.orbit.body.non_rotating_reference_frame
    our_position = vessel.position(inertial_frame)
    candidates = [other for other in space_center.vessels
                  if other != vessel and other.orbit.body == vessel.orbit.body and other.type.name not in NOT_A_TARGET]
    if not candidates:
        return
    candidates.sort(key=lambda other: math.dist(our_position, other.position(inertial_frame)))
    step = 1 if int(request.get('step', 1)) >= 0 else -1
    if target_vessel in candidates:
        index = (candidates.index(target_vessel) + step) % len(candidates)
    else:
        index = 0 if step > 0 else -1       # nothing targeted yet: the nearest, or the farthest going backwards
    space_center.target_vessel = candidates[index]


def _target_next_port(space_center, target_vessel, target_port):
    try:
        free_ports = [port for port in target_vessel.parts.docking_ports if port.state.name == 'ready']
    except Exception:
        free_ports = []                     # the target is beyond physics range: its parts are not loaded
    next_index = free_ports.index(target_port) + 1 if target_port in free_ports else 0
    if next_index < len(free_ports):
        space_center.target_docking_port = free_ports[next_index]
    else:
        space_center.target_vessel = target_vessel


def control_from_port(link, from_port):
    """cmd/control_from: control from the vessel's first free docking port, or from where it was controlled when
    the gateway bound it."""
    vessel = link.vessel
    if not from_port:
        vessel.parts.controlling = link.default_control_part
        link.target_facts = None        # the control point is one of them
        return
    free_ports = [port for port in vessel.parts.docking_ports if port.state.name == 'ready']
    if free_ports:
        vessel.parts.controlling = free_ports[0].part
    link.target_facts = None            # the control point is one of them


def undock(link):
    """cmd/undock: the port the vessel is controlled from if it is docked, else the first docked port."""
    docked_ports = link.parts.ports_docked_to_a_port()
    if not docked_ports:
        return
    controlling_part = link.vessel.parts.controlling
    controlled_from = [port for port in docked_ports if port.part == controlling_part]
    (controlled_from or docked_ports)[0].undock()
    time.sleep(0.2)                 # let KSP split the vessel
    link.unbind()                   # the part list has changed: rebuild every stream
