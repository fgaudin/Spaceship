import math, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cockpit import Cockpit  # noqa: E402
from cockpit.display_format import fit_number, format_mission_time  # noqa: E402

P = 'panel/eng/in/'
O = 'panel/eng/out/'


def topics(msgs):
    return {m.topic: m.payload for m in msgs}


def fed(c, t=0.0, **over):
    """Feed one fresh, nominal set of telemetry; returns every message published meanwhile."""
    out = []
    out += c.handle('gateway/status', {'connected': True, 'plant': 'mock'}, t)
    out += c.handle('tlm/time', {'ut': 100 + t, 'met': 65 + t, 'warp': 1}, t)
    fl = {'alt': 12345.6, 'radar': 12000, 'vs': 120.0, 'hs': 300.0, 'speed': 323.0, 'q': 1000.0, 'g': 1.5}
    fl.update(over.get('flight', {}))
    out += c.handle('tlm/flight', fl, t)
    ve = {'mass': 12500.0, 'thrust': 100000.0, 'thrust_avail': 200000.0, 'stage': 3, 'sas': False, 'rcs': False,
          'gear': False, 'lights': False}
    ve.update(over.get('vessel', {}))
    out += c.handle('tlm/vessel', ve, t)
    res = over.get('resources', {'stage': {'LiquidFuel': {'amount': 50, 'max': 100}},
                                 'total': {'ElectricCharge': {'amount': 90, 'max': 100}}})
    out += c.handle('tlm/resources', res, t)
    out += c.handle('tlm/orbit', {'apo': 80000.0, 'peri': -100000.0}, t)
    return out + c.tick(t)


def test_throttle_needs_engine_arm():
    c = Cockpit()
    fed(c)
    out = topics(c.handle(P + 'throttle', {'v': 0.7}, 1))
    assert out.get('cmd/throttle', {'v': 0})['v'] == 0 or 'cmd/throttle' not in out
    out = topics(c.handle(P + 'eng_arm', {'v': 1}, 2))
    assert out['cmd/throttle'] == {'v': 0.7}
    assert out[O + 'led_eng_arm'] == {'on': True, 'blink': False}
    out = topics(c.handle(P + 'eng_arm', {'v': 0}, 3))
    assert out['cmd/throttle'] == {'v': 0.0}


def test_stage_needs_arm_and_edge():
    c = Cockpit()
    fed(c)
    assert 'cmd/stage' not in topics(c.handle(P + 'stage', {'v': 1}, 1))
    c.handle(P + 'stage', {'v': 0}, 1.1)
    c.handle(P + 'stage_arm', {'v': 1}, 2)
    assert 'cmd/stage' in topics(c.handle(P + 'stage', {'v': 1}, 3))
    # holding the button does not stage again
    assert 'cmd/stage' not in topics(c.handle(P + 'stage', {'v': 1}, 3.5))


def test_abort_guarded():
    c = Cockpit()
    fed(c)
    assert 'cmd/abort' not in topics(c.handle(P + 'abort', {'v': 1}, 1))
    c.handle(P + 'abort', {'v': 0}, 1.2)
    c.handle(P + 'abort_arm', {'v': 1}, 2)
    out = topics(c.handle(P + 'abort', {'v': 1}, 3))
    assert 'cmd/abort' in out and out[O + 'lamp_abort'] == {'on': True, 'blink': True}


def test_lamp_test_lights_everything():
    c = Cockpit()
    fed(c)
    out = topics(c.handle(P + 'lamp_test', {'v': 1}, 1))
    assert out[O + 'cw_high_g'] == {'on': True, 'blink': False}
    assert out[O + 'disp_alt']['text'].startswith('8.8.')
    out = topics(c.handle(P + 'lamp_test', {'v': 0}, 2))
    assert out[O + 'cw_high_g'] == {'on': False, 'blink': False}


def test_main_breaker_kills_outputs_and_throttle():
    c = Cockpit()
    fed(c)
    c.handle(P + 'eng_arm', {'v': 1}, 1)
    c.handle(P + 'throttle', {'v': 1.0}, 1)
    out = topics(c.handle(P + 'cb_main', {'v': 0}, 2))
    assert out['cmd/throttle'] == {'v': 0.0}
    assert out[O + 'disp_alt'] == {'text': '', 'blank': True, 'blink': False}
    assert out[O + 'led_eng_arm'] == {'on': False, 'blink': False}
    # inputs are ignored while unpowered
    assert 'cmd/stage' not in topics(c.handle(P + 'stage_arm', {'v': 1}, 3) + c.handle(P + 'stage', {'v': 1}, 3.1))


def test_warning_blinks_until_acknowledged_and_returns_after_clearing():
    c = Cockpit()
    out = topics(fed(c, 0, flight={'g': 6.5}))
    assert out[O + 'cw_high_g'] == {'on': True, 'blink': True}
    assert out[O + 'master_alarm'] == {'on': True, 'blink': True}
    assert out[O + 'buzzer'] == {'on': True}
    out = topics(c.handle(P + 'master_alarm', {'v': 1}, 1))
    assert out[O + 'master_alarm'] == {'on': False, 'blink': False}
    assert out[O + 'cw_high_g'] == {'on': True, 'blink': False}
    assert out[O + 'buzzer'] == {'on': False}
    c.handle(P + 'master_alarm', {'v': 0}, 1.1)
    fed(c, 2)                                   # clears
    out = topics(fed(c, 3, flight={'g': 7}))    # comes back: needs a new ack
    assert out[O + 'master_alarm'] == {'on': True, 'blink': True}


def test_caution_does_not_sound():
    c = Cockpit()
    out = topics(fed(c, 0, resources={'stage': {'LiquidFuel': {'amount': 5, 'max': 100}}, 'total': {}}))
    assert out[O + 'cw_low_fuel'] == {'on': True, 'blink': True}
    assert out[O + 'master_caution']['on'] is True
    assert out.get(O + 'buzzer', {'on': False}) == {'on': False}


def test_no_link_when_telemetry_stale():
    c = Cockpit()
    fed(c, 0)
    out = topics(c.tick(5.0))
    assert out[O + 'cw_no_link'] == {'on': True, 'blink': True}
    assert out[O + 'disp_alt'] == {'text': '--------', 'blank': False, 'blink': False}


def test_no_alarm_in_the_vab():
    c = Cockpit()
    fed(c, 0)
    c.handle('gateway/status', {'connected': False, 'plant': 'ksp', 'scene': 'editor_vab'}, 1)
    c.tick(5.0)
    assert not c.published[O + 'cw_no_link']['on'] and not c.published[O + 'master_alarm']['on']
    assert not c.published[O + 'buzzer']['on']
    c.handle('gateway/status', {'connected': False, 'plant': 'ksp', 'scene': 'space_center'}, 6)
    c.tick(6.0)
    assert c.published[O + 'cw_no_link']['on'] and c.published[O + 'buzzer']['on']   # out of the VAB: NO LINK again


def test_sas_panel_wins_and_disagree_lamp():
    c = Cockpit()
    fed(c)
    out = topics(c.handle(P + 'sas', {'v': 1}, 1))
    assert out['cmd/sas'] == {'on': True}
    assert out[O + 'led_sas'] == {'on': True, 'blink': True}       # switch on, game still off: disagree
    out = topics(fed(c, 2.5))                                       # still off in the game: re-sent
    assert out.get('cmd/sas') == {'on': True}
    out = topics(fed(c, 3.2))
    assert out[O + 'cw_sas_dis']['on'] is True
    out = topics(fed(c, 4, vessel={'sas': True}))
    assert out[O + 'led_sas'] == {'on': True, 'blink': False}
    assert out[O + 'cw_sas_dis'] == {'on': False, 'blink': False}


