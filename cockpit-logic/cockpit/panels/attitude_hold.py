"""ATTITUDE HOLD (its own module, on the eng bus): a pitch and a heading set on two knobs, held by kRPC's autopilot
while HOLD is on, so that a gravity turn can be flown by the numbers ("pitch 45° at 10 km").

    hold_pitch, hold_hdg    knobs, 0..1: −90°..+90° and 0..360°, in whole degrees, shown on disp_hold_pitch/hdg
    hold                    toggle, its LED led_hold

It holds only with SAS off (the two would fight) and lets go while the rotation stick is off centre, as SAS does, then
takes the attitude back. The LED is steady when within HOLD_ON_TARGET_DEG of the set attitude, blinking while it turns
there or cannot hold (SAS on, the stick, no answer from the game).
"""
import math

from .. import settings as S
from ..display_format import fit_number
from ..messages import PanelOutputs
from . import hand_controller

CONTROLS = ('hold', 'hold_pitch', 'hold_hdg')
DISPLAYS = ('disp_hold_pitch', 'disp_hold_hdg')


def set_attitude(cockpit):
    """(pitch, heading) in whole degrees, from the knobs."""
    pitch = round(-90 + 180 * float(cockpit.inputs.get('hold_pitch', S.HOLD_DEFAULT_PITCH_KNOB) or 0.0))
    heading = round(360 * float(cockpit.inputs.get('hold_hdg', S.HOLD_DEFAULT_HEADING_KNOB) or 0.0)) % 360
    return pitch, heading


def can_hold(cockpit):
    """HOLD is on and nothing stops the autopilot: power, SAS off, the stick centred."""
    return (cockpit.is_on('hold') and cockpit.powered() and not cockpit.is_on('sas')
            and not hand_controller.steering(cockpit))


def wanted_command(cockpit):
    pitch, heading = set_attitude(cockpit)
    return {'on': True, 'pitch': pitch, 'heading': heading} if can_hold(cockpit) else {'on': False}


def sync(cockpit):
    """cmd/hold when what the cockpit wants changed (the knobs, the switch, SAS, the stick)."""
    wanted = wanted_command(cockpit)
    last = cockpit.last_commands.get('cmd/hold')
    if last is None and not wanted['on']:
        return []                           # never engaged: nothing to switch off
    return cockpit.command_once('cmd/hold', wanted)


def handle_input(cockpit, change):
    if change.control not in CONTROLS:
        return None
    return sync(cockpit)


def tick(cockpit):
    """SAS switched on or off, and the game's word: send again if the gateway (restarted) does not hold as wanted."""
    commands = sync(cockpit)
    holding = cockpit.vessel.get('hold')
    last = cockpit.last_commands.get('cmd/hold')
    if (not commands and last is not None and holding is not None and cockpit.telemetry_is_fresh()
            and bool(holding) != last[0]['on']
            and cockpit.seconds_since_command('cmd/hold') >= S.REASSERT_EVERY_S):
        commands = cockpit.command('cmd/hold', last[0])
    return commands


def attitude_error(cockpit):
    """Degrees between where the nose points and the set attitude; None without attitude telemetry."""
    attitude = cockpit.telemetry.get('tlm/attitude') or {}
    if attitude.get('pitch') is None or attitude.get('heading') is None:
        return None
    def direction(pitch, heading):
        pitch, heading = math.radians(pitch), math.radians(heading)
        return (math.cos(pitch) * math.cos(heading), math.cos(pitch) * math.sin(heading), math.sin(pitch))
    now, wanted = direction(attitude['pitch'], attitude['heading']), direction(*set_attitude(cockpit))
    return math.degrees(math.acos(max(-1.0, min(1.0, sum(a * b for a, b in zip(now, wanted))))))


def render(cockpit, wanted):
    outputs = PanelOutputs(wanted, S.ENGINE_PANEL)
    if not cockpit.powered():
        outputs.all_dark(['led_hold'], DISPLAYS)
        return
    if cockpit.lamp_test():
        outputs.all_lit(['led_hold'], DISPLAYS)
        return
    pitch, heading = set_attitude(cockpit)
    outputs.text('disp_hold_pitch', fit_number(pitch, 0, 4, signed=True))
    outputs.text('disp_hold_hdg', fit_number(heading, 0, 4))
    if not cockpit.is_on('hold'):
        outputs.lamp('led_hold', False)
        return
    fresh = cockpit.telemetry_is_fresh()
    holding = fresh and can_hold(cockpit) and cockpit.vessel.get('hold', True)
    error = attitude_error(cockpit) if fresh else None
    on_target = holding and error is not None and error <= S.HOLD_ON_TARGET_DEG
    outputs.lamp('led_hold', True, blink=not on_target)
