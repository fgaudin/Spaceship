"""UNDOCK from the RDV panel, in KSP.

    .venv/bin/python tests/e2e_ksp_undock.py --save <a save with the active vessel docked to another>

Loads the save.
"""
import json, sys, time
import krpc
import paho.mqtt.client as mqtt

SAVE = sys.argv[sys.argv.index('--save') + 1]
seen = {}
cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id='e2e-undock')
cli.on_message = lambda c, u, m: seen.__setitem__(m.topic, json.loads(m.payload or b'{}'))
cli.connect('localhost', 1883); cli.subscribe('#'); cli.loop_start()
conn = krpc.connect(name='e2e-undock')
sc = conn.space_center
sc.load(SAVE)
time.sleep(6)
sc.active_vessel.control.throttle = 0.0
fails = []


def check(name, cond, info=''):
    print(('PASS ' if cond else 'FAIL ') + name + (f'   [{info}]' if not cond else ''), flush=True)
    if not cond:
        fails.append(name)


def wait(pred, timeout=10):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if pred():
                return True
        except Exception:
            pass
        time.sleep(0.1)
    return False


def pin(ctl, v, retain=True):
    cli.publish(f'panel/rdv/in/{ctl}', json.dumps({'v': v}), qos=1, retain=retain); time.sleep(0.3)


out = lambda n: seen.get(f'panel/rdv/out/{n}') or {}
pin('undock_arm', 0)
n0, parts0 = len(sc.vessels), len(sc.active_vessel.parts.all)
check('DOCKED lamp on', wait(lambda: out('lamp_docked').get('on')), seen.get('tlm/target'))
pin('undock', 1, False); pin('undock', 0, False)
time.sleep(1.5)
check('UNDOCK refused without UNDOCK ARM', len(sc.vessels) == n0)
pin('undock_arm', 1)
pin('undock', 1, False); pin('undock', 0, False)
check('UNDOCK → two vessels', wait(lambda: len(sc.vessels) == n0 + 1 and len(sc.active_vessel.parts.all) < parts0), (len(sc.vessels), n0))
check('telemetry follows the smaller vessel', wait(lambda: abs(seen['tlm/vessel']['mass'] - sc.active_vessel.mass) < 50, 15),
      (seen.get('tlm/vessel', {}).get('mass'), sc.active_vessel.mass))
check('DOCKED lamp off after undocking', wait(lambda: not out('lamp_docked').get('on')), out('lamp_docked'))
pin('undock_arm', 0)
print('all passed' if not fails else f'{len(fails)} FAILED')
sys.exit(1 if fails else 0)
