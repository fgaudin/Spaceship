"""End-to-end test with KSP: the stack with gateway-ksp (not the mock), acting as the panels; every result is checked on
the bus (tlm/*, panel outputs) and against KSP itself through a separate kRPC connection (ground truth).

    docker compose stop plant-mock && docker compose --profile ksp up -d --build gateway-ksp
    .venv/bin/python tests/e2e_ksp.py [--save lor3-selftest-lko]

Loads the save (vessel in orbit), so nothing irreversible is tested: no staging, no abort, no chute.
"""
import json, math, sys, time
import krpc
import paho.mqtt.client as mqtt

SAVE = sys.argv[sys.argv.index('--save') + 1] if '--save' in sys.argv else 'lor3-selftest-lko'
seen = {}
cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id='e2e-ksp')
cli.on_message = lambda c, u, m: seen.__setitem__(m.topic, json.loads(m.payload or b'{}'))
cli.connect('localhost', 1883)
cli.subscribe('#')
cli.loop_start()
conn = krpc.connect(name='e2e-ksp')
sc = conn.space_center


def inp(panel, ctl, v, retain=True):
    cli.publish(f'panel/{panel}/in/{ctl}', json.dumps({'v': v}), qos=1, retain=retain)
    time.sleep(0.3)


def press(panel, ctl):
    inp(panel, ctl, 1, retain=False)
    inp(panel, ctl, 0, retain=False)


def out(panel, name):
    return seen.get(f'panel/{panel}/out/{name}', {})


def wait(pred, timeout=8):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if pred():
                return True
        except Exception:
            pass
        time.sleep(0.1)
    return False


fails = []
def check(name, cond, info=''):
    print(('PASS ' if cond else 'FAIL ') + name + (f'   [{info}]' if info and not cond else ''), flush=True)
    if not cond:
        fails.append(name)


# ---------- setup: load the save, zero the throttle (KSP sets 50 % on load, G11) ----------
sc.load(SAVE)
for _ in range(100):
    try:
        sc.active_vessel.control.throttle = 0.0
        break
    except Exception:
        time.sleep(0.1)
time.sleep(3)
v = sc.active_vessel
v.control.throttle = 0.0
print(f'loaded {SAVE}: {v.name}, {v.situation.name}, {v.orbit.body.name}', flush=True)
for p, c, val in (('eng', 'cb_main', 1), ('eng', 'eng_arm', 0), ('eng', 'stage_arm', 0), ('eng', 'abort_arm', 0),
                  ('eng', 'throttle', 0), ('eng', 'sas', 0), ('eng', 'rcs', 0), ('sys', 'lights', 0), ('eng', 'sas_mode', 0),
                  ('sys', 'solar', 0), ('sys', 'brakes', 0), ('sys', 'evt_src', 0), ('sys', 'chute_arm', 0),
                  ('eng', 'thrust_lim', 1), ('eng', 'gimbal_lock', 0), ('cmp', 'burn_arm', 0),
                  ('rdv', 'ctrl_port', 0), ('sys', 'pause', 0)):
    inp(p, c, val)

# ---------- link ----------
check('gateway connected to KSP', wait(lambda: seen['gateway/status']['plant'] == 'ksp' and seen['gateway/status']['connected'], 20))
check('gateway bound the vessel', wait(lambda: seen['gateway/status']['vessel'] == v.name, 20), seen.get('gateway/status'))
for t in ('tlm/time', 'tlm/flight', 'tlm/vessel', 'tlm/attitude', 'tlm/orbit', 'tlm/resources', 'tlm/target'):
    check(f'{t} flowing', wait(lambda: t in seen, 10))
check('no NO LINK', wait(lambda: not out('eng', 'cw_no_link').get('on'), 10))

# ---------- telemetry against KSP ----------
fl, ve, orb, att = seen['tlm/flight'], seen['tlm/vessel'], seen['tlm/orbit'], seen['tlm/attitude']
o = v.orbit
check('apoapsis matches KSP', abs(orb['apo'] - o.apoapsis_altitude) < 200, (orb['apo'], o.apoapsis_altitude))
check('true anomaly published', isinstance(orb.get('nu'), (int, float)))
check('mass matches KSP', abs(ve['mass'] - v.mass) < 50, (ve['mass'], v.mass))
f = v.flight()
check('pitch/heading match the navball', abs(att['pitch'] - f.pitch) < 2 and abs(((att['heading'] - f.heading) + 180) % 360 - 180) < 2,
      (att, f.pitch, f.heading))
