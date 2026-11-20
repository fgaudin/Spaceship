"""The mock plant's model: a launcher in a plane around Kerbin, flying its own gravity turn, that answers the same
commands and reports the same telemetry as the KSP gateway (protocol/topics.md).

Positions and velocities are in an inertial frame centred on Kerbin: the launch site starts on the +y axis and east
is +x. Rendezvous is not simulated: a scripted target closes from 2 km and stops at 30 m.

Failures (sim/failures/<name>): engine_out (every engine), engine_one_out (one engine of a cluster), battery_short,
overheat, comm_lost. telemetry_freeze is handled by the service, which stops publishing.
"""
import copy
import math

import vehicle as V
from vehicle import STAGES

SWITCH_COMMANDS = {'cmd/sas': 'sas', 'cmd/rcs': 'rcs', 'cmd/gear': 'gear', 'cmd/lights': 'lights',
                   'cmd/brakes': 'brakes', 'cmd/fuel_cell': 'fuel_cell', 'cmd/precision': 'precision',
                   'cmd/wheels': 'wheels'}
GROUND_SITUATIONS = ('pre_launch', 'landed', 'crashed')
ACTION_GROUP_COUNT = 10
ON_THE_PAD = -1                 # value of `firing_stage` before the first staging
KICK_ANGLE = math.radians(3)    # the gravity turn starts with a 3° lean to the east ...
KICK_UNTIL_SPEED, KICK_UNTIL_ALTITUDE = 60.0, 500.0     # ... held until 60 m/s and 500 m
SOFT_LANDING_SPEED = 6.0
WARP_TO_SECONDS_AHEAD = 4       # warp at a rate only while the time left is at least this many seconds of it
ROLL_PROGRAM_START_S, ROLL_PROGRAM_LENGTH_S = 8.0, 12.0     # a 90° roll shortly after liftoff, for the attitude display
# electric charge, units per second
BASE_DRAIN, LIGHTS_DRAIN, SAS_DRAIN, SOLAR_CHARGE, SHORT_CIRCUIT_DRAIN = 0.5, 3.0, 1.0, 2.5, 20.0
FUEL_CELL_CHARGE = 1.5                         # EC/s while the fuel cell runs


def clamp(value, low, high):
    return max(low, min(high, value))


