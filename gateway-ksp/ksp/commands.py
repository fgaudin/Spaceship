"""cmd/* messages from the cockpit, turned into kRPC calls (protocol/topics.md lists the payloads)."""
import time

from .failures import PlantFailures
from .station import STATIONS
from .target import control_from_port, select_target, undock
from .vessel_link import SAS_MODE_TO_KRPC

RAILS_WARP_RATES = [1, 5, 10, 50, 100, 1000, 10000, 100000]     # KSP's rails warp factors 0 to 7
PHYSICS_WARP_MAX_FACTOR = 3
WARP_TO_SECONDS_AHEAD = 4       # warp at a rate only while the time left is at least this many seconds of it
SPEED_MODES = ('orbit', 'surface', 'target')
SCIENCE_ACTIONS = ('run', 'transmit', 'dump', 'reset')
# KSP puts SAS back to stability when it is switched on, and can drop a mode set in the same moment: the wanted mode
# is set again this long after either.
SAS_MODE_SET_AGAIN_AFTER_S = (0.5, 1.5)
SAS_MODE_SETTLES_S = 0.5           # a mode just set shows in the telemetry after this
ACTION_GROUP_SWITCHES = {'cmd/rcs': 'rcs', 'cmd/gear': 'gear', 'cmd/lights': 'lights',
                         'cmd/brakes': 'brakes', 'cmd/precision': 'precision_mode'}


def clamp(value, low, high):
    return max(low, min(high, value))