check('north/east speed published', fl.get('vn') is not None and fl.get('ve') is not None)
check('solar and chute state published', 'solar' in ve and ve.get('chute') in ('stowed', 'armed', 'deployed', 'cut', None), ve)

# ---------- ENG panel → KSP ----------
inp('eng', 'sas', 1)
check('SAS switch → KSP SAS on', wait(lambda: v.control.sas))
check('SAS LED shows the game', wait(lambda: out('eng', 'led_sas') == {'on': True, 'blink': False}))
inp('eng', 'sas_mode', 1)
check('SAS mode rotary → prograde', wait(lambda: v.control.sas_mode == sc.SASMode.prograde), v.control.sas_mode)
check('tlm sas_mode prograde', wait(lambda: seen['tlm/vessel']['sas_mode'] == 'prograde'))
inp('eng', 'sas_mode', 0)
v.control.sas = False                                   # the game disagrees with the switch → panel wins
check('panel wins: SAS re-commanded on', wait(lambda: v.control.sas, 5))
inp('eng', 'sas', 0)
check('SAS off', wait(lambda: not v.control.sas))
inp('eng', 'rcs', 1)
check('RCS switch → KSP', wait(lambda: v.control.rcs))
inp('eng', 'rcs', 0)
check('RCS off', wait(lambda: not v.control.rcs))
inp('sys', 'lights', 1)
check('lights switch → KSP', wait(lambda: v.control.lights))
inp('sys', 'lights', 0)
inp('eng', 'throttle', 0.3)
check('throttle refused without ENG ARM', wait(lambda: v.control.throttle == 0.0) and seen['tlm/vessel']['throttle'] == 0.0)
inp('eng', 'eng_arm', 1)
check('throttle with ENG ARM → KSP 0.3', wait(lambda: abs(v.control.throttle - 0.3) < 0.01), v.control.throttle)
inp('eng', 'cb_main', 0)
check('MAIN BUS off → throttle 0', wait(lambda: v.control.throttle == 0.0))
check('MAIN BUS off → displays blank', wait(lambda: out('eng', 'disp_alt').get('blank')))
inp('eng', 'cb_main', 1)
inp('eng', 'throttle', 0.0)
inp('eng', 'eng_arm', 0)
check('throttle back to 0', wait(lambda: v.control.throttle == 0.0))
apo_txt = out('lab', 'disp_apo').get('text', '')
check('ORBIT shows APO in km', wait(lambda: abs(float(out('lab', 'disp_apo')['text']) - o.apoapsis_altitude / 1000) < 1), apo_txt)

# ---------- SYS panel ----------
has_solar = any(p.deployable for p in v.parts.solar_panels)
if has_solar:
    inp('sys', 'solar', 1)
    check('SOLAR switch → panels deploying', wait(lambda: any(p.state.name in ('extending', 'extended') for p in v.parts.solar_panels), 8))
    check('solar LED on', wait(lambda: out('sys', 'led_solar').get('on'), 15))
    inp('sys', 'solar', 0)
    check('SOLAR off → retracting', wait(lambda: all(p.state.name in ('retracting', 'retracted') for p in v.parts.solar_panels if p.deployable), 8))
inp('sys', 'brakes', 1)
check('BRAKES switch → KSP', wait(lambda: v.control.brakes))
inp('sys', 'brakes', 0)
check('stage Δv displayed', wait(lambda: out('eng', 'disp_dv').get('text', '-').replace('-', '') != ''), out('eng', 'disp_dv'))
check('TWR displayed', wait(lambda: '-' not in out('eng', 'disp_twr').get('text', '-')), out('eng', 'disp_twr'))
check('EC displayed', wait(lambda: '-' not in out('sys', 'disp_ec').get('text', '-')), out('sys', 'disp_ec'))
inp('sys', 'evt_src', 2)
t_apo = o.time_to_apoapsis
check('event timer counts down to apoapsis', wait(lambda: out('sys', 'disp_evt')['text'].startswith('-')), out('sys', 'disp_evt'))
inp('sys', 'evt_src', 0)
press('sys', 'warp_up'); press('sys', 'warp_up')
check('FASTER → KSP warps', wait(lambda: sc.rails_warp_factor >= 1, 6), sc.rails_warp_factor)
check('warp rate on the panel', wait(lambda: float(out('sys', 'disp_warp').get('text') or 1) > 1, 6), out('sys', 'disp_warp'))
press('sys', 'warp_stop')
check('STOP WARP → 1×', wait(lambda: sc.rails_warp_factor == 0 and sc.warp_rate == 1, 8))
v.control.throttle = 0.0

