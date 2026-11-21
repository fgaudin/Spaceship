"""Simpit messages ↔ the bus's topics (protocol/topics.md), with no serial port and no MQTT: pure, unit-testable.

What Simpit gives is a subset of what gateway-ksp (kRPC) publishes: altitude, speeds, apsides and their times, orbit
elements, attitude, flight status, action groups, stage Δv, resources, the body and the vessel's name. No UT or MET,
no target geometry for docking, no maneuver nodes, no parts (engines, parachutes, heat by part): those panels stay
dark on this plant. Commands: throttle, stage, abort, SAS / RCS / gear / lights / brakes, SAS mode, rotation,
translation, custom action groups, time warp up / down / stop.
"""
import math

from . import protocol as P

# the channels the gateway registers after the handshake
CHANNELS = (P.ALTITUDE, P.VELOCITY, P.APSIDES, P.APSIDES_TIME, P.ORBIT, P.ROTATION_DATA, P.FLIGHT_STATUS,
            P.ACTION_STATUS, P.DELTAV, P.SOI, P.VESSEL_NAME, P.SCENE_CHANGE, P.LF, P.OX, P.MONO, P.ELECTRIC,
            P.LF_STAGE, P.OX_STAGE, P.SAS_MODE_INFO)
RESOURCES = {P.LF: ('total', 'LiquidFuel'), P.OX: ('total', 'Oxidizer'), P.MONO: ('total', 'MonoPropellant'),
             P.ELECTRIC: ('total', 'ElectricCharge'), P.LF_STAGE: ('stage', 'LiquidFuel'),
             P.OX_STAGE: ('stage', 'Oxidizer')}
SWITCHES = {'cmd/sas': P.SAS_ACTION, 'cmd/rcs': P.RCS_ACTION, 'cmd/gear': P.GEAR_ACTION,
            'cmd/lights': P.LIGHT_ACTION, 'cmd/brakes': P.BRAKES_ACTION}
SAS_MODE_NAMES = {number: name for name, number in P.AUTOPILOT_MODES.items()}


class Bridge:
    """The last value of each topic, built from the messages as they come; `topics()` gives what to publish."""
    def __init__(self):
        self.flight, self.orbit, self.vessel, self.attitude = {}, {}, {}, {}
        self.resources = {'stage': {}, 'total': {}}
        self.in_flight = None           # SCENE_CHANGE: True in the flight scene, False out of it, None not told yet
        self.changed = set()

    # ---------- from the game ----------
    def on_message(self, message_type, payload):
        """One Simpit message; returns the topics it changed."""
        value = P.decode(message_type, payload)
        if value is None:
            return set()
        before = set(self.changed)
        handler = HANDLERS.get(message_type)
        if handler:
            handler(self, message_type, value)
        return self.changed - before

    def _altitude(self, _, value):
        self.flight.update(alt=value['sealevel'], radar=value['surface'])
        self.changed.add('tlm/flight')

    def _velocity(self, _, value):
        surface, vertical = value['surface'], value['vertical']
        self.flight.update(v_orb=value['orbital'], speed=surface, vs=vertical,
                           hs=math.sqrt(max(surface ** 2 - vertical ** 2, 0.0)))
        self.changed.add('tlm/flight')

    def _apsides(self, _, value):
        self.orbit.update(apo=value['apoapsis'], peri=value['periapsis'])
        self.changed.add('tlm/orbit')

    def _apsides_time(self, _, value):
        self.orbit.update(t_apo=value['apoapsis'], t_peri=value['periapsis'])
        self.changed.add('tlm/orbit')

    def _orbit(self, _, value):
        # passed on as Simpit sends them; the units of the angles (degrees, as tlm/orbit wants) are not checked yet
        self.orbit.update(e=value['eccentricity'], a=value['semi_major_axis'], i=value['inclination'],
                          lan=value['lan'], argp=value['arg_periapsis'], nu=value['true_anomaly'],
                          period=value['period'])
        self.changed.add('tlm/orbit')

    def _rotation(self, _, value):
        self.attitude.update(pitch=value['pitch'], heading=value['heading'], roll=value['roll'],
                             prograde={'pitch': value['surface_pitch'], 'heading': value['surface_heading']})
        self.changed.add('tlm/attitude')

    def _flight_status(self, _, value):
        self.vessel.update(situation=P.SITUATIONS.get(value['situation']), stage=value['stage'], crew=value['crew'],
                           comm=value['comm_percent'] > 0)
        self.in_flight = bool(value['flags'] & P.FLIGHT_IN_FLIGHT)
        self.changed.update({'tlm/vessel', 'gateway/status'})

    def _action_status(self, _, bits):
        self.vessel.update(sas=bool(bits & P.SAS_ACTION), rcs=bool(bits & P.RCS_ACTION),
                           gear=bool(bits & P.GEAR_ACTION), lights=bool(bits & P.LIGHT_ACTION),
                           brakes=bool(bits & P.BRAKES_ACTION))
        self.changed.add('tlm/vessel')

    def _sas_mode(self, _, mode):
        self.vessel['sas_mode'] = SAS_MODE_NAMES.get(mode)
        self.changed.add('tlm/vessel')

    def _deltav(self, _, value):
        self.vessel['stage_dv'] = value['stage']
        self.changed.add('tlm/vessel')

    def _soi(self, _, name):
        self.orbit['body'] = name
        self.changed.add('tlm/orbit')

    def _vessel_name(self, _, name):
        self.vessel['name'] = name
        self.changed.update({'tlm/vessel', 'gateway/status'})

    def _scene(self, _, scene):
        self.in_flight = scene == 0                         # 0: a flight is ready, 1: leaving the flight scene
        self.changed.add('gateway/status')

    def _resource(self, message_type, value):
        group, name = RESOURCES[message_type]
        self.resources[group][name] = {'amount': value['available'], 'max': value['total']}
        self.changed.add('tlm/resources')

    def topics(self, which=None):
        """{topic: payload} for `which` (default: what changed since the last call), and forget the changes."""
        which = self.changed if which is None else which
        out = {}
        for topic in which:
            if topic == 'tlm/flight':
                out[topic] = dict(self.flight)
            elif topic == 'tlm/orbit':
                out[topic] = dict(self.orbit)
            elif topic == 'tlm/vessel':
                out[topic] = dict(self.vessel)
            elif topic == 'tlm/attitude':
                out[topic] = dict(self.attitude)
            elif topic == 'tlm/resources':
                out[topic] = {'stage': dict(self.resources['stage']), 'total': dict(self.resources['total'])}
            elif topic == 'gateway/status':
                out[topic] = self.status(True)
        self.changed = set()
        return out

    def status(self, connected):
        return {'connected': connected, 'plant': 'simpit',
                'scene': 'flight' if self.in_flight else ('space_center' if self.in_flight is False else None),
                'vessel': self.vessel.get('name'), 'paused': False}