class CommandHandler:
    def __init__(self, link, failures=None):
        self.link = link
        # what the instructor broke (SimSup); outlives a kRPC connection, since the failures arrive only once
        self.failures = failures if failures is not None else PlantFailures()
        self.wanted_sas_mode = None         # the mode SAS takes when it comes on: asked for, then the game's
        self.sas_mode_applied_at = 0.0      # when it was last set (monotonic)
        self.sas_mode_set_again_at = []     # times (monotonic) at which to set it again
        self.handlers = {
            'cmd/sas': self.sas,
            'cmd/throttle': self.throttle, 'cmd/stage': self.stage, 'cmd/abort': self.abort,
            'cmd/solar': self.solar_panels, 'cmd/fuel_cell': self.fuel_cells, 'cmd/wheels': self.reaction_wheels, 'cmd/chute': self.parachutes, 'cmd/sas_mode': self.sas_mode,
            'cmd/antenna': self.antennas, 'cmd/action_group': self.action_group, 'cmd/speed_mode': self.speed_mode,
            'cmd/thrust_limit': self.thrust_limit, 'cmd/gimbal': self.gimbal_lock,
            'cmd/target': lambda request: select_target(self.link, request),
            'cmd/undock': lambda request: undock(self.link),
            'cmd/control_from': lambda request: control_from_port(self.link, bool(request.get('port'))),
            'cmd/node': self.maneuver_node, 'cmd/pause': self.pause, 'cmd/game': self.save_or_load,
            'cmd/science': self.science, 'cmd/warp': self.warp, 'cmd/rotate': self.rotate, 'cmd/translate': self.translate,
            'cmd/station': self.station, 'cmd/hold': self.hold,
        }
        self.wanted_hold = None             # (pitch, heading) in degrees while ATTITUDE HOLD is on, else None
        self.hold_vessel = None             # the vessel whose autopilot holds it
        self.hold_refused = False           # the game refused the last hold: wait for the next cmd/hold

    def run(self, topic, request):
        if topic.startswith('sim/'):
            self.instructor(topic, request)
        elif self.failures.blocks(topic):
            return
        elif topic in ACTION_GROUP_SWITCHES:
            setattr(self.link.vessel.control, ACTION_GROUP_SWITCHES[topic], bool(request.get('on')))
        elif topic in self.handlers:
            self.handlers[topic](request)

    # ---------- engine and staging ----------
    def throttle(self, request):
        self.link.commanded_throttle = clamp(float(request.get('v', 0)), 0.0, 1.0)
        self.link.vessel.control.throttle = self.link.commanded_throttle

    def stage(self, request):
        self.link.vessel.control.activate_next_stage()
        time.sleep(0.1)                     # let the part list settle before it is read again
        self.link.parts.forget_stage()

    def abort(self, request):
        self.link.vessel.control.abort = True

    def thrust_limit(self, request):
        """Every lit engine that can be throttled; solid boosters cannot be limited in flight."""
        limit = clamp(float(request.get('v', 1)), 0.0, 1.0)
        for engine in self.link.parts.all_engines():
            if engine.active and not engine.throttle_locked:
                engine.thrust_limit = limit
        self.link.parts.read_engine_settings()

    def gimbal_lock(self, request):
        for engine in self.link.parts.all_engines():
            if engine.gimballed:
                engine.gimbal_locked = bool(request.get('locked'))
        self.link.parts.read_engine_settings()

    # ---------- the instructor (SimSup) ----------
    def instructor(self, topic, request):
        if topic.startswith('sim/failures/'):
            self.failures.update(self.link, topic.rsplit('/', 1)[1], request)
        elif topic == 'sim/freeze':
            self.link.connection.krpc.paused = bool(request.get('on'))
        elif topic == 'sim/load' and request.get('save'):
            self.link.space_center.load(str(request['save']))     # the vessel changes: the main loop binds again

    # ---------- hand controllers ----------
    def rotate(self, request):
        """{'pitch', 'yaw', 'roll'}, −1..1: + nose up, + nose right, + roll right."""
        control = self.link.vessel.control
        control.pitch = clamp(float(request.get('pitch', 0)), -1.0, 1.0)
        control.yaw = clamp(float(request.get('yaw', 0)), -1.0, 1.0)
        control.roll = clamp(float(request.get('roll', 0)), -1.0, 1.0)

    def translate(self, request):
        """{'right', 'up', 'forward'}, −1..1: RCS translation."""
        control = self.link.vessel.control
        control.right = clamp(float(request.get('right', 0)), -1.0, 1.0)
        control.up = clamp(float(request.get('up', 0)), -1.0, 1.0)
        control.forward = clamp(float(request.get('forward', 0)), -1.0, 1.0)

    # ---------- SAS ----------
    def sas(self, request):
        self.link.vessel.control.sas = bool(request.get('on'))
        if request.get('on'):
            self._set_sas_mode_soon()

    def sas_mode(self, request):
        mode = request.get('mode', 'stability')
        if mode not in SAS_MODE_TO_KRPC:
            return
        self.wanted_sas_mode = mode
        self._apply_sas_mode()
        self._set_sas_mode_soon()

    def _set_sas_mode_soon(self):
        now = time.monotonic()
        self.sas_mode_set_again_at = [now + delay for delay in SAS_MODE_SET_AGAIN_AFTER_S]

    def _apply_sas_mode(self):
        """Set the wanted mode if SAS is on; with SAS off it waits for SAS to come on (KSP refuses it then)."""
        control = self.link.vessel.control
        if self.wanted_sas_mode is None or not control.sas:
            return
        self.sas_mode_applied_at = time.monotonic()
        try:
            control.sas_mode = getattr(self.link.space_center.SASMode, SAS_MODE_TO_KRPC[self.wanted_sas_mode])
        except Exception as error:          # e.g. a mode this pilot or probe core cannot hold
            print('sas_mode refused:', self.wanted_sas_mode, str(error).splitlines()[0], flush=True)

    # ---------- ATTITUDE HOLD: kRPC's autopilot ----------
    def hold(self, request):
        """{'on', 'pitch', 'heading'}: hold that pitch and heading against the horizon, with kRPC's autopilot (the
        cockpit sends it only with SAS off: the two would fight). Roll is left free."""
        self.wanted_hold = (float(request['pitch']), float(request['heading'])) if request.get('on') else None
        self.hold_refused = False
        self._apply_hold_safely()

    def _apply_hold_safely(self):
        """A hold the game refuses is reported (tlm/vessel hold false, so HOLD's LED blinks), never a lost link."""
        try:
            self._apply_hold()
        except Exception as error:
            print('hold refused:', repr(error)[:200], flush=True)
            self.hold_vessel, self.link.hold_engaged = None, False
            self.hold_refused = True        # not tried again until the cockpit asks again (once a second at most)

    def _apply_hold(self):
        vessel = self.link.vessel
        if self.wanted_hold is None:
            if self.hold_vessel is not None:
                try:
                    self.hold_vessel.auto_pilot.engaged = False
                except Exception:           # the vessel is gone (staged away, scene changed)
                    pass
            self.hold_vessel = None
            self.link.hold_engaged = False
            return
        if vessel is None:                  # unbound for a moment (an undocking): continue_hold() applies it
            return
        autopilot = vessel.auto_pilot
        if self.hold_vessel != vessel:      # first time, or a new active vessel: set it up and engage
            autopilot.reference_frame = vessel.surface_reference_frame
            autopilot.target_roll = float('nan')
            autopilot.engaged = True       # kRPC 0.7: a property, not engage()
            self.hold_vessel = vessel
        autopilot.target_pitch_and_heading(*self.wanted_hold)
        self.link.hold_engaged = True

    def continue_hold(self):
        """Called on every loop: a new active vessel (undocking, a vessel switch) takes the hold over."""
        if self.wanted_hold is not None and not self.hold_refused and self.hold_vessel != self.link.vessel:
            self._apply_hold_safely()

    def continue_sas_mode(self):
        """Called on every loop: set the wanted SAS mode again when it is due."""
        now = time.monotonic()
        if self.sas_mode_set_again_at and now >= self.sas_mode_set_again_at[0]:
            self.sas_mode_set_again_at.pop(0)
            self._apply_sas_mode()

    def follow_sas_mode(self, vessel):
        """Called with every tlm/vessel: once nothing is left to set, the game's mode is the one to keep, whatever
        changed it (KSP's own buttons, a node deleted, a mode refused), so that SAS coming on again does not bring
        back an old one."""
        settled = time.monotonic() - self.sas_mode_applied_at > SAS_MODE_SETTLES_S
        if vessel and vessel.get('sas_mode') and not self.sas_mode_set_again_at and settled:
            self.wanted_sas_mode = vessel['sas_mode']

    def speed_mode(self, request):
        """{'mode': 'orbit' | 'surface' | 'target'}: the navball's speed reference, which PRO and RETRO follow."""
        mode = request.get('mode')
        if mode in SPEED_MODES:
            self.link.vessel.control.speed_mode = getattr(self.link.space_center.SpeedMode, mode)

    # ---------- systems ----------
    def solar_panels(self, request):
        for panel in self.link.parts.solar_panels:
            panel.deployed = bool(request.get('on'))

    def fuel_cells(self, request):
        """Start or stop every fuel cell (stock: the Fuel Cell and Fuel Cell Array resource converters)."""
        for converter, index in self.link.parts.fuel_cells:
            if request.get('on'):
                converter.start(index)
            else:
                converter.stop(index)

    def reaction_wheels(self, request):
        """Switch every reaction wheel on or off (the pods' own included); SAS then has only RCS to turn with."""
        for wheel in self.link.parts.reaction_wheels:
            wheel.active = bool(request.get('on'))

    def antennas(self, request):
        for antenna in self.link.parts.antennas:
            antenna.deployed = bool(request.get('on'))

    def action_group(self, request):
        """{'n': 1..10}: toggle that action group (kRPC calls the tenth one 0)."""
        number = int(request.get('n', 0))
        if 1 <= number <= 10:
            self.link.vessel.control.toggle_action_group(number % 10)

    def parachutes(self, request):
        for parachute in self.link.parts.parachutes:
            if parachute.state.name in ('stowed', 'armed'):
                parachute.deploy()

    def maneuver_node(self, request):
        """Replace whatever node exists: the PAD is the one maneuver, so a node made in map view goes too."""
        control = self.link.vessel.control
        control.remove_nodes()
        if request.get('clear') or request.get('ut', 0) <= self.link.universal_time():
            return
        prograde, normal, radial = (float(component) for component in request['dv'])
        control.add_node(float(request['ut']), prograde=prograde, normal=normal, radial=radial)

    # ---------- science ----------
    def science(self, request):
        """{'all': true}: run every experiment that can run; {'index', 'action'}: run, transmit, dump or reset one."""
        watched = self.link.parts.experiments
        if request.get('all'):
            for item in watched:
                if item.available() and not item.has_data() and not item.inoperable():
                    item.experiment.run()
        elif request.get('action') in SCIENCE_ACTIONS:
            getattr(watched[int(request['index'])].experiment, request['action'])()

    # ---------- the CM and the LM ----------
    def station(self, request):
        """{'to': 'cm' | 'lm'}: the crew goes across and the craft is flown from that capsule; with
        'controls_only', the crew stays where it is."""
        if request.get('to') in STATIONS:
            self.link.station.go_to(request['to'], self.link, move_crew=not request.get('controls_only'))

    # ---------- game ----------
    def pause(self, request):
        self.link.connection.krpc.paused = bool(request.get('on'))

    def save_or_load(self, request):
        """Quick save, quick load, or back to the launch of this flight."""
        if request.get('quicksave'):
            self.link.space_center.quicksave()
        elif request.get('quickload'):
            self.link.space_center.quickload()      # the vessel object changes: the main loop binds again
        elif request.get('revert') and self.link.space_center.can_revert_to_launch():
            self.link.space_center.revert_to_launch()   # the same: a new vessel object

    def warp(self, request):
        """{'to_ut'}: warp to a time (worked on by continue_warp_to); {'step': ±1} or {'stop'}: manual warp."""
        space_center, vessel = self.link.space_center, self.link.vessel
        if 'to_ut' in request:
            self.link.warp_to_universal_time = float(request['to_ut'])
            return
        self.link.warp_to_universal_time = None     # a manual command cancels a warp-to
        if request.get('stop'):
            space_center.rails_warp_factor = 0
            space_center.physics_warp_factor = 0
            return
        step = int(request.get('step', 0))
        body = vessel.orbit.body
        in_atmosphere = body.has_atmosphere and vessel.flight().mean_altitude < body.atmosphere_depth
        # KSP only allows physics warp in the atmosphere
        if space_center.warp_mode.name == 'physics' or (space_center.rails_warp_factor == 0 and in_atmosphere):
            space_center.physics_warp_factor = clamp(space_center.physics_warp_factor + step, 0, PHYSICS_WARP_MAX_FACTOR)
        else:
            space_center.rails_warp_factor = clamp(space_center.rails_warp_factor + step, 0, len(RAILS_WARP_RATES) - 1)

    def continue_warp_to(self):
        """Called on every loop: pick the rails warp rate from the time left. (kRPC's own warp_to blocks until it
        arrives, which would freeze the telemetry.) Done when under about 20 s are left."""
        link = self.link
        if link.warp_to_universal_time is None:
            return
        seconds_left = link.warp_to_universal_time - link.universal_time()
        usable = [factor for factor, rate in enumerate(RAILS_WARP_RATES) if rate * WARP_TO_SECONDS_AHEAD <= seconds_left]
        wanted_factor = max(usable, default=0)
        if wanted_factor == 0:
            link.warp_to_universal_time = None
        space_center = link.space_center
        wanted_factor = min(wanted_factor, space_center.maximum_rails_warp_factor)   # KSP limits warp at low altitude
        if space_center.rails_warp_factor != wanted_factor:
            space_center.rails_warp_factor = wanted_factor