# ---------- target (set through kRPC: there is no target selector on a panel yet) ----------
others = [w for w in sc.vessels if w != v and w.orbit.body == v.orbit.body and w.type.name != 'debris']
if others:
    tgt = min(others, key=lambda w: abs(w.orbit.semi_major_axis - v.orbit.semi_major_axis))
    sc.target_vessel = tgt
    check(f'tlm/target follows the KSP target ({tgt.name})', wait(lambda: seen['tlm/target'].get('set') and seen['tlm/target']['name'] == tgt.name, 6))
    nrf = v.orbit.body.non_rotating_reference_frame
    rng = math.dist(v.position(nrf), tgt.position(nrf))
    check('target range matches KSP', wait(lambda: abs(seen['tlm/target']['range'] - rng) / rng < 0.01), (seen['tlm/target'].get('range'), rng))
    sc.clear_target()
    check('target cleared', wait(lambda: seen['tlm/target'].get('set') is False, 6))

# ---------- engines: status matrix, limiter, gimbal, cutoff ----------
v = sc.active_vessel
lit = [e for e in v.parts.engines if e.active]
grid = lambda: ''.join(out('eng', 'mx_eng').get('rows', []))
check('tlm/engines lists every engine', wait(lambda: len(seen['tlm/engines']['engines']) == len(v.parts.engines)), seen.get('tlm/engines'))
check('matrix: one white LED per lit, idle engine', wait(lambda: grid().count('w') == len(lit) and grid().count('g') == 0), grid())
if lit:
    inp('eng', 'thrust_lim', 0.5)
    check('THRUST LIMIT knob → engines at 50 %', wait(lambda: all(abs(e.thrust_limit - 0.5) < 0.01 for e in lit if not e.throttle_locked)))
    inp('eng', 'thrust_lim', 1)
    check('limiter back to 100 %', wait(lambda: all(e.thrust_limit > 0.99 for e in lit if not e.throttle_locked)))
gim = [e for e in v.parts.engines if e.gimballed]
if gim:
    inp('eng', 'gimbal_lock', 1)
    check('GIMBAL LOCK → engines, LED on', wait(lambda: all(e.gimbal_locked for e in gim) and out('eng', 'led_gimbal').get('on')))
    inp('eng', 'gimbal_lock', 0)
    check('gimbal free again', wait(lambda: not any(e.gimbal_locked for e in gim) and not out('eng', 'led_gimbal').get('on')))

# ---------- burn computer: PAD → node, SAS MNVR, a real 5 m/s burn cut off by the computer ----------
press('cmp', 'pad_clr')
for n in list(v.control.nodes):
    n.remove()
met = seen['tlm/time']['met']
cli.publish('pad/uplink', json.dumps({'tig_met': met + 40, 'dv': [5.0, 0.0, 0.0]}), qos=1)
check('uplinked PAD blinks on the computer', wait(lambda: out('cmp', 'lamp_uplink').get('on') and out('cmp', 'disp_pro').get('text') == '+5.0'))
check('no node before ACCEPT', len(v.control.nodes) == 0)
press('cmp', 'pad_accept')
check('ACCEPT → KSP maneuver node, 5 m/s prograde', wait(lambda: len(v.control.nodes) == 1 and abs(v.control.nodes[0].prograde - 5.0) < 0.01))
nd = v.control.nodes[0] if v.control.nodes else None
tb = float(out('cmp', 'disp_tb').get('text') or 0) if '-' not in out('cmp', 'disp_tb').get('text', '-') else 0
check('node at TIG + half the burn time', nd is not None and abs((nd.ut - sc.ut) - (40 - (seen['tlm/time']['met'] - met) + tb / 2)) < 1.5,
      (nd and nd.ut - sc.ut, tb))