def test_gear_game_wins_no_resend():
    c = Cockpit()
    fed(c)
    c.handle('panel/eng/in/gear', {'v': 1}, 1)
    out = topics(fed(c, 3))
    assert 'cmd/gear' not in out
    assert out.get(O + 'led_gear', c.published[O + 'led_gear']) == {'on': True, 'blink': True}


def test_ascent_displays_and_formats():
    c = Cockpit()
    fed(c)
    assert c.published[O + 'disp_alt']['text'] == '12346'         # above the sea, m
    c.handle(P + 'alt_ref', {'v': 1}, 0.1)
    assert c.published[O + 'disp_alt']['text'] == '12000'         # ALT REF on RADAR
    assert c.published[O + 'disp_g']['text'] == '1.50'
    assert c.published[O + 'disp_met']['text'] == format_mission_time(65)
    assert fit_number(123456.78, 1, 7) == '123456.8'
    assert fit_number(-1.5, 1, 7) == '-1.5'
    assert fit_number(-0.01, 1, 5, signed=True) == '+0.0'


def test_outputs_published_once():
    c = Cockpit()
    fed(c)
    assert c.tick(0.5) == [] or all(m.topic.startswith('cmd/') for m in c.tick(0.6))


def test_reset_keeps_link_and_clears_latches():
    c = Cockpit()
    fed(c)
    c.handle(P + 'abort_arm', {'v': 1}, 1); c.handle(P + 'abort', {'v': 1}, 1.1)
    assert c.abort_fired
    out = topics(c.reset())
    assert not c.abort_fired and c.link_up
    assert out.get(O + 'cw_no_link', c.published[O + 'cw_no_link']) == {'on': False, 'blink': False}


# ---------- abort, engine extras, engine display, rendezvous, warp and game ----------
R = 'panel/rdv/out/'
S = 'panel/sys/out/'


def abort(c):
    c.handle(P + 'abort_arm', {'v': 1}, 2)
    return topics(c.handle(P + 'abort', {'v': 1}, 3))


def test_abort_fires_the_abort_group_only():
    c = Cockpit(); fed(c)
    c.handle(P + 'eng_arm', {'v': 1}, 0.5); c.handle(P + 'throttle', {'v': 0.6}, 0.6)
    assert 'cmd/abort' not in topics(c.handle(P + 'abort', {'v': 1}, 1))          # needs ABORT ARM
    c.handle(P + 'abort', {'v': 0}, 1.5)
    out = abort(c)
    assert out['cmd/abort'] == {} and out[O + 'lamp_abort'] == {'on': True, 'blink': True}
    # what the craft's builder wired to the abort group does the rest: nothing else is touched
    assert not {'cmd/stage', 'cmd/throttle', 'cmd/sas', 'cmd/rcs'} & set(out) and not c.throttle_cut_latched





def test_cutoff_button_and_engine_settings():
    c = Cockpit(); fed(c)
    c.handle(P + 'eng_arm', {'v': 1}, 1); c.handle(P + 'throttle', {'v': 0.7}, 1.1)
    out = topics(c.handle(P + 'eng_cutoff', {'v': 1}, 2))
    assert out['cmd/throttle'] == {'v': 0.0} and out[O + 'lamp_cutoff']['on']
    # the first report of a knob or switch position is not a command (VAB limiters are kept)
    assert 'cmd/thrust_limit' not in topics(c.handle(P + 'thrust_lim', {'v': 1}, 3))
    assert 'cmd/gimbal' not in topics(c.handle(P + 'gimbal_lock', {'v': 0}, 3))
    assert topics(c.handle(P + 'thrust_lim', {'v': 0.26}, 4))['cmd/thrust_limit'] == {'v': 0.25}
    assert topics(c.handle(P + 'gimbal_lock', {'v': 1}, 5))['cmd/gimbal'] == {'locked': True}


def engines(c, t, lst, **vessel):
    c.handle('tlm/engines', {'engines': lst, 'limit': 1.0, 'gimbal_locked': False}, t)
    return topics(fed(c, t, vessel={'throttle': 1.0, 'stage': 3, **vessel}))


def eng(x, z, thrust=100.0, on=True, fuel=True, stage=3):
    return {'x': x, 'z': z, 'on': on, 'thrust': thrust, 'max': 100.0, 'fuel': fuel, 'stage': stage}


def test_engine_matrix_layout_and_failures():
    c = Cockpit(); fed(c)
    five = [eng(0, 0), eng(1.3, 0), eng(-1.3, 0), eng(0, 1.3), eng(0, -1.3), eng(0, 0, on=False, thrust=0, stage=2)]
    engines(c, 1, five)
    rows = c.published[O + 'mx_eng']['rows']
    assert rows[4] == 'g...g...g' and rows[0][4] == 'g' and rows[8][4] == 'g' and sum(r.count('g') for r in rows) == 5
    assert c.published[O + 'disp_eng_on']['text'] == ' 5'
    # one engine has fuel but no thrust: amber at once, ENG FAIL after a second
    five[1] = eng(1.3, 0, thrust=0)
    out = engines(c, 2, five)
    assert c.published[O + 'mx_eng']['rows'][4] == 'g...g...a' and 'cw_eng_fail' not in c.active_alarms()
    engines(c, 3.5, five)
    assert c.published[O + 'cw_eng_fail']['on'] and c.published[O + 'master_alarm']['on']
    # flameout: red, a caution (the cue to stage), not a failure
    c = Cockpit(); fed(c)
    engines(c, 1, [eng(0, 0), eng(1, 0, thrust=0, fuel=False)])
    assert c.published[O + 'mx_eng']['rows'][4] == '....g...r' and c.published[O + 'cw_flameout']['on']
    assert not c.published[O + 'cw_eng_fail']['on']
    # an engine that disappears without staging is lost: red, ENG FAIL
    engines(c, 2, [eng(0, 0)])
    assert c.published[O + 'mx_eng']['rows'][4] == '....g...r' and c.published[O + 'cw_eng_fail']['on']
    # after staging the display starts again
    engines(c, 3, [eng(0, 0, stage=2)], stage=2)
    assert c.published[O + 'mx_eng']['rows'][4] == '....g....' and not c.published[O + 'cw_eng_fail']['on']


def test_boosters_flamed_out_then_staged_are_not_failures():
    c = Cockpit(); fed(c)
    core, boosters = eng(0, 0), [eng(1.3, 0, thrust=0, fuel=False), eng(-1.3, 0, thrust=0, fuel=False)]
    before_staging = {'engines': [core, *boosters], 'stage': 3, 'limit': 1.0, 'gimbal_locked': False}
    c.handle('tlm/engines', before_staging, 1)
    fed(c, 1, vessel={'throttle': 1.0, 'stage': 3})
    assert c.published[O + 'mx_eng']['rows'][4] == 'r...g...r' and c.published[O + 'cw_flameout']['on']
    # staging: the vessel's stage number arrives before the new engine list
    fed(c, 2, vessel={'throttle': 1.0, 'stage': 2})
    assert not c.published[O + 'cw_eng_fail']['on']
    c.handle('tlm/engines', {**before_staging, 'engines': [core], 'stage': 2}, 2.5)
    fed(c, 4, vessel={'throttle': 1.0, 'stage': 2})
    assert c.published[O + 'mx_eng']['rows'][4] == '....g....'
    assert not c.published[O + 'cw_eng_fail']['on'] and not c.published[O + 'cw_flameout']['on']


