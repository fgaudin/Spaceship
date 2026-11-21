"""The eng bus: caution and warning, the flight data and landing panel, engine, staging (with what the next stage does), engine status matrix and abort, and the
ATTITUDE panel (on the FDAI module): its switches, attitude and rate displays, and the settings of the ball; and the
SAS MODE panel's ten buttons."""
import math

from .. import settings as S
from ..alarms import ALARMS, stage_fuel_fraction
from ..display_format import fit_number, format_mission_time
from ..engines import IDLE, OFF, THRUSTING
from ..messages import PanelOutputs, switch_lamp
from ..performance import current_thrust_to_weight, hover_time, speeds_in_reference, stage_delta_v, time_to_impact

SWITCHES_WITH_LAMP = ('sas', 'rcs')
NEXT_STAGE_LAMPS = {'engines': 'lamp_ns_engines', 'solids': 'lamp_ns_solids', 'decouple': 'lamp_ns_decouple',
                    'clamps': 'lamp_ns_clamps', 'chutes': 'lamp_ns_chutes', 'fairing': 'lamp_ns_fairing'}
LAMPS = ['master_alarm', 'master_caution', 'led_eng_arm', 'lamp_stage', 'lamp_abort', 'lamp_cutoff', 'led_gimbal',
         'lamp_contact', *(f'led_{switch}' for switch in SWITCHES_WITH_LAMP), 'led_speed_ref',
         *(f'lamp_sas_{key}' for key in S.SAS_MODE_BUTTONS),
         *NEXT_STAGE_LAMPS.values(), 'led_rcs_fine', 'led_gear', 'lamp_td_sink', 'lamp_td_drift', 'lamp_td_upright', 'lamp_td_gear', *ALARMS]
# display → (digits, the dashes shown without telemetry)
DISPLAYS = {'disp_alt': 8, 'disp_hs': 5, 'disp_vs': 5, 'disp_speed': 5, 'disp_g': 4, 'disp_q': 4, 'disp_hover': 4,
            'disp_impact': 5, 'disp_drift_right': 5, 'disp_drift_up': 5, 'disp_met': 7,
            'disp_stage': 2, 'disp_eng_on': 2, 'disp_dv': 5, 'disp_twr': 4, 'disp_att_pitch': 5, 'disp_att_hdg': 5, 'disp_att_roll': 5, 'disp_rate_pitch': 4,
            'disp_rate_yaw': 4, 'disp_rate_roll': 4}
BARS = ['bar_fuel', 'bar_thrust']


# ---------- inputs ----------
def handle_input(cockpit, change):
    """Commands for a control of this panel, or None when the control belongs to another panel."""
    control = change.control
    if control in ('throttle', 'eng_arm', 'cb_main'):
        return cockpit.command_throttle()
    if control == 'eng_cutoff':
        return cockpit.cut_throttle() if change.pressed else []
    if control == 'met_reset':
        # MET RESET, next to MET: held 2 s, the mission clock starts again from the vessel flown (gateway)
        if change.pressed:
            cockpit.met_reset_pressed_at = cockpit.now
            return []
        pressed_at, cockpit.met_reset_pressed_at = cockpit.met_reset_pressed_at, None
        if pressed_at is not None and cockpit.now - pressed_at >= S.MET_RESET_HOLD_S:
            return cockpit.command('cmd/met_reset', {})
        return []
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
        if not (change.pressed and cockpit.is_on('abort_arm')):
            return []
        cockpit.abort_fired = True
        return cockpit.command('cmd/abort', {})     # KSP's abort group: what the craft's builder wired to it
    if control == 'speed_ref':
        # Only when moved: KSP changes the reference by itself (to surface low down, to target near one).
        if not change.moved:
            return []
        return cockpit.command('cmd/speed_mode', {'mode': cockpit.selected('speed_ref', S.SPEED_MODES)})
    if control.startswith('sas_') and control[4:] in S.SAS_MODE_BUTTONS:
        if not change.pressed:
            return []
        cockpit.sas_mode_choice, cockpit.sas_mode_retries = S.SAS_MODE_BUTTONS[control[4:]], 0
        return cockpit.command('cmd/sas_mode', {'mode': cockpit.sas_mode_choice})
    return None


