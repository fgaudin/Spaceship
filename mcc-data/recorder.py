"""The flight recorder: one sample of the telemetry a second, and the flight's events, for Mission Control's charts
and its wall display. A page opened mid-flight asks for it all and has the whole flight at once.

A flight starts when the mission clock (MET) starts again from zero: a new launch, or a revert to the launch. A
quickload to an earlier moment of the same flight drops what came after it. Switching vessels keeps the flight: a
separated stage or lander keeps the launch's clock.
"""
from dataclasses import dataclass

MAX_POINTS = 7200           # past it, every other point goes: the whole flight stays, at half the resolution
MAX_EVENTS = 400
NEW_FLIGHT_MET_S = 1.0      # the clock back under this: a new flight
THRUST_ON_FRACTION = 0.01   # of the thrust available
ENGINE_DEBOUNCE_S = 2.0     # an engine must stay on or off this long to be an event
MAX_Q_MIN_PA = 1000.0
MAX_Q_FALL = 0.9            # max Q once the pressure has fallen under 90 % of its peak

# the columns of a sample: name → how it is read from the latest telemetry
COLUMNS = {
    'ut': lambda t: t['tlm/time'].get('ut'),
    'alt': lambda t: t['tlm/flight'].get('alt'),
    'radar': lambda t: t['tlm/flight'].get('radar'),
    'apo': lambda t: t['tlm/orbit'].get('apo'),
    'peri': lambda t: t['tlm/orbit'].get('peri'),
    'spd': lambda t: t['tlm/flight'].get('speed'),
    'vorb': lambda t: t['tlm/flight'].get('v_orb'),
    'vs': lambda t: t['tlm/flight'].get('vs'),
    'q': lambda t: t['tlm/flight'].get('q'),
    'g': lambda t: t['tlm/flight'].get('g'),
    'lat': lambda t: t['tlm/flight'].get('lat'),
    'lon': lambda t: t['tlm/flight'].get('lon'),
    'thr': lambda t: t['tlm/vessel'].get('throttle'),
    'thrust': lambda t: t['tlm/vessel'].get('thrust'),
    'mass': lambda t: t['tlm/vessel'].get('mass'),
    'heat': lambda t: t['tlm/thermal'].get('max'),
    'ec': lambda t: charge_fraction(t['tlm/resources']),
    'body': lambda t: t['tlm/orbit'].get('body'),
}
SITUATION_EVENTS = {
    ('pre_launch', 'flying'): 'LIFTOFF', ('landed', 'flying'): 'LIFTOFF', ('splashed', 'flying'): 'LIFTOFF',
    ('pre_launch', 'sub_orbital'): 'LIFTOFF', ('landed', 'sub_orbital'): 'LIFTOFF',
}
SITUATION_NAMES = {'orbiting': 'ORBIT', 'escaping': 'ESCAPE TRAJECTORY', 'landed': 'TOUCHDOWN', 'splashed': 'SPLASHDOWN',
                   'sub_orbital': 'SUBORBITAL'}


def charge_fraction(resources):
    charge = (resources.get('total') or {}).get('ElectricCharge') or {}
    return charge['amount'] / charge['max'] if charge.get('max') else None


def launch_point(points, met):
    """Where the vessel left the ground at `met`: the last sample before it on the body it climbed from (a stale
    sample from before a revert can name another), else the first sample after. None without one."""
    after = next((point for point in points if point['t'] >= met and point['body']), None)
    body = after['body'] if after else None
    before = [point for point in points if point['t'] <= met and point['body'] == body and point['lat'] is not None]
    chosen = before[-1] if before else after
    if not chosen or chosen['lat'] is None:
        return None
    return {'lat': chosen['lat'], 'lon': chosen['lon'], 'body': chosen['body'], 't': met}


@dataclass
class Event:
    t: float            # MET
    text: str
    kind: str           # 'milestone', 'stage', 'engine', 'comm', 'alarm', 'info'

    def payload(self):
        return {'t': round(self.t, 1), 'text': self.text, 'kind': self.kind}