def test_spent_engine_still_attached_is_not_shown():
    c = Cockpit(); fed(c)
    # the first stage ran dry and stays attached while the engine of the next stage burns
    engines(c, 1, [eng(1, 0, thrust=0, fuel=False, stage=3), eng(0, 0, stage=2)], stage=2)
    assert c.published[O + 'mx_eng']['rows'][4] == '....g....'
    assert not c.published[O + 'cw_flameout']['on'] and not c.published[O + 'cw_eng_fail']['on']


def test_engines_next_to_ignite_show_white_before_ignition():
    c = Cockpit(); fed(c)
    engines(c, 1, [eng(0, 0, on=False, thrust=0, stage=3), eng(0, 0, on=False, thrust=0, stage=2)], stage=4, throttle=0.0)
    assert c.published[O + 'mx_eng']['rows'][4] == '....w....'


def test_rendezvous_and_docking_panels():
    c = Cockpit(); fed(c)
    assert c.published[R + 'txt_tgt']['text'] == 'NO TARGET'
    assert topics(c.handle('panel/rdv/in/tgt_next', {'v': 1}, 1))['cmd/target'] == {'step': 1}
    c.handle('tlm/target', {'set': True, 'name': 'Orbiter', 'range': 1200.0, 'closing': 2.5, 'los_rate': 0.31, 'rel_v': 2.6,
                            'ctrl_port': False}, 2)
    s = c.published
    assert s[R + 'txt_tgt']['text'] == 'ORBITER' and s[R + 'disp_range']['text'] == '1200.0' and s[R + 'disp_closing']['text'] == '+2.50'
    assert not s[R + 'led_km']['on'] and not s[O + 'cw_closing']['on']
    c.handle('tlm/target', {'set': True, 'name': 'Orbiter', 'range': 400.0, 'closing': 2.5, 'los_rate': 0.31, 'rel_v': 2.6,
                            'ctrl_port': False}, 3)
    assert s[O + 'cw_closing']['on']                                      # over the braking gate: the caution stays
    c.handle('tlm/target', {'set': True, 'name': 'Orbiter', 'range': 250000.0, 'closing': 20.0, 'rel_v': 20.0,
                            'ctrl_port': False}, 3.5)
    assert s[R + 'led_km']['on'] and s[R + 'disp_range']['text'] == '250.0'
    port = {'axial': 4.0, 'x': 0.1, 'z': -0.2, 'v_axial': -0.1, 'vx': 0, 'vz': 0, 'angle': 3.0, 'from_port': True,
            'right': 0.1, 'up': -0.2, 'fwd': 4.0, 'v_right': -0.02, 'v_up': 0.0, 'yaw': 1.5, 'pitch': -2.5, 'roll': 12.0}
    c.handle('tlm/target', {'set': True, 'name': 'Orbiter', 'range': 4.0, 'closing': 0.1, 'rel_v': 0.1, 'ctrl_port': True,
                            'port': port}, 4)
    assert s[R + 'lamp_capture']['on'] and s[R + 'disp_up']['text'] == '-0.20' and s[R + 'disp_vright']['text'] == '-0.02'
    assert s[R + 'disp_yaw']['text'] == '+1.5' and s[R + 'disp_pitch']['text'] == '-2.5' and s[R + 'disp_roll']['text'] == '+12.0'
    assert s[R + 'disp_axial']['text'] == '4.00' and s[R + 'disp_vaxial']['text'] == '-0.10'    # range rate: closing
    assert s[R + 'disp_yaw_rate']['text'] == '----'                       # one sample: no rate yet
    assert s[R + 'led_ctrl_port'] == {'on': True, 'blink': True}          # the game controls from the port, the switch is off
    c.handle('tlm/target', {'set': True, 'name': 'Orbiter', 'range': 4.0, 'closing': 0.5, 'rel_v': 0.5, 'ctrl_port': True,
                            'port': {**port, 'v_axial': -0.5}}, 5)
    assert not s[R + 'lamp_capture']['on']                                # too fast for the capture envelope
    assert 'cmd/control_from' not in topics(c.handle('panel/rdv/in/ctrl_port', {'v': 0}, 6))
    assert topics(c.handle('panel/rdv/in/ctrl_port', {'v': 1}, 7))['cmd/control_from'] == {'port': True}


def test_docking_rates_follow_the_angles_over_game_time():
    c = Cockpit(); fed(c)
    port = {'axial': 20.0, 'x': 0, 'z': 0, 'v_axial': -0.2, 'vx': 0, 'vz': 0, 'angle': 3.0, 'from_port': True,
            'right': 0.0, 'up': 0.0, 'fwd': 20.0, 'v_right': 0.0, 'v_up': 0.0, 'yaw': 4.0, 'pitch': -2.0, 'roll': 179.0}

    def at(met, **angles):
        c.handle('tlm/time', {'ut': 100 + met, 'met': met, 'warp': 1}, met)
        c.handle('tlm/target', {'set': True, 'name': 'Orbiter', 'range': 20.0, 'closing': 0.2, 'rel_v': 0.2,
                                'ctrl_port': True, 'port': {**port, **angles}}, met)

    at(10.0)
    at(10.5, yaw=3.0, pitch=-2.0, roll=-179.0)          # yaw closing at 2 °/s; roll crossing ±180° the short way
    s = c.published
    assert s[R + 'disp_yaw_rate']['text'] == '-2.0' and s[R + 'disp_pitch_rate']['text'] == '+0.0'
    assert s[R + 'disp_roll_rate']['text'] == '+4.0'
    c.handle('tlm/target', {'set': True, 'name': 'Orbiter', 'range': 20.0, 'closing': 0.2, 'rel_v': 0.2,
                            'ctrl_port': True}, 11)       # port no longer targeted
    assert s[R + 'disp_yaw_rate']['text'] == '----'


def test_warp_to_event_pause_and_saves():
    c = Cockpit(); fed(c)
    c.handle('tlm/orbit', {'apo': 80000.0, 'peri': 75000.0, 't_apo': 900.0, 't_peri': 2400.0}, 0)
    assert 'cmd/warp' not in topics(c.handle('panel/sys/in/warp_to', {'v': 1}, 1))          # source MAN: no event
    c.handle('panel/sys/in/warp_to', {'v': 0}, 1.1)
    c.handle('panel/sys/in/evt_src', {'v': 2}, 1.2)
    assert topics(c.handle('panel/sys/in/warp_to', {'v': 1}, 1.3))['cmd/warp'] == {'to_ut': 940.0}   # UT 100 + 900 − 60
    assert 'cmd/pause' not in topics(c.handle('panel/sys/in/pause', {'v': 0}, 2))
    assert topics(c.handle('panel/sys/in/pause', {'v': 1}, 3))['cmd/pause'] == {'on': True}
    c.handle('tlm/time', {'ut': 100, 'met': 65, 'warp': 1, 'paused': True}, 3.1)
    assert c.published[S + 'led_pause']['on']
    assert topics(c.handle('panel/sys/in/quickload', {'v': 1}, 4))['cmd/game'] == {'quickload': True}   # no guard
    assert topics(c.handle('panel/sys/in/quicksave', {'v': 1}, 5))['cmd/game'] == {'quicksave': True}


