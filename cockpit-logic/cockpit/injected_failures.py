"""Failures the instructor injects (SimSup, sim/failures/<id>) that act on the cockpit itself, because KSP does not
model them: instruments and switches. Failures of the vehicle (engines, RCS, comms) are the plant's.

    false_alarm     {"alarm": "cw_low_fuel"}     that caution or warning lights with no cause
    panel_dark      {"panel", "outputs": ["sys/disp_ec"], "inputs": ["solar"]}   that panel (SimSup looks up its wires)
                                                 loses power: every output dark, every input dead
    display_frozen  {"output": "eng/disp_alt"}   the display keeps the value it showed when the failure came
    switch_stuck    {"control": "sas"}           the switch or button does nothing
    ls_gauge        {"resource": "Oxygen", "reads": "0.05"}   that gauge shows this fraction of full, and its alarms follow
    chute_gauge     {"reads": "safe"}            the chute safety lamps show this
    science_dead    {}                           the SCIENCE controls do nothing
"""
COCKPIT_FAILURES = ('false_alarm', 'panel_dark', 'display_frozen', 'switch_stuck', 'ls_gauge', 'chute_gauge',
                    'science_dead')


class InjectedFailures:
    def __init__(self):
        self.active = {}                # failure id → parameters
        self.frozen_payloads = {}       # topic → the payload it froze on

    def update(self, failure, payload, published):
        """sim/failures/<failure>; `published` is what the cockpit has published so far (to freeze a display)."""
        if failure not in COCKPIT_FAILURES:
            return
        if payload.get('on'):
            self.active[failure] = {key: value for key, value in payload.items() if key != 'on'}
            if failure == 'display_frozen':
                topic = self._output_topic()
                self.frozen_payloads = {topic: published.get(topic)} if topic else {}
        else:
            self.active.pop(failure, None)
            if failure == 'display_frozen':
                self.frozen_payloads = {}

    def _output_topic(self):
        output = self.active.get('display_frozen', {}).get('output', '')
        panel, _, name = output.partition('/')
        return f'panel/{panel}/out/{name}' if panel and name else None

    # ---------- what they change ----------
    def false_alarms(self):
        alarm = self.active.get('false_alarm', {}).get('alarm')
        return {alarm} if alarm else set()

    def input_is_dead(self, panel, control):
        return (control in self.active.get('panel_dark', {}).get('inputs', ())
                or self.active.get('switch_stuck', {}).get('control') == control)

    def life_support_reading(self, name, carried):
        """What the gauge of a life support resource shows: {'amount', 'max'}, wrong under ls_gauge."""
        fault = self.active.get('ls_gauge')
        wanted = str((fault or {}).get('resource', '')).strip().lower()
        if not fault or not carried or name.lower() != {'o2': 'oxygen'}.get(wanted, wanted):
            return carried
        try:
            fraction = max(0.0, min(1.0, float(fault.get('reads'))))
        except (TypeError, ValueError):
            return carried
        return {**carried, 'amount': carried['max'] * fraction}

    def chute_reading(self):
        """The verdict forced on the chute safety lamps, or None."""
        reads = self.active.get('chute_gauge', {}).get('reads')
        return str(reads).strip().lower() if reads else None

    def science_is_dead(self):
        return 'science_dead' in self.active

    def apply_to_outputs(self, wanted):
        """Change the wanted outputs in place: a dark panel, a frozen display."""
        for output in self.active.get('panel_dark', {}).get('outputs', ()):
            bus, _, name = output.partition('/')
            topic = f'panel/{bus}/out/{name}'
            if topic in wanted:
                wanted[topic] = dark(wanted[topic])
        for topic, payload in self.frozen_payloads.items():
            if payload is not None and topic in wanted:
                wanted[topic] = payload


def dark(payload):
    """The unpowered form of an output, whatever its kind."""
    if 'text' in payload:
        return {'text': '', 'blank': True, 'blink': False}
    if 'rows' in payload:
        return {'rows': ['.' * len(row) for row in payload['rows']]}
    if 'v' in payload:
        return {'v': 0.0}
    return {**payload, 'on': False, **({'blink': False} if 'blink' in payload else {})}
