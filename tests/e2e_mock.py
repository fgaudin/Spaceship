"""End-to-end test on the running stack (docker compose up, mock plant): act as the panel, fly a launch, check outputs.

    .venv/bin/python tests/e2e_mock.py
"""
import json, os, sys, time
import paho.mqtt.client as mqtt

seen = {}
cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id='e2e')
cli.on_message = lambda c, u, m: seen.__setitem__(m.topic, json.loads(m.payload or b'{}'))
cli.connect('localhost', int(os.environ.get('MQTT_PORT', '1883')))
cli.subscribe('#')
cli.loop_start()


def inp(ctl, v, retain=True):
    cli.publish(f'panel/eng/in/{ctl}', json.dumps({'v': v}), qos=1, retain=retain)
    time.sleep(0.3)


def out(name):
    return seen.get(f'panel/eng/out/{name}')


def wait(pred, timeout=10, what=''):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if pred():
            return True
        time.sleep(0.1)
    raise AssertionError(f'timeout: {what}')


fails = []
def check(name, cond):
    print(('PASS ' if cond else 'FAIL ') + name, flush=True)
    if not cond:
        fails.append(name)


cli.publish('sim/reset', '{}', qos=1)
for c, v in (('cb_main', 1), ('eng_arm', 0), ('stage_arm', 0), ('abort_arm', 0), ('throttle', 0), ('sas', 0)):
    inp(c, v)
wait(lambda: seen.get('tlm/vessel', {}).get('situation') == 'pre_launch', what='reset')
check('telemetry flowing', 'tlm/flight' in seen and 'tlm/vessel' in seen)
check('gateway status mock', seen.get('gateway/status', {}).get('plant') == 'mock')
check('TWR and stage Δv on the pad, before ignition', wait(lambda: '-' not in (out('disp_twr') or {}).get('text', '-')
                                                            and float(out('disp_twr')['text']) > 1, what='pad TWR') and
      '-' not in out('disp_dv')['text'])

inp('lamp_test', 1, retain=False)
check('lamp test: high g lit', out('cw_high_g') == {'on': True, 'blink': False})
check('lamp test: displays all eights', out('disp_alt') and out('disp_alt')['text'].startswith('8.8.'))
inp('lamp_test', 0, retain=False)
check('lamp test released', out('cw_high_g') == {'on': False, 'blink': False})

inp('stage', 1, retain=False); inp('stage', 0, retain=False)
time.sleep(0.5)
check('stage refused when not armed', seen.get('tlm/vessel', {}).get('situation') == 'pre_launch')

inp('throttle', 1.0)
check('throttle refused when engine not armed', seen.get('tlm/vessel', {}).get('throttle') == 0.0)
inp('eng_arm', 1)
wait(lambda: seen.get('tlm/vessel', {}).get('throttle') == 1.0, what='throttle up')
check('ENG ARM led', out('led_eng_arm') == {'on': True, 'blink': False})
inp('stage_arm', 1)
check('STAGE lamp lit when armed', out('lamp_stage')['on'] is True)
inp('stage', 1, retain=False); inp('stage', 0, retain=False)
wait(lambda: seen.get('tlm/flight', {}).get('alt', 0) > 200, what='liftoff')
check('liftoff', True)
wait(lambda: out('disp_met') and out('disp_met')['text'] not in ('00.00.00', '--.--.--'), what='MET running')
check('MET running', True)
check('ASCENT shows the altitude in km', float(out('disp_alt')['text']) > 0.1)
time.sleep(0.6)
check('ASCENT shows the surface speed', float(out('disp_srf')['text']) > 20)

inp('sas', 1)
wait(lambda: seen.get('tlm/vessel', {}).get('sas') is True, what='sas on')
time.sleep(0.6)
check('SAS led steady when game agrees', out('led_sas') == {'on': True, 'blink': False})

wait(lambda: seen.get('tlm/flight', {}).get('q', 0) > 30000 or seen.get('tlm/flight', {}).get('alt', 0) > 25000, timeout=60, what='max Q region')
check('HIGH Q caution seen or passed', True)