def test_new_cautions():
    c = Cockpit(); fed(c)
    c.handle(P + 'throttle', {'v': 0.4}, 1)
    assert 'cw_throttle' in c.active_alarms()                                   # lever up with ENG ARM off
    fed(c, 2, flight={'radar': 300.0, 'vs': -60.0}, vessel={'situation': 'sub_orbital'})
    assert 'cw_sink' in c.active_alarms()
    fed(c, 3, flight={'radar': 300.0, 'vs': -20.0}, vessel={'situation': 'sub_orbital'})
    assert 'cw_sink' not in c.active_alarms()
    fed(c, 4, resources={'stage': {}, 'total': {'MonoPropellant': {'amount': 2, 'max': 30}}})
    assert 'cw_rcs_low' in c.active_alarms()


def test_countdown_timer():
    c = Cockpit(); fed(c)
    for ctl in ('evt_min', 'evt_min', 'evt_sec'):                        # 2 min 10 s
        c.handle('panel/sys/in/' + ctl, {'v': 1}, 1); c.handle('panel/sys/in/' + ctl, {'v': 0}, 1)
    c.handle('panel/sys/in/evt_down', {'v': 1}, 1)
    assert c.published[S + 'disp_evt']['text'] == '02.10'
    c.handle('panel/sys/in/evt_start', {'v': 1}, 1)                      # MET 65 in fed()
    c.handle('tlm/time', {'ut': 200, 'met': 165, 'warp': 1}, 2)
    assert c.published[S + 'disp_evt'] == {'text': '00.30', 'blank': False, 'blink': False}
    c.handle('tlm/time', {'ut': 300, 'met': 265, 'warp': 1}, 3)
    assert c.published[S + 'disp_evt'] == {'text': '00.00', 'blank': False, 'blink': True} and not c.event_timer.running
    assert c.published[S + 'led_evt_run'] == {'on': True, 'blink': True}
    c.handle('panel/sys/in/evt_reset', {'v': 1}, 4)
    assert c.published[S + 'disp_evt'] == {'text': '00.00', 'blank': False, 'blink': False}


def test_contact_and_entry_lights():
    c = Cockpit(); fed(c, vessel={'contact': True, 'situation': 'pre_launch'})
    assert not c.published[O + 'lamp_contact']['on']                     # standing on the pad is not a landing
    fed(c, 1, vessel={'contact': True, 'situation': 'flying'}, flight={'vs': -1.0})
    assert c.published[O + 'lamp_contact']['on']
    fed(c, 2, vessel={'thrust': 0.0, 'situation': 'sub_orbital'}, flight={'vs': -300.0, 'g': 0.02})
    assert not c.published['panel/sys/out/lamp_05g']['on']
    fed(c, 3, vessel={'thrust': 0.0, 'situation': 'sub_orbital'}, flight={'vs': -300.0, 'g': 0.06})
    assert c.published['panel/sys/out/lamp_05g']['on']
    fed(c, 4, vessel={'thrust': 0.0, 'situation': 'flying'}, flight={'vs': 200.0, 'g': 0.5})   # coasting upwards: not an entry
    assert not c.published['panel/sys/out/lamp_05g']['on']


def test_more_cautions():
    c = Cockpit(); fed(c)
    c.handle('tlm/thermal', {'max': 0.85}, 1)
    assert 'cw_overheat' in c.active_alarms()
    fed(c, 2, vessel={'has_gear': True, 'gear': False, 'situation': 'sub_orbital'}, flight={'radar': 200.0, 'vs': -5.0})
    assert 'cw_gear' in c.active_alarms()
    fed(c, 3, vessel={'has_gear': True, 'gear': True, 'situation': 'sub_orbital'}, flight={'radar': 200.0, 'vs': -5.0})
    assert 'cw_gear' not in c.active_alarms()
    fed(c, 4, vessel={'chute': 'stowed', 'situation': 'flying'}, flight={'alt': 9000.0, 'vs': -150.0})
    assert 'cw_chute' in c.active_alarms()
    c.handle('panel/sys/in/chute_arm', {'v': 1}, 4.5)
    assert 'cw_chute' not in c.active_alarms()
    fed(c, 5, vessel={'comm': False})
    assert 'cw_comm' in c.active_alarms()


def test_burn_caution_attitude():
    c = Cockpit(); fed(c, vessel={'isp': 345.0})
    c.handle('pad/uplink', {'tig_met': 85, 'dv': [50, 0, 0]}, 1); c.handle('panel/cmp/in/pad_accept', {'v': 1}, 1)
    c.handle('tlm/node', {'set': True, 'ut': c.node_mirror.known_node['ut'], 'dv': [50.0, 0.0, 0.0], 'att_err': 20.0}, 4)
    assert 'cw_att' in c.active_alarms()                                        # 20 s to TIG and 20° off
    c.handle('tlm/node', {'set': True, 'ut': c.node_mirror.known_node['ut'], 'dv': [50.0, 0.0, 0.0], 'att_err': 2.0}, 5)
    assert 'cw_att' not in c.active_alarms() and c.published['panel/cmp/out/disp_att']['text'] == '2.0'
    c.burn_computer.cutoff, c.burn_computer.delta_v_counted = True, 47.0
    c.burn_computer.delta_v_counted = 49.8


def test_undock_needs_arm_and_docked_lamp():
    c = Cockpit(); fed(c)
    c.handle('tlm/target', {'set': False, 'ctrl_port': False, 'docked': True}, 1)
    assert c.published[R + 'lamp_docked']['on']
    assert 'cmd/undock' not in topics(c.handle('panel/rdv/in/undock', {'v': 1}, 2))
    c.handle('panel/rdv/in/undock', {'v': 0}, 2.1)
    c.handle('panel/rdv/in/undock_arm', {'v': 1}, 3)
    assert topics(c.handle('panel/rdv/in/undock', {'v': 1}, 4))['cmd/undock'] == {}


def test_sas_mode_is_sent_again_when_the_game_drops_it():
    c = Cockpit(); fed(c)
    assert topics(c.handle(P + 'sas_mnvr', {'v': 1}, 0))['cmd/sas_mode'] == {'mode': 'maneuver'}
    c.handle(P + 'sas_mnvr', {'v': 0}, 0.1)
    fed(c, 0.5, vessel={'sas': True, 'sas_mode': 'stability'})
    assert 'cmd/sas_mode' not in topics(c.tick(0.6))                    # not within a second of the command
    assert topics(c.tick(1.1))['cmd/sas_mode'] == {'mode': 'maneuver'}
    fed(c, 1.5, vessel={'sas': True, 'sas_mode': 'maneuver'})
    assert 'cmd/sas_mode' not in topics(c.tick(3.0))                    # the game agrees
    # then the game changes it (the node deleted, KSP's own buttons): the panel follows, it does not fight
    sent = sum('cmd/sas_mode' in topics(fed(c, second, vessel={'sas': True, 'sas_mode': 'stability'}))
               for second in range(4, 10))
    assert sent == 0 and c.sas_mode_memory == 'stability'


def test_a_refused_sas_mode_is_tried_a_few_times_then_the_game_wins():
    c = Cockpit(); fed(c, 0, vessel={'sas': True, 'sas_mode': 'stability'})
    c.handle(P + 'sas_tgt', {'v': 1}, 0); c.handle(P + 'sas_tgt', {'v': 0}, 0.1)
    sent = sum('cmd/sas_mode' in topics(fed(c, second, vessel={'sas': True, 'sas_mode': 'stability'}))
               for second in range(1, 20))
    assert sent == 5                                                    # no target: refused for good
    assert c.published[O + 'lamp_sas_stab'] == {'on': True, 'blink': False}
    assert c.published[O + 'lamp_sas_tgt'] == {'on': False, 'blink': False}


