"""SimSup: the simulation supervisor's station, as pure logic (no I/O, time passed in).

In Apollo the SimSup team ran the simulations: they set up the scenario and injected failures without warning the
crew, then debriefed. Here SimSup owns the sim/* topics:

    sim/failures/<id>   {"on", ...parameters}, retained: what is failed now (the gateway, the mock plant and the
                        cockpit each act on the failures that concern them, see FAILURES)
    sim/freeze          {"on"}: the instructor's pause, independent of the crew's PAUSE switch
    sim/load            {"save"}: load a KSP save (the gateway does it)
    sim/simsup/state    retained: what the page shows (failures, armed triggers, scenario, debrief)
    sim/simsup/log      retained: the event log
    sim/simsup/scenarios  retained: the scenarios the page can start

The page sends its requests on sim/simsup/cmd.

    simsup = SimSup(scenarios)
    messages = simsup.handle(topic, payload, now)    # every bus message; returns Messages to publish
    messages = simsup.tick(now)                      # once a second
"""
from dataclasses import dataclass, field

LOG_LIMIT = 2000
THROTTLE_LOG_EVERY_S = 1.0          # a lever or stick moving sends many messages: log one a second per control
NOISY_COMMANDS = {'cmd/throttle', 'cmd/rotate', 'cmd/translate'}
FLIGHT_EVENT_CONTROLS = {'stage', 'abort', 'eng_cutoff', 'master_alarm', 'master_caution', 'undock',
                         'chute_deploy', 'revert'}

# id → (group, title, where it acts, parameters the page asks for)
FAILURES = {
    'engine_out': ('Propulsion', 'All lit engines shut down', 'plant', {}),
    'engine_one_out': ('Propulsion', 'One engine of the cluster shuts down', 'plant', {}),
    'gimbal_stuck': ('Propulsion', 'Gimbals locked (GIMBAL LOCK switch has no effect)', 'plant', {}),
    'rcs_fail': ('Attitude', 'RCS thrusters dead', 'plant', {}),
    'wheels_fail': ('Attitude', 'Reaction wheels dead (SAS weak or useless)', 'plant', {}),
    'chute_fail': ('Recovery', 'Parachutes do not deploy', 'plant', {}),
    'chute_gauge': ('Recovery', 'The chute safety lamps read wrong', 'cockpit', {'reads': 'safe'}),
    'ls_gauge': ('Life support', 'A life support gauge reads wrong (fraction of full)', 'cockpit',
                 {'resource': 'Oxygen', 'reads': '0.05'}),
    'science_dead': ('Science', 'The SCIENCE controls do nothing', 'cockpit', {}),
    'comm_lost': ('Communications', 'Radio link lost (LOS)', 'plant', {}),
    'telemetry_freeze': ('Instruments', 'All telemetry stops (NO LINK)', 'plant', {}),
    'battery_short': ('Electrical', 'Battery short (mock plant only)', 'plant', {}),
    'overheat': ('Thermal', 'Overheat (mock plant only)', 'plant', {}),
    'false_alarm': ('Instruments', 'A caution or warning lights with no cause', 'cockpit', {'alarm': 'cw_low_fuel'}),
    'panel_dark': ('Instruments', 'A panel loses power: dark and dead', 'cockpit', {'panel': 'electrical'}),
    'display_frozen': ('Instruments', 'A display freezes on its last value', 'cockpit', {'output': 'eng/disp_alt'}),
    'switch_stuck': ('Instruments', 'A switch or button does nothing', 'cockpit', {'control': 'sas'}),
}

TRIGGERS = ('now', 'met', 'alt_below', 'alt_above', 'stage')


@dataclass
class Message:
    topic: str
    payload: dict
    retain: bool = False
    qos: int = 1