class Plant:
    def __init__(self):
        self.reset()

    def reset(self):
        self.time = 0.0
        self.liftoff_time = None
        # inertial position and velocity; at rest on the turning ground
        self.x, self.y = 0.0, V.RADIUS
        self.velocity_x, self.velocity_y = V.ROTATION_RATE * V.RADIUS, 0.0
        self.pitch = 90.0
        self.firing_stage = ON_THE_PAD          # index into STAGES of the stage whose engines are lit
        self.stages_attached = len(STAGES)      # the last N stages of STAGES are still on the vehicle
        self.propellant = [stage.propellant_mass for stage in STAGES]
        self.situation = 'pre_launch'
        self.thrust, self.g_force, self.dynamic_pressure = 0.0, 1.0, 0.0
        self.electric_charge = V.BATTERY_CAPACITY
        self.failures = set()
        # what the cockpit commands
        self.throttle, self.thrust_limit, self.gimbal_locked = 0.0, 1.0, False
        self.sas, self.rcs, self.gear, self.lights, self.brakes = False, False, True, False, False
        self.precision = False
        self.sas_mode = 'stability'
        self.speed_mode = 'surface'
        self.solar_deployed, self.parachute = False, 'stowed'
        self.fuel_cell = False
        self.wheels = True              # KSP's reaction wheels start on
        self.antenna_deployed = False
        self.action_groups = [False] * ACTION_GROUP_COUNT
        self.warp_index, self.warp_to_time, self.paused = 0, None, False
        self.frozen = False                     # the instructor's freeze (sim/freeze), apart from the crew's PAUSE
        self.maneuver_node = None
        # the scripted target
        self.target_index, self.target_port_index = None, None
        self.target_range = V.TARGET_START_RANGE
        self.controlled_from_port, self.docked = False, False

    # ---------- commands ----------
    def command(self, topic, request):
        if topic in SWITCH_COMMANDS:
            setattr(self, SWITCH_COMMANDS[topic], bool(request.get('on')))
        elif topic == 'cmd/throttle':
            self.throttle = clamp(float(request.get('v', 0)), 0.0, 1.0)
        elif topic == 'cmd/thrust_limit':
            self.thrust_limit = clamp(float(request.get('v', 1)), 0.0, 1.0)
        elif topic == 'cmd/gimbal' and 'gimbal_stuck' in self.failures:
            pass
        elif topic == 'cmd/gimbal':
            self.gimbal_locked = bool(request.get('locked'))
        elif topic == 'cmd/sas_mode':
            self.sas_mode = request.get('mode', 'stability')
        elif topic == 'cmd/stage':
            self._stage()
        elif topic == 'cmd/abort':                  # the capsule leaves everything behind
            self.throttle, self.stages_attached, self.firing_stage = 0.0, 0, len(STAGES)
        elif topic == 'cmd/solar':
            self.solar_deployed = bool(request.get('on'))
        elif topic == 'cmd/speed_mode':
            if request.get('mode') in ('orbit', 'surface', 'target'):
                self.speed_mode = request['mode']
        elif topic == 'cmd/antenna':
            self.antenna_deployed = bool(request.get('on'))
        elif topic == 'cmd/action_group':
            number = int(request.get('n', 0))
            if 1 <= number <= ACTION_GROUP_COUNT:
                self.action_groups[number - 1] = not self.action_groups[number - 1]
        elif topic == 'cmd/chute' and 'chute_fail' in self.failures:
            pass                                    # the instructor broke them
        elif topic == 'cmd/chute':
            if self.parachute == 'stowed':
                self.parachute = 'deployed'
        elif topic == 'cmd/target':
            self._select_target(request)
        elif topic == 'cmd/undock':
            self.docked = False
        elif topic == 'cmd/control_from':
            self.controlled_from_port = bool(request.get('port'))
        elif topic == 'cmd/node':
            self.maneuver_node = None if request.get('clear') else {'ut': request.get('ut'), 'dv': request.get('dv')}
        elif topic == 'cmd/pause':
            self.paused = bool(request.get('on'))
        elif topic == 'cmd/game':
            self._save_or_load(request)
        elif topic == 'cmd/warp':
            self._warp(request)
        elif topic == 'sim/reset':
            self.reset()
        elif topic == 'sim/freeze':
            self.frozen = bool(request.get('on'))
        elif topic.startswith('sim/failures/'):
            failure = topic.split('/')[-1]
            (self.failures.add if request.get('on') else self.failures.discard)(failure)

    def _stage(self):
        if self.firing_stage == ON_THE_PAD:         # liftoff: light the first stage
            self.firing_stage, self.situation, self.liftoff_time = 0, 'flying', self.time
        elif self.firing_stage < len(STAGES):       # drop the firing stage and light the next one
            self.stages_attached = len(STAGES) - self.firing_stage - 1
            self.firing_stage += 1

    def _select_target(self, request):
        if request.get('clear'):
            self.target_index = self.target_port_index = None
        elif 'port' in request:                     # next port, then back to the vessel itself
            if self.target_index is None:
                return
            if self.target_port_index is None:
                self.target_port_index = 0
            elif self.target_port_index + 1 < V.TARGET_PORT_COUNT:
                self.target_port_index += 1
            else:
                self.target_port_index = None
        else:
            step = 1 if int(request.get('step', 1)) >= 0 else -1
            if self.target_index is None:
                self.target_index = 0 if step > 0 else len(V.TARGET_NAMES) - 1
            else:
                self.target_index = (self.target_index + step) % len(V.TARGET_NAMES)
            self.target_port_index, self.target_range = None, V.TARGET_START_RANGE

    def _save_or_load(self, request):
        if request.get('quicksave'):
            self.quicksave = copy.deepcopy({name: value for name, value in vars(self).items() if name != 'quicksave'})
        elif request.get('quickload') and getattr(self, 'quicksave', None):
            vars(self).update(copy.deepcopy(self.quicksave))

    def _warp(self, request):
        if 'to_ut' in request:
            self.warp_to_time = float(request['to_ut'])
            return
        self.warp_to_time = None                    # a manual command cancels a warp-to
        if request.get('stop'):
            self.warp_index = 0
        else:
            self.warp_index = clamp(self.warp_index + int(request.get('step', 0)), 0, len(V.WARP_RATES) - 1)

    def warp_rate(self):
        return V.WARP_RATES[self.warp_index]

    # ---------- the vehicle ----------
    def firing_stage_or_none(self):
        """The Stage whose engines are lit, if it is still attached."""
        index = self.firing_stage
        still_attached = index >= len(STAGES) - self.stages_attached
        return STAGES[index] if 0 <= index < len(STAGES) and still_attached else None

    def mass(self):
        first_attached = len(STAGES) - self.stages_attached
        stages_mass = sum(STAGES[index].dry_mass + self.propellant[index] for index in range(first_attached, len(STAGES)))
        return V.PAYLOAD_MASS + stages_mass

    def can_thrust(self):
        stage = self.firing_stage_or_none()
        return stage is not None and self.propellant[self.firing_stage] > 0 and 'engine_out' not in self.failures

    def working_engine_fraction(self):
        """1, or (n − 1) / n with the failure engine_one_out on a cluster of n engines."""
        stage = self.firing_stage_or_none()
        engine_count = len(stage.engine_positions) if stage else 1
        if 'engine_one_out' in self.failures and engine_count > 1:
            return (engine_count - 1) / engine_count
        return 1.0

    def target_closing_speed(self):
        """The scripted approach: a little over the course's range / 400 s braking gate, stopping at 30 m."""
        if self.target_range <= V.TARGET_STOP_RANGE:
            return 0.0
        return max(0.2, self.target_range / 300.0)

    # ---------- physics ----------
    def step(self, time_step):
        self.time += time_step
        self._advance_target(time_step)
        self._continue_warp_to()

        radius = math.hypot(self.x, self.y)
        altitude = radius - V.RADIUS
        up = (self.x / radius, self.y / radius)
        east = (up[1], -up[0])
        # velocity relative to the air, which turns with the planet
        air_velocity = (self.velocity_x - V.ROTATION_RATE * self.y, self.velocity_y + V.ROTATION_RATE * self.x)
        airspeed = math.hypot(*air_velocity)
        in_atmosphere = altitude < V.ATMOSPHERE_TOP
        pressure = self.static_pressure()
        density = V.SEA_LEVEL_DENSITY * math.exp(-altitude / V.DENSITY_SCALE_HEIGHT) if in_atmosphere else 0.0
        mass = self.mass()
        gravity = V.GRAVITATIONAL_PARAMETER / radius ** 2

        thrust = self._burn_propellant(time_step, pressure)
        if self.situation in GROUND_SITUATIONS and thrust <= mass * gravity:
            # held on the ground until thrust exceeds weight
            self.thrust, self.dynamic_pressure = thrust, 0.0
            self.g_force = 0.0 if self.situation == 'crashed' else 1.0
            return
        if self.situation == 'crashed':
            return

        heading = self._steer(up, east, air_velocity, airspeed, altitude)
        self.pitch = math.degrees(math.atan2(heading[0] * up[0] + heading[1] * up[1],
                                             heading[0] * east[0] + heading[1] * east[1]))
        parachute_open = self.parachute == 'deployed' and altitude < V.PARACHUTE_OPENS_BELOW
        drag_area = V.DRAG_AREA + (V.PARACHUTE_DRAG_AREA if parachute_open else 0.0)
        drag = 0.5 * density * airspeed ** 2 * drag_area
        against_the_air = (air_velocity[0] / airspeed, air_velocity[1] / airspeed) if airspeed else (0.0, 0.0)
        acceleration = [thrust / mass * heading[axis] - drag / mass * against_the_air[axis] - gravity * up[axis]
                        for axis in (0, 1)]
        self.velocity_x += acceleration[0] * time_step
        self.velocity_y += acceleration[1] * time_step
        self.x += self.velocity_x * time_step
        self.y += self.velocity_y * time_step

        self.thrust = thrust
        self.dynamic_pressure = 0.5 * density * airspeed ** 2
        # what an accelerometer feels: everything but gravity
        self.g_force = math.hypot(acceleration[0] + gravity * up[0], acceleration[1] + gravity * up[1]) / V.STANDARD_GRAVITY
        self._update_situation(up, airspeed, altitude)
        self._drain_battery(time_step)

    def _advance_target(self, time_step):
        if self.target_index is None:
            return
        self.target_range = max(V.TARGET_STOP_RANGE, self.target_range - self.target_closing_speed() * time_step)
        if self.target_port_index is not None and self.target_range <= V.TARGET_STOP_RANGE:
            # an approach to a port ends docked
            self.docked, self.target_index, self.target_port_index = True, None, None

    def _continue_warp_to(self):
        if self.warp_to_time is None:
            return
        seconds_left = self.warp_to_time - self.time
        usable = [index for index, rate in enumerate(V.WARP_RATES) if rate * WARP_TO_SECONDS_AHEAD <= seconds_left]
        self.warp_index = max(usable, default=0)
        if seconds_left <= WARP_TO_SECONDS_AHEAD:
            self.warp_index, self.warp_to_time = 0, None

    def _burn_propellant(self, time_step, pressure):
        """Thrust for this step (N); takes the propellant it costs out of the firing stage."""
        if not self.can_thrust():
            return 0.0
        stage = self.firing_stage_or_none()
        mass_flow = (stage.mass_flow_at_full_throttle() * self.throttle * self.thrust_limit
                     * self.working_engine_fraction())
        self.propellant[self.firing_stage] -= min(self.propellant[self.firing_stage], mass_flow * time_step)
        return mass_flow * stage.specific_impulse_at(pressure) * V.STANDARD_GRAVITY

    @staticmethod
    def _steer(up, east, air_velocity, airspeed, altitude):
        """The mock flies itself: a small kick east off the pad, then along the airflow (a gravity turn), then
        horizontal above the atmosphere to circularise. Returns the unit vector the nose points along."""
        if airspeed < KICK_UNTIL_SPEED or altitude < KICK_UNTIL_ALTITUDE:
            return (up[0] * math.cos(KICK_ANGLE) + east[0] * math.sin(KICK_ANGLE),
                    up[1] * math.cos(KICK_ANGLE) + east[1] * math.sin(KICK_ANGLE))
        if altitude > V.ATMOSPHERE_TOP:
            return east
        return air_velocity[0] / airspeed, air_velocity[1] / airspeed

    def _update_situation(self, up_before_step, airspeed, altitude):
        if math.hypot(self.x, self.y) < V.RADIUS:       # hit the ground: put it back on the surface, at rest
            self.situation = 'landed' if airspeed < SOFT_LANDING_SPEED else 'crashed'
            self.x, self.y = up_before_step[0] * V.RADIUS, up_before_step[1] * V.RADIUS
            self.velocity_x, self.velocity_y = V.ROTATION_RATE * self.y, -V.ROTATION_RATE * self.x
        elif altitude > V.ATMOSPHERE_TOP:
            self.situation = 'orbiting' if self.orbit()['peri'] > V.ATMOSPHERE_TOP else 'sub_orbital'
        else:
            self.situation = 'flying'

    def _drain_battery(self, time_step):
        rate = BASE_DRAIN + (LIGHTS_DRAIN if self.lights else 0) + (SAS_DRAIN if self.sas else 0) \
            - (SOLAR_CHARGE if self.solar_deployed else 0) - (FUEL_CELL_CHARGE if self.fuel_cell else 0) + (SHORT_CIRCUIT_DRAIN if 'battery_short' in self.failures else 0)
        self.electric_charge = clamp(self.electric_charge - rate * time_step, 0.0, V.BATTERY_CAPACITY)

    # ---------- orbit ----------
    def orbit(self):
        """tlm/orbit, from the position and velocity (two-body, in the plane)."""
        mu = V.GRAVITATIONAL_PARAMETER
        radius = math.hypot(self.x, self.y)
        speed_squared = self.velocity_x ** 2 + self.velocity_y ** 2
        specific_energy = speed_squared / 2 - mu / radius
        angular_momentum = self.x * self.velocity_y - self.y * self.velocity_x
        eccentricity = math.sqrt(max(0.0, 1 + 2 * specific_energy * angular_momentum ** 2 / mu ** 2))
        semi_major_axis = -mu / (2 * specific_energy) if abs(specific_energy) > 1e-9 else float('inf')
        semi_latus_rectum = angular_momentum ** 2 / mu
        periapsis_radius = semi_latus_rectum / (1 + eccentricity)
        apoapsis_radius = semi_latus_rectum / (1 - eccentricity) if eccentricity < 1 else float('inf')
        # true anomaly from the radius, with the sign of the radial speed (positive while climbing)
        true_anomaly = 0.0
        if eccentricity > 1e-6:
            cosine = clamp((semi_latus_rectum / radius - 1) / eccentricity, -1.0, 1.0)
            climbing = self.x * self.velocity_x + self.y * self.velocity_y >= 0
            true_anomaly = math.degrees(math.acos(cosine)) * (1 if climbing else -1)
        closed = eccentricity < 1 and semi_major_axis > 0
        return {'body': 'Kerbin', 'atm': V.ATMOSPHERE_TOP, 'mu': V.GRAVITATIONAL_PARAMETER, 'radius': V.RADIUS,
                'apo': apoapsis_radius - V.RADIUS if math.isfinite(apoapsis_radius) else None,
                'peri': periapsis_radius - V.RADIUS, 'a': semi_major_axis, 'e': eccentricity, 'i': 0.0,
                'nu': round(true_anomaly, 3), 'ut': round(self.time, 2),
                'lan': 0.0, 'argp': 0.0,            # in the plane: only the circularisation PAD uses the mock's orbit
                'period': 2 * math.pi * math.sqrt(semi_major_axis ** 3 / mu) if closed else None,
                't_soi': None, **self._times_to_apsides(semi_major_axis, eccentricity, true_anomaly)}

    @staticmethod
    def _times_to_apsides(semi_major_axis, eccentricity, true_anomaly_degrees):
        """Time to apoapsis and periapsis on an ellipse, by Kepler's equation."""
        if not (0 <= eccentricity < 1) or semi_major_axis <= 0:
            return {'t_apo': None, 't_peri': None}
        true_anomaly = math.radians(true_anomaly_degrees)
        eccentric_anomaly = 2 * math.atan2(math.sqrt(1 - eccentricity) * math.sin(true_anomaly / 2),
                                           math.sqrt(1 + eccentricity) * math.cos(true_anomaly / 2))
        mean_anomaly = (eccentric_anomaly - eccentricity * math.sin(eccentric_anomaly)) % (2 * math.pi)
        mean_motion = math.sqrt(V.GRAVITATIONAL_PARAMETER / semi_major_axis ** 3)
        return {'t_peri': round(((2 * math.pi - mean_anomaly) % (2 * math.pi)) / mean_motion, 1),
                't_apo': round(((math.pi - mean_anomaly) % (2 * math.pi)) / mean_motion, 1)}

    # ---------- telemetry ----------
    def telemetry(self):
        """{topic: payload}, the same topics as the KSP gateway."""
        radius = math.hypot(self.x, self.y)
        up = (self.x / radius, self.y / radius)
        east = (up[1], -up[0])
        air_velocity = (self.velocity_x - V.ROTATION_RATE * self.y, self.velocity_y + V.ROTATION_RATE * self.x)
        vertical_speed = air_velocity[0] * up[0] + air_velocity[1] * up[1]
        horizontal_speed = air_velocity[0] * east[0] + air_velocity[1] * east[1]
        altitude = radius - V.RADIUS
        mission_time = self.time - self.liftoff_time if self.liftoff_time is not None else 0.0
        moving = math.hypot(vertical_speed, horizontal_speed) > 1
        prograde = {'pitch': round(math.degrees(math.atan2(vertical_speed, horizontal_speed)), 2), 'heading': 90.0}
        # the same velocity along the vessel's axes: the mock flies in one plane, nose `pitch` above the east
        nose_up, nose_east = math.sin(math.radians(self.pitch)), math.cos(math.radians(self.pitch))
        velocity_forward = vertical_speed * nose_up + horizontal_speed * nose_east
        velocity_down = -(vertical_speed * nose_east - horizontal_speed * nose_up)
        link_up = 'comm_lost' not in self.failures
        return {
            'tlm/time': {'ut': round(self.time, 2), 'met': round(mission_time, 2), 'warp': self.warp_rate(),
                         'paused': self.paused or self.frozen},
            'tlm/flight': {'alt': round(altitude, 1), 'radar': round(altitude, 1), 'vs': round(vertical_speed, 2),
                           'hs': round(horizontal_speed, 2), 'speed': round(math.hypot(*air_velocity), 2),
                           'v_orb': round(math.hypot(self.velocity_x, self.velocity_y), 2),
                           'q': round(self.dynamic_pressure, 1), 'g': round(self.g_force, 3),
                           'vn': 0.0, 've': round(horizontal_speed, 2), 'lat': 0.0,
                           'v_right': 0.0, 'v_fwd': round(velocity_forward, 2), 'v_down': round(velocity_down, 2),
                           'p': round(self.static_pressure(), 1),
                           'lon': round(math.degrees(math.atan2(self.x, self.y) - V.ROTATION_RATE * self.time), 4)},
            'tlm/vessel': self._vessel_telemetry(),
            # the mock flies due east; the nose pitch is the one it steers
            'tlm/attitude': {'pitch': round(self.pitch, 2), 'heading': 90.0, 'roll': self._roll(mission_time),
                             'prograde': prograde if moving else None},
            'tlm/orbit': self.orbit(),
            'tlm/resources': self._resource_telemetry(),
            'tlm/target': self._target_telemetry(),
            'tlm/engines': self._engine_telemetry(),
            'tlm/thermal': {'max': 0.9 if 'overheat' in self.failures else 0.2, 'outside': self.outside_temperature()},
            'tlm/node': ({'set': True, **self.maneuver_node, 'att_err': 1.0, 'yaw': 0.6, 'pitch': -0.8}
                         if self.maneuver_node else {'set': False}),
            'tlm/comm': {'link': link_up, 'strength': 0.8 if link_up else 0.0, 'hops': 1 if link_up else 0,
                         'via': 'KSC' if link_up else None, 'antenna': self.antenna_deployed},
            'tlm/groups': {'on': list(self.action_groups)},
        }

    def _roll(self, mission_time):
        """A roll program from −90° to 0° shortly after liftoff."""
        if self.liftoff_time is None:
            return -90.0
        progress = clamp((mission_time - ROLL_PROGRAM_START_S) / ROLL_PROGRAM_LENGTH_S, 0.0, 1.0)
        return round(progress * 90.0 - 90.0, 2)

    def ksp_stage_number(self):
        """KSP counts stages down: 4 on the pad, 3 with the first stage lit, ..."""
        if self.firing_stage == ON_THE_PAD:
            return len(STAGES) + 1
        return len(STAGES) - self.firing_stage

    def _next_stage(self):
        """What cmd/stage does next (see _stage): liftoff lights S1 and lets go of the pad, then each staging drops
        the firing stage and lights the one above; the last only drops."""
        if self.firing_stage >= len(STAGES):
            return None
        lit = STAGES[self.firing_stage + 1] if self.firing_stage + 1 < len(STAGES) else None
        on_the_pad = self.firing_stage == ON_THE_PAD
        return {'stage': self.ksp_stage_number() - 1, 'engines': len(lit.engine_positions) if lit else 0, 'solids': 0,
                'decouple': not on_the_pad, 'clamps': on_the_pad, 'chutes': False, 'fairing': False}

    def _vessel_telemetry(self):
        stage = self.firing_stage_or_none()
        available_thrust = 0.0
        if self.can_thrust():
            available_thrust = stage.vacuum_thrust * self.thrust_limit * self.working_engine_fraction()
        return {'name': 'Mock X', 'mass': round(self.mass(), 1), 'thrust': round(self.thrust, 1),
                'thrust_avail': available_thrust, 'isp': stage.vacuum_isp if stage else 0,
                'situation': self.situation, 'stage': self.ksp_stage_number(), 'throttle': self.throttle,
                'sas': self.sas, 'rcs': self.rcs, 'gear': self.gear, 'lights': self.lights, 'brakes': self.brakes, 'precision': self.precision,
                'sas_mode': self.sas_mode, 'speed_mode': self.speed_mode, 'solar': self.solar_deployed, 'chute': self.parachute,
                'fuel_cell': self.fuel_cell, 'wheels': self.wheels, 'next_stage': self._next_stage(),
                'comm': 'comm_lost' not in self.failures, 'has_gear': False,
                'contact': self.situation in ('pre_launch', 'landed')}

    def _resource_telemetry(self):
        stage = self.firing_stage_or_none()
        stage_resources = {}
        if stage:
            stage_resources['LiquidFuel'] = {
                'amount': round(self.propellant[self.firing_stage] / V.PROPELLANT_KG_PER_UNIT, 2),
                'max': stage.propellant_mass / V.PROPELLANT_KG_PER_UNIT}
        charge = {'amount': round(self.electric_charge, 2), 'max': V.BATTERY_CAPACITY}
        return {'stage': stage_resources, 'total': {'ElectricCharge': charge}}

    def _target_telemetry(self):
        state = {'set': self.target_index is not None, 'ctrl_port': self.controlled_from_port, 'docked': self.docked}
        if self.target_index is None:
            return state
        closing_speed = self.target_closing_speed()
        state.update({'name': V.TARGET_NAMES[self.target_index], 'range': round(self.target_range, 2),
                      'closing': round(closing_speed, 3), 'los_rate': 0.5, 'rel_v': round(closing_speed, 3)})
        if self.target_port_index is not None:      # fixed, slightly misaligned docking geometry
            state['port'] = {'axial': round(self.target_range, 3), 'x': 0.1, 'z': -0.05,
                             'v_axial': -round(closing_speed, 4), 'vx': 0.0, 'vz': 0.0, 'angle': 2.0,
                             'from_port': self.controlled_from_port,
                             'right': 0.1, 'up': 0.05, 'fwd': round(self.target_range, 3),
                             'v_right': -0.01, 'v_up': 0.0, 'yaw': 1.5, 'pitch': -0.5, 'roll': 4.0}
        return state

    def outside_temperature(self):
        """°C: a standard atmosphere, cooling 6.5 °C per km down to −60 °C, and space's 4 K above the atmosphere."""
        altitude = math.hypot(self.x, self.y) - V.RADIUS
        if altitude >= V.ATMOSPHERE_TOP:
            return -269.0
        return round(max(-60.0, 15.0 - 0.0065 * altitude), 1)

    def static_pressure(self):
        altitude = math.hypot(self.x, self.y) - V.RADIUS
        if altitude >= V.ATMOSPHERE_TOP:
            return 0.0
        return V.SEA_LEVEL_PRESSURE * math.exp(-altitude / V.PRESSURE_SCALE_HEIGHT)

    def _engine_telemetry(self):
        """Every engine still on the vehicle; those of the firing stage are lit."""
        engines = []
        pressure = self.static_pressure()
        first_attached = len(STAGES) - self.stages_attached
        for index in range(first_attached, len(STAGES)):
            stage = STAGES[index]
            lit = index == self.firing_stage
            engine_count = len(stage.engine_positions)
            has_fuel = self.propellant[index] > 0 and 'engine_out' not in self.failures
            full_thrust_each = stage.vacuum_thrust * self.thrust_limit / engine_count
            working_count = engine_count * self.working_engine_fraction() if lit else engine_count
            for number, (x, z) in enumerate(stage.engine_positions):
                # with the failure engine_one_out, the second engine of the cluster is the one that stops
                failed = lit and 'engine_one_out' in self.failures and engine_count > 1 and number == 1
                thrust = self.thrust / working_count if lit and has_fuel and not failed else 0.0
                # the mock's engines burn propellant at a fixed rate: their thrust follows the specific impulse
                rated = full_thrust_each * stage.specific_impulse_at(pressure) / stage.vacuum_isp if has_fuel else 0.0
                engines.append({'x': x, 'z': z, 'stage': len(STAGES) - index, 'on': lit, 'fuel': has_fuel,
                                'max': round(full_thrust_each if has_fuel else 0.0, 1), 'thrust': round(thrust, 1),
                                'rated': round(rated, 1), 'isp_vac': stage.vacuum_isp, 'isp_sl': stage.sea_level_isp})
        return {'engines': engines, 'stage': self.ksp_stage_number(), 'limit': self.thrust_limit,
                'gimbal_locked': self.gimbal_locked}
