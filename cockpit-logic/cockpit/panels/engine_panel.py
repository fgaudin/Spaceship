"""ENG panel: caution and warning, main displays, engine and staging, engine status matrix, attitude switches, abort."""
from .. import settings as S
from ..alarms import ALARMS, stage_fuel_fraction
from ..display_format import fit_number, format_mission_time
from ..engines import IDLE, OFF, THRUSTING
from ..messages import PanelOutputs, switch_lamp

SWITCHES_WITH_LAMP = ('sas', 'rcs', 'gear', 'lights')
LAMPS = ['master_alarm', 'master_caution', 'led_eng_arm', 'lamp_stage', 'lamp_abort', 'lamp_cutoff', 'led_gimbal',
         'lamp_contact', 'lamp_05g', *(f'led_{switch}' for switch in SWITCHES_WITH_LAMP),
         *(f'lamp_ref_{mode}' for mode in S.SPEED_MODES), 'led_rcs_fine', *ALARMS]
DISPLAYS = ['disp_a', 'disp_met', 'disp_stage', 'disp_eng_on']
BARS = ['bar_fuel', 'bar_thrust']
MAIN_DISPLAY_DIGITS = 7


# ---------- inputs ----------
def handle_input(cockpit, change):
    """Commands for a control of this panel, or None when the control belongs to another panel."""
    control = change.control
    if control in ('throttle', 'eng_arm', 'cb_main'):
        return cockpit.command_throttle()
    if control == 'eng_cutoff':
        return cockpit.cut_throttle() if change.pressed else []
    if control == 'thrust_lim':
        # Only when the knob moves: limiters set in the VAB are left alone until then.
        if not change.moved:
            return []
        steps = round(1 / S.THRUST_LIMIT_STEP)
        return cockpit.command_once('cmd/thrust_limit', {'v': round(float(change.value) * steps) / steps})
    if control == 'gimbal_lock':
        return cockpit.command('cmd/gimbal', {'locked': change.on}) if change.moved else []
    if control == 'stage':
        return cockpit.command('cmd/stage', {}) if change.pressed and cockpit.is_on('stage_arm') else []
    if control == 'abort':
        return run_abort(cockpit) if change.pressed and cockpit.is_on('abort_arm') else []
    if control == 'speed_ref':
        # Only when moved: KSP changes the reference by itself (to surface low down, to target near one).
        if not change.moved:
            return []
        return cockpit.command('cmd/speed_mode', {'mode': cockpit.selected('speed_ref', S.SPEED_MODES)})
    if control == 'sas_mode':
        if change.value is None:
            return []
        cockpit.sas_mode_retries = 0
        return cockpit.command('cmd/sas_mode', {'mode': S.SAS_MODES[int(change.value) % len(S.SAS_MODES)]})
    return None


def run_abort(cockpit):
    """Run the sequence of the selected abort mode (settings.ABORT_SEQUENCES)."""
    cockpit.abort_fired = True
    commands = []
    for step in S.ABORT_SEQUENCES[cockpit.selected('abort_mode', S.ABORT_MODES)]:
        if step == 'cut_throttle':
            commands += cockpit.cut_throttle()
        elif step == 'abort_group':
            commands += cockpit.command('cmd/abort', {})
        elif step == 'stage':
            commands += cockpit.command('cmd/stage', {})
        elif step in ('sas_hold', 'sas_radial_out'):
            cockpit.forced_switches['sas'] = True
            commands += cockpit.command('cmd/sas', {'on': True})
            commands += cockpit.command('cmd/sas_mode', {'mode': 'radial' if step == 'sas_radial_out' else 'stability'})
        elif step == 'rcs_on':
            cockpit.forced_switches['rcs'] = True
            commands += cockpit.command('cmd/rcs', {'on': True})
    return commands


# ---------- outputs ----------
def render(cockpit, wanted, active_alarms, unacknowledged_alarms):
    outputs = PanelOutputs(wanted, S.ENGINE_PANEL)
    warning_waiting = any(ALARMS[name].is_warning for name in unacknowledged_alarms)
    caution_waiting = any(not ALARMS[name].is_warning for name in unacknowledged_alarms)
    powered, lamp_test = cockpit.powered(), cockpit.is_on('lamp_test')
    outputs.raw('buzzer', {'on': powered and not lamp_test and warning_waiting})

    if not powered:
        outputs.all_dark(LAMPS, DISPLAYS, BARS)
        outputs.raw('mx_eng', {'rows': [OFF * S.ENGINE_GRID_SIZE] * S.ENGINE_GRID_SIZE})
        return
    if lamp_test:
        outputs.all_lit(LAMPS, DISPLAYS, BARS)
        outputs.raw('mx_eng', {'rows': [IDLE * S.ENGINE_GRID_SIZE] * S.ENGINE_GRID_SIZE})
        return

    # caution and warning: an alarm blinks until its master button is pressed, then stays steady while it lasts
    for name in ALARMS:
        outputs.lamp(name, name in active_alarms, blink=name in unacknowledged_alarms)
    outputs.lamp('master_alarm', warning_waiting, blink=True)
    outputs.lamp('master_caution', caution_waiting)

    _render_lamps(cockpit, outputs)
    _render_displays(cockpit, outputs)