@dataclass
class ArmedFailure:
    """A failure waiting for its trigger: {'met': s}, {'alt_below': m}, {'alt_above': m} or {'stage': n}."""
    failure: str
    parameters: dict
    trigger: dict
    number: int = 0

    def due(self, telemetry):
        kind, value = next(iter(self.trigger.items()))
        mission_time = telemetry.get('tlm/time', {}).get('met')
        altitude = telemetry.get('tlm/flight', {}).get('alt')
        stage = telemetry.get('tlm/vessel', {}).get('stage')
        situation = telemetry.get('tlm/vessel', {}).get('situation')
        if kind == 'met':
            # MET counts from liftoff: on the pad it is zero and does not move
            return mission_time is not None and situation != 'pre_launch' and mission_time >= value
        if kind == 'alt_below':
            return altitude is not None and altitude < value
        if kind == 'alt_above':
            return altitude is not None and altitude > value
        if kind == 'stage':
            return stage is not None and stage <= value     # KSP counts stages down
        return False

    def describe(self):
        kind, value = next(iter(self.trigger.items()))
        when = {'met': f'at MET {value:.0f} s', 'alt_below': f'below {value:.0f} m', 'alt_above': f'above {value:.0f} m',
                'stage': f'at stage {value}'}.get(kind, kind)
        return f'{self.failure} {when}'