# ---------- outputs ----------
def sas_mode_lamps(choice, memory, game_mode):
    """{button key: (lit, blink)}. One lamp: the game's mode while SAS is on, the mode SAS will take while it is off.
    A button just pressed lights its own lamp, blinking while SAS is on in another mode (the game has not taken it
    yet: it may still refuse, with no node or no target)."""
    shown = choice or game_mode or memory
    return {key: (mode == shown, mode == shown == choice and game_mode is not None and game_mode != choice)
            for key, mode in S.SAS_MODE_BUTTONS.items()}


def _render_sas_mode_lamps(cockpit, outputs, fresh):
    game_mode = cockpit.game_sas_mode() if fresh else None
    for key, (lit, blink) in sas_mode_lamps(cockpit.sas_mode_choice, cockpit.sas_mode_memory, game_mode).items():
        outputs.lamp(f'lamp_sas_{key}', lit, blink=blink)


def render(cockpit, wanted, active_alarms, unacknowledged_alarms):
    outputs = PanelOutputs(wanted, S.ENGINE_PANEL)
    warning_waiting = any(ALARMS[name].is_warning for name in unacknowledged_alarms)
    caution_waiting = any(not ALARMS[name].is_warning for name in unacknowledged_alarms)
    powered, lamp_test = cockpit.powered(), cockpit.lamp_test()
    outputs.raw('buzzer', {'on': powered and not lamp_test and warning_waiting})
    outputs.raw('fdai', fdai_settings(cockpit))

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


def _render_attitude(cockpit, outputs):
    """Pitch, heading and roll with their rates. The heading's rate counts for less as the nose nears the vertical:
    the yaw rate is that rate times the cosine of the pitch."""
    attitude, rates = cockpit.telemetry.get('tlm/attitude', {}), cockpit.attitude_rates.rates
    pitch = attitude.get('pitch')
    heading_rate = rates.get('heading')
    yaw_rate = heading_rate * math.cos(math.radians(pitch)) if None not in (heading_rate, pitch) else None
    outputs.text('disp_att_pitch', fit_number(pitch, 1, 5, signed=True))
    outputs.text('disp_att_hdg', fit_number(attitude.get('heading'), 1, 5))
    outputs.text('disp_att_roll', fit_number(attitude.get('roll'), 1, 5, signed=True))
    outputs.text('disp_rate_pitch', fit_number(rates.get('pitch'), 1, 4, signed=True))
    outputs.text('disp_rate_yaw', fit_number(yaw_rate, 1, 4, signed=True))
    outputs.text('disp_rate_roll', fit_number(rates.get('roll'), 1, 4, signed=True))


def fdai_settings(cockpit):
    """panel/eng/out/fdai: how the FDAI page draws, from the FDAI controls on the ATTITUDE panel."""
    return {'needles': cockpit.selected('fdai_needles', S.FDAI_NEEDLES),
            'error_scale': cockpit.selected('fdai_error', S.FDAI_ERROR_SCALES_DEG),
            'markers': bool(cockpit.inputs.get('fdai_markers', 1))}


def _render_lamps(cockpit, outputs):
    vessel = cockpit.vessel
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
    outputs.lamp('led_gear', *switch_lamp(vessel.get('gear'), cockpit.switch_wanted('gear')))
    # SPEED REF's LED: lit when the game reports its reference, blinking when that is not the knob's (KSP changes it
    # by itself: to surface low down, to target near one).
    game_mode = vessel.get('speed_mode') if fresh else None
    knob_mode = cockpit.selected('speed_ref', S.SPEED_MODES)
    outputs.lamp('led_speed_ref', game_mode is not None, blink=game_mode is not None and game_mode != knob_mode)

    _render_sas_mode_lamps(cockpit, outputs, fresh)
    _render_touchdown_lamps(cockpit, outputs, fresh)
    # NEXT STAGE: what pressing STAGE would do; dark with no stage left or no telemetry
    next_stage = (vessel.get('next_stage') if fresh else None) or {}
    for key, lamp in NEXT_STAGE_LAMPS.items():
        outputs.lamp(lamp, bool(next_stage.get(key)))

    # event lights
    landed = bool(vessel.get('contact')) and vessel.get('situation') != 'pre_launch'    # the pad is not a landing
    outputs.lamp('lamp_contact', fresh and landed)