def test_sas_coming_on_again_asks_for_the_last_mode_the_game_held():
    c = Cockpit(); fed(c, 0, vessel={'sas': True, 'sas_mode': 'prograde'})
    fed(c, 1, vessel={'sas': False, 'sas_mode': None})
    assert c.published[O + 'lamp_sas_pro'] == {'on': True, 'blink': False}     # the mode SAS will take
    fed(c, 3, vessel={'sas': True, 'sas_mode': 'stability'})                   # KSP's fallback
    assert c.last_commands['cmd/sas_mode'][0] == {'mode': 'prograde'}
    assert c.published[O + 'lamp_sas_pro']['blink']
    fed(c, 4, vessel={'sas': True, 'sas_mode': 'prograde'})
    assert c.published[O + 'lamp_sas_pro'] == {'on': True, 'blink': False}


def test_sas_mode_buttons_light_the_chosen_mode():
    c = Cockpit(); fed(c, 0, vessel={'sas': True, 'sas_mode': 'stability'})
    keys = ('stab', 'pro', 'retro', 'nml', 'anml', 'rad', 'arad', 'tgt', 'atgt', 'mnvr')
    lit = lambda: {key for key in keys if c.published[O + f'lamp_sas_{key}']['on']}
    assert lit() == {'stab'}                                            # nothing chosen yet: the game's mode
    # PRO, then MNVR: nothing in between is sent, as a knob turned from one to the other would
    sent = [topics(c.handle(P + 'sas_pro', {'v': v}, t)).get('cmd/sas_mode') for v, t in ((1, 1), (0, 1.1))]
    sent += [topics(c.handle(P + 'sas_mnvr', {'v': v}, t)).get('cmd/sas_mode') for v, t in ((1, 2), (0, 2.1))]
    assert [command for command in sent if command] == [{'mode': 'prograde'}, {'mode': 'maneuver'}]
    fed(c, 2.2, vessel={'sas': True, 'sas_mode': 'stability'})         # not taken yet
    assert lit() == {'mnvr'} and c.published[O + 'lamp_sas_mnvr']['blink']
    fed(c, 2.5, vessel={'sas': True, 'sas_mode': 'maneuver'})
    assert lit() == {'mnvr'} and not c.published[O + 'lamp_sas_mnvr']['blink']
    fed(c, 3, vessel={'sas': False, 'sas_mode': None})                 # SAS off: the mode it will take, steady
    assert lit() == {'mnvr'} and not c.published[O + 'lamp_sas_mnvr']['blink']
    fed(c, 4, vessel={'sas': False, 'sas_mode': 'retrograde'})         # the mock reports a mode with SAS off: ignored
    assert lit() == {'mnvr'}


def test_throttle_is_sent_again_when_the_game_disagrees():
    c = Cockpit(); fed(c)
    c.handle(P + 'eng_arm', {'v': 1}, 0)
    assert topics(c.handle(P + 'throttle', {'v': 0.8}, 0))['cmd/throttle'] == {'v': 0.8}
    assert 'cmd/throttle' not in topics(fed(c, 0.5, vessel={'throttle': 0.0}))      # the command is still on its way
    assert topics(fed(c, 1.5, vessel={'throttle': 0.0}))['cmd/throttle'] == {'v': 0.8}      # a gateway restarted
    assert 'cmd/throttle' not in topics(fed(c, 3, vessel={'throttle': 0.8}))
    c.handle('tlm/vessel', {'throttle': 0.0}, 5)
    c.handle('tlm/time', {'ut': 105, 'met': 70, 'warp': 50}, 5)                     # KSP holds it at 0 in time warp
    assert 'cmd/throttle' not in topics(c.tick(6.5))


def test_speed_reference_knob_acts_only_when_moved_and_its_led_shows_the_game():
    c = Cockpit(); fed(c, vessel={'speed_mode': 'surface'})
    assert 'cmd/speed_mode' not in topics(c.handle(P + 'speed_ref', {'v': 0}, 1))      # first report: not a command
    assert c.published[O + 'led_speed_ref'] == {'on': True, 'blink': True}            # knob ORBIT, game SURF
    assert topics(c.handle(P + 'speed_ref', {'v': 1}, 2))['cmd/speed_mode'] == {'mode': 'surface'}
    assert c.published[O + 'led_speed_ref'] == {'on': True, 'blink': False}


def test_stage_delta_v_on_the_pad_comes_from_the_engines_to_ignite():
    c = Cockpit()
    pad = {'stage': 4, 'mass': 20000.0, 'thrust': 0.0, 'thrust_avail': 0.0, 'isp': 0.0}
    fed(c, vessel=pad, flight={'alt': 70.0, 'p': 101325.0},
        resources={'stage': {'LiquidFuel': {'amount': 900, 'max': 900}, 'Oxidizer': {'amount': 1100, 'max': 1100}},
                   'total': {'ElectricCharge': {'amount': 90, 'max': 100}}})
    c.handle('tlm/orbit', {'body': 'Kerbin', 'apo': 0.0, 'peri': -600000.0}, 0)
    engine = {'x': 0, 'z': 0, 'stage': 3, 'on': False, 'thrust': 0.0, 'max': 0.0, 'fuel': True,
              'rated': 300000.0, 'isp_vac': 310.0, 'isp_sl': 285.0}
    c.handle('tlm/engines', {'engines': [engine], 'stage': 4, 'limit': 1.0, 'gimbal_locked': False}, 0)
    # Δv 285 s × g0 × ln(20 / 10) = 1937 m/s at sea level; no thrust yet, so the TWR is 0
    assert c.published[O + 'disp_twr']['text'] == '0.00'
    assert c.published[O + 'disp_dv']['text'] == '1937'
    # an engine lit but giving nothing is a flameout, not "before ignition": no figures
    c.handle('tlm/engines', {'engines': [{**engine, 'on': True, 'stage': 4}], 'stage': 4, 'limit': 1.0,
                             'gimbal_locked': False}, 1)
    assert c.published[O + 'disp_dv']['text'] == '-----' and c.published[O + 'disp_twr']['text'] == '0.00'


def test_hand_controller_axes_become_rotate_and_translate_commands():
    c = Cockpit(); fed(c)
    HC = 'panel/hc/in/'
    assert topics(c.handle(HC + 'rot_pitch', {'v': -0.6}, 1))['cmd/rotate'] == {'pitch': -0.6, 'yaw': 0.0, 'roll': 0.0}
    assert 'cmd/rotate' not in topics(c.handle(HC + 'rot_yaw', {'v': 0.02}, 1))         # inside the deadband
    assert topics(c.handle(HC + 'rot_pitch', {'v': 0.01}, 2))['cmd/rotate'] == {'pitch': 0.0, 'yaw': 0.0, 'roll': 0.0}
    assert topics(c.handle(HC + 'trans_fwd', {'v': 1.5}, 3))['cmd/translate'] == {'right': 0.0, 'up': 0.0, 'forward': 1.0}
    # main bus off: everything released
    out = topics(c.handle(P + 'cb_main', {'v': 0}, 4))
    assert out['cmd/translate'] == {'right': 0.0, 'up': 0.0, 'forward': 0.0} and out['cmd/throttle'] == {'v': 0.0}


def test_cutoff_lamp_blinks_until_the_lever_is_back_at_idle():
    c = Cockpit(); fed(c)
    c.handle(P + 'eng_arm', {'v': 1}, 0); c.handle(P + 'throttle', {'v': 0.8}, 0)
    c.handle(P + 'eng_cutoff', {'v': 1}, 1)
    assert c.published[O + 'lamp_cutoff'] == {'on': True, 'blink': True}
    assert 'cmd/throttle' not in topics(c.handle(P + 'throttle', {'v': 0.9}, 2))        # pushing it up does nothing
    c.handle(P + 'throttle', {'v': 0.0}, 3)
    assert c.published[O + 'lamp_cutoff'] == {'on': False, 'blink': False}
    assert topics(c.handle(P + 'throttle', {'v': 0.5}, 4))['cmd/throttle'] == {'v': 0.5}