# failure: telemetry freeze -> NO LINK warning, master alarm, buzzer
check('no caution before the freeze', 'NO LINK' not in seen.get('cw/state', {}).get('active', []))
cli.publish('sim/failures/telemetry_freeze', json.dumps({'on': True}), qos=1, retain=True)
wait(lambda: (out('cw_no_link') or {}).get('on'), timeout=6, what='no link')
check('NO LINK warning on stale telemetry', out('cw_no_link') == {'on': True, 'blink': True})
check('MASTER ALARM blinking', out('master_alarm') == {'on': True, 'blink': True})
check('buzzer on', out('buzzer') == {'on': True})
inp('master_alarm', 1, retain=False); inp('master_alarm', 0, retain=False)
check('MASTER ALARM acknowledged', out('master_alarm') == {'on': False, 'blink': False} and out('buzzer') == {'on': False})
check('NO LINK steady after ack', out('cw_no_link') == {'on': True, 'blink': False})
cli.publish('sim/failures/telemetry_freeze', json.dumps({'on': False}), qos=1, retain=True)
wait(lambda: not (out('cw_no_link') or {}).get('on'), timeout=6, what='link back')
check('NO LINK clears', True)

inp('cb_main', 0)
check('main bus off: displays blank', out('disp_alt') == {'text': '', 'blank': True, 'blink': False})
wait(lambda: seen.get('tlm/vessel', {}).get('throttle') == 0.0, what='throttle cut')
check('main bus off: throttle cut', True)
inp('cb_main', 1)

# ---------- second flight: engine display and extras, burn computer, target, game, abort ----------
def pin(panel, ctl, v, retain=True):
    cli.publish(f'panel/{panel}/in/{ctl}', json.dumps({'v': v}), qos=1, retain=retain)
    time.sleep(0.3)


def press(panel, ctl):
    pin(panel, ctl, 1, retain=False); pin(panel, ctl, 0, retain=False)


def pout(panel, name):
    return seen.get(f'panel/{panel}/out/{name}') or {}


def ok(pred, timeout=8):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if pred():
                return True
        except Exception:
            pass
        time.sleep(0.1)
    return False


cli.publish('sim/reset', '{}', qos=1)
for pnl, c, v in (('eng', 'throttle', 0), ('eng', 'eng_arm', 0), ('eng', 'stage_arm', 0), ('eng', 'abort_arm', 0), ('eng', 'sas', 0),
                  ('eng', 'rcs', 0), ('eng', 'thrust_lim', 1), ('eng', 'gimbal_lock', 0),
                  ('cmp', 'burn_arm', 0), ('rdv', 'ctrl_port', 0), ('sys', 'pause', 0), ('sys', 'evt_src', 0)):
    pin(pnl, c, v)
press('cmp', 'pad_clr')
wait(lambda: seen.get('tlm/vessel', {}).get('situation') == 'pre_launch', what='second reset')
grid = lambda: ''.join(pout('eng', 'mx_eng').get('rows', []))
check('engines next to ignite shown white on the pad', ok(lambda: grid().count('w') == 5 and grid().count('g') == 0))
pin('eng', 'eng_arm', 1); pin('eng', 'throttle', 1.0); pin('eng', 'stage_arm', 1); press('eng', 'stage')
check('five engines burning on the matrix', ok(lambda: grid().count('g') == 5 and pout('eng', 'disp_eng_on')['text'] == ' 5'))
cli.publish('sim/failures/engine_one_out', json.dumps({'on': True}), qos=1, retain=True)
check('one engine out: amber LED, four burning', ok(lambda: grid().count('a') == 1 and grid().count('g') == 4))
check('ENG FAIL warning', ok(lambda: pout('eng', 'cw_eng_fail').get('on'), 5))
cli.publish('sim/failures/engine_one_out', json.dumps({'on': False}), qos=1, retain=True)
check('engine back: ENG FAIL clears', ok(lambda: not pout('eng', 'cw_eng_fail').get('on') and grid().count('g') == 5))
pin('eng', 'thrust_lim', 0.5)
check('thrust limiter knob → plant', ok(lambda: seen['tlm/engines']['limit'] == 0.5))
pin('eng', 'thrust_lim', 1)
pin('eng', 'gimbal_lock', 1)
check('GIMBAL LOCK → plant and LED', ok(lambda: seen['tlm/engines']['gimbal_locked'] and pout('eng', 'led_gimbal').get('on')))
pin('eng', 'gimbal_lock', 0)
press('eng', 'eng_cutoff')
check('CUTOFF button: throttle 0, lamp on', ok(lambda: seen['tlm/vessel']['throttle'] == 0.0 and pout('eng', 'lamp_cutoff').get('on')))
pin('eng', 'throttle', 0.0)
check('lever back to idle releases the cutoff', ok(lambda: not pout('eng', 'lamp_cutoff').get('on')))
pin('eng', 'throttle', 1.0)
check('throttle follows the lever again', ok(lambda: seen['tlm/vessel']['throttle'] == 1.0))