def _render_touchdown_lamps(cockpit, outputs, fresh):
    """LANDING: near the ground, each lamp lights while that condition is good for touching down."""
    flight, vessel = cockpit.flight, cockpit.vessel
    radar, sink = flight.get('radar'), -(flight.get('vs') or 0.0)
    right, down, pitch = flight.get('v_right'), flight.get('v_down'), cockpit.telemetry.get('tlm/attitude', {}).get('pitch')
    descending = (fresh and radar is not None and 0 < radar < S.SINK_RATE_BELOW_ALTITUDE_M
                  and vessel.get('situation') not in ('landed', 'splashed', 'pre_launch'))
    allowed_sink = S.TOUCHDOWN_SINK_BASE_M_S + S.TOUCHDOWN_SINK_PER_ALTITUDE * (radar or 0.0)
    outputs.lamp('lamp_td_sink', descending and sink <= allowed_sink)
    outputs.lamp('lamp_td_drift', descending and None not in (right, down)
                 and math.hypot(right, down) <= S.TOUCHDOWN_DRIFT_M_S)
    outputs.lamp('lamp_td_upright', descending and pitch is not None and 90 - pitch <= S.TOUCHDOWN_TILT_DEG)
    outputs.lamp('lamp_td_gear', descending and vessel.get('gear'))


def _render_ascent_descent(cockpit, outputs):
    """Altitude above the ground or the sea (ALT REF), the speeds against the SPEED REF knob's reference, g, dynamic
    pressure, hover time and time to impact."""
    flight = cockpit.flight
    horizontal, vertical, total = speeds_in_reference(cockpit)
    altitude = flight.get('radar' if cockpit.is_on('alt_ref') else 'alt')
    outputs.text('disp_alt', fit_number(round(altitude) if altitude is not None else None, 0, 8))    # never "-0"
    outputs.text('disp_hs', fit_number(horizontal, 1, 5))
    outputs.text('disp_vs', fit_number(vertical, 1, 5, signed=True))
    outputs.text('disp_speed', fit_number(total, 1, 5))
    outputs.text('disp_g', fit_number(flight.get('g'), 2, 4))
    pressure = flight.get('q')
    outputs.text('disp_q', fit_number(pressure / 1000 if pressure is not None else None, 2, 4))
    outputs.text('disp_hover', fit_number(hover_time(cockpit), 0, 4))
    outputs.text('disp_impact', fit_number(time_to_impact(cockpit), 0, 5))
    # across the craft's own axis, as on TRANSLATION: for a lander standing on its tail, which way it slides
    down = flight.get('v_down')
    outputs.text('disp_drift_right', fit_number(flight.get('v_right'), 1, 5, signed=True))
    outputs.text('disp_drift_up', fit_number(-down if down is not None else None, 1, 5, signed=True))


def _render_displays(cockpit, outputs):
    vessel = cockpit.vessel
    if not cockpit.telemetry_is_fresh():
        for display, digits in DISPLAYS.items():
            outputs.text(display, '--.--.--' if display == 'disp_met' else '-' * digits)
        outputs.bar('bar_fuel', 0.0)
        outputs.bar('bar_thrust', 0.0)
        outputs.raw('mx_eng', {'rows': [OFF * S.ENGINE_GRID_SIZE] * S.ENGINE_GRID_SIZE})
        return
    _render_ascent_descent(cockpit, outputs)
    outputs.text('disp_dv', fit_number(stage_delta_v(cockpit), 0, DISPLAYS['disp_dv']))
    outputs.text('disp_twr', fit_number(current_thrust_to_weight(cockpit), 2, DISPLAYS['disp_twr']))
    _render_attitude(cockpit, outputs)
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

