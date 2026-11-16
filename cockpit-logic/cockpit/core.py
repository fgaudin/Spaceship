"""The cockpit: the rules KSP does not model (interlocks, caution and warning, the burn computer, displays).

Pure logic: no I/O, and the time is passed in, so it runs the same in tests and behind MQTT (service.py).

    cockpit = Cockpit()
    messages = cockpit.handle(topic, payload, now)    # for every bus message; returns the Messages to publish
    messages = cockpit.tick(now)                      # about four times a second

Every panel output is computed from the whole state on each call and only the ones that changed are published
(retained), so a panel that reconnects gets the full picture from the broker.
"""
from dataclasses import dataclass

from . import settings as S
from .alarms import ALARMS, active_alarms
from .burn_computer import BurnComputer
from .dsky import Dsky
from .engines import EngineMonitor
from .event_timer import EventTimer
from .messages import Message
from .node_mirror import NodeMirror
from .panels import computer_panel, engine_panel, rendezvous_panel, systems_panel

UPLINK_TOPICS = ('pad/uplink', 'dsky/uplink')       # Mission Control reads up a PAD: both computers get it
PANELS_WITH_INPUTS = (engine_panel, systems_panel, computer_panel, rendezvous_panel)
NEVER = -1e9


@dataclass
class ControlChange:
    """One reported position of a panel control."""
    control: str
    previous: object        # None on the first report after a restart
    value: object

    @property
    def on(self):
        return bool(self.value)

    @property
    def pressed(self):
        """A push button going down."""
        return bool(self.value) and not bool(self.previous)

    @property
    def moved(self):
        """A switch or knob the crew moved, as opposed to the first report of where it already was. Controls that
        set something the craft's builder may have set (limiter, gimbal, pause) only act when moved."""
        return self.previous is not None and self.value is not None and self.value != self.previous