def test_sas_lets_go_while_the_stick_is_off_centre():
    c = Cockpit(); fed(c, vessel={'sas': True})
    c.handle(P + 'sas', {'v': 1}, 0)
    HC = 'panel/hc/in/'
    out = topics(c.handle(HC + 'rot_yaw', {'v': 0.5}, 1))
    assert out['cmd/sas'] == {'on': False} and out['cmd/rotate']['yaw'] == 0.5
    # the game follows; no SAS DISAGREE and no "panel wins" re-command while steering
    for t in range(2, 6):
        assert 'cmd/sas' not in topics(fed(c, t, vessel={'sas': False}))
    assert 'cw_sas_dis' not in c.active_alarms()
    out = topics(c.handle(HC + 'rot_yaw', {'v': 0.0}, 6))
    assert out['cmd/sas'] == {'on': True} and out['cmd/rotate']['yaw'] == 0.0


def test_rcs_fine_scales_the_sticks():
    c = Cockpit(); fed(c)
    HC = 'panel/hc/in/'
    assert topics(c.handle(HC + 'trans_fwd', {'v': 1.0}, 1))['cmd/translate']['forward'] == 1.0
    out = topics(c.handle(P + 'rcs_fine', {'v': 1}, 2))                  # switching with the stick held
    assert out['cmd/translate']['forward'] == 0.3 and c.published[O + 'led_rcs_fine']['on']
    assert out['cmd/precision'] == {'on': True}                           # KSP's precision mode, for the keyboard
    assert topics(c.handle(HC + 'rot_roll', {'v': -0.5}, 3))['cmd/rotate']['roll'] == -0.15


def test_rcs_fine_wins_over_the_game_precision_mode():
    c = Cockpit(); fed(c)
    c.handle(P + 'rcs_fine', {'v': 1}, 1)
    assert topics(fed(c, 1, vessel={'precision': True})).get('cmd/precision') is None
    assert topics(fed(c, 3, vessel={'precision': False}))['cmd/precision'] == {'on': True}   # Caps Lock in the game


def test_a_small_throttle_left_in_the_game_is_cut():
    c = Cockpit(); fed(c)
    c.handle(P + 'throttle', {'v': 0.0}, 0)
    c.command('cmd/throttle', {'v': 0.0})
    assert topics(fed(c, 2, vessel={'throttle': 0.02}))['cmd/throttle'] == {'v': 0.0}


# ---------- power, lights, fuel cell, recovery ----------
def test_no_electric_charge_is_no_power():
    c = Cockpit()
    fed(c)
    c.handle(P + 'eng_arm', {'v': 1}, 1)
    c.handle(P + 'throttle', {'v': 1.0}, 1)
    out = topics(fed(c, 2, resources={'stage': {}, 'total': {'ElectricCharge': {'amount': 0.0, 'max': 100}}}))
    assert out['cmd/throttle'] == {'v': 0.0} and out['cockpit/power'] == {'on': False}
    assert c.published[O + 'disp_alt']['blank'] and not c.published[O + 'led_eng_arm']['on']
    assert 'cmd/stage' not in topics(c.handle(P + 'stage_arm', {'v': 1}, 3) + c.handle(P + 'stage', {'v': 1}, 3.1))
    # a craft with no battery at all is not "out of charge"
    c = Cockpit()
    fed(c, resources={'stage': {}, 'total': {}})
    assert c.powered() and c.published['cockpit/power'] == {'on': True}


def test_lights_panel():
    c = Cockpit(); fed(c)
    assert c.published['cockpit/lighting'] == {'cabin': False, 'backlight': False}
    assert topics(c.handle('panel/sys/in/backlight', {'v': 1}, 1))['cockpit/lighting'] == {'cabin': False, 'backlight': True}
    c.handle('panel/sys/in/cabin_light', {'v': 1}, 2)
    assert c.published['cockpit/lighting'] == {'cabin': True, 'backlight': True}
    out = topics(c.handle('panel/sys/in/lights', {'v': 1}, 3))         # EXTERNAL: the craft's lights
    assert out['cmd/lights'] == {'on': True} and out[S + 'led_lights'] == {'on': True, 'blink': True}
    fed(c, 4, resources={'stage': {}, 'total': {'ElectricCharge': {'amount': 0.0, 'max': 100}}})
    assert c.published['cockpit/lighting'] == {'cabin': False, 'backlight': False}       # no power, no light


def test_wheels_switch():
    c = Cockpit(); fed(c, vessel={'wheels': True})
    assert c.published[S + 'led_wheels'] == {'on': True, 'blink': True}     # the game's wheels on, the switch off
    c.handle('panel/sys/in/wheels', {'v': 1}, 1)
    assert c.published[S + 'led_wheels'] == {'on': True, 'blink': False}
    out = topics(c.handle('panel/sys/in/wheels', {'v': 0}, 1))
    assert out['cmd/wheels'] == {'on': False} and out[S + 'led_wheels'] == {'on': True, 'blink': True}
    fed(c, 2, vessel={'wheels': False})
    assert c.published[S + 'led_wheels'] == {'on': False, 'blink': False}
    fed(c, 3, vessel={'wheels': None})          # no reaction wheel on board: the lamp stays dark
    assert c.published[S + 'led_wheels'] == {'on': False, 'blink': False}


def test_fuel_cell_outside_temperature_and_ablator():
    c = Cockpit(); fed(c, vessel={'fuel_cell': False})
    out = topics(c.handle('panel/sys/in/fuel_cell', {'v': 1}, 1))
    assert out['cmd/fuel_cell'] == {'on': True} and out[S + 'led_fuel_cell'] == {'on': True, 'blink': True}
    fed(c, 2, vessel={'fuel_cell': True},
        resources={'stage': {}, 'total': {'ElectricCharge': {'amount': 90, 'max': 100}, 'Ablator': {'amount': 150, 'max': 200}}})
    c.handle('tlm/thermal', {'max': 0.3, 'outside': -42.4}, 2)
    assert c.published[S + 'led_fuel_cell'] == {'on': True, 'blink': False}
    assert c.published[S + 'disp_outside']['text'] == '-42' and c.published[S + 'bar_ablator'] == {'v': 0.75}


def test_speeds_follow_the_speed_reference_knob():
    c = Cockpit(); fed(c, flight={'v_orb': 500.0, 'vs': 300.0})
    shown = lambda: [c.published[O + name]['text'] for name in ('disp_hs', 'disp_vs', 'disp_speed')]
    assert shown() == ['400.0', '+300.0', '500.0']                    # ORBIT: horizontal from the total and the vertical
    c.handle(P + 'speed_ref', {'v': 1}, 1)
    assert shown() == ['300.0', '+300.0', '323.0']                  # SURF
    c.handle(P + 'speed_ref', {'v': 2}, 2)
    assert shown() == ['300.0', '+300.0', '323.0']                  # TGT reads the surface too


