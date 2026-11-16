"""Failures the instructor injects (SimSup, sim/failures/<id>) that act on the vessel in KSP. The cockpit handles
the instrument failures; battery_short and overheat exist only in the mock plant.

Each failure is applied when it comes on and checked again on every slow cycle, because the crew (or KSP) can undo
it: an engine relit from the game, a new vessel after a save loads.
"""

ENGINE_FAILURES = ('engine_out', 'engine_one_out')
BLOCKED_COMMANDS = {'gimbal_stuck': 'cmd/gimbal', 'chute_fail': 'cmd/chute'}
NO_SIGNAL = {'link': False, 'strength': 0.0, 'hops': 0, 'via': None}


class PlantFailures:
    def __init__(self):
        self.active = {}                # failure id → parameters
        self.failed_engines = []        # kRPC Engine objects held shut down

    def update(self, link, failure, payload):
        """sim/failures/<failure>: apply or repair it."""
        was_on, on = failure in self.active, bool(payload.get('on'))
        if on:
            self.active[failure] = payload
        else:
            self.active.pop(failure, None)
        if link.vessel is None or on == was_on:
            return
        if on:
            self._apply(link, failure)
        else:
            self._repair(link, failure)

    def blocks(self, topic):
        """A crew command that a failure makes useless."""
        return any(BLOCKED_COMMANDS.get(failure) == topic for failure in self.active)

    def keep_applied(self, link):
        """On every slow cycle: an engine relit, a new part list, a reloaded vessel."""
        for failure in self.active:
            try:
                self._apply(link, failure)
            except Exception as error:       # the vessel changed under us: try again on the next cycle
                print('failure not applied:', failure, str(error).splitlines()[0][:120], flush=True)

    def filter_telemetry(self, payloads):
        """What the telemetry failures change in the payloads about to be published."""
        if 'telemetry_freeze' in self.active:
            return {}
        if 'comm_lost' in self.active:
            if 'tlm/comm' in payloads:
                payloads['tlm/comm'] = {**payloads['tlm/comm'], **NO_SIGNAL}
            if 'tlm/vessel' in payloads:
                payloads['tlm/vessel'] = {**payloads['tlm/vessel'], 'comm': False}
        return payloads

    # ---------- applying and repairing ----------
    def _apply(self, link, failure):
        parts = link.vessel.parts
        if failure == 'engine_out':
            self._shut_down([engine for engine in parts.engines if engine.active], keep_previous=True)
        elif failure == 'engine_one_out':
            if not self.failed_engines:
                lit = [engine for engine in parts.engines if engine.active]
                if lit:
                    # the engine farthest from the axis, so that the matrix shows which one
                    reference = link.vessel.reference_frame
                    off_axis = lambda engine: sum(axis ** 2 for axis in engine.part.position(reference)[::2])
                    self._shut_down([max(lit, key=off_axis)], keep_previous=False)
            self._shut_down(self.failed_engines, keep_previous=True)
        elif failure == 'gimbal_stuck':
            for engine in parts.engines:
                if engine.gimballed and not engine.gimbal_locked:
                    engine.gimbal_locked = True
        elif failure == 'rcs_fail':
            for thruster in parts.rcs:
                if thruster.enabled:
                    thruster.enabled = False
        elif failure == 'wheels_fail':
            for wheel in parts.reaction_wheels:
                if wheel.active:
                    wheel.active = False

    def _shut_down(self, engines, keep_previous):
        for engine in engines:
            try:
                if engine.active:
                    engine.active = False
            except Exception:               # staged away or destroyed
                continue
            if engine not in self.failed_engines:
                self.failed_engines.append(engine)
        if not keep_previous:
            self.failed_engines = list(engines)

    def _repair(self, link, failure):
        parts = link.vessel.parts
        if failure in ENGINE_FAILURES:
            # Repaired, not relit: the crew relights them (STAGE, or the engine panel) as after any shutdown.
            if not any(name in self.active for name in ENGINE_FAILURES):
                self.failed_engines = []
        elif failure == 'gimbal_stuck':
            for engine in parts.engines:
                if engine.gimballed and engine.gimbal_locked:
                    engine.gimbal_locked = False
        elif failure == 'rcs_fail':
            for thruster in parts.rcs:
                thruster.enabled = True
        elif failure == 'wheels_fail':
            for wheel in parts.reaction_wheels:
                wheel.active = True
