"""Caution and warning: which alarms are active, from the telemetry and the switch positions.

A warning (red) lights MASTER ALARM and sounds the tone; a caution (amber) lights MASTER CAUTION.
"""
from dataclasses import dataclass

from . import settings as S
from .engines import DEAD, WEAK


@dataclass(frozen=True)
class Alarm:
    legend: str
    is_warning: bool


CAUTION, WARNING = False, True
# Output name on the annunciator → alarm.
ALARMS = {
    'cw_no_link': Alarm('NO LINK', WARNING),
    'cw_high_g': Alarm('HIGH G', WARNING),
    'cw_q': Alarm('HIGH Q', CAUTION),
    'cw_low_fuel': Alarm('LOW FUEL', CAUTION),
    'cw_low_power': Alarm('LOW POWER', CAUTION),
    'cw_rcs_low': Alarm('RCS LOW', CAUTION),
    'cw_overheat': Alarm('OVERHEAT', WARNING),
    'cw_comm': Alarm('COMM LOST', CAUTION),
    'cw_sink': Alarm('SINK RATE', WARNING),
    'cw_gear': Alarm('GEAR UP', WARNING),
    'cw_chute': Alarm('CHUTE', CAUTION),
    'cw_throttle': Alarm('THROTTLE', CAUTION),
    'cw_flameout': Alarm('FLAMEOUT', CAUTION),
    'cw_eng_fail': Alarm('ENG FAIL', WARNING),
    'cw_sas_dis': Alarm('SAS DISAGREE', CAUTION),
    'cw_att': Alarm('ATT ERR', CAUTION),
    'cw_resid': Alarm('DV RESID', CAUTION),
    'cw_closing': Alarm('CLOSING', CAUTION),
    'cw_ls_low': Alarm('LS LOW', CAUTION),
    'cw_ls_out': Alarm('LS OUT', WARNING),
}

DESCENDING_SITUATIONS = ('flying', 'sub_orbital')


def injected_false_alarms(cockpit):
    """The alarms SimSup lights with no cause; the instructor may name one by id (cw_q) or by legend (HIGH Q)."""
    asked = {name.strip().lower() for name in cockpit.injected_failures.false_alarms()}
    return {name for name, alarm in ALARMS.items() if name in asked or alarm.legend.lower() in asked}


def active_alarms(cockpit):
    """The set of active alarm names. Without a link nothing else can be trusted, so NO LINK stands alone."""
    if not cockpit.telemetry_is_fresh() or not cockpit.link_up:
        return {'cw_no_link'}
    active = injected_false_alarms(cockpit)
    _vehicle_alarms(cockpit, active)
    _descent_alarms(cockpit, active)
    _engine_alarms(cockpit, active)
    _burn_alarms(cockpit, active)
    _rendezvous_alarms(cockpit, active)
    return active


def fraction_left(resources, name):
    """Amount / capacity of a resource in a {'<name>': {'amount', 'max'}} table, or None if there is none."""
    resource = resources.get(name)
    if not resource or not resource.get('max'):
        return None
    return resource['amount'] / resource['max']


def stage_fuel_fraction(resources):
    """Liquid and solid fuel left in the current stage, as a fraction, or its xenon for a stage with neither (an ion
    stage). None when the stage has none of them."""
    stage = resources.get('stage', {})
    amount = sum(stage.get(name, {}).get('amount', 0) for name in ('LiquidFuel', 'SolidFuel'))
    capacity = sum(stage.get(name, {}).get('max', 0) for name in ('LiquidFuel', 'SolidFuel'))
    if capacity > 0:
        return amount / capacity
    return fraction_left(stage, 'XenonGas')


def braking_gate(target_range):
    """The closing speed allowed at this range (docking chapter of the course)."""
    return max(S.BRAKING_GATE_FLOOR_M_S, target_range / S.BRAKING_GATE_TIME_S)


def _is_below(fraction, limit):
    return fraction is not None and fraction < limit


def _life_support_alarms(vessel, totals, active):
    """Only with a crew aboard and for what the vessel carries (TAC Life Support adds these resources)."""
    if not vessel.get('crew'):
        return
    fractions = [fraction_left(totals, name) for name in S.LIFE_SUPPORT_USE_PER_KERBAL_S]
    fractions = [fraction for fraction in fractions if fraction is not None]
    if any(fraction < S.LOW_LIFE_SUPPORT_FRACTION for fraction in fractions):
        active.add('cw_ls_low')
    if any(fraction <= 0 for fraction in fractions):
        active.add('cw_ls_out')