@dataclass
class SimSup:
    scenarios: list = field(default_factory=list)
    panels: dict = field(default_factory=dict)          # panel id → its wires (panel_wiring)
    choices: dict = field(default_factory=dict)         # what the page offers (parameter_choices)
    active: dict = field(default_factory=dict)          # failure id → parameters
    armed: list = field(default_factory=list)           # ArmedFailure
    scenario: str = None                                # title of the scenario started last
    telemetry: dict = field(default_factory=dict)       # topic → last payload
    log: list = field(default_factory=list)             # {'t', 'met', 'kind', 'text'}
    alarms_on: set = field(default_factory=set)
    last_logged: dict = field(default_factory=dict)     # control → wall time last logged (noisy controls)
    held_back: dict = field(default_factory=dict)       # control → (kind, text) not logged yet: the latest value
    debrief: list = field(default_factory=list)         # {'failure', 'met', 'first_ack', 'first_action'}
    frozen: bool = False
    probe_mode: bool = False                            # probe/mode: the probe control room flies, not the crew
    clearance: list = None                              # probe/clearance: the room's groups cleared; None: not known yet
    next_number: int = 1
    now: float = 0.0
    changed: bool = True

    # ---------- bus messages in ----------
    def handle(self, topic, payload, now):
        self.now = now
        messages = []
        if topic == 'sim/simsup/cmd':
            messages += self._request(payload)
        elif topic in ('probe/mode', 'probe/clearance'):
            self._adopt_probe_state(topic, payload)
        elif topic.startswith('tlm/'):
            self.telemetry[topic] = payload
            if topic in ('tlm/time', 'tlm/flight', 'tlm/vessel'):
                messages += self._fire_due()
        elif topic.startswith('panel/') and '/in/' in topic:
            self._log_crew_input(topic, payload)
        elif topic.startswith('cmd/'):
            self._log_command(topic, payload)
            if topic == 'cmd/game' and payload.get('revert'):
                messages += self._flight_reverted()
        elif topic == 'cw/state':
            self._log_alarms(payload)
        return messages + self._state_if_changed()

    def tick(self, now):
        self.now = now
        self._log_held_back()
        return self._fire_due() + self._state_if_changed()

    def _rate_limited(self, key, kind, text):
        """True when `key` was logged under a second ago: then its latest text waits, so that the final value of a
        lever or command (throttle back to 0) is never lost."""
        last = self.last_logged.get(key)
        if last is not None and self.now - last < THROTTLE_LOG_EVERY_S:
            self.held_back[key] = (kind, text)
            return True
        self.last_logged[key] = self.now
        self.held_back.pop(key, None)
        return False

    def _log_held_back(self):
        for key, (kind, text) in list(self.held_back.items()):
            if self.now - self.last_logged.get(key, 0) >= THROTTLE_LOG_EVERY_S:
                del self.held_back[key]
                self.last_logged[key] = self.now
                self._add_log(kind, text)

    def startup(self):
        """Retained messages to publish when the service starts: the scenarios, and no failure left over."""
        messages = [Message('sim/simsup/scenarios', {'scenarios': self.scenarios,
                                                          'failures': failure_catalogue(self.choices)},
                            retain=True)]
        messages += [Message(f'sim/failures/{failure}', {'on': False}, retain=True) for failure in FAILURES]
        return messages + [Message('sim/freeze', {'on': False}, retain=True)] + self._state()

    # ---------- the page's requests ----------
    def _request(self, request):
        action = request.get('action')
        failure, parameters = request.get('failure'), request.get('parameters') or {}
        if action == 'inject' and failure in FAILURES:
            return self._inject(failure, {**FAILURES[failure][3], **parameters})
        if action == 'clear' and failure in self.active:
            return self._clear(failure)
        if action == 'clear_all':
            messages = []
            for name in list(self.active):
                messages += self._clear(name)
            self.armed = []
            self.changed = True
            return messages
        if action == 'arm' and failure in FAILURES and request.get('trigger'):
            self._arm(failure, {**FAILURES[failure][3], **parameters}, request['trigger'])
            return []
        if action == 'disarm':
            self.armed = [armed for armed in self.armed if armed.number != request.get('number')]
            self.changed = True
            return []
        if action == 'freeze':
            self.frozen = bool(request.get('on'))
            self._add_log('simsup', 'FREEZE' if self.frozen else 'UNFREEZE')
            return [Message('sim/freeze', {'on': self.frozen}, retain=True)]
        if action == 'scenario':
            return self._start_scenario(request.get('name'))
        if action == 'load':
            self._add_log('simsup', f"load save {request.get('save')}")
            return [Message('sim/load', {'save': request.get('save')})]
        if action == 'new_session':
            self.log, self.debrief, self.scenario = [], [], None
            self._add_log('simsup', 'new session')
            return []
        if action == 'probe_mode':
            self.probe_mode = bool(request.get('on'))
            self._add_log('simsup', 'PROBE MODE ON' if self.probe_mode else 'PROBE MODE OFF')
            return [Message('probe/mode', {'on': self.probe_mode}, retain=True)]
        if action == 'clearance':
            groups = request.get('groups')
            if not isinstance(groups, list):
                return []
            before = set(self.clearance or [])
            self.clearance = sorted({str(group) for group in groups})
            added, removed = sorted(set(self.clearance) - before), sorted(before - set(self.clearance))
            if added:
                self._add_log('simsup', f"cleared: {', '.join(added)}")
            if removed:
                self._add_log('simsup', f"clearance withdrawn: {', '.join(removed)}")
            return [Message('probe/clearance', {'groups': self.clearance}, retain=True)]
        if action == 'note':
            self._add_log('note', str(request.get('text', ''))[:200])
            return []
        return []

    def _adopt_probe_state(self, topic, payload):
        """Our own retained probe/mode and probe/clearance, read back when the service starts: a restart keeps what
        the instructor had cleared. After that the service's own state is the truth."""
        if topic == 'probe/mode':
            self.probe_mode = bool(payload.get('on'))
        elif self.clearance is None and isinstance(payload.get('groups'), list):
            self.clearance = sorted(str(group) for group in payload['groups'])

    def _arm(self, failure, parameters, trigger):
        if 'now' in trigger:
            return
        armed = ArmedFailure(failure, parameters, dict(trigger), self.next_number)
        self.next_number += 1
        self.armed.append(armed)
        self._add_log('simsup', f'armed: {armed.describe()}')
        self.changed = True

    def _flight_reverted(self):
        """A new start: what had failed is cleared; failures armed and not fired yet still wait for their trigger."""
        self._add_log('simsup', 'flight reverted to launch: active failures cleared')
        messages = []
        for name in list(self.active):
            messages += self._clear(name)
        return messages

    def _inject(self, failure, parameters):
        wiring = {}
        if failure == 'panel_dark':
            wiring = self.panels.get(parameters.get('panel'))
            if wiring is None:
                self._add_log('simsup', f"panel_dark: no panel {parameters.get('panel')!r}")
                return []
        self.active[failure] = parameters
        details = f' {parameters}' if parameters else ''
        self._add_log('failure', f'{failure} ON{details}')
        self.debrief.append({'failure': failure, 'met': self._met(), 'first_ack': None, 'first_action': None})
        self.changed = True
        return [Message(f'sim/failures/{failure}', {'on': True, **parameters, **wiring}, retain=True)]

    def _clear(self, failure):
        self.active.pop(failure, None)
        self._add_log('failure', f'{failure} OFF')
        self.changed = True
        return [Message(f'sim/failures/{failure}', {'on': False}, retain=True)]

    def _start_scenario(self, name):
        scenario = next((each for each in self.scenarios if each.get('name') == name), None)
        if scenario is None:
            return []
        messages = self._request({'action': 'clear_all'})
        self.scenario, self.debrief, self.log = scenario['name'], [], []
        self._add_log('simsup', f"scenario: {scenario['name']}")
        if scenario.get('save'):
            messages.append(Message('sim/load', {'save': scenario['save']}))
        for step in scenario.get('failures', []):
            trigger = step.get('trigger') or {'now': True}
            if 'now' in trigger:
                messages += self._inject(step['failure'], {**FAILURES[step['failure']][3], **step.get('parameters', {})})
            else:
                self._arm(step['failure'], {**FAILURES[step['failure']][3], **step.get('parameters', {})}, trigger)
        return messages

    def _fire_due(self):
        messages = []
        for armed in list(self.armed):
            if armed.due(self.telemetry):
                self.armed.remove(armed)
                self._add_log('simsup', f'trigger: {armed.describe()}')
                messages += self._inject(armed.failure, armed.parameters)
        return messages

    # ---------- the log ----------
    def _met(self):
        return self.telemetry.get('tlm/time', {}).get('met')

    def _add_log(self, kind, text):
        self.log.append({'t': round(self.now, 2), 'met': self._met(), 'kind': kind, 'text': text})
        del self.log[:-LOG_LIMIT]
        self.changed = True

    def _log_crew_input(self, topic, payload):
        _, panel, _, control = topic.split('/', 3)
        value = payload.get('v')
        if control in FLIGHT_EVENT_CONTROLS and not value:
            return                                      # a button's release says nothing new
        text = f'{panel}/{control} = {value}'
        if control not in FLIGHT_EVENT_CONTROLS and control != 'key' and self._rate_limited(control, 'crew', text):
            return
        self._add_log('crew', text)
        for entry in self.debrief:
            if entry['first_action'] is None and control not in ('master_alarm', 'master_caution'):
                entry['first_action'] = self._met()
            if entry['first_ack'] is None and control in ('master_alarm', 'master_caution'):
                entry['first_ack'] = self._met()

    def _log_command(self, topic, payload):
        text = f'{topic} {payload}'
        if topic in NOISY_COMMANDS and self._rate_limited(topic, 'command', text):
            return
        self._add_log('command', text)

    def _log_alarms(self, state):
        active = set(state.get('active') or [])
        for legend in sorted(active - self.alarms_on):
            self._add_log('alarm', f'{legend} ON')
        for legend in sorted(self.alarms_on - active):
            self._add_log('alarm', f'{legend} off')
        self.alarms_on = active

    # ---------- what the page shows ----------
    def _state(self):
        # The page reads the flight itself from tlm/*: this is only what SimSup alone knows.
        state = {
            'scenario': self.scenario, 'frozen': self.frozen,
            'active': [{'failure': name, 'parameters': parameters} for name, parameters in self.active.items()],
            'armed': [{'number': armed.number, 'failure': armed.failure, 'text': armed.describe()} for armed in self.armed],
            'debrief': [{**entry, 'ack_after': _after(entry, 'first_ack'), 'action_after': _after(entry, 'first_action')}
                        for entry in self.debrief],
        }
        return [Message('sim/simsup/state', state, retain=True), Message('sim/simsup/log', {'log': self.log}, retain=True)]

    def _state_if_changed(self):
        if not self.changed:
            return []
        self.changed = False
        return self._state()