def test_dynamic_pressure_and_time_to_impact():
    c = Cockpit(); fed(c, flight={'q': 12340.0, 'radar': 500.0, 'vs': -20.0})
    assert c.published[O + 'disp_q']['text'] == '12.34'
    assert c.published[O + 'disp_impact']['text'] == '25'
    fed(c, 1, flight={'radar': 500.0, 'vs': 20.0})
    assert c.published[O + 'disp_impact']['text'] == '-----'                # climbing
    c.handle('tlm/flight', {'radar': 90000.0, 'vs': -20.0}, 2)
    c.handle('tlm/orbit', {'apo': 120000.0, 'peri': 80000.0}, 2)
    assert c.published[O + 'disp_impact']['text'] == '-----'                # descending along an orbit that stays up


def test_propellant_panel_shows_the_vessel_burn_time_and_rcs():
    c = Cockpit()
    resources = {'stage': {'LiquidFuel': {'amount': 90.0, 'max': 90.0}, 'Oxidizer': {'amount': 110.0, 'max': 110.0}},
                 'total': {'LiquidFuel': {'amount': 45.0, 'max': 180.0}, 'Oxidizer': {'amount': 110.0, 'max': 220.0},
                           'MonoPropellant': {'amount': 50.0, 'max': 100.0}, 'XenonGas': {'amount': 300.0, 'max': 400.0}}}
    fed(c, vessel={'mass': 4000.0, 'thrust': 0.0, 'thrust_avail': 20000.0, 'isp': 300.0}, resources=resources)
    sys_out = 'panel/sys/out/'
    assert c.published[sys_out + 'bar_lf'] == {'v': 0.25} and c.published[sys_out + 'bar_xenon'] == {'v': 0.75}
    # 1000 kg at 20 kN and 300 s: 147 s; 200 kg of monopropellant at 240 s: 121 m/s
    assert c.published[sys_out + 'disp_burn_time']['text'] == '147'
    assert c.published[sys_out + 'disp_rcs_dv']['text'] == '120.7'


def test_an_ion_stage_counts_its_xenon_only():
    c = Cockpit()
    stage = {'LiquidFuel': {'amount': 90.0, 'max': 90.0}, 'XenonGas': {'amount': 400.0, 'max': 800.0}}
    fed(c, vessel={'mass': 1000.0, 'thrust': 2000.0, 'thrust_avail': 2000.0, 'isp': 4200.0},
        resources={'stage': stage, 'total': {}})
    c.handle('tlm/engines', {'engines': [{'x': 0.0, 'z': 0.0, 'on': True, 'stage': 3, 'thrust': 2000.0, 'max': 2000.0, 'fuel': True,
                                         'propellants': ['XenonGas', 'ElectricCharge']}]}, 0)
    c.tick(0)
    # 40 kg of xenon at 2 kN and 4200 s: 824 s
    assert c.published['panel/sys/out/disp_burn_time']['text'] == '824'
    assert fit_number(4200 * 9.80665 * math.log(1000 / 960), 0, 5) == c.published[O + 'disp_dv']['text']


def test_life_support_panel_and_its_alarms():
    c = Cockpit()
    def aboard(t, oxygen, crew=3):
        totals = {'Food': {'amount': 4.388, 'max': 4.388}, 'Water': {'amount': 2.9, 'max': 2.9},
                  'Oxygen': {'amount': oxygen, 'max': 444.152}}
        fed(c, t, vessel={'crew': crew}, resources={'stage': {}, 'total': totals})
    aboard(0, 444.152)
    sys_out = 'panel/sys/out/'
    assert c.published[sys_out + 'disp_crew']['text'] == ' 3' and c.published[sys_out + 'bar_ls_oxygen'] == {'v': 1.0}
    assert c.published[sys_out + 'disp_ls_oxygen']['text'] == '24.0' and c.published[sys_out + 'disp_ls_food']['text'] == '24.0'
    assert not c.published[O + 'cw_ls_low']['on']
    aboard(1, 20.0)
    assert c.published[O + 'cw_ls_low']['on'] and not c.published[O + 'cw_ls_out']['on']
    aboard(2, 0.0)
    assert c.published[O + 'cw_ls_out']['on']
    aboard(3, 0.0, crew=0)                                                  # nobody aboard: nothing to warn about
    assert not c.published[O + 'cw_ls_out']['on'] and c.published[sys_out + 'disp_ls_oxygen']['text'] == '----'


def test_twr_follows_the_present_thrust():
    c = Cockpit()
    def flying(t, thrust):
        fed(c, t, vessel={'mass': 1000.0, 'thrust': thrust, 'thrust_avail': 20000.0, 'isp': 300.0},
            flight={'alt': 0.0})
        c.handle('tlm/orbit', {'body': 'Kerbin', 'apo': 80000.0, 'peri': -100000.0}, t)
    flying(0, 0.0)
    assert c.published[O + 'disp_twr']['text'] == '0.00'
    flying(1, 9810.0)
    assert c.published[O + 'disp_twr']['text'] == '1.00'


def test_twr_uses_the_body_the_game_sends():
    c = Cockpit()
    fed(c, 0, vessel={'mass': 1000.0, 'thrust': 9810.0, 'thrust_avail': 20000.0, 'isp': 300.0}, flight={'alt': 0.0})
    # JNSQ's Kerbin: 1 600 km, μ 2.5105e13, so g = 9.807 m/s² at the surface, as stock's 600 km one
    c.handle('tlm/orbit', {'body': 'Kerbin', 'mu': 2.5105024e13, 'radius': 1600000.0, 'apo': 80000.0, 'peri': -100000.0}, 0)
    assert c.published[O + 'disp_twr']['text'] == '1.00'
    # its Mun, 400 km: g = 1.42 m/s², where stock's table would say 1.63
    fed(c, 1, vessel={'mass': 1000.0, 'thrust': 1422.0, 'thrust_avail': 20000.0, 'isp': 300.0}, flight={'alt': 0.0})
    c.handle('tlm/orbit', {'body': 'Mun', 'mu': 2.2751428e11, 'radius': 400000.0, 'apo': 80000.0, 'peri': -100000.0}, 1)
    assert c.published[O + 'disp_twr']['text'] == '1.00'


def test_revert_to_launch_needs_its_arm_switch():
    c = Cockpit(); fed(c)
    SYS_IN = 'panel/sys/in/'
    assert 'cmd/game' not in topics(c.handle(SYS_IN + 'revert', {'v': 1}, 1))
    c.handle(SYS_IN + 'revert', {'v': 0}, 1.1)
    out = topics(c.handle(SYS_IN + 'revert_arm', {'v': 1}, 2))
    assert out['panel/sys/out/lamp_revert'] == {'on': True, 'blink': False}
    assert topics(c.handle(SYS_IN + 'revert', {'v': 1}, 3))['cmd/game'] == {'revert': True}


def test_landing_aid_shows_the_drift_and_the_touchdown_conditions():
    c = Cockpit()
    def descent(t, **flight):
        fed(c, t, vessel={'situation': 'flying', 'gear': True},
            flight={'radar': 50.0, 'vs': -5.0, 'v_right': 0.3, 'v_down': -0.4, **flight})
        c.handle('tlm/attitude', {'pitch': 85.0, 'heading': 90.0, 'roll': 0.0}, t)
    descent(0)
    assert c.published[O + 'disp_drift_right']['text'] == '+0.3' and c.published[O + 'disp_drift_up']['text'] == '+0.4'
    assert all(c.published[O + lamp]['on'] for lamp in ('lamp_td_sink', 'lamp_td_drift', 'lamp_td_upright', 'lamp_td_gear'))
    descent(1, vs=-9.0, v_right=2.0)                                        # 7 m/s allowed at 50 m
    assert not c.published[O + 'lamp_td_sink']['on'] and not c.published[O + 'lamp_td_drift']['on']
    descent(2, radar=5000.0)                                                # too high for the lamps to mean anything
    assert not c.published[O + 'lamp_td_gear']['on']