class Recorder:
    def __init__(self):
        self.latest = {topic: {} for topic in ('tlm/time', 'tlm/flight', 'tlm/orbit', 'tlm/vessel', 'tlm/thermal',
                                               'tlm/resources')}
        self.start_flight()

    def start_flight(self):
        # what was heard before belongs to the flight before (a revert: its orbit can still name the Mun); the
        # clock stays, it is what said a new flight started
        for topic in self.latest:
            if topic != 'tlm/time':
                self.latest[topic] = {}
        self.points = []                # dicts: 't' (MET) and the COLUMNS
        self.events = []
        self.launch = None              # {'lat', 'lon', 'body'}: where it left the ground
        self.flight_number = getattr(self, 'flight_number', 0) + 1
        self.seen = {}                  # the last state of each thing that makes events
        self.engine_since = None        # (on, MET) of a change not yet an event
        self.peak_q = (0.0, None)       # (Pa, MET)

    # ---------- input ----------
    def on_message(self, topic, payload):
        """New telemetry; returns the events it makes (cw/state, tlm/comm, tlm/target make them at once)."""
        if topic in self.latest:
            self.latest[topic] = payload
            return []
        met = self.latest['tlm/time'].get('met')
        if met is None:
            return []
        if topic == 'cw/state':
            active = set(payload.get('active') or [])
            new = sorted(active - self.seen.get('alarms', set()))
            self.seen['alarms'] = active
            return self._add([Event(met, f'C&W {legend}', 'alarm') for legend in new])
        if topic == 'tlm/comm':
            return self._change('link', bool(payload.get('link')), met, lambda on: ('AOS' if on else 'LOS', 'comm'))
        if topic == 'tlm/target':
            return self._change('docked', bool(payload.get('docked')), met,
                                lambda on: ('DOCKED' if on else 'UNDOCKED', 'milestone'))
        return []

    # ---------- one sample a second ----------
    def sample(self):
        """Adds a sample if the mission clock moved on; returns the events found."""
        met = self.latest['tlm/time'].get('met')
        if met is None or not self.latest['tlm/flight']:
            return []
        if self.points and met < self.points[-1]['t'] - NEW_FLIGHT_MET_S:
            if met < NEW_FLIGHT_MET_S:
                self.start_flight()
            else:                                                   # a quickload: back to that moment
                self.points = [point for point in self.points if point['t'] <= met]
                self.events = [event for event in self.events if event.t <= met]
        if self.points and met <= self.points[-1]['t']:
            return []
        point = {'t': round(met, 2)}
        for name, read in COLUMNS.items():
            value = read(self.latest)
            point[name] = round(value, 4) if isinstance(value, float) else value
        previous = self.points[-1] if self.points else None
        self.points.append(point)
        if len(self.points) > MAX_POINTS:
            thinned = self.points[::2]
            self.points = thinned if thinned[-1] is point else thinned + [point]
        return self._events_of(point, previous)

    def _events_of(self, point, previous):
        met, vessel = point['t'], self.latest['tlm/vessel']
        events = []
        situation = vessel.get('situation')
        before = self.seen.get('situation')
        if situation and before and situation != before:
            text = SITUATION_EVENTS.get((before, situation)) or SITUATION_NAMES.get(situation)
            if text == 'LIFTOFF':
                self.launch = launch_point(self.points, met)
            if text:
                events.append(Event(met, text, 'milestone'))
        if situation:
            self.seen['situation'] = situation
        stage = vessel.get('stage')
        if stage is not None and self.seen.get('stage') is not None and stage < self.seen['stage']:
            events.append(Event(met, f'STAGE {stage}', 'stage'))
        if stage is not None:
            self.seen['stage'] = stage
        if point['body'] and self.seen.get('body') and point['body'] != self.seen['body']:
            events.append(Event(met, f'SOI {point["body"].upper()}', 'milestone'))
        if point['body']:
            self.seen['body'] = point['body']
        events += self._engine_event(met, vessel)
        events += self._max_q(point)
        atmosphere = self.latest['tlm/orbit'].get('atm') or 0
        if atmosphere and point['alt'] is not None:
            above = point['alt'] > atmosphere
            events += self._change('above_atmosphere', above, met,
                                   lambda out: ('LEFT THE ATMOSPHERE' if out else 'ENTRY INTERFACE', 'milestone'))
        return self._add(events)

    def _engine_event(self, met, vessel):
        thrust, available = vessel.get('thrust') or 0, vessel.get('thrust_avail') or 0
        on = thrust > THRUST_ON_FRACTION * max(available, 1.0)
        if self.seen.get('engine') is None:
            self.seen['engine'] = on
            return []
        if on == self.seen['engine']:
            self.engine_since = None
            return []
        if self.engine_since is None or self.engine_since[0] != on:
            self.engine_since = (on, met)
        if met - self.engine_since[1] < ENGINE_DEBOUNCE_S:
            return []
        self.seen['engine'], started = on, self.engine_since[1]
        self.engine_since = None
        return [Event(started, 'ENGINE ON' if on else 'ENGINE CUTOFF', 'engine')]

    def _max_q(self, point):
        q = point['q'] or 0
        peak, peak_met = self.peak_q
        if self.seen.get('max_q_done'):
            return []
        if q > peak:
            self.peak_q = (q, point['t'])
            return []
        if peak >= MAX_Q_MIN_PA and q < MAX_Q_FALL * peak:
            self.seen['max_q_done'] = True
            return [Event(peak_met, f'MAX Q {peak / 1000:.1f} kPa', 'milestone')]
        return []

    def _change(self, name, value, met, describe):
        before = self.seen.get(name)
        self.seen[name] = value
        if before is None or before == value:
            return []
        text, kind = describe(value)
        return self._add([Event(met, text, kind)])

    def _add(self, events):
        self.events = (self.events + events)[-MAX_EVENTS:]
        return events

    # ---------- kept on disk, for a restart mid-flight ----------
    def state(self):
        seen = {name: sorted(value) if isinstance(value, set) else value for name, value in self.seen.items()}
        return {'points': self.points, 'events': [event.payload() for event in self.events], 'launch': self.launch,
                'flight_number': self.flight_number, 'seen': seen, 'peak_q': list(self.peak_q)}

    def restore(self, state):
        self.points = state.get('points') or []
        self.events = [Event(event['t'], event['text'], event['kind']) for event in state.get('events') or []]
        self.launch = state.get('launch')
        self.flight_number = state.get('flight_number', 1)
        self.seen = dict(state.get('seen') or {})
        if 'alarms' in self.seen:
            self.seen['alarms'] = set(self.seen['alarms'])
        self.peak_q = tuple(state.get('peak_q') or (0.0, None))
        lift_off = next((event.t for event in self.events if event.text == 'LIFTOFF'), None)
        if self.launch and lift_off is not None:            # saved before launch_point was careful: found again
            self.launch = launch_point(self.points, lift_off) or self.launch

    # ---------- output ----------
    def history(self):
        """mcc/history/<id>: the flight so far, the samples as columns."""
        columns = {'t': [point['t'] for point in self.points]}
        for name in COLUMNS:
            columns[name] = [point[name] for point in self.points]
        return {'flight': self.flight_number, 'launch': self.launch, 'columns': columns,
                'events': [event.payload() for event in self.events]}