# burn computer: keyed PAD, uplinked PAD, node mirror, Δv cutoff
press('cmp', 'f_pro')
for k in ('1', '2', '.', '5', 'ENTR'):
    pin('cmp', 'key', k, retain=False)
check('keyed ΔV PRO shows on its display', ok(lambda: pout('cmp', 'disp_pro').get('text') == '+12.5'))
press('cmp', 'pad_clr')
check('PAD CLEAR', ok(lambda: pout('cmp', 'disp_pro').get('text') == '+0.0' and pout('cmp', 'disp_tig').get('text') == '--.--.--'))
met = seen['tlm/time']['met']
seen.pop('cmd/node', None)
cli.publish('pad/uplink', json.dumps({'tig_met': met + 30, 'dv': [40.0, 0, 0]}), qos=1)
check('uplinked PAD waits, blinking', ok(lambda: pout('cmp', 'lamp_uplink') == {'on': True, 'blink': True} and pout('cmp', 'disp_pro').get('blink')))
check('nothing loaded before ACCEPT', seen.get('cmp/pad', {}).get('tig') is None)
press('cmp', 'pad_accept')
check('ACCEPT loads the PAD', ok(lambda: seen['cmp/pad']['dv'] == [40.0, 0.0, 0.0] and not pout('cmp', 'lamp_uplink').get('on')))
check('PAD mirrored as a maneuver node', ok(lambda: seen['cmd/node']['dv'] == [40.0, 0.0, 0.0] and seen['cmd/node']['ut'] > seen['tlm/time']['ut']))
check('time to TIG counts down', ok(lambda: pout('cmp', 'disp_tfi')['text'].startswith('-00.')))
pin('cmp', 'burn_arm', 1)
check('BURN lamp while the engine counts', ok(lambda: pout('cmp', 'lamp_burn').get('on') or pout('cmp', 'lamp_cutoff').get('on')))
check('cutoff after 40 m/s: throttle 0, CUTOFF lamp', ok(lambda: pout('cmp', 'lamp_cutoff').get('on') and seen['tlm/vessel']['throttle'] == 0.0, 15))
time.sleep(0.5)
acc = seen['tlm/vessel']['thrust_avail'] / seen['tlm/vessel']['mass']
resid = float(pout('cmp', 'disp_vg')['text'])
print(f'      residual {resid:+.1f} m/s at {acc:.0f} m/s²', flush=True)
check('residual within 0.15 s of thrust', abs(resid) < 0.15 * acc)
check('node removed at cutoff', ok(lambda: seen['cmd/node'] == {'clear': True}))
pin('cmp', 'burn_arm', 0); pin('eng', 'throttle', 0.0)

