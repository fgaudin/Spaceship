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
from .angle_rates import AngleRates
from .burn_computer import BurnComputer
from .engines import EngineMonitor, propulsion
from .event_timer import EventTimer
from .injected_failures import InjectedFailures
from .messages import Message
from .node_mirror import NodeMirror
from .panels import (aux_panel, comm_panel, computer_panel, engine_panel, hand_controller, rendezvous_panel,
                     science_panel, solo_panel, station_panel, systems_panel)

PANELS_WITH_INPUTS = (engine_panel, systems_panel, computer_panel, rendezvous_panel, comm_panel, aux_panel,
                      science_panel, station_panel, hand_controller)
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
        self.scene = None                       # its game scene there: 'flight', 'editor_vab', ...
        self.published = {}                     # topic → last payload published (only changes go out)
        self.last_commands = {}                 # command topic → (payload, time sent)
        self.acknowledged_alarms = set()        # active alarms whose master button was pressed
        self.condition_started = {}             # condition name → when it became true (see has_lasted)
        self.abort_fired = False
        self.throttle_cut_latched = False       # a cutoff holds the throttle at 0 until the lever is back at idle
        self.sas_mode_retries = 0               # times the SAS mode was sent again since the game last agreed
        self.charge_rate = 0.0                  # EC/s, smoothed
        self.previous_charge_sample = None      # (mission time, amount)
        self.docking_rates = rendezvous_panel.DockingRates()   # yaw, pitch and roll rates against the port
        self.attitude_rates = AngleRates(S.ATTITUDE_RATE_SMOOTHING)   # pitch, heading and roll rates
        self.was_powered = True
        self.burn_computer = BurnComputer()
        self.node_mirror = NodeMirror()
        self.event_timer = EventTimer()
        self.engine_monitor = EngineMonitor()
        self.link_watch = comm_panel.LinkWatch()
        self.cameras = []                       # cam/list: what the camera monitor can show, [{'id', 'name'}]
        self.camera_monitor = {}                # cam/status: {'online', 'playing'}
        self.selected_camera_id = None
        self.selected_experiment = 0            # its place in the list of tlm/science
        self.station_move = station_panel.StationMove()     # CM ⇄ LM: the blackout, then the power-up
        self.injected_failures = InjectedFailures()   # instruments and switches the instructor broke (SimSup)

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
        """Every lamp and display works and the inputs are live: the cockpit has power and is not in the blackout of
        a move between the CM and the LM (station_panel). Otherwise everything is dark and the inputs are dead."""
        return self.has_power() and self.station_move.phase(self.now) != 'dark'

    def has_power(self):
        """The craft has electric charge (and the CB MAIN BUS breaker, when the console has one, is in). A craft with
        no battery at all, or telemetry not in yet, counts as powered."""
        charge = self.resources.get('total', {}).get('ElectricCharge')
        out_of_charge = bool(charge) and (charge.get('max') or 0) > 0 and (charge.get('amount') or 0) < S.NO_CHARGE_BELOW
        return bool(self.inputs.get('cb_main', 1)) and not out_of_charge

    def lamp_test(self):
        """Every lamp and segment lit: the LAMP TEST switch, or the power-up after a move between the CM and LM."""
        return self.is_on('lamp_test') or self.station_move.phase(self.now) == 'lamp test'

    def telemetry_is_fresh(self):
        return self.now - self.last_telemetry_time <= S.TELEMETRY_STALE_AFTER_S

    def is_on(self, control):
        return bool(self.inputs.get(control))

    def mcc_mode(self):
        """The SOLO / MCC switch on MCC: Mission Control flies with the crew, so ORBIT, NAVIGATION and PAD REQUEST
        (what a solo pilot needs in its place) are dark."""
        return self.is_on('mcc_mode')

    def selected(self, rotary, positions):
        """The position a rotary selector points at."""
        return positions[int(self.inputs.get(rotary) or 0) % len(positions)]

    def switch_wanted(self, switch):
        """What the cockpit wants a switch's system to be: the switch. SAS lets go while the rotation stick is off
        centre, as KSP does when the pilot steers with the keyboard."""
        if switch == 'sas' and hand_controller.steering(self):
            return False
        return self.is_on(switch)

    def has_lasted(self, condition_name, is_true, seconds):
        """True once `is_true` has held for `seconds` without interruption."""
        if not is_true:
            self.condition_started.pop(condition_name, None)
            return False
        started = self.condition_started.setdefault(condition_name, self.now)
        return self.now - started >= seconds

    def survey_engines(self):
        return self.engine_monitor.survey(self.telemetry.get('tlm/engines', {}), self.vessel)

    def propulsion(self):
        """(thrust at full throttle, specific impulse), also before ignition; see engines.propulsion."""
        return propulsion(self.telemetry.get('tlm/engines', {}), self.vessel, self.flight)

    def life_support_resources(self):
        """Food, water and oxygen as the gauges show them (SimSup can make one read wrong)."""
        totals = self.resources.get('total', {})
        return {name: self.injected_failures.life_support_reading(name, totals[name])
                for name in S.LIFE_SUPPORT_USE_PER_KERBAL_S if name in totals}

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
        elif topic == 'pad/uplink':                 # Mission Control reads up a PAD
            self.burn_computer.receive_uplink(payload)
        elif levels[0] == 'tlm':
            commands = self._on_telemetry(topic, payload)
        elif topic == 'gateway/status':
            self.link_up = bool(payload.get('connected'))
            self.scene = payload.get('scene')
        elif topic.startswith('sim/failures/'):
            self.injected_failures.update(topic.rsplit('/', 1)[1], payload, self.published)
        elif topic == 'fd/status':
            self.telemetry['fd/status'] = payload        # not telemetry from the plant: not counted as fresh
        elif topic == 'cam/list':
            self.cameras = payload.get('cameras') or []
        elif topic == 'cam/status':
            self.camera_monitor = payload
        return commands + self._on_power_change() + self.render()

    def _on_power_change(self):
        """Losing power (breaker out or no charge left) must still stop the engine and release the sticks."""
        powered, was_powered = self.powered(), self.was_powered
        self.was_powered = powered
        if was_powered and not powered:
            return self.command('cmd/throttle', {'v': 0.0}) + hand_controller.release(self)
        return []

    def _on_panel_input(self, panel, control, value):
        # Keypads send each key press on one input; the value is the key.
        if self.injected_failures.input_is_dead(panel, control):
            return []                           # a dead panel or a stuck switch: the input never arrives
        if control == 'key':
            if panel == S.COMPUTER_PANEL:
                return computer_panel.press_key(self, str(value))
            return []
        change = ControlChange(control, self.inputs.get(control), value)
        self.inputs[control] = value
        if control in ('master_alarm', 'master_caution') and change.pressed:
            self._acknowledge(warnings=control == 'master_alarm')
        if not self.powered():
            return []                           # no power: the inputs are dead (see _on_power_change)
        for panel_module in PANELS_WITH_INPUTS:
            commands = panel_module.handle_input(self, change)
            if commands is not None:
                return commands
        if control in S.TOGGLE_COMMANDS and value is not None:
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
        elif topic == 'tlm/comm':
            comm_panel.track_link(self)
        elif topic == 'tlm/attitude':
            angles = {name: payload[name] for name in ('pitch', 'heading', 'roll') if payload.get(name) is not None}
            self.attitude_rates.track(angles if len(angles) == 3 else None, self.clock.get('ut'))
        elif topic == 'tlm/target':
            self.docking_rates.track(payload.get('port'), self.clock.get('met'))
        return []

    def _count_burn(self):
        """Advance the burn computer's Δv counter; when it reaches the PAD's Δv, cut the throttle."""
        was_cut = self.burn_computer.cutoff
        self.burn_computer.count_delta_v(self.telemetry)
        if not self.burn_computer.cutoff or was_cut:
            return []
        # The burn is over: remove the node too, so that SAS does not chase the residual.
        self.node_mirror.forget()
        return self.cut_throttle() + self.command('cmd/node', {'clear': True})

    def tick(self, now):
        """Periodic work: mirror the PAD to the game, and re-command "panel wins" switches the game disagrees with."""
        self.now = now
        commands = station_panel.tick(self) + self._on_power_change()
        if self.powered() and self.telemetry_is_fresh():
            commands += self.node_mirror.pad_to_node(self)
            for switch in S.PANEL_WINS:
                wanted, field = self.switch_wanted(switch), S.SWITCH_TELEMETRY.get(switch, switch)
                disagrees = field in self.vessel and bool(self.vessel[field]) != wanted
                if disagrees and self.seconds_since_command(S.TOGGLE_COMMANDS[switch]) >= S.REASSERT_EVERY_S:
                    commands += self.command(S.TOGGLE_COMMANDS[switch], {'on': wanted})
            commands += self._reassert_sas_mode()
            commands += self._reassert_throttle()
        return commands + self.render()

    def _reassert_throttle(self):
        """The throttle last commanded wins over the game: a gateway that restarts, or a save that loads, leaves
        the game's throttle somewhere else. Not during time warp, when KSP holds it at zero."""
        last_command, game_throttle = self.last_commands.get('cmd/throttle'), self.vessel.get('throttle')
        if last_command is None or game_throttle is None or (self.clock.get('warp') or 1) > 1:
            return []
        disagrees = abs(game_throttle - last_command[0]['v']) > S.THROTTLE_DISAGREE_ABOVE
        if not disagrees or self.seconds_since_command('cmd/throttle') < S.REASSERT_EVERY_S:
            return []
        return self.command('cmd/throttle', last_command[0])

    def _reassert_sas_mode(self):
        """The SAS mode last commanded wins over the game: KSP falls back to stability when SAS is switched on, and
        can drop a mode set in the very frame its reference appears. Only a few tries, because the game refuses for
        good a mode that has no reference (no node, no target)."""
        last_command, game_mode = self.last_commands.get('cmd/sas_mode'), self.vessel.get('sas_mode')
        if last_command is None or game_mode is None or game_mode == last_command[0]['mode']:
            self.sas_mode_retries = 0           # nothing commanded yet, SAS off, or the game agrees
            return []
        if self.sas_mode_retries >= S.SAS_MODE_RETRIES or self.seconds_since_command('cmd/sas_mode') < S.REASSERT_EVERY_S:
            return []
        self.sas_mode_retries += 1
        return self.command('cmd/sas_mode', last_command[0])

    def reset(self):
        """sim/reset: a new flight. Switch positions, the link and the telemetry are facts about the world and are
        kept; what the cockpit latched or remembered is cleared."""
        self.abort_fired = False
        self.throttle_cut_latched = False
        self.acknowledged_alarms.clear()
        self.condition_started.clear()
        self.last_commands.clear()
        self.burn_computer = BurnComputer()
        self.burn_computer.arm(self.is_on('burn_arm'))
        self.node_mirror = NodeMirror()
        self.event_timer = EventTimer()
        self.engine_monitor = EngineMonitor()
        self.link_watch = comm_panel.LinkWatch()
        self.docking_rates = rendezvous_panel.DockingRates()
        self.attitude_rates = AngleRates(S.ATTITUDE_RATE_SMOOTHING)
        self.station_move.stop()
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
        comm_panel.render(self, wanted)
        aux_panel.render(self, wanted)
        solo_panel.render(self, wanted)
        science_panel.render(self, wanted)
        station_panel.render(self, wanted)
        wanted['cam/select'] = aux_panel.camera_selection(self)
        wanted.update(station_panel.window_cameras(self))
        wanted['cmp/pad'] = self._pad_summary()
        wanted['cw/state'] = self._alarm_summary(active, unacknowledged)
        powered = self.powered()
        wanted['cockpit/power'] = {'on': powered}
        wanted['cockpit/lighting'] = {'cabin': powered and self.is_on('cabin_light'),
                                      'backlight': powered and self.is_on('backlight')}

        self.injected_failures.apply_to_outputs(wanted)
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
