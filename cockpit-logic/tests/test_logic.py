import os, sys
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
    assert out[O + 'disp_a']['text'].startswith('8.8.')
    out = topics(c.handle(P + 'lamp_test', {'v': 0}, 2))
    assert out[O + 'cw_high_g'] == {'on': False, 'blink': False}


def test_main_breaker_kills_outputs_and_throttle():
    c = Cockpit()
    fed(c)
    c.handle(P + 'eng_arm', {'v': 1}, 1)
    c.handle(P + 'throttle', {'v': 1.0}, 1)
    out = topics(c.handle(P + 'cb_main', {'v': 0}, 2))
    assert out['cmd/throttle'] == {'v': 0.0}
    assert out[O + 'disp_a'] == {'text': '', 'blank': True, 'blink': False}
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
    assert out[O + 'disp_a'] == {'text': '-------', 'blank': False, 'blink': False}


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
    c.handle(P + 'gear', {'v': 1}, 1)
    out = topics(fed(c, 3))
    assert 'cmd/gear' not in out
    assert out.get(O + 'led_gear', c.published[O + 'led_gear']) == {'on': True, 'blink': True}


def test_display_selector_and_formats():
    c = Cockpit()
    fed(c)
    assert c.published[O + 'disp_a']['text'] == '12.35'           # ALT in km
    out = topics(c.handle(P + 'disp_sel', {'v': 3}, 1))
    assert out[O + 'disp_a']['text'] == '323.0'                    # VEL
    assert c.published[O + 'disp_met']['text'] == format_mission_time(65)
    assert fit_number(123456.78, 1, 7) == '123456.8'
    assert fit_number(-1.5, 1, 7) == '-1.5'


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


# ---------- abort modes, engine extras, engine display, rendezvous, warp and game ----------
R = 'panel/rdv/out/'
S = 'panel/sys/out/'


def abort(c, mode):
    c.handle(P + 'abort_mode', {'v': mode}, 1)
    c.handle(P + 'abort_arm', {'v': 1}, 2)
    return topics(c.handle(P + 'abort', {'v': 1}, 3))


def test_abort_modes():
    c = Cockpit(); fed(c)
    c.handle(P + 'eng_arm', {'v': 1}, 0.5); c.handle(P + 'throttle', {'v': 0.6}, 0.6)
    out = abort(c, 0)                                    # PAD: cut (held while the lever is up), abort group
    assert 'cmd/abort' in out and 'cmd/stage' not in out and c.throttle_cut_latched
    c = Cockpit(); fed(c)
    out = abort(c, 1)                                    # ASCENT: cut, stage, SAS and RCS on
    assert 'cmd/stage' in out and 'cmd/abort' not in out and out['cmd/sas'] == {'on': True} and out['cmd/rcs'] == {'on': True}
    c = Cockpit(); fed(c)
    out = abort(c, 2)                                    # ORBIT: nothing thrown away
    assert 'cmd/stage' not in out and 'cmd/abort' not in out and out['cmd/sas_mode'] == {'mode': 'stability'}
    c = Cockpit(); fed(c)
    c.handle(P + 'eng_arm', {'v': 1}, 0.5); c.handle(P + 'throttle', {'v': 0.6}, 0.6)
    out = abort(c, 3)                                    # DESCENT: the throttle stays with the pilot
    assert 'cmd/abort' in out and out['cmd/sas_mode'] == {'mode': 'radial'} and 'cmd/throttle' not in out and not c.throttle_cut_latched


def test_abort_forced_sas_is_not_fought_until_the_switch_moves():
    c = Cockpit(); fed(c)
    c.handle(P + 'sas', {'v': 0}, 0.5)
    abort(c, 2)
    out = topics(fed(c, 6, vessel={'sas': True, 'rcs': True}))        # the switch says off, the abort said on
    assert 'cmd/sas' not in out and c.published[O + 'led_sas'] == {'on': True, 'blink': False}
    assert topics(c.handle(P + 'sas', {'v': 1}, 7))['cmd/sas'] == {'on': True} and 'sas' not in c.forced_switches


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


def test_engines_next_to_ignite_show_white_before_ignition():
    c = Cockpit(); fed(c)
    engines(c, 1, [eng(0, 0, on=False, thrust=0, stage=3), eng(0, 0, on=False, thrust=0, stage=2)], stage=4, throttle=0.0)
    assert c.published[O + 'mx_eng']['rows'][4] == '....w....'