def test_reentry_panel():
    c = Cockpit(); fed(c, flight={'alt': 100000.0, 'vs': -100.0}, vessel={'chute_safe': 'risky'})
    c.handle('tlm/orbit', {'atm': 70000.0, 'peri': 30000.0}, 0)
    c.handle('tlm/thermal', {'max': 0.634, 'outside': -40.0}, 0)
    sys_out = 'panel/sys/out/'
    assert c.published[sys_out + 'disp_heat']['text'] == '63' and c.published[sys_out + 'disp_to_atm']['text'] == '300'
    assert c.published[sys_out + 'lamp_chute_risky']['on'] and not c.published[sys_out + 'lamp_chute_safe']['on']
    c.handle('tlm/orbit', {'atm': 70000.0, 'peri': 80000.0}, 1)             # this orbit stays above the atmosphere
    assert c.published[sys_out + 'disp_to_atm']['text'] == '-----'


def test_science_panel_steps_through_experiments_and_commands_the_one_shown():
    c = Cockpit(); fed(c)
    goo = {'title': 'Mystery Goo', 'available': True, 'data': False, 'inoperable': False, 'value': None, 'transmit': None}
    report = {'title': 'Crew Report', 'available': False, 'data': True, 'inoperable': False, 'value': 5.0, 'transmit': 3.2}
    c.handle('tlm/science', {'experiments': [goo, report], 'biome': 'Shores'}, 1)
    out, IN = 'panel/sci/out/', 'panel/sci/in/'
    assert c.published[out + 'txt_sci']['text'] == 'MYSTERY GOO' and c.published[out + 'led_sci_ready']['on']
    assert c.published[out + 'txt_biome']['text'] == 'SHORES'
    c.handle(IN + 'sci_next', {'v': 1}, 2)
    assert c.published[out + 'txt_sci']['text'] == 'CREW REPORT' and c.published[out + 'disp_sci_transmit']['text'] == '3.2'
    assert topics(c.handle(IN + 'sci_transmit', {'v': 1}, 3))['cmd/science'] == {'index': 1, 'action': 'transmit'}
    assert topics(c.handle(IN + 'sci_run_all', {'v': 1}, 4))['cmd/science'] == {'all': True}


def test_ablator_low_caution():
    c = Cockpit()
    fed(c, resources={'stage': {}, 'total': {'Ablator': {'amount': 100.0, 'max': 800.0}}})
    assert 'cw_ablator' in c.active_alarms()
    fed(c, 1, resources={'stage': {}, 'total': {'Ablator': {'amount': 400.0, 'max': 800.0}}})
    assert 'cw_ablator' not in c.active_alarms()


def test_outside_pressure_in_kilopascals():
    c = Cockpit(); fed(c, flight={'p': 101325.0})
    assert c.published['panel/sys/out/disp_pressure']['text'] == '101.3'
    fed(c, 1, flight={'p': 520.0})
    assert c.published['panel/sys/out/disp_pressure']['text'] == '0.52'


def test_fdai_controls_set_how_the_ball_is_drawn():
    c = Cockpit(); fed(c)
    assert c.published[O + 'fdai'] == {'needles': 'prograde', 'error_scale': 5, 'markers': True}
    c.handle(P + 'fdai_needles', {'v': 1}, 1)
    c.handle(P + 'fdai_error', {'v': 1}, 1)
    out = topics(c.handle(P + 'fdai_markers', {'v': 0}, 1))
    assert out[O + 'fdai'] == {'needles': 'retrograde', 'error_scale': 50, 'markers': False}


def test_attitude_displays_and_rates():
    c = Cockpit(); fed(c)

    def at(ut, pitch, heading, roll):
        c.handle('tlm/time', {'ut': ut, 'met': 0, 'warp': 1}, 1)          # on the pad the mission clock stands still
        c.handle('tlm/attitude', {'pitch': pitch, 'heading': heading, 'roll': roll}, 1)

    at(100.0, 60.0, 359.0, 179.0)
    assert c.published[O + 'disp_att_pitch']['text'] == '+60.0' and c.published[O + 'disp_att_hdg']['text'] == '359.0'
    assert c.published[O + 'disp_att_roll']['text'] == '+179.0' and c.published[O + 'disp_rate_roll']['text'] == '----'
    at(100.5, 61.0, 1.0, -179.0)                                          # heading and roll cross their wrap
    assert c.published[O + 'disp_rate_pitch']['text'] == '+2.0' and c.published[O + 'disp_rate_roll']['text'] == '+4.0'
    assert c.published[O + 'disp_rate_yaw']['text'] == '+1.9'             # 4 °/s of heading × cos 61°


def test_attitude_hold_holds_the_knobs_attitude_with_sas_off():
    c = Cockpit(); fed(c)
    c.handle(P + 'hold_pitch', {'v': 0.75}, 0.1)                       # +45°
    c.handle(P + 'hold_hdg', {'v': 0.25}, 0.2)                         # 90°, east
    assert c.published[O + 'disp_hold_pitch']['text'].strip() == '+45'
    assert topics(c.handle(P + 'hold', {'v': 1}, 1))['cmd/hold'] == {'on': True, 'pitch': 45, 'heading': 90}
    assert c.published[O + 'led_hold'] == {'on': True, 'blink': True}  # not there yet
    c.handle('tlm/attitude', {'pitch': 44.0, 'heading': 91.0}, 1.5)
    c.handle('tlm/vessel', {**c.vessel, 'hold': True}, 1.5)
    assert c.published[O + 'led_hold'] == {'on': True, 'blink': False}
    assert topics(c.handle(P + 'hold_hdg', {'v': 0.5}, 2))['cmd/hold']['heading'] == 180   # a new heading, at once
    # SAS on: the two would fight, so the hold lets go and its LED blinks
    c.handle(P + 'sas', {'v': 1}, 3)
    assert topics(c.tick(3.1))['cmd/hold'] == {'on': False}
    assert c.published[O + 'led_hold']['blink']
    c.handle(P + 'sas', {'v': 0}, 4)
    assert topics(c.tick(4.1))['cmd/hold']['on']
    # the stick takes over while off centre
    assert topics(c.handle('panel/hc/in/rot_pitch', {'v': 0.5}, 5))['cmd/hold'] == {'on': False}
    assert topics(c.handle('panel/hc/in/rot_pitch', {'v': 0.0}, 5.5))['cmd/hold']['on']
    assert topics(c.handle(P + 'hold', {'v': 0}, 6))['cmd/hold'] == {'on': False}
    assert c.published[O + 'led_hold'] == {'on': False, 'blink': False}


def test_next_stage_lamps_show_what_staging_does():
    c = Cockpit()
    fed(c, 0, vessel={'next_stage': {'stage': 3, 'engines': 5, 'solids': 2, 'decouple': False, 'clamps': True,
                                     'chutes': False, 'fairing': False}})
    lit = {key for key, lamp in (('engines', 'lamp_ns_engines'), ('solids', 'lamp_ns_solids'), ('decouple', 'lamp_ns_decouple'),
                                 ('clamps', 'lamp_ns_clamps'), ('chutes', 'lamp_ns_chutes'), ('fairing', 'lamp_ns_fairing'))
           if c.published[O + lamp]['on']}
    assert lit == {'engines', 'solids', 'clamps'}
    fed(c, 1, vessel={'next_stage': None})                              # no stage left: all dark
    assert not any(c.published[O + f'lamp_ns_{key}']['on'] for key in ('engines', 'solids', 'clamps'))
