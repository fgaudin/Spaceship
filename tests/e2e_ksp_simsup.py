"""SimSup in KSP: every failure, freeze and save loading, driven the way the SimSup page drives it.

    .venv/bin/python tests/e2e_ksp_simsup.py --save <a save with a multi-engine launcher on the pad>

Needs the simsup service running. Loads the save through SimSup, stages at zero throttle (engines lit, the rocket
stays on the pad), then injects and clears each failure and checks the game and the panels.
"""
import json, sys, time
import krpc
import paho.mqtt.client as mqtt

SAVE = sys.argv[sys.argv.index('--save') + 1]
seen = {}
cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id='e2e-simsup')
cli.on_message = lambda c, u, m: seen.__setitem__(m.topic, json.loads(m.payload or b'{}'))
cli.connect('localhost', 1883); cli.subscribe('#'); cli.loop_start()
conn = krpc.connect(name='e2e-simsup')
sc = conn.space_center
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


def simsup(**request):
    cli.publish('sim/simsup/cmd', json.dumps(request), qos=1)
    time.sleep(0.5)


def pin(panel, ctl, v, retain=True):
    cli.publish(f'panel/{panel}/in/{ctl}', json.dumps({'v': v}), qos=1, retain=retain); time.sleep(0.3)


def press(panel, ctl):
    pin(panel, ctl, 1, False); pin(panel, ctl, 0, False)


out = lambda panel, name: seen.get(f'panel/{panel}/out/{name}') or {}
active_failures = lambda: {each['failure'] for each in seen.get('sim/simsup/state', {}).get('active', [])}

# ---------- loading a save, freezing ----------
check('simsup service up', wait(lambda: 'sim/simsup/scenarios' in seen, 5))
simsup(action='clear_all')
simsup(action='load', save=SAVE)
check('LOAD → the save is loaded', wait(lambda: sc.active_vessel.situation.name == 'pre_launch'
                                             and seen['tlm/vessel']['situation'] == 'pre_launch', 30))
time.sleep(3)
vessel = sc.active_vessel
simsup(action='freeze', on=True)
check('FREEZE → KSP paused', wait(lambda: conn.krpc.paused, 5))
simsup(action='freeze', on=False)
check('UNFREEZE → KSP runs', wait(lambda: not conn.krpc.paused, 5))

# ---------- engines lit at zero throttle ----------
for panel, control, value in (('eng', 'cb_main', 1), ('eng', 'throttle', 0), ('eng', 'eng_arm', 0), ('eng', 'stage_arm', 0),
                              ('eng', 'gimbal_lock', 0), ('eng', 'sas', 0), ('eng', 'rcs', 0)):
    pin(panel, control, value)
pin('eng', 'stage_arm', 1); press('eng', 'stage')
lit = lambda: [engine for engine in vessel.parts.engines if engine.active]
check('engines lit at zero throttle', wait(lambda: len(lit()) > 1, 10), len(lit()))
# Released clamps at zero thrust drop the rocket onto the pad, which can break the lowest engine: follow the engine
# SimSup shuts down, not a count.
time.sleep(2)
lit_before = lit()


def still_off(engine):
    try:
        return not engine.active
    except Exception:                   # destroyed: off too
        return True


simsup(action='inject', failure='engine_one_out')
check('engine_one_out → one engine shut down in KSP',
      wait(lambda: len([engine for engine in lit_before if still_off(engine)]) == 1, 5), len(lit()))
failed = [engine for engine in lit_before if still_off(engine)]
check('... ENG FAIL on the panel', wait(lambda: out('eng', 'cw_eng_fail').get('on'), 6), out('eng', 'cw_eng_fail'))
check('... still shut down a few seconds later', time.sleep(3) or all(still_off(engine) for engine in failed))
simsup(action='clear', failure='engine_one_out')
check('cleared: SimSup shows nothing active', wait(lambda: not active_failures(), 3), active_failures())

simsup(action='inject', failure='gimbal_stuck')
gimballed = [engine for engine in vessel.parts.engines if engine.gimballed]
check('gimbal_stuck → gimbals locked in KSP', wait(lambda: all(engine.gimbal_locked for engine in gimballed), 5))
pin('eng', 'gimbal_lock', 1); pin('eng', 'gimbal_lock', 0)
check('... the GIMBAL LOCK switch cannot unlock them', time.sleep(1) or all(engine.gimbal_locked for engine in gimballed))
simsup(action='clear', failure='gimbal_stuck')
check('cleared: gimbals free', wait(lambda: not any(engine.gimbal_locked for engine in gimballed), 5))

if vessel.parts.rcs:
    simsup(action='inject', failure='rcs_fail')
    check('rcs_fail → RCS thrusters disabled', wait(lambda: not any(thruster.enabled for thruster in vessel.parts.rcs), 5))
    simsup(action='clear', failure='rcs_fail')
    check('cleared: RCS enabled', wait(lambda: all(thruster.enabled for thruster in vessel.parts.rcs), 5))

simsup(action='inject', failure='wheels_fail')
check('wheels_fail → reaction wheels off', wait(lambda: not any(wheel.active for wheel in vessel.parts.reaction_wheels), 5))
simsup(action='clear', failure='wheels_fail')
check('cleared: reaction wheels on', wait(lambda: all(wheel.active for wheel in vessel.parts.reaction_wheels), 5))

simsup(action='inject', failure='comm_lost')
check('comm_lost → COM panel LOS, COMM LOST caution', wait(lambda: out('com', 'lamp_los').get('on')
                                                           and out('eng', 'cw_comm').get('on'), 6))
simsup(action='clear', failure='comm_lost')
check('cleared: AOS', wait(lambda: out('com', 'lamp_aos').get('on'), 6))

simsup(action='inject', failure='telemetry_freeze')
check('telemetry_freeze → NO LINK', wait(lambda: out('eng', 'cw_no_link').get('on'), 6))
simsup(action='clear', failure='telemetry_freeze')
check('cleared: NO LINK off', wait(lambda: not out('eng', 'cw_no_link').get('on'), 6))

# ---------- cockpit failures ----------
simsup(action='inject', failure='false_alarm', parameters={'alarm': 'HIGH Q'})
check('false_alarm → HIGH Q lit on the pad', wait(lambda: out('eng', 'cw_q').get('on'), 3), out('eng', 'cw_q'))
simsup(action='inject', failure='panel_dark', parameters={'panel': 'sys'})
check('panel_dark → SYS displays blank', wait(lambda: out('sys', 'disp_ec').get('blank'), 3))
simsup(action='clear_all')
check('CLEAR ALL → all back', wait(lambda: not out('eng', 'cw_q').get('on') and not out('sys', 'disp_ec').get('blank'), 4))

# ---------- the log and the debrief ----------
state = seen['sim/simsup/state']
check('debrief lists every failure injected', len(state['debrief']) >= 8, len(state['debrief']))
kinds = {line['kind'] for line in seen['sim/simsup/log']['log']}
check('log has failures, alarms, crew inputs and commands', {'failure', 'alarm', 'crew', 'command'} <= kinds, kinds)

pin('eng', 'stage_arm', 0)
print('all passed' if not fails else f'{len(fails)} FAILED')
sys.exit(1 if fails else 0)
