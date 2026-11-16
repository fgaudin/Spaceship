"""Engine status matrix through booster flameouts and staging, in KSP.

    .venv/bin/python tests/e2e_ksp_boosters.py --save <a save on the pad, with boosters dropped before the core>

Loads the save and launches straight up. Each time engines run dry: they must show red with the FLAMEOUT caution
and without ENG FAIL; after staging them away the matrix must show only engines that burn, and ENG FAIL must stay
off (it used to come on, because the stage number reaches the cockpit before the new engine list).
"""
import json, sys, time
import krpc
import paho.mqtt.client as mqtt

SAVE = sys.argv[sys.argv.index('--save') + 1]
FLAMEOUTS_TO_CHECK = 2
WAIT_FOR_FLAMEOUT_S = 240
WATCH_AFTER_STAGING_S = 6
seen = {}
cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id='e2e-boosters')
cli.on_message = lambda c, u, m: seen.__setitem__(m.topic, json.loads(m.payload or b'{}'))
cli.connect('localhost', 1883); cli.subscribe('#'); cli.loop_start()
conn = krpc.connect(name='e2e-boosters')
sc = conn.space_center
sc.load(SAVE)
time.sleep(8)
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
    cli.publish(f'panel/eng/in/{ctl}', json.dumps({'v': v}), qos=1, retain=retain); time.sleep(0.3)


def press(ctl):
    pin(ctl, 1, False); pin(ctl, 0, False)


out = lambda n: seen.get(f'panel/eng/out/{n}') or {}
matrix = lambda: ''.join(out('mx_eng').get('rows') or [])
engines = lambda: seen['tlm/engines']['engines']
dry = lambda: [engine for engine in engines() if engine['on'] and not engine['fuel']]
burning = lambda: [engine for engine in engines() if engine['on'] and engine['fuel']]

for control, value in (('cb_main', 1), ('throttle', 0), ('eng_arm', 0), ('stage_arm', 0), ('sas', 0)):
    pin(control, value)
pin('sas', 1); pin('eng_arm', 1); pin('stage_arm', 1); pin('throttle', 1.0)
press('stage')
check('liftoff: every lit engine green', wait(lambda: len(burning()) > 1 and matrix().count('g') == len(burning())
                                               and 'r' not in matrix()), (matrix(), seen.get('tlm/engines')))
engine_count = len(burning())
print(f'      {engine_count} engines burning', flush=True)

for number in range(1, FLAMEOUTS_TO_CHECK + 1):
    if not wait(lambda: dry() and burning(), WAIT_FOR_FLAMEOUT_S):
        check(f'flameout {number} happened', False, seen.get('tlm/engines'))
        break
    dry_count = len(dry())
    check(f'flameout {number}: {dry_count} engines red, FLAMEOUT caution, no ENG FAIL',
          wait(lambda: matrix().count('r') == dry_count and out('cw_flameout').get('on'))
          and not out('cw_eng_fail').get('on'), (matrix(), out('cw_flameout'), out('cw_eng_fail')))
    press('stage')
    # ENG FAIL must not show at any moment while the new engine list arrives
    saw_engine_fail, watch_until = False, time.time() + WATCH_AFTER_STAGING_S
    while time.time() < watch_until:
        saw_engine_fail = saw_engine_fail or bool(out('cw_eng_fail').get('on'))
        time.sleep(0.05)
    check(f'staging {number}: ENG FAIL never came on', not saw_engine_fail)
    check(f'staging {number}: matrix shows the {len(burning())} burning engines and no red',
          'r' not in matrix() and matrix().count('g') == len(burning()) and len(burning()) < engine_count,
          (matrix(), len(burning())))
    check(f'staging {number}: FLAMEOUT caution cleared', not out('cw_flameout').get('on'))

pin('throttle', 0); pin('eng_arm', 0); pin('stage_arm', 0)
print('all passed' if not fails else f'{len(fails)} FAILED')
sys.exit(1 if fails else 0)