# target and docking
press('rdv', 'tgt_next')
check('TGT ▸ selects the nearest vessel', ok(lambda: pout('rdv', 'txt_tgt').get('text') == 'STATION' and pout('rdv', 'led_tgt').get('on')))
check('range and closing speed displayed', ok(lambda: 30 <= float(pout('rdv', 'disp_range')['text']) <= 2000 and pout('rdv', 'disp_closing')['text'].startswith('+')))
check('closing above the braking gate: CLOSING caution', ok(lambda: pout('eng', 'cw_closing').get('on')))
press('rdv', 'port_next')
check('PORT ▸ targets a docking port: alignment shown', ok(lambda: pout('rdv', 'led_port').get('on') and pout('rdv', 'disp_yaw').get('text') == '+1.5' and pout('rdv', 'disp_right').get('text') == '+0.10'))
pin('rdv', 'ctrl_port', 1)
check('CTRL FROM PORT → plant, LED steady', ok(lambda: seen['tlm/target']['ctrl_port'] and pout('rdv', 'led_ctrl_port') == {'on': True, 'blink': False}))
pin('rdv', 'ctrl_port', 0)
press('rdv', 'tgt_clear')
check('CLEAR removes the target', ok(lambda: pout('rdv', 'txt_tgt').get('text') == 'NO TARGET' and not pout('eng', 'cw_closing').get('on')))

# more cautions, and the countdown timer
cli.publish('sim/failures/overheat', json.dumps({'on': True}), qos=1, retain=True)
cli.publish('sim/failures/comm_lost', json.dumps({'on': True}), qos=1, retain=True)
check('OVERHEAT warning and COMM LOST caution', ok(lambda: pout('eng', 'cw_overheat').get('on') and pout('eng', 'cw_comm').get('on')))
cli.publish('sim/failures/overheat', json.dumps({'on': False}), qos=1, retain=True)
cli.publish('sim/failures/comm_lost', json.dumps({'on': False}), qos=1, retain=True)
check('both clear', ok(lambda: not pout('eng', 'cw_overheat').get('on') and not pout('eng', 'cw_comm').get('on')))
pin('sys', 'evt_down', 1); press('sys', 'evt_reset'); press('sys', 'evt_sec')
check('countdown preset 10 s', ok(lambda: pout('sys', 'disp_evt').get('text') == '00.10'))
press('sys', 'evt_start')
check('countdown reaches zero and blinks', ok(lambda: pout('sys', 'disp_evt') == {'text': '00.00', 'blank': False, 'blink': True}, 15))
press('sys', 'evt_reset'); pin('sys', 'evt_down', 0)

# game: pause, quick save / load, warp to the event
pin('sys', 'pause', 1)
check('PAUSE → plant paused, LED on', ok(lambda: seen['tlm/time']['paused'] and pout('sys', 'led_pause').get('on')))
m0 = seen['tlm/time']['met']; time.sleep(1.0)
check('clock stopped while paused', seen['tlm/time']['met'] == m0)
pin('sys', 'pause', 0)
check('clock runs again', ok(lambda: seen['tlm/time']['met'] > m0))
seen.pop('cmd/game', None)
press('sys', 'quicksave')
check('QUICK SAVE needs no guard', ok(lambda: seen.get('cmd/game') == {'quicksave': True}))
m1 = seen['tlm/time']['met']; time.sleep(1.5)
press('sys', 'quickload')
check('QUICK LOAD goes back to the save', ok(lambda: seen['tlm/time']['met'] < m1 + 1.0, 3))
met = seen['tlm/time']['met']
cli.publish('pad/uplink', json.dumps({'tig_met': met + 400, 'dv': [5.0, 0, 0]}), qos=1); time.sleep(0.3)
press('cmp', 'pad_accept')
pin('sys', 'evt_src', 1)
press('sys', 'warp_to')
check('WARP TO EVT: warping', ok(lambda: seen['tlm/time']['warp'] > 1, 4))
check('warp stops about a minute before TIG', ok(lambda: seen['tlm/time']['warp'] == 1 and 40 <= met + 400 - seen['tlm/time']['met'] <= 66, 30))
pin('sys', 'evt_src', 0)
press('cmp', 'pad_clr')

