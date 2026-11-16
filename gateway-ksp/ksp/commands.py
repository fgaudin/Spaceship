"""cmd/* messages from the cockpit, turned into kRPC calls (protocol/topics.md lists the payloads)."""
import time

from .target import control_from_port, select_target, undock
from .vessel_link import SAS_MODE_TO_KRPC

RAILS_WARP_RATES = [1, 5, 10, 50, 100, 1000, 10000, 100000]     # KSP's rails warp factors 0 to 7
PHYSICS_WARP_MAX_FACTOR = 3
WARP_TO_SECONDS_AHEAD = 4       # warp at a rate only while the time left is at least this many seconds of it
ACTION_GROUP_SWITCHES = {'cmd/sas': 'sas', 'cmd/rcs': 'rcs', 'cmd/gear': 'gear', 'cmd/lights': 'lights',
                         'cmd/brakes': 'brakes'}


def clamp(value, low, high):
    return max(low, min(high, value))


class CommandHandler:
    def __init__(self, link):
        self.link = link
        self.handlers = {
            'cmd/throttle': self.throttle, 'cmd/stage': self.stage, 'cmd/abort': self.abort,
            'cmd/solar': self.solar_panels, 'cmd/chute': self.parachutes, 'cmd/sas_mode': self.sas_mode,
            'cmd/thrust_limit': self.thrust_limit, 'cmd/gimbal': self.gimbal_lock,
            'cmd/target': lambda request: select_target(self.link, request),
            'cmd/undock': lambda request: undock(self.link),
            'cmd/control_from': lambda request: control_from_port(self.link, bool(request.get('port'))),
            'cmd/node': self.maneuver_node, 'cmd/pause': self.pause, 'cmd/game': self.save_or_load,
            'cmd/warp': self.warp,
        }

    def run(self, topic, request):
        if topic in ACTION_GROUP_SWITCHES:
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

    def sas_mode(self, request):
        mode = request.get('mode', 'stability')
        if mode not in SAS_MODE_TO_KRPC:
            return
        try:
            self.link.vessel.control.sas_mode = getattr(self.link.space_center.SASMode, SAS_MODE_TO_KRPC[mode])
        except Exception as error:          # e.g. a mode this pilot or probe core cannot hold
            print('sas_mode refused:', mode, error, flush=True)

    # ---------- systems ----------
    def solar_panels(self, request):
        for panel in self.link.parts.solar_panels:
            panel.deployed = bool(request.get('on'))

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

    # ---------- game ----------
    def pause(self, request):
        self.link.connection.krpc.paused = bool(request.get('on'))

    def save_or_load(self, request):
        if request.get('quicksave'):
            self.link.space_center.quicksave()
        elif request.get('quickload'):
            self.link.space_center.quickload()      # the vessel object changes: the main loop binds again

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