def _render_lamps(cockpit, outputs):
    vessel, flight = cockpit.vessel, cockpit.flight
    fresh = cockpit.telemetry_is_fresh()
    outputs.lamp('led_eng_arm', cockpit.is_on('eng_arm'))
    outputs.lamp('lamp_stage', cockpit.is_on('stage_arm'))
    outputs.lamp('lamp_abort', cockpit.abort_fired or cockpit.is_on('abort_arm'), blink=cockpit.abort_fired)
    # Steady while the cutoff holds; blinking while the lever is still up, because the engine restarts only once the
    # lever has been back to idle.
    lever_up = float(cockpit.inputs.get('throttle') or 0.0) >= S.THROTTLE_IDLE_BELOW
    outputs.lamp('lamp_cutoff', cockpit.throttle_cut_latched, blink=lever_up)
    outputs.lamp('led_gimbal', cockpit.telemetry.get('tlm/engines', {}).get('gimbal_locked'))
    for switch in SWITCHES_WITH_LAMP:
        outputs.lamp(f'led_{switch}', *switch_lamp(vessel.get(switch), cockpit.switch_wanted(switch)))
    outputs.lamp('led_rcs_fine', cockpit.is_on('rcs_fine'))
    # The game's speed reference, which the knob may not match: KSP changes it by itself.
    for mode in S.SPEED_MODES:
        outputs.lamp(f'lamp_ref_{mode}', fresh and vessel.get('speed_mode') == mode)

    # event lights
    landed = bool(vessel.get('contact')) and vessel.get('situation') != 'pre_launch'    # the pad is not a landing
    outputs.lamp('lamp_contact', fresh and landed)
    drag_felt = (flight.get('g') or 0) >= S.ENTRY_G_FORCE and not vessel.get('thrust')
    descending = (flight.get('vs') or 0) < 0 and vessel.get('situation') in ('flying', 'sub_orbital')
    outputs.lamp('lamp_05g', fresh and drag_felt and descending)


def _render_displays(cockpit, outputs):
    vessel = cockpit.vessel
    if not cockpit.telemetry_is_fresh():
        outputs.text('disp_a', '-' * MAIN_DISPLAY_DIGITS)
        outputs.text('disp_met', '--.--.--')
        outputs.text('disp_stage', '--')
        outputs.text('disp_eng_on', '--')
        outputs.bar('bar_fuel', 0.0)
        outputs.bar('bar_thrust', 0.0)
        outputs.raw('mx_eng', {'rows': [OFF * S.ENGINE_GRID_SIZE] * S.ENGINE_GRID_SIZE})
        return
    outputs.text('disp_a', main_display_text(cockpit))
    mission_time = cockpit.clock.get('met')
    outputs.text('disp_met', format_mission_time(mission_time) if mission_time is not None else '--.--.--')
    stage = vessel.get('stage')
    outputs.text('disp_stage', f'{stage:2d}' if isinstance(stage, int) else '--')
    outputs.bar('bar_fuel', stage_fuel_fraction(cockpit.resources))
    thrust_available = vessel.get('thrust_avail') or 0
    outputs.bar('bar_thrust', vessel.get('thrust', 0) / thrust_available if thrust_available > 0 else 0.0)

    survey = cockpit.survey_engines()
    outputs.raw('mx_eng', {'rows': survey.rows()})
    engines_reported = 'tlm/engines' in cockpit.telemetry
    outputs.text('disp_eng_on', f'{survey.count(THRUSTING):2d}' if engines_reported else '--')


def main_display_text(cockpit):
    """DISP A: the quantity its selector points at. Altitudes in km, mass in t, speeds in m/s."""
    source = cockpit.selected('disp_sel', S.MAIN_DISPLAY_SOURCES)
    flight, orbit, vessel = cockpit.flight, cockpit.orbit, cockpit.vessel
    value, scale, decimals = {
        'ALT': (flight.get('alt'), 1000.0, 2),
        'APO': (orbit.get('apo'), 1000.0, 2),
        'PERI': (orbit.get('peri'), 1000.0, 2),
        'VEL': (flight.get('speed'), 1.0, 1),
        'V/S': (flight.get('vs'), 1.0, 1),
        'MASS': (vessel.get('mass'), 1000.0, 3),
    }[source]
    if value is None:
        return '-' * MAIN_DISPLAY_DIGITS
    return fit_number(value / scale, decimals, MAIN_DISPLAY_DIGITS)
