"""Probe sequencer: the stored program of an uncrewed probe, flown by the cockpit logic in probe mode.

The probe control room (panels/virtual/probe.html) uplinks a program; GO starts it. The steps run one after the
other, each when its time comes: `t` seconds after GO, at mission time `met`, or `burnout` seconds after the engines
the next staging will drop have run out of propellant (see burnout_engines). Nothing steers the probe but what
the students wrote: the steps are KSP's own controls (staging, throttle, a pitch-over input held for some seconds,
SAS and its modes) and burns cut off by the burn computer on accumulated Δv.

    sequencer = ProbeSequencer()
    sequencer.load(cockpit, {'name': 'hop', 'steps': [{'t': 0, 'do': 'throttle', 'v': 1}, {'t': 1, 'do': 'stage'}]})
    sequencer.execute(cockpit, {'do': 'go'})        # or 'stop', 'clear'
    commands = sequencer.tick(cockpit)               # four times a second
    sequencer.summary()                              # probe/sequencer

Steps ({'t', 'met' or 'burnout', 'do', ...}):
    stage                                   next stage
    throttle   v 0..1
    sas        on                           SAS on (stability) or off
    sas_mode   mode                         SAS on, in that mode (settings.SAS_MODES)
    kick       pitch, yaw, roll −1..1, s    SAS off, those control inputs held s seconds, then centred and SAS on
    burn       dv [prograde, normal, radial], throttle (default 1); met only: the TIG. Its PAD is loaded in the burn
               computer as soon as the burn is the next one in the program (the node then exists for SAS MANEUVER);
               at TIG the computer is armed and the throttle opened; the step ends at the computer's cutoff.
    chute                                   deploy the parachutes
    science                                 run every experiment that can run

The uplink needs the radio link (as KSP's CommNet does to control a probe); a program already running carries on
without it. Pure logic: the time is the game's (tlm/time), so pause and time warp are honoured.
"""
import math

from . import settings as S

ACTIONS = ('stage', 'throttle', 'sas', 'sas_mode', 'kick', 'burn', 'chute', 'science')
MAX_STEPS = 60
MAX_KICK_S = 60.0
NO_THRUST_GIVE_UP_S = 10.0          # a burn that counts no Δv this long after TIG is given up
FLAMEOUT_S = 3.0                    # a burn whose thrust stops this long before the cutoff has flamed out
LOG_LENGTH = 40
BURNOUT_CONFIRM_S = 0.5             # the engines must read empty this long (game time) before a burnout counts


class ProgramError(ValueError):
    pass


def _number(step, key, low=-math.inf, high=math.inf, default=None):
    value = step.get(key, default)
    if value is None:
        raise ProgramError(f'{key} missing')
    try:
        value = float(value)
    except (TypeError, ValueError):
        raise ProgramError(f'{key} is not a number') from None
    if not (low <= value <= high) or not math.isfinite(value):
        raise ProgramError(f'{key} out of range ({low} to {high})')
    return value


def parse_program(payload):
    """The program as clean steps, or ProgramError saying which step is wrong and why."""
    steps = payload.get('steps')
    if not isinstance(steps, list) or not steps:
        raise ProgramError('no steps')
    if len(steps) > MAX_STEPS:
        raise ProgramError(f'more than {MAX_STEPS} steps')
    clean = []
    for number, step in enumerate(steps, 1):
        try:
            if not isinstance(step, dict):
                raise ProgramError('not a step')
            action = step.get('do')
            if action not in ACTIONS:
                raise ProgramError(f'unknown action {action!r}')
            triggers = [key for key in ('t', 'met', 'burnout') if key in step]
            if len(triggers) != 1:
                raise ProgramError('give one of t, met or burnout')
            when = {triggers[0]: _number(step, triggers[0], 0, 3600 if triggers[0] == 'burnout' else math.inf)}
            item = {'do': action, **when}
            if action == 'throttle':
                item['v'] = _number(step, 'v', 0, 1)
            elif action == 'sas':
                item['on'] = bool(step.get('on'))
            elif action == 'sas_mode':
                if step.get('mode') not in S.SAS_MODES:
                    raise ProgramError(f"unknown SAS mode {step.get('mode')!r}")
                item['mode'] = step['mode']
            elif action == 'kick':
                item.update({axis: _number(step, axis, -1, 1, 0) for axis in ('pitch', 'yaw', 'roll')})
                item['s'] = _number(step, 's', 0.1, MAX_KICK_S)
            elif action == 'burn':
                if 'met' not in step:
                    raise ProgramError('a burn needs its TIG as met')
                dv = step.get('dv')
                if not isinstance(dv, list) or len(dv) != 3:
                    raise ProgramError('dv needs 3 components')
                item['dv'] = [_number({'c': component}, 'c', -10000, 10000) for component in dv]
                if not any(item['dv']):
                    raise ProgramError('dv is zero')
                item['throttle'] = _number(step, 'throttle', 0.01, 1, 1)
            clean.append(item)
        except ProgramError as error:
            raise ProgramError(f'step {number}: {error}') from None
    return clean