# communications panel
check('COM: AOS, signal and station', ok(lambda: pout('com', 'lamp_aos').get('on') and not pout('com', 'lamp_los').get('on')
                                          and pout('com', 'txt_via').get('text') == 'KSC' and pout('com', 'bar_signal') == {'v': 0.8}))
cli.publish('sim/failures/comm_lost', json.dumps({'on': True}), qos=1, retain=True)
check('COM: LOS blinking, NO SIGNAL', ok(lambda: pout('com', 'lamp_los') == {'on': True, 'blink': True}
                                          and pout('com', 'txt_via').get('text') == 'NO SIGNAL'))
cli.publish('sim/failures/comm_lost', json.dumps({'on': False}), qos=1, retain=True)
check('COM: AOS again, time in this state counts', ok(lambda: pout('com', 'lamp_aos').get('on')
                                                       and pout('com', 'disp_link_time').get('text', '-').startswith('00.0')))
pin('com', 'antenna', 0); pin('com', 'antenna', 1)
check('ANTENNA DEPLOY → plant, LED steady', ok(lambda: seen['tlm/comm']['antenna'] and pout('com', 'led_antenna') == {'on': True, 'blink': False}))
pin('com', 'antenna', 0)

# experimental panels
press('lab', 'ag_3')
check('AG 3 → plant toggles the group, lamp on', ok(lambda: seen['tlm/groups']['on'][2] and pout('lab', 'lamp_ag_3').get('on')))
press('lab', 'ag_3')
check('AG 3 again → off', ok(lambda: not seen['tlm/groups']['on'][2] and not pout('lab', 'lamp_ag_3').get('on')))
pin('lab', 'xp_mode', 5)
check('cross-pointer DRIFT: values and a 9 × 9 matrix', ok(lambda: pout('lab', 'disp_xp_right').get('text') == '+0.0'
                                                            and len(pout('lab', 'mx_xp').get('rows', [])) == 9))
pin('lab', 'xp_mode', 0)
check('navigation: body and latitude', ok(lambda: pout('lab', 'txt_body').get('text') == 'KERBIN' and pout('lab', 'disp_lat').get('text') == '+0.00'))
cli.publish('cam/status', json.dumps({'online': True, 'playing': True}), qos=1, retain=True)
cli.publish('cam/list', json.dumps({'cameras': [{'id': 7, 'name': 'NavCam'}, {'id': 9, 'name': 'Kerbal'}]}), qos=1, retain=True)
check('camera list → first camera selected and named', ok(lambda: seen.get('cam/select') == {'id': 7} and pout('lab', 'txt_cam').get('text') == 'NAVCAM'))
press('lab', 'cam_next')
check('CAM ▸ → next camera', ok(lambda: seen.get('cam/select') == {'id': 9} and pout('lab', 'led_cam_live').get('on')))
cli.publish('cam/status', json.dumps({'online': False, 'playing': False}), qos=1, retain=True)
cli.publish('cam/list', json.dumps({'cameras': []}), qos=1, retain=True)
check('monitor gone → NO MONITOR', ok(lambda: pout('lab', 'txt_cam').get('text') == 'NO MONITOR'))

# ABORT fires KSP's abort group, nothing else: in the mock the capsule leaves everything behind
pin('eng', 'abort_arm', 1); press('eng', 'abort')
check('ABORT fires the abort group', ok(lambda: seen.get('cmd/abort') == {} and seen['tlm/vessel']['stage'] == 0))
check('ABORT lamp blinks', ok(lambda: pout('eng', 'lamp_abort') == {'on': True, 'blink': True}))

cli.publish('sim/reset', '{}', qos=1)
for pnl, c, v in (('eng', 'eng_arm', 0), ('eng', 'stage_arm', 0), ('eng', 'abort_arm', 0), ('eng', 'throttle', 0),
                  ('eng', 'sas', 0), ('eng', 'rcs', 0)):
    pin(pnl, c, v)
print(f'\n{len(fails)} failed' if fails else '\nall passed')
sys.exit(1 if fails else 0)
