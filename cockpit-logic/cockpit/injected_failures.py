"""Failures the instructor injects (SimSup, sim/failures/<id>) that act on the cockpit itself, because KSP does not
model them: instruments and switches. Failures of the vehicle (engines, RCS, comms) are the plant's.

    false_alarm     {"alarm": "cw_low_fuel"}     that caution or warning lights with no cause
    panel_dark      {"panel": "sys"}             the panel loses power: every output dark, every input dead
    display_frozen  {"output": "eng/disp_alt"}   the display keeps the value it showed when the failure came
    switch_stuck    {"control": "sas"}           the switch or button does nothing
"""
COCKPIT_FAILURES = ('false_alarm', 'panel_dark', 'display_frozen', 'switch_stuck')


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
        return (self.active.get('panel_dark', {}).get('panel') == panel
                or self.active.get('switch_stuck', {}).get('control') == control)

    def apply_to_outputs(self, wanted):
        """Change the wanted outputs in place: a dark panel, a frozen display."""
        dark_panel = self.active.get('panel_dark', {}).get('panel')
        if dark_panel:
            prefix = f'panel/{dark_panel}/out/'
            for topic, payload in wanted.items():
                if topic.startswith(prefix):
                    wanted[topic] = dark(payload)
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