class ProbeSequencer:
    def __init__(self):
        self.name = None
        self.steps = []                 # parse_program's, each with 'status': wait, active, done, failed
        self.state = 'empty'            # empty, loaded, running, done, stopped
        self.current = 0                # the step waiting or running
        self.go_ut = None
        self.step_started_ut = None
        self.burn_loaded = None         # index of the burn whose PAD is in the burn computer
        self.message = ''               # the last answer to the room (a rejection, an error)
        self.log = []                   # [{'met', 'text'}]
        self.burnout_since = None       # game time the watched engines first read empty, for the current step
        self.thrust_seen_ut = None      # last game time a running burn had thrust

    # ---------- the room's requests ----------
    def load(self, cockpit, payload):
        if self.state == 'running':
            return self._refuse(cockpit, 'RUNNING: STOP IT FIRST')
        if not _link_up(cockpit):
            return self._refuse(cockpit, 'NO LINK: UPLINK REFUSED')
        try:
            steps = parse_program(payload)
        except ProgramError as error:
            return self._refuse(cockpit, f'PROGRAM REJECTED: {error}')
        self._release_burn(cockpit)
        self.name = str(payload.get('name') or 'program')[:40]
        self.steps = [{**step, 'status': 'wait'} for step in steps]
        self.state, self.current, self.go_ut, self.step_started_ut = 'loaded', 0, None, None
        self.message = ''
        self._log(cockpit, f'program {self.name} loaded, {len(steps)} steps')
        return []

    def execute(self, cockpit, payload):
        action = payload.get('do')
        if not _link_up(cockpit):
            return self._refuse(cockpit, 'NO LINK: COMMAND REFUSED')
        if action == 'go':
            if self.state != 'loaded':
                return self._refuse(cockpit, 'GO: NO PROGRAM LOADED' if self.state != 'running' else 'ALREADY RUNNING')
            ut = cockpit.clock.get('ut')
            if ut is None:
                return self._refuse(cockpit, 'GO: NO CLOCK')
            self.state, self.go_ut, self.message = 'running', ut, ''
            self._log(cockpit, f'GO {self.name}')
            self._load_next_burn(cockpit)
            return self.tick(cockpit)
        if action == 'stop':
            return self.stop(cockpit, 'STOP')
        if action == 'clear':
            if self.state == 'running':
                return self._refuse(cockpit, 'RUNNING: STOP IT FIRST')
            self._release_burn(cockpit)
            self.__init__()
            return []
        return self._refuse(cockpit, f'unknown command {action!r}')

    def stop(self, cockpit, why):
        """Throttle closed, inputs centred, the burn computer let go; the program keeps its place for the debrief.
        Also after the last step: a program that is done can leave the engine burning (its last step opened the
        throttle), and STOP is how the room cuts it."""
        if self.state == 'running':
            step = self._step()
            if step and step['status'] == 'active':
                step['status'] = 'failed'
            self.state = 'stopped'
        self._log(cockpit, why)
        self._release_burn(cockpit)
        cockpit.throttle_cut_latched = False
        return (cockpit.command('cmd/throttle', {'v': 0.0})
                + cockpit.command('cmd/rotate', {'pitch': 0.0, 'yaw': 0.0, 'roll': 0.0}))

    # ---------- running ----------
    def tick(self, cockpit):
        commands = []
        while self.state == 'running':
            step = self._step()
            if step is None:
                self.state = 'done'
                self._log(cockpit, 'program complete')
                break
            if step['status'] == 'wait':
                if not self._due(cockpit, step):
                    break
                step['status'] = 'active'
                self.step_started_ut = cockpit.clock.get('ut')
                self.burnout_since = None
                commands += self._start(cockpit, step)
            if step['status'] == 'active':
                commands += self._follow(cockpit, step)
            if step['status'] in ('done', 'failed'):
                self.current += 1
                continue
            break
        return commands

    def _due(self, cockpit, step):
        clock = cockpit.clock
        if 'burnout' in step:
            return self._burnout_due(cockpit, step)
        if 't' in step:
            return clock.get('ut') is not None and clock['ut'] - self.go_ut >= step['t']
        return clock.get('met') is not None and clock['met'] >= step['met']

    def _burnout_due(self, cockpit, step):
        ut = cockpit.clock.get('ut')
        if ut is None or not burned_out(cockpit):
            self.burnout_since = None
            return False
        if self.burnout_since is None:
            self.burnout_since = ut
            self._log(cockpit, 'burnout')
        return ut - self.burnout_since >= max(BURNOUT_CONFIRM_S, step['burnout'])

    def _start(self, cockpit, step):
        action = step['do']
        self._log(cockpit, describe(step))
        if action == 'stage':
            step['status'] = 'done'
            return cockpit.command('cmd/stage', {})
        if action == 'throttle':
            step['status'] = 'done'
            cockpit.throttle_cut_latched = False
            return cockpit.command('cmd/throttle', {'v': round(step['v'], 3)})
        if action == 'sas':
            step['status'] = 'done'
            return cockpit.command('cmd/sas', {'on': step['on']})
        if action == 'sas_mode':
            step['status'] = 'done'
            cockpit.sas_mode_choice, cockpit.sas_mode_retries = step['mode'], 0   # the cockpit tries again if refused
            return cockpit.command('cmd/sas', {'on': True}) + cockpit.command('cmd/sas_mode', {'mode': step['mode']})
        if action == 'kick':
            return (cockpit.command('cmd/sas', {'on': False})
                    + cockpit.command('cmd/rotate', {axis: step[axis] for axis in ('pitch', 'yaw', 'roll')}))
        if action == 'burn':
            if self.burn_loaded != self.current:
                self._load_burn(cockpit, self.current)
            cockpit.burn_computer.arm(True)
            self.thrust_seen_ut = None
            cockpit.throttle_cut_latched = False
            return cockpit.command('cmd/throttle', {'v': round(step['throttle'], 3)})
        if action == 'chute':
            step['status'] = 'done'
            return cockpit.command('cmd/chute', {'deploy': True})
        if action == 'science':
            step['status'] = 'done'
            return cockpit.command('cmd/science', {'all': True})
        return []

    def _follow(self, cockpit, step):
        """A step that lasts: a kick until its time is up, a burn until the cutoff."""
        elapsed = (cockpit.clock.get('ut') or self.step_started_ut) - self.step_started_ut
        if step['do'] == 'kick' and elapsed >= step['s']:
            step['status'] = 'done'
            return (cockpit.command('cmd/rotate', {'pitch': 0.0, 'yaw': 0.0, 'roll': 0.0})
                    + cockpit.command('cmd/sas', {'on': True}))
        if step['do'] == 'burn':
            computer = cockpit.burn_computer
            if computer.cutoff:             # the cockpit cut the throttle and removed the node (core._count_burn)
                step['status'] = 'done'
                self._log(cockpit, f'cutoff, residual {-computer.delta_v_to_go():+.1f} m/s')
                self._release_burn(cockpit)
                self._load_next_burn(cockpit)
            ut = cockpit.clock.get('ut')
            if (cockpit.vessel.get('thrust') or 0) > 0:
                self.thrust_seen_ut = ut
            if computer.cutoff:
                pass
            elif (computer.delta_v_counted > 0 and self.thrust_seen_ut is not None and ut is not None
                  and ut - self.thrust_seen_ut >= FLAMEOUT_S):
                # the engine died before the cutoff (no propellant left, or no power): the burn is over, short
                step['status'] = 'failed'
                self._log(cockpit, f'flameout: burn {computer.delta_v_to_go():.1f} m/s short')
                self._release_burn(cockpit)
                self._load_next_burn(cockpit)
                cockpit.throttle_cut_latched = False
                return cockpit.command('cmd/throttle', {'v': 0.0})
            elif computer.delta_v_counted <= 0 and elapsed >= NO_THRUST_GIVE_UP_S:
                step['status'] = 'failed'
                self._log(cockpit, f'burn given up: no thrust {NO_THRUST_GIVE_UP_S:.0f} s after TIG')
                self._release_burn(cockpit)
                self._load_next_burn(cockpit)
                cockpit.throttle_cut_latched = False
                return cockpit.command('cmd/throttle', {'v': 0.0})
        return []

    # ---------- the burn computer ----------
    def _load_next_burn(self, cockpit):
        upcoming = next((index for index in range(self.current, len(self.steps))
                         if self.steps[index]['do'] == 'burn' and self.steps[index]['status'] == 'wait'), None)
        if upcoming is not None:
            self._load_burn(cockpit, upcoming)

    def _load_burn(self, cockpit, index):
        step = self.steps[index]
        cockpit.burn_computer.load(step['met'], step['dv'])
        cockpit.burn_computer.arm(False)
        self.burn_loaded = index

    def _release_burn(self, cockpit):
        if self.burn_loaded is not None:
            cockpit.burn_computer.arm(False)
            cockpit.burn_computer.clear()
            self.burn_loaded = None

    # ---------- reporting ----------
    def _step(self):
        return self.steps[self.current] if self.current < len(self.steps) else None

    def _refuse(self, cockpit, text):
        self.message = text
        self._log(cockpit, text)
        return []

    def _log(self, cockpit, text):
        met = cockpit.clock.get('met')
        self.log.append({'met': None if met is None else round(met, 1), 'text': text})
        del self.log[:-LOG_LENGTH]

    def summary(self):
        """probe/sequencer: only what changes step by step (the page counts the time itself from go_ut)."""
        return {'state': self.state, 'name': self.name, 'current': self.current, 'go_ut': self.go_ut,
                'message': self.message, 'log': list(self.log),
                'steps': [dict(step) for step in self.steps]}


