"""Sign check of the docking displays in KSP: with a docking port targeted a few metres away, push each control and see
that the matching display moves the way its legend says.

    .venv/bin/python tests/e2e_ksp_docking.py --save <a save with the chaser near a target that has a free port>

Loads the save. Needs RCS propellant; uses the RDV panel to pick the target and the port.
"""
import json, sys, time
import krpc
import paho.mqtt.client as mqtt

SAVE = sys.argv[sys.argv.index('--save') + 1]
seen = {}
cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id='e2e-dock')
cli.on_message = lambda c, u, m: seen.__setitem__(m.topic, json.loads(m.payload or b'{}'))
cli.connect('localhost', 1883); cli.subscribe('#'); cli.loop_start()
conn = krpc.connect(name='e2e-dock')
sc = conn.space_center
sc.load(SAVE)
time.sleep(5)
v = sc.active_vessel
v.control.throttle = 0.0
fails = []


def check(name, cond, info=''):
    print(('PASS ' if cond else 'FAIL ') + name + (f'   [{info}]' if not cond else ''), flush=True)
    if not cond:
        fails.append(name)


def press(ctl):
    for x in (1, 0):
        cli.publish(f'panel/rdv/in/{ctl}', json.dumps({'v': x}), qos=1); time.sleep(0.3)


port = lambda: seen.get('tlm/target', {}).get('port') or {}
press('tgt_next'); time.sleep(1); press('port_next'); time.sleep(2)
check('a docking port is targeted', 'right' in port(), seen.get('tlm/target'))
sw = lambda ctl, x: (cli.publish(f'panel/eng/in/{ctl}', json.dumps({'v': x}), qos=1, retain=True), time.sleep(0.4))
sw('cb_main', 1); sw('sas', 1); sw('rcs', 1)     # through the panel: its switches win over the game
time.sleep(8)                                     # let SAS settle: a turning vessel moves the offsets by itself
for ctl, rate, label in (('right', 'v_right', 'translate right → the PORT IS RIGHT rate goes down'),
                         ('up', 'v_up', 'translate up → the PORT IS UP rate goes down')):
    r0 = port()[rate]
    setattr(v.control, ctl, 1.0); time.sleep(3.0); setattr(v.control, ctl, 0.0)
    time.sleep(1.0)
    r1 = port()[rate]
    check(label, r1 - r0 < -0.02, (r0, r1))
    setattr(v.control, ctl, -1.0); time.sleep(3.0); setattr(v.control, ctl, 0.0)
    time.sleep(1.0)
    check(label.replace('right →', 'left →').replace('up →', 'down →').replace('goes down', 'comes back'), abs(port()[rate] - r0) < abs(r1 - r0) / 2,
          (r0, r1, port()[rate]))
sw('sas', 0); sw('rcs', 0)
for axis, key, label in (('yaw', 'yaw', 'yaw right → YAW error goes down'), ('pitch', 'pitch', 'pitch up → PITCH error goes down'),
                         ('roll', 'roll', 'roll right → ROLL error goes down')):
    a0 = port()[key]
    setattr(v.control, axis, 0.3); time.sleep(1.0); setattr(v.control, axis, 0.0)
    time.sleep(0.6)
    d = (port()[key] - a0 + 180) % 360 - 180
    check(label, d < -0.2, (a0, port()[key]))
    setattr(v.control, axis, -0.3); time.sleep(1.0); setattr(v.control, axis, 0.0)
print('all passed' if not fails else f'{len(fails)} FAILED')
sys.exit(1 if fails else 0)