def _vehicle_alarms(cockpit, active):
    flight, vessel, resources = cockpit.flight, cockpit.vessel, cockpit.resources
    totals = resources.get('total', {})
    if flight.get('g', 0) > S.G_FORCE_LIMIT:
        active.add('cw_high_g')
    if flight.get('q', 0) > S.DYNAMIC_PRESSURE_LIMIT_PA:
        active.add('cw_q')
    if _is_below(stage_fuel_fraction(resources), S.LOW_FUEL_FRACTION) and vessel.get('thrust_avail', 0) > 0:
        active.add('cw_low_fuel')
    if _is_below(fraction_left(totals, 'ElectricCharge'), S.LOW_POWER_FRACTION):
        active.add('cw_low_power')
    if _is_below(fraction_left(totals, 'MonoPropellant'), S.LOW_MONOPROPELLANT_FRACTION):
        active.add('cw_rcs_low')
    if (cockpit.telemetry.get('tlm/thermal', {}).get('max') or 0) >= S.OVERHEAT_FRACTION:
        active.add('cw_overheat')
    _life_support_alarms(vessel, cockpit.life_support_resources(), active)
    if vessel.get('comm') is False:
        active.add('cw_comm')
    # SAS switch against the game for a while
    sas_disagrees = 'sas' in vessel and 'sas' in cockpit.inputs and bool(vessel['sas']) != cockpit.switch_wanted('sas')
    if cockpit.has_lasted('sas_disagree', sas_disagrees, S.SAS_DISAGREE_AFTER_S):
        active.add('cw_sas_dis')


def _descent_alarms(cockpit, active):
    flight, vessel = cockpit.flight, cockpit.vessel
    radar_altitude, vertical_speed = flight.get('radar'), flight.get('vs')
    situation = vessel.get('situation')
    descending = vertical_speed is not None and vertical_speed < 0 and situation in DESCENDING_SITUATIONS
    if not descending:
        return
    if radar_altitude is not None:
        allowed_sink_rate = S.SINK_RATE_BASE_M_S + S.SINK_RATE_PER_ALTITUDE * radar_altitude
        if 0 < radar_altitude < S.SINK_RATE_BELOW_ALTITUDE_M and -vertical_speed > allowed_sink_rate:
            active.add('cw_sink')
        if vessel.get('has_gear') and vessel.get('gear') is False and radar_altitude < S.GEAR_UP_BELOW_ALTITUDE_M:
            active.add('cw_gear')
    # in the air, going down, parachute neither armed nor out
    altitude = flight.get('alt')
    low_enough = altitude is not None and altitude < S.CHUTE_BELOW_ALTITUDE_M
    if situation == 'flying' and low_enough and vessel.get('chute') == 'stowed' and not cockpit.inputs.get('chute_arm'):
        active.add('cw_chute')


def _engine_alarms(cockpit, active):
    lever = float(cockpit.inputs.get('throttle') or 0)
    if lever > S.THROTTLE_UP_ABOVE and not cockpit.inputs.get('eng_arm'):
        active.add('cw_throttle')                   # arming now would light the engine at once
    survey = cockpit.survey_engines()
    if survey.count(DEAD) and not survey.engine_lost:
        active.add('cw_flameout')                   # a caution: it is also the cue to stage
    engine_weak = survey.count(WEAK) > 0
    weak_for_long = cockpit.has_lasted('engine_weak', engine_weak or survey.engine_lost, S.ENGINE_FAIL_AFTER_S)
    if survey.engine_lost or weak_for_long:
        active.add('cw_eng_fail')


def _burn_alarms(cockpit, active):
    computer, node = cockpit.burn_computer, cockpit.telemetry.get('tlm/node', {})
    state = computer.state(cockpit.telemetry)
    time_from_ignition = computer.time_from_ignition(cockpit.telemetry)
    if state in ('ready', 'armed', 'burn') and time_from_ignition is not None:
        in_window = time_from_ignition >= -S.ATTITUDE_ERROR_WINDOW_S
        if state == 'ready':                        # a PAD nobody armed stops mattering 30 s after its TIG
            in_window = in_window and time_from_ignition < S.ATTITUDE_ERROR_WINDOW_S
        if in_window and node.get('set') and (node.get('att_err') or 0) > S.ATTITUDE_ERROR_LIMIT_DEG:
            active.add('cw_att')
    allowed_residual = max(S.RESIDUAL_MIN_M_S, S.RESIDUAL_FRACTION * computer.delta_v_total())
    if state == 'done' and abs(computer.delta_v_to_go()) > allowed_residual:
        active.add('cw_resid')


def _rendezvous_alarms(cockpit, active):
    target = cockpit.target
    target_range, closing_speed = target.get('range'), target.get('closing') or 0
    if target.get('set') and target_range is not None \
            and closing_speed > S.CLOSING_CAUTION_MARGIN * braking_gate(target_range):
        active.add('cw_closing')
