"""The link to KSP: one kRPC connection, bound to the active vessel, turned into the tlm/* payloads of the protocol
(protocol/topics.md)."""
import math

import krpc

from .parts_watch import PartsWatch
from .engine_sharing import EngineSharing
from .mission_clock import MissionClock
from .station import StationWatch
from .streams import FAST_HZ, SLOW_HZ, UNLIMITED, StreamGroup
from .target import target_telemetry

# protocol name of an SAS mode → name of the kRPC SASMode member
SAS_MODE_TO_KRPC = {'stability': 'stability_assist', 'prograde': 'prograde', 'retrograde': 'retrograde',
                    'normal': 'normal', 'antinormal': 'anti_normal', 'radial': 'radial', 'antiradial': 'anti_radial',
                    'target': 'target', 'antitarget': 'anti_target', 'maneuver': 'maneuver'}
SAS_MODE_FROM_KRPC = {krpc_name: name for name, krpc_name in SAS_MODE_TO_KRPC.items()}
GROUND_SITUATIONS = ('landed', 'splashed', 'pre_launch')
ACTION_GROUP_COUNT = 10
ORBIT_STREAMS = ('body', 'apoapsis_altitude', 'periapsis_altitude', 'semi_major_axis', 'eccentricity', 'inclination',
                 'period', 'time_to_apoapsis', 'time_to_periapsis', 'time_to_soi_change', 'true_anomaly',
                 'argument_of_periapsis', 'longitude_of_ascending_node')
MOVING_ABOVE_M_S = 1.0          # under this speed the direction of travel means nothing
KELVIN_AT_0_CELSIUS = 273.15

NO_VESSEL, SAME_VESSEL, NEW_VESSEL = 'no vessel', 'same vessel', 'new vessel'


