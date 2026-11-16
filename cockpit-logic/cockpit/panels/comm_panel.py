"""COM panel: the radio link to the ground. AOS (acquisition of signal) and LOS (loss of signal) lamps, signal
strength, the first station or relay on the way, how long the link has been in its present state, and the antennas.
"""
from dataclasses import dataclass

from .. import settings as S
from ..display_format import fit_number, format_event_time
from ..messages import PanelOutputs, switch_lamp

LAMPS = ['lamp_aos', 'lamp_los', 'led_antenna']
DISPLAYS = ['disp_hops', 'disp_link_time']
BARS = ['bar_signal']
NEW_STATE_BLINKS_FOR_S = 10.0       # game time


@dataclass
class LinkWatch:
    """Remembers when the link last changed state, in game time, for the "time in this state" display."""
    link_up: object = None              # None until the first report
    since_universal_time: float = 0.0
    changed: bool = False               # False while the state is the one first seen: its age is then unknown

    def update(self, link_up, universal_time):
        if link_up != self.link_up:
            self.changed = self.link_up is not None
            self.link_up, self.since_universal_time = link_up, universal_time

    def seconds_in_state(self, universal_time):
        return max(0.0, universal_time - self.since_universal_time)


def handle_input(cockpit, change):
    """Commands for a control of this panel, or None when the control belongs to another panel."""
    if change.control == 'antenna':
        # Only when the switch moves: retracting the antennas on a restart could cut the link.
        return cockpit.command('cmd/antenna', {'on': change.on}) if change.moved else []
    return None


def link_state(cockpit):
    """True / False, or None when the plant does not say."""
    comm = cockpit.telemetry.get('tlm/comm', {})
    link_up = comm.get('link', cockpit.vessel.get('comm'))
    return None if link_up is None else bool(link_up)


def track_link(cockpit):
    """Called on every tlm/comm."""
    link_up, universal_time = link_state(cockpit), cockpit.clock.get('ut')
    if link_up is not None and universal_time is not None:
        cockpit.link_watch.update(link_up, universal_time)


def render(cockpit, wanted):
    outputs = PanelOutputs(wanted, S.COMM_PANEL)
    if not cockpit.powered():
        outputs.all_dark(LAMPS, [*DISPLAYS, 'txt_via'], BARS)
        return
    if cockpit.is_on('lamp_test'):
        outputs.all_lit(LAMPS, DISPLAYS, BARS)
        outputs.text('txt_via', '*' * S.STATION_NAME_CHARACTERS)
        return
    comm = cockpit.telemetry.get('tlm/comm', {}) if cockpit.telemetry_is_fresh() else {}
    link_up = link_state(cockpit) if cockpit.telemetry_is_fresh() else None
    watch, universal_time = cockpit.link_watch, cockpit.clock.get('ut')
    seconds_in_state = watch.seconds_in_state(universal_time) if universal_time is not None else None
    just_changed = watch.changed and seconds_in_state is not None and seconds_in_state < NEW_STATE_BLINKS_FOR_S

    outputs.lamp('lamp_aos', link_up is True, blink=just_changed)
    outputs.lamp('lamp_los', link_up is False, blink=just_changed)
    outputs.bar('bar_signal', comm.get('strength') if link_up else 0.0)
    outputs.text('disp_hops', fit_number(comm.get('hops') if link_up else None, 0, 1))
    if link_up is None:
        station = ''
    elif not link_up:
        station = 'NO SIGNAL'
    else:
        # KSP names a ground station "Kerbin: Harvester Massif": the display keeps the station
        station = (comm.get('via') or 'DIRECT').split(': ')[-1].upper()[:S.STATION_NAME_CHARACTERS]
    outputs.text('txt_via', station)
    known_age = link_up is not None and watch.changed and seconds_in_state is not None
    outputs.text('disp_link_time', format_event_time(seconds_in_state) if known_age else '--.--')
    outputs.lamp('led_antenna', *switch_lamp(comm.get('antenna'), cockpit.is_on('antenna')))