inp('eng', 'sas', 1)
inp('eng', 'sas_mode', 9)
check('SAS MODE MNVR → KSP holds the node', wait(lambda: v.control.sas_mode == sc.SASMode.maneuver), v.control.sas_mode)
if lit:
    wait(lambda: seen['tlm/time']['met'] >= met + 25, 30)             # let SAS turn to the burn attitude
    # a small burn is flown on a low limiter (rendezvous report): the cutoff is only as fine as thrust × 0.1 s
    lim = min(1.0, max(0.05, round(5.0 / (v.available_thrust / v.mass) * 20) / 20))      # about 5 m/s²
    inp('eng', 'thrust_lim', lim)
    wait(lambda: all(abs(e.thrust_limit - lim) < 0.01 for e in lit if not e.throttle_locked))
    m0 = v.mass
    inp('cmp', 'burn_arm', 1)
    inp('eng', 'eng_arm', 1)
    wait(lambda: seen['tlm/time']['met'] >= met + 40, 20)
    inp('eng', 'throttle', 1.0)
    check('computer cuts the throttle', wait(lambda: out('cmp', 'lamp_cutoff').get('on') and v.control.throttle == 0.0, 30))
    time.sleep(1.0)
    dv = v.specific_impulse * 9.80665 * math.log(m0 / v.mass) if v.mass < m0 else 0.0
    acc = v.available_thrust / v.mass
    counted = 5.0 - float(out('cmp', 'disp_vg')['text'])
    print(f'      burn: {dv:.2f} m/s from KSP masses, {counted:.2f} m/s counted by the computer, at {acc:.1f} m/s² (limiter {lim:.0%})', flush=True)
    check("the computer's Δv counter agrees with KSP's masses", abs(counted - dv) < 0.5, (counted, dv))
    check('burn delivered 5 m/s (within 0.1 s of thrust)', abs(dv - 5.0) < max(0.3, 0.1 * acc), dv)
    check('node removed at cutoff', wait(lambda: len(v.control.nodes) == 0))
    inp('eng', 'throttle', 0.6)
    check('throttle stays cut until the lever is back at idle', v.control.throttle == 0.0)
    inp('eng', 'throttle', 0.0)
    inp('eng', 'eng_arm', 0)
    inp('cmp', 'burn_arm', 0)
    inp('eng', 'thrust_lim', 1)
press('cmp', 'pad_clr')
inp('eng', 'sas_mode', 0)
inp('eng', 'sas', 0)

# ---------- a node made in the game (map view) shows up as the PAD ----------
time.sleep(2.5)
nd = v.control.add_node(sc.ut + 600, prograde=25.0, normal=-3.0)
check('game node → PAD on the computer', wait(lambda: out('cmp', 'disp_pro').get('text') == '+25.0' and out('cmp', 'disp_nrm').get('text') == '-3.0'),
      (out('cmp', 'disp_pro'), out('cmp', 'disp_nrm')))
check('the game node is left as it is', len(v.control.nodes) == 1 and abs(v.control.nodes[0].ut - nd.ut) < 0.01)
check('TIG is the node time less half the burn', wait(lambda: 0 <= (nd.ut - sc.ut) - (seen['cmp/pad']['tig'] - seen['tlm/time']['met']) < 60),
      (nd.ut - sc.ut, seen.get('cmp/pad')))
check('attitude error to the burn shown', wait(lambda: '-' not in out('cmp', 'disp_att').get('text', '-')), out('cmp', 'disp_att'))
nd.prograde = 40.0
check('editing the node updates the PAD', wait(lambda: out('cmp', 'disp_pro').get('text') == '+40.0'), out('cmp', 'disp_pro'))
press('cmp', 'pad_clr')
check('PAD CLEAR removes the node', wait(lambda: len(v.control.nodes) == 0))
check('new telemetry topics', all(t in seen for t in ('tlm/node', 'tlm/thermal')) and 'contact' in seen['tlm/vessel'] and 't_soi' in seen['tlm/orbit'])