class VesselLink:
    def __init__(self, krpc_host, mission_clock=None):
        self.connection = krpc.connect(name='capsule-gateway', address=krpc_host)
        self.space_center = self.connection.space_center
        self.vessel = None
        self.streams = StreamGroup(self.connection)
        self.parts = None                   # PartsWatch of the bound vessel
        self.station = None                 # StationWatch of the bound vessel: the CM and LM capsules
        self.commanded_throttle = 0.0       # what the cockpit last asked for
        self.warp_to_universal_time = None  # set by cmd/warp {"to_ut"}, worked on by the main loop
        self.has_target = False
        self.target_facts = None            # target.SlowFacts, read on the slow cycle
        self.vessel_name = None             # read on the slow cycle only (a plain kRPC read)
        self.hold_engaged = False           # ATTITUDE HOLD: the autopilot holds the cockpit's pitch and heading (commands.py)
        self.engine_sharing = EngineSharing()   # docked: the engines of the capsule not flown are held (engine_sharing.py)
        # one MET for the flight, across undockings (mission_clock.py); outlives a kRPC connection (KSP restarted)
        self.mission_clock = mission_clock if mission_clock is not None else MissionClock()

    # ---------- binding to the active vessel ----------
    def bind(self):
        """Follow the game's active vessel. Returns NO_VESSEL (VAB, Space Center, tracking station), SAME_VESSEL, or
        NEW_VESSEL after rebuilding every stream."""
        active_vessel = self.space_center.active_vessel
        if active_vessel is None:
            self.unbind()
            return NO_VESSEL
        if self.vessel is not None and active_vessel == self.vessel:
            if self.read['body']() != self.streams_body:
                # a new sphere of influence: the speeds were measured in the old body's frames (at the Mun, against
                # Kerbin's turning surface: thousands of m/s), so open the streams again in the new body's
                self.streams.close()
                self._open_streams(active_vessel)
            return SAME_VESSEL
        self.unbind()
        self.vessel = active_vessel
        # KSP sets the throttle to 50 % when a save loads: the panel is the authority, so put its value back.
        active_vessel.control.throttle = self.commanded_throttle
        self._open_streams(active_vessel)
        self.parts = PartsWatch(self.connection, active_vessel)
        self.station = StationWatch(self.space_center, active_vessel)
        self.body_names = {}
        self.body_figures = {}              # body → its atm (top of the atmosphere, m, None without), mu, radius
        self.warp_to_universal_time = None
        controlling_part = active_vessel.parts.controlling
        # where CTRL FROM PORT off goes back to
        self.default_control_part = (controlling_part if controlling_part.docking_port is None
                                     else active_vessel.parts.root)
        decision = self.mission_clock.bind(active_vessel.name, self.space_center.ut, active_vessel.met,
                                           active_vessel.situation.name)
        print(f'mission clock: {decision}, launch UT {self.mission_clock.launch_ut}', flush=True)
        return NEW_VESSEL

    def unbind(self):
        """Forget the vessel; the next bind() rebuilds everything (also used after the vessel splits)."""
        self.streams.close()
        if self.parts:
            self.parts.close()
        self.vessel, self.parts, self.station, self.vessel_name, self.target_facts = None, None, None, None, None

    def _open_streams(self, vessel):
        streams = self.streams
        body = vessel.orbit.body
        self.streams_body = body            # the frames below are this body's: bind() opens them again on a new one
        over_the_ground = vessel.flight(body.reference_frame)   # speeds relative to the turning surface
        around_the_body = vessel.flight(body.non_rotating_reference_frame)  # the speed along the orbit
        against_the_horizon = vessel.flight()                   # pitch, heading, roll against the local horizon
        # Axes of the local horizon (x up, y north, z east), moving with the ground: the vessel's velocity in this
        # frame is its surface velocity already split into up, north and east.
        # The motion of these frames (velocity and angular velocity) must be the ground's: a hybrid frame otherwise
        # takes its angular velocity from the frame that gives its axes, and a velocity measured in a frame that turns
        # with the vessel picks up its turn rate times the distance to the planet's centre (thousands of m/s).
        hybrid = lambda axes: self.space_center.ReferenceFrame.create_hybrid(
            position=body.reference_frame, rotation=axes, velocity=body.reference_frame,
            angular_velocity=body.reference_frame)
        ground_frame_with_horizon_axes = hybrid(vessel.surface_reference_frame)
        # The same velocity along the vessel's own axes (x right, y forward, z down).
        ground_frame_with_vessel_axes = hybrid(vessel.reference_frame)
        control, orbit = vessel.control, vessel.orbit

        def open_all(rate_hz, sources):
            return {name: streams.attribute(kerbal_object, attribute_name, rate_hz)
                    for name, (kerbal_object, attribute_name) in sources.items()}

        self.read = {
            # What the burn computer counts Δv with: every game update, so that the cutoff is not late.
            **open_all(UNLIMITED, {
                'universal_time': (self.space_center, 'ut'),
                'mission_time': (vessel, 'met'),
                'mass': (vessel, 'mass'),
                'thrust': (vessel, 'thrust'),
                'throttle': (control, 'throttle'),
            }),
            # The rest of what goes out on every telemetry cycle.
            **open_all(FAST_HZ, {
                'warp_rate': (self.space_center, 'warp_rate'),
                'paused': (self.connection.krpc, 'paused'),
                'altitude': (over_the_ground, 'mean_altitude'),
                'radar_altitude': (over_the_ground, 'surface_altitude'),
                'vertical_speed': (over_the_ground, 'vertical_speed'),
                'horizontal_speed': (over_the_ground, 'horizontal_speed'),
                'speed': (over_the_ground, 'speed'),
                'orbital_speed': (around_the_body, 'speed'),
                'dynamic_pressure': (over_the_ground, 'dynamic_pressure'),
                'g_force': (over_the_ground, 'g_force'),
                'latitude': (over_the_ground, 'latitude'),
                'longitude': (over_the_ground, 'longitude'),
                'pitch': (against_the_horizon, 'pitch'),
                'heading': (against_the_horizon, 'heading'),
                'roll': (against_the_horizon, 'roll'),
                'situation': (vessel, 'situation'),
                'stage': (control, 'current_stage'),
                'sas': (control, 'sas'),
                'sas_mode': (control, 'sas_mode'),
                'rcs': (control, 'rcs'),
                'gear': (control, 'gear'),
                'lights': (control, 'lights'),
                'brakes': (control, 'brakes'),
                'precision': (control, 'precision_mode'),
            }),
            # Slow to change, or only published on the slow cycle.
            **open_all(SLOW_HZ, {
                'static_pressure': (over_the_ground, 'static_pressure'),
                'outside_temperature': (over_the_ground, 'static_air_temperature'),
                'speed_mode': (control, 'speed_mode'),
                'available_thrust': (vessel, 'available_thrust'),
                'crew_count': (vessel, 'crew_count'),
                'biome': (vessel, 'biome'),
                'specific_impulse': (vessel, 'specific_impulse'),
                'can_communicate': (vessel.comms, 'can_communicate'),
                'body': (orbit, 'body'),
                'apoapsis_altitude': (orbit, 'apoapsis_altitude'),
                'periapsis_altitude': (orbit, 'periapsis_altitude'),
                'semi_major_axis': (orbit, 'semi_major_axis'),
                'eccentricity': (orbit, 'eccentricity'),
                'inclination': (orbit, 'inclination'),
                'period': (orbit, 'period'),
                'time_to_apoapsis': (orbit, 'time_to_apoapsis'),
                'time_to_periapsis': (orbit, 'time_to_periapsis'),
                'time_to_soi_change': (orbit, 'time_to_soi_change'),
                'true_anomaly': (orbit, 'true_anomaly'),
                'argument_of_periapsis': (orbit, 'argument_of_periapsis'),
                'longitude_of_ascending_node': (orbit, 'longitude_of_ascending_node'),
            }),
            'velocity_up_north_east': streams.call(FAST_HZ, vessel.velocity, ground_frame_with_horizon_axes),
            'velocity_right_forward_down': streams.call(FAST_HZ, vessel.velocity, ground_frame_with_vessel_axes),
            'signal_strength': streams.attribute(vessel.comms, 'signal_strength', SLOW_HZ),
        }
        # The orbit goes out on every cycle while the engines push, so that a cutoff on the apoapsis display is on
        # time; its streams are then sped up (see _orbit_rate).
        self.orbit_streams = [self.read[name] for name in ORBIT_STREAMS]
        self.orbit_streams_fast = False
        # action groups 1 to 10; kRPC calls the tenth one 0
        self.action_groups = [streams.call(SLOW_HZ, control.get_action_group, number % 10)
                              for number in range(1, ACTION_GROUP_COUNT + 1)]
    def universal_time(self):
        return self.read['universal_time']()

    # ---------- telemetry ----------
    def telemetry(self, include_slow, include_target):
        """{topic: payload}. Time, flight, attitude and vessel on every call; orbit, resources, engines, heat, the
        maneuver node, the radio link and the action groups only with `include_slow`; the target with `include_slow`,
        or with `include_target` while one is set (docking needs it faster)."""
        now = {name: stream() for name, stream in self.read.items()}
        self.mission_clock.follow(now['universal_time'], now['mission_time'], now['situation'].name)
        mission_time = self.mission_clock.met(now['universal_time'])
        if mission_time is None:
            mission_time = now['mission_time']
        thrusting = now['thrust'] > 0
        self._orbit_rate(fast=thrusting)
        travel = self._direction_of_travel(now)
        payloads = {
            'tlm/attitude': {'pitch': round(now['pitch'], 2), 'heading': round(now['heading'], 2),
                             'roll': round(now['roll'], 2), 'prograde': travel and travel['prograde']},
            'tlm/time': {'ut': round(now['universal_time'], 2), 'met': round(mission_time, 2),
                         'vessel_met': round(now['mission_time'], 2),
                         'warp': now['warp_rate'], 'paused': now['paused']},
            'tlm/flight': self._flight_payload(now, travel),
            'tlm/vessel': self._vessel_payload(now, refresh_name=include_slow),
        }
        if include_slow or thrusting:
            payloads['tlm/orbit'] = self._orbit_payload(now)
        if include_slow:
            payloads['tlm/resources'] = {
                'stage': self.parts.stage_propellant(now['stage']),
                'total': self.parts.total_resources()}
            payloads['tlm/engines'] = self.parts.engine_telemetry()
            payloads['tlm/thermal'] = {**self.parts.thermal_telemetry(),
                                       'outside': round(now['outside_temperature'] - KELVIN_AT_0_CELSIUS, 1)}
            payloads['tlm/node'] = self._node_payload()
            payloads['tlm/comm'] = self._comm_payload(now)
            payloads['tlm/groups'] = {'on': [bool(group()) for group in self.action_groups]}
            payloads['tlm/science'] = {'experiments': self.parts.science_telemetry(), 'biome': now['biome']}
            for other in self.station.other_vessels():       # the other capsule, apart: part of this flight
                try:
                    self.mission_clock.adopt(other.name, now['universal_time'], other.met)
                except RuntimeError:
                    pass
            payloads['tlm/station'] = {**self.station.telemetry(),
                                       'held': sum(1 for engine in self.engine_sharing.held if engine.part.vessel == self.vessel)}
        if include_slow or (include_target and self.has_target):
            payloads['tlm/target'] = target_telemetry(self, refresh_slow_facts=include_slow)
        return payloads

    def _orbit_rate(self, fast):
        """Set the orbit streams' rate; a call to the game for each, so only when it changes."""
        if fast == self.orbit_streams_fast:
            return
        for stream in self.orbit_streams:
            stream.rate = FAST_HZ if fast else SLOW_HZ
        self.orbit_streams_fast = fast

    @staticmethod
    def _direction_of_travel(now):
        """Surface velocity as north and east components, and as the prograde marker's pitch and heading.
        None when hardly moving."""
        if now['speed'] <= MOVING_ABOVE_M_S:
            return None
        up, north, east = now['velocity_up_north_east']
        prograde = {'pitch': round(math.degrees(math.atan2(up, math.hypot(north, east))), 2),
                    'heading': round(math.degrees(math.atan2(east, north)) % 360, 2)}
        return {'north': north, 'east': east, 'prograde': prograde}

    @staticmethod
    def _flight_payload(now, travel):
        right, forward, down = now['velocity_right_forward_down']
        return {'alt': round(now['altitude'], 3), 'radar': round(now['radar_altitude'], 3),
                'vs': round(now['vertical_speed'], 3), 'hs': round(now['horizontal_speed'], 3),
                'speed': round(now['speed'], 3), 'v_orb': round(now['orbital_speed'], 3),
                'q': round(now['dynamic_pressure'], 3), 'g': round(now['g_force'], 3),
                'lat': round(now['latitude'], 3), 'lon': round(now['longitude'], 3),
                'vn': round(travel['north'], 2) if travel else None,
                've': round(travel['east'], 2) if travel else None,
                'v_right': round(right, 2), 'v_fwd': round(forward, 2), 'v_down': round(down, 2),
                'p': round(now['static_pressure'], 1)}

    def _vessel_payload(self, now, refresh_name):
        if refresh_name or self.vessel_name is None:
            self.vessel_name = self.vessel.name
        situation = now['situation'].name
        sas_mode = SAS_MODE_FROM_KRPC.get(now['sas_mode'].name, now['sas_mode'].name) if now['sas'] else None
        return {'name': self.vessel_name, 'mass': round(now['mass'], 1), 'thrust': round(now['thrust'], 1),
                'thrust_avail': round(now['available_thrust'], 1), 'isp': round(now['specific_impulse'], 1),
                'situation': situation, 'crew': now['crew_count'], 'stage': now['stage'], 'throttle': round(now['throttle'], 3),
                'sas': now['sas'], 'rcs': now['rcs'], 'gear': now['gear'], 'lights': now['lights'],
                'brakes': now['brakes'], 'precision': now['precision'], 'hold': self.hold_engaged, 'sas_mode': sas_mode, 'speed_mode': now['speed_mode'].name,
                'solar': self.parts.solar_deployed_state(), 'chute': self.parts.parachute_state(),
                'chute_safe': self.parts.parachute_safety_state(),
                'fuel_cell': self.parts.fuel_cell_state(), 'wheels': self.parts.wheels_state(),
                'next_stage': self.parts.next_stage,
                'comm': now['can_communicate'], 'has_gear': self.parts.has_landing_gear(),
                'contact': situation in GROUND_SITUATIONS or self.parts.touches_ground()}

    def _orbit_payload(self, now):
        body = now['body']
        if body._object_id not in self.body_names:      # the name is a plain read: once per body
            self.body_names[body._object_id] = body.name
            self.body_figures[body._object_id] = {'atm': body.atmosphere_depth if body.has_atmosphere else None,
                                                  'mu': body.gravitational_parameter, 'radius': body.equatorial_radius}
        closed_orbit = now['eccentricity'] < 1          # an escape trajectory has no apoapsis and no period
        finite_or_none = lambda value: value if math.isfinite(value) else None
        return {'body': self.body_names[body._object_id], **self.body_figures[body._object_id],
                'apo': finite_or_none(now['apoapsis_altitude']), 'peri': now['periapsis_altitude'],
                'a': now['semi_major_axis'], 'e': now['eccentricity'], 'i': math.degrees(now['inclination']),
                'period': now['period'] if closed_orbit else None,
                't_apo': now['time_to_apoapsis'] if closed_orbit else None, 't_peri': now['time_to_periapsis'],
                'nu': math.degrees(now['true_anomaly']), 'argp': math.degrees(now['argument_of_periapsis']),
                'lan': math.degrees(now['longitude_of_ascending_node']), 'ut': round(now['universal_time'], 2),
                't_soi': finite_or_none(now['time_to_soi_change'])}

    def _node_payload(self):
        """The first maneuver node in the game, whoever made it, with the angle between the vessel's axis and the
        burn direction."""
        try:
            nodes = self.vessel.control.nodes
        except RuntimeError:            # KSP has no maneuver nodes here (career tracking station not upgraded)
            nodes = []
        if not nodes:
            return {'set': False}
        node = nodes[0]
        right, forward, down = node.direction(self.vessel.reference_frame)
        attitude_error = math.degrees(math.acos(max(-1.0, min(1.0, forward))))
        return {'set': True, 'ut': round(node.ut, 2),
                'dv': [round(node.prograde, 3), round(node.normal, 3), round(node.radial, 3)],
                'att_err': round(attitude_error, 2),
                # how to turn to face the burn direction: + is nose right, nose up
                'yaw': round(math.degrees(math.atan2(right, forward)), 2),
                'pitch': round(math.degrees(math.atan2(-down, forward)), 2)}

    def _comm_payload(self, now):
        """tlm/comm: the link to the ground. `via` is the first station or relay on the way."""
        link_up = bool(now['can_communicate'])
        hops, first_hop = 0, None
        if link_up:
            try:
                path = self.vessel.comms.control_path
                hops = len(path)
                first_hop = path[0].end.name if path else None
            except Exception:           # the link dropped between the two reads
                pass
        return {'link': link_up, 'strength': round(now['signal_strength'], 3) if link_up else 0.0,
                'hops': hops, 'via': first_hop, 'antenna': self.parts.antenna_deployed_state()}

    def close(self):
        try:
            self.connection.close()
        except Exception:
            pass