class Cockpit:
    def __init__(self):
        self.now = 0.0
        self.inputs = {'cb_main': 1}            # control name → last reported position (names are unique across panels)
        self.telemetry = {}                     # topic → last payload
        self.last_telemetry_time = NEVER
        self.link_up = False                    # what the plant says in gateway/status
        self.published = {}                     # topic → last payload published (only changes go out)
        self.last_commands = {}                 # command topic → (payload, time sent)
        self.acknowledged_alarms = set()        # active alarms whose master button was pressed
        self.condition_started = {}             # condition name → when it became true (see has_lasted)
        self.abort_fired = False
        self.throttle_cut_latched = False       # a cutoff holds the throttle at 0 until the lever is back at idle
        self.forced_switches = {}               # sas / rcs states an abort imposed, until the pilot moves the switch
        self.charge_rate = 0.0                  # EC/s, smoothed
        self.previous_charge_sample = None      # (mission time, amount)
        self.burn_computer = BurnComputer()
        self.dsky = Dsky()
        self.node_mirror = NodeMirror()
        self.event_timer = EventTimer()
        self.engine_monitor = EngineMonitor()

    # ---------- reading the state ----------
    @property
    def vessel(self):
        return self.telemetry.get('tlm/vessel', {})

    @property
    def flight(self):
        return self.telemetry.get('tlm/flight', {})

    @property
    def orbit(self):
        return self.telemetry.get('tlm/orbit', {})

    @property
    def resources(self):
        return self.telemetry.get('tlm/resources', {})

    @property
    def clock(self):
        return self.telemetry.get('tlm/time', {})

    @property
    def target(self):
        return self.telemetry.get('tlm/target', {})

    def powered(self):
        """CB MAIN BUS: off makes every lamp and display dark and the inputs dead."""
        return bool(self.inputs.get('cb_main', 1))

    def telemetry_is_fresh(self):
        return self.now - self.last_telemetry_time <= S.TELEMETRY_STALE_AFTER_S

    def is_on(self, control):
        return bool(self.inputs.get(control))

    def selected(self, rotary, positions):
        """The position a rotary selector points at."""
        return positions[int(self.inputs.get(rotary) or 0) % len(positions)]

    def switch_wanted(self, switch):
        """What the cockpit wants a switch's system to be: the switch, unless an abort forced it."""
        return self.forced_switches.get(switch, self.is_on(switch))

    def has_lasted(self, condition_name, is_true, seconds):
        """True once `is_true` has held for `seconds` without interruption."""
        if not is_true:
            self.condition_started.pop(condition_name, None)
            return False
        started = self.condition_started.setdefault(condition_name, self.now)
        return self.now - started >= seconds

    def survey_engines(self):
        return self.engine_monitor.survey(self.telemetry.get('tlm/engines', {}).get('engines') or [], self.vessel)

    def active_alarms(self):
        return active_alarms(self)

    # ---------- sending commands to the plant ----------
    def command(self, topic, payload):
        """A command message for the plant, as a list (handy to concatenate)."""
        self.last_commands[topic] = (payload, self.now)
        return [Message(topic, payload, retain=False, qos=0 if topic == 'cmd/throttle' else 1)]

    def command_once(self, topic, payload):
        """Like command(), but not if this is what was sent last on the topic."""
        last = self.last_commands.get(topic)
        return [] if last and last[0] == payload else self.command(topic, payload)

    def seconds_since_command(self, topic):
        last = self.last_commands.get(topic)
        return self.now - last[1] if last else float('inf')

    def command_throttle(self):
        """The throttle follows the lever when ENG ARM is on and no cutoff is latched; otherwise it is 0."""
        lever = float(self.inputs.get('throttle') or 0.0)
        if self.throttle_cut_latched and lever < S.THROTTLE_IDLE_BELOW:
            self.throttle_cut_latched = False       # lever back at idle: the pilot has acknowledged the cutoff
        allowed = self.is_on('eng_arm') and not self.throttle_cut_latched
        throttle = round(max(0.0, min(1.0, lever)), 3) if allowed else 0.0
        last = self.last_commands.get('cmd/throttle')
        if last and abs(last[0]['v'] - throttle) < 0.002:
            return []
        return self.command('cmd/throttle', {'v': throttle})

    def cut_throttle(self):
        self.throttle_cut_latched = True
        return self.command_throttle()

    # ---------- bus messages in ----------
    def handle(self, topic, payload, now):
        self.now = now
        levels = topic.split('/')
        commands = []
        if len(levels) == 4 and levels[0] == 'panel' and levels[2] == 'in':
            commands = self._on_panel_input(panel=levels[1], control=levels[3], value=payload.get('v'))
        elif topic in UPLINK_TOPICS:
            self.dsky.uplink(payload, now)
            self.burn_computer.receive_uplink(payload)
        elif levels[0] == 'tlm':
            commands = self._on_telemetry(topic, payload)
        elif topic == 'gateway/status':
            self.link_up = bool(payload.get('connected'))
        return commands + self.render()

    def _on_panel_input(self, panel, control, value):
        # Keypads send each key press on one input; the value is the key.
        if control == 'key':
            if panel == S.COMPUTER_PANEL:
                return computer_panel.press_key(self, str(value))
            if panel == S.DSKY_PANEL and self.powered() and self.inputs.get('cb_dsky', 1):
                self.dsky.key(str(value), self.now, self.telemetry)
            return []
        change = ControlChange(control, self.inputs.get(control), value)
        self.inputs[control] = value
        if control in ('master_alarm', 'master_caution') and change.pressed:
            self._acknowledge(warnings=control == 'master_alarm')
        if not self.powered():
            # Switching the main bus off must still stop the engine.
            return self.command('cmd/throttle', {'v': 0.0}) if control == 'cb_main' else []
        for panel_module in PANELS_WITH_INPUTS:
            commands = panel_module.handle_input(self, change)
            if commands is not None:
                return commands
        if control in S.TOGGLE_COMMANDS and value is not None:
            self.forced_switches.pop(control, None)         # the pilot takes the switch back after an abort
            return self.command(S.TOGGLE_COMMANDS[control], {'on': change.on})
        return []

    def _acknowledge(self, warnings):
        self.acknowledged_alarms |= {name for name in self.active_alarms() if ALARMS[name].is_warning == warnings}

    def _on_telemetry(self, topic, payload):
        self.telemetry[topic] = payload
        self.last_telemetry_time = self.now
        if topic == 'tlm/vessel':
            return self._count_burn()
        if topic == 'tlm/resources':
            systems_panel.track_charge_rate(self)
        elif topic == 'tlm/node':
            self.node_mirror.node_to_pad(self, payload)
        return []

    def _count_burn(self):
        """Advance both computers' Δv counters; when one reaches its PAD's Δv, cut the throttle."""
        dsky_was_cut, computer_was_cut = self.dsky.cutoff, self.burn_computer.cutoff
        self.dsky.step_time(self.now, self.telemetry)
        self.burn_computer.count_delta_v(self.telemetry)
        commands = []
        if (self.dsky.cutoff and not dsky_was_cut) or (self.burn_computer.cutoff and not computer_was_cut):
            commands += self.cut_throttle()
        if self.burn_computer.cutoff and not computer_was_cut:
            # The burn is over: remove the node, so that SAS does not chase the residual.
            commands += self.command('cmd/node', {'clear': True})
            self.node_mirror.forget()
        return commands

    def tick(self, now):
        """Periodic work: mirror the PAD to the game, and re-command "panel wins" switches the game disagrees with."""
        self.now = now
        commands = []
        if self.powered() and self.telemetry_is_fresh():
            commands += self.node_mirror.pad_to_node(self)
            for switch in S.PANEL_WINS:
                wanted = self.switch_wanted(switch)
                disagrees = switch in self.vessel and bool(self.vessel[switch]) != wanted
                if disagrees and self.seconds_since_command(S.TOGGLE_COMMANDS[switch]) >= S.REASSERT_EVERY_S:
                    commands += self.command(S.TOGGLE_COMMANDS[switch], {'on': wanted})
        return commands + self.render()

    def reset(self):
        """sim/reset: a new flight. Switch positions, the link and the telemetry are facts about the world and are
        kept; what the cockpit latched or remembered is cleared."""
        self.abort_fired = False
        self.throttle_cut_latched = False
        self.forced_switches.clear()
        self.acknowledged_alarms.clear()
        self.condition_started.clear()
        self.last_commands.clear()
        self.dsky = Dsky()
        self.burn_computer = BurnComputer()
        self.burn_computer.arm(self.is_on('burn_arm'))
        self.node_mirror = NodeMirror()
        self.event_timer = EventTimer()
        self.engine_monitor = EngineMonitor()
        return self.render()

    # ---------- panel outputs ----------
    def render(self):
        """Compute every output; return the Messages for those that changed since they were last published."""
        active = self.active_alarms()
        self.acknowledged_alarms &= active      # an alarm that clears needs a new acknowledgement next time
        unacknowledged = active - self.acknowledged_alarms

        wanted = {}
        engine_panel.render(self, wanted, active, unacknowledged)
        systems_panel.render(self, wanted)
        rendezvous_panel.render(self, wanted)
        computer_panel.render(self, wanted)
        dsky_powered = self.powered() and bool(self.inputs.get('cb_dsky', 1))
        for name, payload in self.dsky.render(self.now, self.telemetry, dsky_powered, self.telemetry_is_fresh()).items():
            wanted[f'panel/{S.DSKY_PANEL}/out/{name}'] = payload
        wanted['cmp/pad'] = self._pad_summary()
        wanted['cw/state'] = self._alarm_summary(active, unacknowledged)

        changed = []
        for topic, payload in wanted.items():
            if self.published.get(topic) != payload:
                self.published[topic] = payload
                changed.append(Message(topic, payload, retain=True, qos=1))
        return changed

    def _pad_summary(self):
        """cmp/pad: the loaded PAD, for other stations (Mission Control, a glass attitude display)."""
        computer = self.burn_computer
        return {'tig': computer.pad['tig'], 'dv': list(computer.pad['dv']), 'armed': computer.armed,
                'state': computer.state(self.telemetry)}

    def _alarm_summary(self, active, unacknowledged):
        """cw/state: the alarms by legend, for other stations."""
        powered = self.powered()
        waiting = lambda is_warning: powered and any(ALARMS[name].is_warning == is_warning for name in unacknowledged)
        return {'master_caution': waiting(False), 'master_alarm': waiting(True),
                'active': sorted(ALARMS[name].legend for name in active),
                'unacked': sorted(ALARMS[name].legend for name in unacknowledged)}