# ---------- target and docking from the panel ----------
sc.clear_target()
if others:
    nrf = v.orbit.body.non_rotating_reference_frame
    nearest = min(others, key=lambda w: math.dist(v.position(nrf), w.position(nrf)))
    press('rdv', 'tgt_next')
    check(f'TGT ▸ → KSP targets the nearest vessel ({nearest.name})', wait(lambda: sc.target_vessel == nearest), sc.target_vessel and sc.target_vessel.name)
    check('target name on the alphanumeric display', wait(lambda: out('rdv', 'txt_tgt').get('text') == nearest.name.upper()[:12]), out('rdv', 'txt_tgt'))
    rng = math.dist(v.position(nrf), nearest.position(nrf))
    shown = lambda: float(out('rdv', 'disp_range')['text']) * (1000 if out('rdv', 'led_km').get('on') else 1)
    check('range display matches KSP', wait(lambda: abs(shown() - rng) / rng < 0.02), (out('rdv', 'disp_range'), rng))
    if len(others) > 1:
        press('rdv', 'tgt_next')
        check('TGT ▸ again → another vessel', wait(lambda: sc.target_vessel is not None and sc.target_vessel != nearest))
        press('rdv', 'tgt_prev')
        check('◂ TGT → back to the nearest', wait(lambda: sc.target_vessel == nearest))
    try:
        ports = [d for d in nearest.parts.docking_ports if d.state.name == 'ready']
    except Exception:
        ports = []
    if ports:
        press('rdv', 'port_next')
        check('PORT ▸ → KSP targets a docking port', wait(lambda: sc.target_docking_port is not None and sc.target_docking_port.part.vessel == nearest))
        check('port alignment displayed', wait(lambda: out('rdv', 'led_port').get('on') and '-' not in out('rdv', 'disp_yaw').get('text', '-').lstrip('-')), out('rdv', 'disp_yaw'))
    press('rdv', 'tgt_clear')
    check('CLEAR → no target in KSP', wait(lambda: sc.target_vessel is None and sc.target_docking_port is None))
    check('display shows NO TARGET', wait(lambda: out('rdv', 'txt_tgt').get('text') == 'NO TARGET'))
if any(d.state.name == 'ready' for d in v.parts.docking_ports):
    home = v.parts.controlling
    inp('rdv', 'ctrl_port', 1)
    check('CTRL FROM PORT → controlled from a docking port', wait(lambda: v.parts.controlling.docking_port is not None))
    check('control LED steady', wait(lambda: out('rdv', 'led_ctrl_port') == {'on': True, 'blink': False}))
    inp('rdv', 'ctrl_port', 0)
    check('control back to the pod', wait(lambda: v.parts.controlling == home))

# ---------- abort: KSP's abort group, nothing else (what the craft's builder wired to it) ----------
inp('eng', 'abort_arm', 1); press('eng', 'abort')
check('ABORT fires the abort group', wait(lambda: v.control.abort))
check('ABORT lamp blinks', wait(lambda: out('eng', 'lamp_abort') == {'on': True, 'blink': True}))
inp('eng', 'abort_arm', 0)
v.control.abort = False
cli.publish('sim/reset', '{}', qos=1)                                  # clears the cockpit's abort latch

# ---------- pause, warp to the event (quick save / load: mock only, it would overwrite the player's quicksave) ----------
inp('sys', 'pause', 1)
check('PAUSE → KSP paused, LED on', wait(lambda: conn.krpc.paused and out('sys', 'led_pause').get('on')))
inp('sys', 'pause', 0)
check('game runs again', wait(lambda: not conn.krpc.paused))
src = 2 if v.orbit.time_to_apoapsis > v.orbit.time_to_periapsis else 3      # the further apsis
t_evt = lambda: v.orbit.time_to_apoapsis if src == 2 else v.orbit.time_to_periapsis
inp('sys', 'evt_src', src)
ut0, t0 = sc.ut, t_evt()
press('sys', 'warp_to')
check('WARP TO EVT → KSP warps', wait(lambda: sc.rails_warp_factor >= 1, 6))
check('warp stops about a minute before the event', wait(lambda: sc.rails_warp_factor == 0 and sc.warp_rate == 1 and sc.ut - ut0 > 30, 90)
      and 55 <= t_evt() <= 85, (t0, t_evt()))
inp('sys', 'evt_src', 0)
v.control.throttle = 0.0

print(f"\n{'all passed' if not fails else f'{len(fails)} FAILED: ' + ', '.join(fails)}", flush=True)
sys.exit(1 if fails else 0)