def burnout_engines(engines, stage):
    """The engines a BURNOUT watches: those the next staging will drop (the boosters while the core burns on, the
    core under its upper stage), lit; when it drops none, every lit engine. `engines`: tlm/engines' list; `stage`:
    the vessel's stage number (the next staging is stage − 1)."""
    lit = [engine for engine in engines if engine.get('on') and not engine.get('held')]
    dropped = [engine for engine in lit if engine.get('drop') == stage - 1]
    return dropped or lit


def burned_out(cockpit):
    """The watched engines have all run out of propellant, as the latest tlm/engines says (read after the last
    staging: its stage number must be the vessel's)."""
    report = cockpit.telemetry.get('tlm/engines') or {}
    stage = cockpit.vessel.get('stage')
    if stage is None or report.get('stage') != stage:
        return False
    watched = burnout_engines(report.get('engines') or [], stage)
    return bool(watched) and not any(engine.get('fuel') for engine in watched)


def describe(step):
    action = step['do']
    if action == 'throttle':
        return f"throttle {step['v'] * 100:.0f} %"
    if action == 'sas':
        return f"SAS {'on' if step['on'] else 'off'}"
    if action == 'sas_mode':
        return f"SAS {step['mode']}"
    if action == 'kick':
        inputs = ', '.join(f'{axis} {step[axis]:+.2f}' for axis in ('pitch', 'yaw', 'roll') if step[axis])
        return f"kick {inputs or 'none'} for {step['s']:g} s"
    if action == 'burn':
        return 'burn ' + ' '.join(f'{name} {value:+.1f}' for name, value in zip(('P', 'N', 'R'), step['dv'])) + ' m/s'
    return action


def _link_up(cockpit):
    comm = cockpit.telemetry.get('tlm/comm')
    if comm is not None:
        return bool(comm.get('link'))
    return cockpit.vessel.get('comm') is not False
