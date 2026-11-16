"""SYS panel: electrical, propellant and stage figures, event timer, recovery, time warp, game."""
import math

from .. import settings as S
from ..alarms import fraction_left
from ..display_format import fit_number, format_event_time
from ..messages import PanelOutputs, switch_lamp

LAMPS = ['led_solar', 'led_brakes', 'lamp_chute', 'led_chute_armed', 'led_warp', 'led_evt_run', 'led_pause']
DISPLAYS = ['disp_ec', 'disp_ec_rate', 'disp_dv', 'disp_twr', 'disp_evt', 'disp_warp']
BARS = ['bar_ec', 'bar_lf', 'bar_ox', 'bar_mono']
EVENT_TIMER_BUTTONS = ('evt_start', 'evt_stop', 'evt_reset', 'evt_min', 'evt_sec')
CHARGE_RATE_SMOOTHING = 0.3         # weight of the newest sample in the EC/s display


# ---------- inputs ----------
def handle_input(cockpit, change):
    """Commands for a control of this panel, or None when the control belongs to another panel."""
    control = change.control
    if control in EVENT_TIMER_BUTTONS:
        if change.pressed:
            _press_event_timer_button(cockpit, control)
        return []
    if control == 'chute_deploy':
        return cockpit.command('cmd/chute', {'deploy': True}) if change.pressed and cockpit.is_on('chute_arm') else []
    if control in ('warp_up', 'warp_down'):
        return cockpit.command('cmd/warp', {'step': 1 if control == 'warp_up' else -1}) if change.pressed else []
    if control == 'warp_stop':
        return cockpit.command('cmd/warp', {'stop': True}) if change.pressed else []
    if control == 'warp_to':
        return _warp_to_event(cockpit) if change.pressed else []
    if control == 'pause':
        return cockpit.command('cmd/pause', {'on': change.on}) if change.moved else []
    if control in ('quicksave', 'quickload'):
        return cockpit.command('cmd/game', {control: True}) if change.pressed and cockpit.is_on('save_arm') else []
    return None


def _press_event_timer_button(cockpit, button):
    timer, mission_time = cockpit.event_timer, cockpit.clock.get('met') or 0.0
    if button == 'evt_start':
        timer.start(mission_time)
    elif button == 'evt_stop':
        timer.stop(mission_time)
    elif button == 'evt_reset':
        timer.reset()
    elif button == 'evt_min':
        timer.add_preset_minute()
    elif button == 'evt_sec':
        timer.add_preset_seconds()


def _warp_to_event(cockpit):
    """WARP TO EVT: warp until a minute before the event the timer's source selects."""
    time_from_event = time_from_selected_event(cockpit)
    universal_time = cockpit.clock.get('ut')
    if time_from_event is None or universal_time is None or -time_from_event <= S.WARP_TO_EVENT_LEAD_S:
        return []
    event_universal_time = universal_time - time_from_event
    return cockpit.command('cmd/warp', {'to_ut': round(event_universal_time - S.WARP_TO_EVENT_LEAD_S, 1)})


def time_from_selected_event(cockpit):
    """Seconds since the event the timer's source selects (negative before it); None for MAN or an unknown time."""
    source = cockpit.selected('evt_src', S.EVENT_TIMER_SOURCES)
    if source == 'TIG':
        mission_time = cockpit.clock.get('met')
        ignition_time = cockpit.burn_computer.pad['tig'] if cockpit.burn_computer.has_pad() else cockpit.dsky.pad['tig']
        return None if mission_time is None or ignition_time is None else mission_time - ignition_time
    time_to_event = {'APO': 't_apo', 'PERI': 't_peri', 'SOI': 't_soi'}.get(source)
    if time_to_event and cockpit.orbit.get(time_to_event) is not None:
        return -cockpit.orbit[time_to_event]
    return None


# ---------- telemetry ----------
def track_charge_rate(cockpit):
    """EC/s for the display: the change of the total electric charge over game time, smoothed."""
    charge = cockpit.resources.get('total', {}).get('ElectricCharge')
    mission_time = cockpit.clock.get('met')
    if not charge or mission_time is None:
        return
    previous = cockpit.previous_charge_sample
    if previous and mission_time > previous[0]:
        rate = (charge['amount'] - previous[1]) / (mission_time - previous[0])
        cockpit.charge_rate += (rate - cockpit.charge_rate) * CHARGE_RATE_SMOOTHING
    cockpit.previous_charge_sample = (mission_time, charge['amount'])