def _after(entry, key):
    """Seconds from the failure to the crew's first acknowledgement or action; None until it happens."""
    if entry.get(key) is None or entry.get('met') is None:
        return None
    return round(entry[key] - entry['met'], 1)


def option(value, label=None):
    return {'value': value, 'label': label or value}


# Parameters whose values do not depend on the panels: {failure: {parameter: options}}
FIXED_CHOICES = {
    'ls_gauge': {'resource': [option('Food'), option('Water'), option('Oxygen')],
                 'reads': [option('0', 'empty'), option('0.05', '5 %'), option('0.1', '10 %'), option('0.25', '25 %'),
                           option('0.5', '50 %'), option('1', 'full')]},
    'chute_gauge': {'reads': [option('safe', 'SAFE'), option('risky', 'RISKY'), option('unsafe', 'UNSAFE')]},
}
DISPLAY_TYPES = ('seg7', 'alpha', 'bar')


def parameter_choices(modules):
    """{failure: {parameter: [{'value', 'label'}]}}: what the page offers, read from the panel definitions."""
    panels, alarms, displays, controls = [], [], [], []
    for module in modules:
        for panel in module.get('panels', []):
            title = panel.get('title', panel['id'])
            items = panel.get('items', [])
            if items:
                panels.append(option(panel['id'], title))
            for item in items:
                name = f"{title} · {item.get('label') or item.get('id')}"
                if isinstance(item.get('in'), str):
                    controls.append(option(item['in'], name))
                if item.get('type') in DISPLAY_TYPES and panel.get('bus') and item.get('out'):
                    displays.append(option(f"{panel['bus']}/{item['out']}", name))
                alarms += [option(cell['out'], cell.get('label')) for cell in item.get('cells', [])
                           if cell.get('out', '').startswith('cw_')]
    by_label = lambda options: sorted(options, key=lambda each: each['label'])
    return {**FIXED_CHOICES, 'panel_dark': {'panel': by_label(panels)}, 'false_alarm': {'alarm': by_label(alarms)},
            'display_frozen': {'output': by_label(displays)}, 'switch_stuck': {'control': by_label(controls)}}