def test_rendezvous_panel():
    c = Cockpit(); fed(c)
    assert c.published[R + 'txt_tgt']['text'] == 'NO TARGET'
    assert topics(c.handle('panel/rdv/in/tgt_next', {'v': 1}, 1))['cmd/target'] == {'step': 1}
    c.handle('tlm/target', {'set': True, 'name': 'Orbiter', 'range': 1200.0, 'closing': 2.5, 'los_rate': 0.31, 'rel_v': 2.6,
                            'ctrl_port': False}, 2)
    s = c.published
    assert s[R + 'txt_tgt']['text'] == 'ORBITER' and s[R + 'disp_range']['text'] == '1200.0' and s[R + 'disp_closing']['text'] == '+2.50'
    assert s[R + 'disp_gate']['text'] == '3.00' and not s[R + 'lamp_overspeed']['on'] and not s[O + 'cw_closing']['on']
    c.handle('tlm/target', {'set': True, 'name': 'Orbiter', 'range': 400.0, 'closing': 2.5, 'los_rate': 0.31, 'rel_v': 2.6,
                            'ctrl_port': False}, 3)
    assert s[R + 'lamp_overspeed'] == {'on': True, 'blink': True} and s[O + 'cw_closing']['on']
    port = {'axial': 4.0, 'x': 0.1, 'z': -0.2, 'v_axial': -0.1, 'vx': 0, 'vz': 0, 'angle': 3.0, 'from_port': True,
            'right': 0.1, 'up': -0.2, 'fwd': 4.0, 'v_right': -0.02, 'v_up': 0.0, 'yaw': 1.5, 'pitch': -2.5, 'roll': 12.0}
    c.handle('tlm/target', {'set': True, 'name': 'Orbiter', 'range': 4.0, 'closing': 0.1, 'rel_v': 0.1, 'ctrl_port': True,
                            'port': port}, 4)
    assert s[R + 'lamp_capture']['on'] and s[R + 'disp_up']['text'] == '-0.20' and s[R + 'disp_vright']['text'] == '-0.02'
    assert s[R + 'disp_yaw']['text'] == '+1.5' and s[R + 'disp_pitch']['text'] == '-2.5' and s[R + 'disp_roll']['text'] == '+12.0'
    assert s[R + 'disp_vaxial']['text'] == '+0.10' and not s[R + 'lamp_aligned']['on']          # pitch is 2.5° off
    assert s[R + 'led_ctrl_port'] == {'on': True, 'blink': True}          # the game controls from the port, the switch is off
    c.handle('tlm/target', {'set': True, 'name': 'Orbiter', 'range': 4.0, 'closing': 0.5, 'rel_v': 0.5, 'ctrl_port': True,
                            'port': {**port, 'v_axial': -0.5}}, 5)
    assert not s[R + 'lamp_capture']['on']                                # too fast for the capture envelope
    assert 'cmd/control_from' not in topics(c.handle('panel/rdv/in/ctrl_port', {'v': 0}, 6))
    assert topics(c.handle('panel/rdv/in/ctrl_port', {'v': 1}, 7))['cmd/control_from'] == {'port': True}


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
    assert 'cmd/game' not in topics(c.handle('panel/sys/in/quickload', {'v': 1}, 4))        # needs SAVE ARM
    c.handle('panel/sys/in/quickload', {'v': 0}, 4.1)
    c.handle('panel/sys/in/save_arm', {'v': 1}, 5)
    assert topics(c.handle('panel/sys/in/quickload', {'v': 1}, 6))['cmd/game'] == {'quickload': True}


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
    assert not c.published[O + 'lamp_05g']['on']
    fed(c, 3, vessel={'thrust': 0.0, 'situation': 'sub_orbital'}, flight={'vs': -300.0, 'g': 0.06})
    assert c.published[O + 'lamp_05g']['on']
    fed(c, 4, vessel={'thrust': 0.0, 'situation': 'flying'}, flight={'vs': 200.0, 'g': 0.5})   # coasting upwards: not an entry
    assert not c.published[O + 'lamp_05g']['on']


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
    fed(c, 6, vessel={'situation': 'orbiting'})
    c.handle('tlm/orbit', {'body': 'Kerbin', 'apo': 90000.0, 'peri': 40000.0, 't_soi': None}, 6)
    assert 'cw_peri' in c.active_alarms() and 'cw_soi' not in c.active_alarms()
    c.handle('tlm/orbit', {'body': 'Mun', 'apo': 90000.0, 'peri': 40000.0, 't_soi': 90.0}, 7)
    assert 'cw_peri' not in c.active_alarms() and 'cw_soi' in c.active_alarms()


def test_burn_cautions_attitude_and_residual():
    c = Cockpit(); fed(c, vessel={'isp': 345.0})
    c.handle('pad/uplink', {'tig_met': 85, 'dv': [50, 0, 0]}, 1); c.handle('panel/cmp/in/pad_accept', {'v': 1}, 1)
    c.handle('tlm/node', {'set': True, 'ut': c.node_mirror.known_node['ut'], 'dv': [50.0, 0.0, 0.0], 'att_err': 20.0}, 4)
    assert 'cw_att' in c.active_alarms()                                        # 20 s to TIG and 20° off
    c.handle('tlm/node', {'set': True, 'ut': c.node_mirror.known_node['ut'], 'dv': [50.0, 0.0, 0.0], 'att_err': 2.0}, 5)
    assert 'cw_att' not in c.active_alarms() and c.published['panel/cmp/out/disp_att']['text'] == '2.0'
    c.burn_computer.cutoff, c.burn_computer.delta_v_counted = True, 47.0
    assert 'cw_resid' in c.active_alarms()                                      # 3 m/s short of 50
    c.burn_computer.delta_v_counted = 49.8
    assert 'cw_resid' not in c.active_alarms()


def test_undock_needs_arm_and_docked_lamp():
    c = Cockpit(); fed(c)
    c.handle('tlm/target', {'set': False, 'ctrl_port': False, 'docked': True}, 1)
    assert c.published[R + 'lamp_docked']['on']
    assert 'cmd/undock' not in topics(c.handle('panel/rdv/in/undock', {'v': 1}, 2))
    c.handle('panel/rdv/in/undock', {'v': 0}, 2.1)
    c.handle('panel/rdv/in/undock_arm', {'v': 1}, 3)
    assert topics(c.handle('panel/rdv/in/undock', {'v': 1}, 4))['cmd/undock'] == {}