# ---------- outputs ----------
def render(cockpit, wanted):
    outputs = PanelOutputs(wanted, S.SYSTEMS_PANEL)
    if not cockpit.powered():
        outputs.all_dark(LAMPS, DISPLAYS, BARS)
        return
    if cockpit.is_on('lamp_test'):
        outputs.all_lit(LAMPS, DISPLAYS, BARS)
        return
    fresh = cockpit.telemetry_is_fresh()
    vessel, clock = cockpit.vessel, cockpit.clock
    _render_electrical_and_propellant(cockpit, outputs, fresh)
    _render_event_timer(cockpit, outputs, fresh)

    warp_rate = clock.get('warp') or 1
    outputs.text('disp_warp', f'{warp_rate:g}' if fresh else '----')
    outputs.lamp('led_warp', warp_rate > 1)
    outputs.lamp('led_pause', clock.get('paused'))
    outputs.lamp('led_chute_armed', cockpit.is_on('chute_arm'))
    outputs.lamp('lamp_chute', vessel.get('chute') == 'deployed')
    for switch in ('solar', 'brakes'):
        outputs.lamp(f'led_{switch}', *switch_lamp(vessel.get(switch), cockpit.is_on(switch)))


def _render_electrical_and_propellant(cockpit, outputs, fresh):
    totals, stage = cockpit.resources.get('total', {}), cockpit.resources.get('stage', {})
    charge = totals.get('ElectricCharge')
    stage_fuel = fraction_left(stage, 'LiquidFuel') or fraction_left(stage, 'SolidFuel')
    outputs.bar('bar_ec', fraction_left(totals, 'ElectricCharge') if fresh else 0.0)
    outputs.bar('bar_lf', stage_fuel if fresh else 0.0)
    outputs.bar('bar_ox', fraction_left(stage, 'Oxidizer') if fresh else 0.0)
    outputs.bar('bar_mono', fraction_left(totals, 'MonoPropellant') if fresh else 0.0)
    outputs.text('disp_ec', fit_number(charge['amount'], 1, 5) if charge and fresh else '-----')
    outputs.text('disp_ec_rate', fit_number(cockpit.charge_rate, 2, 5, signed=True) if charge and fresh else '-----')
    outputs.text('disp_dv', fit_number(stage_delta_v(cockpit), 0, 5) if fresh else '-----')
    outputs.text('disp_twr', fit_number(thrust_to_weight(cockpit), 2, 4) if fresh else '----')


def stage_delta_v(cockpit):
    """Δv left in the current stage: the rocket equation on its propellant (course TM-4). None when unknown."""
    stage = cockpit.resources.get('stage', {})
    units = sum(stage.get(name, {}).get('amount', 0.0) for name in ('LiquidFuel', 'Oxidizer', 'SolidFuel'))
    propellant_mass = S.PROPELLANT_KG_PER_UNIT * units
    mass, specific_impulse = cockpit.vessel.get('mass'), cockpit.vessel.get('isp')
    if not (mass and specific_impulse) or mass <= propellant_mass:
        return None
    return specific_impulse * S.STANDARD_GRAVITY * math.log(mass / (mass - propellant_mass))


def thrust_to_weight(cockpit):
    """Available thrust over weight in the local gravity. None when the body or the altitude is unknown."""
    body = S.BODIES.get(cockpit.orbit.get('body'))
    mass, altitude = cockpit.vessel.get('mass'), cockpit.flight.get('alt')
    if not (body and mass) or altitude is None:
        return None
    gravitational_parameter, radius = body
    local_gravity = gravitational_parameter / (radius + altitude) ** 2
    return (cockpit.vessel.get('thrust_avail') or 0.0) / (mass * local_gravity)


def _render_event_timer(cockpit, outputs, fresh):
    timer = cockpit.event_timer
    manual = cockpit.selected('evt_src', S.EVENT_TIMER_SOURCES) == 'MAN'
    reached_zero = False
    if not manual:
        seconds = time_from_selected_event(cockpit)
    elif cockpit.is_on('evt_down'):
        seconds, reached_zero = timer.countdown(cockpit.clock.get('met'))
    else:
        seconds = timer.elapsed(cockpit.clock.get('met'))
    outputs.text('disp_evt', format_event_time(seconds) if seconds is not None and fresh else '--.--',
                 blink=reached_zero)
    if manual:
        # RUN: steady while the stopwatch runs, blinking when a countdown has reached zero
        outputs.lamp('led_evt_run', timer.running or reached_zero, blink=reached_zero)
    else:
        # RUN blinks in the last seconds before the event
        imminent = seconds is not None and -S.EVENT_IMMINENT_S <= seconds < 0
        outputs.lamp('led_evt_run', imminent, blink=True)