def failure_catalogue(choices=None):
    """The failures for the page; `choices` are the values each parameter can take."""
    choices = choices or FIXED_CHOICES
    return [{'id': name, 'group': group, 'title': title, 'where': where, 'parameters': parameters,
             'choices': choices.get(name, {})}
            for name, (group, title, where, parameters) in FAILURES.items()]


def panel_wiring(modules):
    """{panel id: {'outputs': ['<bus>/<output>'], 'inputs': [control]}} from the module definitions: a panel moved to
    another module, or sharing its bus with others, stays one panel."""
    wiring = {}
    for module in modules:
        for panel in module.get('panels', []):
            inputs, outputs = set(), set()
            collect_wires(panel.get('items', []), inputs, outputs)
            bus = panel.get('bus')
            wiring[panel['id']] = {'outputs': sorted(f'{bus}/{name}' for name in outputs) if bus else [],
                                   'inputs': sorted(inputs)}
    return wiring


def collect_wires(node, inputs, outputs):
    if isinstance(node, list):
        for each in node:
            collect_wires(each, inputs, outputs)
    elif isinstance(node, dict):
        for key, value in node.items():
            if key == 'in' and isinstance(value, str):
                inputs.add(value)
            elif key == 'out' and isinstance(value, str):
                outputs.add(value)
            else:
                collect_wires(value, inputs, outputs)