HANDLERS = {
    P.ALTITUDE: Bridge._altitude, P.VELOCITY: Bridge._velocity, P.APSIDES: Bridge._apsides,
    P.APSIDES_TIME: Bridge._apsides_time, P.ORBIT: Bridge._orbit, P.ROTATION_DATA: Bridge._rotation,
    P.FLIGHT_STATUS: Bridge._flight_status, P.ACTION_STATUS: Bridge._action_status, P.SAS_MODE_INFO: Bridge._sas_mode,
    P.DELTAV: Bridge._deltav, P.SOI: Bridge._soi, P.VESSEL_NAME: Bridge._vessel_name, P.SCENE_CHANGE: Bridge._scene,
    **{channel: Bridge._resource for channel in RESOURCES},
}


# ---------- to the game ----------
def command(topic, request):
    """The packets (bytes) for one cmd/* message; [] for a command Simpit cannot do."""
    if topic == 'cmd/throttle':
        return [P.throttle(request.get('v', 0.0))]
    if topic == 'cmd/stage':
        return [P.action(P.STAGE_ACTION, True)]
    if topic == 'cmd/abort':
        return [P.action(P.ABORT_ACTION, True)]
    if topic in SWITCHES:
        return [P.action(SWITCHES[topic], bool(request.get('on')))]
    if topic == 'cmd/sas_mode' and request.get('mode') in P.AUTOPILOT_MODES:
        return [P.frame(P.SAS_MODE, bytes([P.AUTOPILOT_MODES[request['mode']]]))]
    if topic == 'cmd/rotate':
        return [P.rotation(request.get('pitch', 0.0), request.get('roll', 0.0), request.get('yaw', 0.0))]
    if topic == 'cmd/translate':
        # X right, Y up, Z forward, as the library's translation demo maps its stick: not checked in KSP yet
        return [P.translation(request.get('right', 0.0), request.get('up', 0.0), request.get('forward', 0.0))]
    if topic == 'cmd/action_group' and 1 <= int(request.get('n', 0)) <= 10:
        return [P.frame(P.CAG_TOGGLE, bytes([int(request['n'])]))]
    if topic == 'cmd/warp':
        if request.get('stop'):
            return [P.frame(P.TIMEWARP, bytes([P.TIMEWARP_X1]))]
        if request.get('step'):
            return [P.frame(P.TIMEWARP, bytes([P.TIMEWARP_UP if request['step'] > 0 else P.TIMEWARP_DOWN]))]
    return []
