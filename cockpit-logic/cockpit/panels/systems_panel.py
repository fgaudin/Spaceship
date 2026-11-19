"""The sys bus: electrical, propellant, life support, event timer, recovery, reentry, time warp, save, lights."""

from .. import settings as S
from ..alarms import fraction_left
from ..display_format import fit_number, format_event_time
from ..messages import PanelOutputs, switch_lamp
from ..performance import burn_time, life_support_hours, rcs_delta_v, time_to_atmosphere

SWITCHES_WITH_LAMP = ('solar', 'brakes', 'fuel_cell', 'lights')
LAMPS = ['lamp_chute', 'lamp_revert', 'lamp_05g', 'lamp_chute_safe', 'lamp_chute_risky', 'lamp_chute_unsafe', 'led_chute_armed', 'led_warp', 'led_evt_run', 'led_pause',
         *(f'led_{switch}' for switch in SWITCHES_WITH_LAMP)]
DISPLAYS = ['disp_ec', 'disp_ec_rate', 'disp_evt', 'disp_warp', 'disp_outside', 'disp_pressure', 'disp_burn_time',
            'disp_rcs_dv', 'disp_ls_food', 'disp_ls_water', 'disp_ls_oxygen', 'disp_crew', 'disp_heat', 'disp_to_atm']
BARS = ['bar_ec', 'bar_lf', 'bar_ox', 'bar_mono', 'bar_xenon', 'bar_ablator', 'bar_ls_food', 'bar_ls_water',
        'bar_ls_oxygen']
LOCAL_SWITCHES = ('cabin_light', 'backlight', 'fan')     # the cockpit's own: nothing for the game (the fan: no effect yet)
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
        return cockpit.command('cmd/game', {control: True}) if change.pressed else []
    if control == 'revert':
        return cockpit.command('cmd/game', {'revert': True}) if change.pressed and cockpit.is_on('revert_arm') else []
    if control in LOCAL_SWITCHES:
        return []
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
        ignition_time = cockpit.burn_computer.pad['tig']
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
    if cockpit.lamp_test():
        outputs.all_lit(LAMPS, DISPLAYS, BARS)
        return
    fresh = cockpit.telemetry_is_fresh()
    vessel, clock = cockpit.vessel, cockpit.clock
    _render_electrical_and_propellant(cockpit, outputs, fresh)
    _render_life_support(cockpit, outputs, fresh)
    _render_event_timer(cockpit, outputs, fresh)

    warp_rate = clock.get('warp') or 1
    outputs.text('disp_warp', f'{warp_rate:g}' if fresh else '----')
    outputs.lamp('led_warp', warp_rate > 1)
    outputs.lamp('led_pause', clock.get('paused'))
    outputs.lamp('led_chute_armed', cockpit.is_on('chute_arm'))
    outputs.lamp('lamp_revert', cockpit.is_on('revert_arm'))
    outputs.lamp('lamp_chute', vessel.get('chute') == 'deployed')
    for switch in SWITCHES_WITH_LAMP:
        outputs.lamp(f'led_{switch}', *switch_lamp(vessel.get(switch), cockpit.switch_wanted(switch)))
    _render_reentry(cockpit, outputs, fresh)
    outside = cockpit.telemetry.get('tlm/thermal', {}).get('outside') if fresh else None
    outputs.text('disp_outside', fit_number(outside, 0, 4, signed=True))
    pressure = cockpit.flight.get('p') if fresh else None
    outputs.text('disp_pressure', fit_number(pressure / 1000 if pressure is not None else None, 2, 4))
    outputs.bar('bar_ablator', fraction_left(cockpit.resources.get('total', {}), 'Ablator') if fresh else 0.0)


def _render_reentry(cockpit, outputs, fresh):
    """The hottest part against its limit, the time to the atmosphere, and what KSP says of opening the chutes now."""
    hottest = cockpit.telemetry.get('tlm/thermal', {}).get('max') if fresh else None
    outputs.text('disp_heat', fit_number(hottest * 100 if hottest is not None else None, 0, 4))
    outputs.text('disp_to_atm', fit_number(time_to_atmosphere(cockpit) if fresh else None, 0, 5))
    flight, vessel = cockpit.flight, cockpit.vessel
    drag_felt = (flight.get('g') or 0) >= S.ENTRY_G_FORCE and not vessel.get('thrust')
    descending = (flight.get('vs') or 0) < 0 and vessel.get('situation') in ('flying', 'sub_orbital')
    outputs.lamp('lamp_05g', fresh and drag_felt and descending)
    safety = (cockpit.injected_failures.chute_reading() or vessel.get('chute_safe')) if fresh else None
    for state in ('safe', 'risky', 'unsafe'):
        outputs.lamp(f'lamp_chute_{state}', safety == state)


def _render_life_support(cockpit, outputs, fresh):
    totals = cockpit.life_support_resources()
    for name, resource in (('food', 'Food'), ('water', 'Water'), ('oxygen', 'Oxygen')):
        outputs.bar(f'bar_ls_{name}', fraction_left(totals, resource) if fresh else 0.0)
        outputs.text(f'disp_ls_{name}', fit_number(life_support_hours(cockpit, resource) if fresh else None, 1, 4))
    crew = cockpit.vessel.get('crew') if fresh else None
    outputs.text('disp_crew', f'{crew:2d}' if crew is not None else '--')


def _render_electrical_and_propellant(cockpit, outputs, fresh):
    totals = cockpit.resources.get('total', {})
    charge = totals.get('ElectricCharge')
    outputs.bar('bar_ec', fraction_left(totals, 'ElectricCharge') if fresh else 0.0)
    # the propellant of the whole vessel; the current stage's fuel is on the ENGINE panel
    for bar, resource in (('bar_lf', 'LiquidFuel'), ('bar_ox', 'Oxidizer'), ('bar_mono', 'MonoPropellant'),
                          ('bar_xenon', 'XenonGas')):
        outputs.bar(bar, fraction_left(totals, resource) if fresh else 0.0)
    outputs.text('disp_burn_time', fit_number(burn_time(cockpit) if fresh else None, 0, 5))
    outputs.text('disp_rcs_dv', fit_number(rcs_delta_v(cockpit) if fresh else None, 1, 4))
    outputs.text('disp_ec', fit_number(charge['amount'], 1, 5) if charge and fresh else '-----')
    outputs.text('disp_ec_rate', fit_number(cockpit.charge_rate, 2, 5, signed=True) if charge and fresh else '-----')


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
