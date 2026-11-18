"""A Mun landing flown on the LAB panel's figures, in KSP.

    .venv/bin/python tests/e2e_ksp_landing.py --save <a save with a lander in low Mun orbit>

Loads the save. Checks the cross-pointer's signs (NODE and RETRO: turn the nose and watch the dot move the other
way), then brakes out of orbit, falls, and starts the final braking at 1.3 times the height needed to stop at full
thrust (worked out by the test). It then lands, checking that HOVER TIME drains at about a second per second near
the hover.

Everything is commanded through panel inputs, except what no panel can do yet: the navball's speed reference
(orbit / surface) and the raw yaw and pitch inputs used to disturb the attitude.
"""
import json, math, sys, time
import krpc
import paho.mqtt.client as mqtt

SAVE = sys.argv[sys.argv.index('--save') + 1]
SAS_MODE = {'stability': 0, 'retrograde': 2, 'radial': 5, 'maneuver': 9}      # positions of the SAS MODE selector
XP_MODE = {'NODE': 0, 'RETRO': 1, 'PRO': 2, 'PORT': 3, 'OFFSET': 4, 'DRIFT': 5}
seen = {}
cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id='e2e-landing')
cli.on_message = lambda c, u, m: seen.__setitem__(m.topic, json.loads(m.payload or b'{}'))
cli.connect('localhost', 1883); cli.subscribe('#'); cli.loop_start()
conn = krpc.connect(name='e2e-landing')
sc = conn.space_center
sc.load(SAVE)
time.sleep(8)
vessel = sc.active_vessel
fails = []


def check(name, cond, info=''):
    print(('PASS ' if cond else 'FAIL ') + name + (f'   [{info}]' if not cond else ''), flush=True)
    if not cond:
        fails.append(name)


def note(text):
    print('      ' + text, flush=True)


def wait(pred, timeout=10):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if pred():
                return True
        except Exception:
            pass
        time.sleep(0.05)
    return False


def pin(panel, ctl, v, retain=True):
    cli.publish(f'panel/{panel}/in/{ctl}', json.dumps({'v': v}), qos=1, retain=retain); time.sleep(0.3)


def press(panel, ctl):
    pin(panel, ctl, 1, False); pin(panel, ctl, 0, False)


def number(panel, name):
    """A display's text as a number, or None for dashes."""
    try:
        return float((seen.get(f'panel/{panel}/out/{name}') or {}).get('text'))
    except (TypeError, ValueError):
        return None


lab = lambda name: seen.get(f'panel/lab/out/{name}') or {}
flight = lambda: seen['tlm/flight']
pointer = lambda: (number('lab', 'disp_xp_right'), number('lab', 'disp_xp_up'))


def disturb(axis, seconds=1.0):
    """Push the nose right (yaw) or up (pitch) by hand for a moment; SAS in stability then holds the new attitude."""
    setattr(vessel.control, axis, 1.0)
    time.sleep(seconds)
    setattr(vessel.control, axis, 0.0)
    time.sleep(2.0)


def check_fly_to_signs(mode):
    """With the dot centred: nose right → the dot goes left; nose up → the dot goes down."""
    pin('eng', 'sas_mode', SAS_MODE['stability'])
    time.sleep(1.0)
    right_before, up_before = pointer()
    disturb('yaw')
    right_after, _ = pointer()
    check(f'{mode}: nose right → the dot moves left', right_after < right_before - 1, (right_before, right_after))
    _, up_before = pointer()
    disturb('pitch')
    _, up_after = pointer()
    check(f'{mode}: nose up → the dot moves down', up_after < up_before - 1, (up_before, up_after))


# ---------- setup ----------
for panel, control, value in (('eng', 'cb_main', 1), ('eng', 'throttle', 0), ('eng', 'eng_arm', 0), ('eng', 'rcs', 0),
                              ('lab', 'gear', 0), ('eng', 'sas', 0), ('eng', 'sas_mode', 0), ('lab', 'xp_mode', 0)):
    pin(panel, control, value)
pin('eng', 'sas', 1)
check('telemetry from the lander', wait(lambda: seen['tlm/vessel']['name'] == vessel.name and 'v_right' in flight(), 15))

# ---------- cross-pointer NODE ----------
node = vessel.control.add_node(sc.ut + 900, prograde=30, normal=10, radial=-8)
pin('eng', 'sas_mode', SAS_MODE['maneuver'])
check('NODE: SAS on the node → dot centred, NULL lit',
      wait(lambda: lab('lamp_xp_null').get('on') and lab('mx_xp')['rows'][4][4] == 'g', 60), (pointer(), lab('mx_xp')))
check_fly_to_signs('NODE')
node.remove()
press('cmp', 'pad_clr')                         # the cockpit had loaded the game's node as its PAD

# ---------- cross-pointer RETRO, then the braking burn out of orbit ----------
pin('eng', 'speed_ref', 0); pin('eng', 'speed_ref', 1)     # SPEED REF knob to SURF
check('SPEED REF knob → navball on surface', wait(lambda: vessel.control.speed_mode.name == 'surface', 5),
      vessel.control.speed_mode.name)
pin('lab', 'xp_mode', XP_MODE['RETRO'])
pin('eng', 'sas_mode', SAS_MODE['retrograde'])
retro_ok = wait(lambda: lab('lamp_xp_null').get('on'), 60)
check('RETRO: SAS on surface retrograde → dot centred, NULL lit', retro_ok, pointer())
check_fly_to_signs('RETRO')
pin('eng', 'sas_mode', SAS_MODE['retrograde'])
aligned = wait(lambda: lab('lamp_xp_null').get('on'), 60)
check('HOVER TIME shown', number('lab', 'disp_hover') is not None, lab('disp_hover'))
if not aligned:
    # Burning off retrograde swings the velocity, SAS chases the moving marker and the speed never drops: the tank
    # empties and the lander falls. A crew would not light the engine; neither does the test.
    check('aligned on retrograde before the braking burn', False,
          (pointer(), seen['tlm/vessel'].get('sas'), seen['tlm/vessel'].get('sas_mode')))
    print(f'{len(fails)} FAILED (burn not attempted)')
    sys.exit(1)

# Burn against the velocity until under 30 m/s, but never more than the speed there was to kill plus a margin: an
# attitude that wanders mid-burn would otherwise keep the engine lit until the tank is dry.
speed_to_kill = flight()['speed']
pin('eng', 'eng_arm', 1); pin('eng', 'throttle', 1.0)
burn_started, delta_v_budget = seen['tlm/time']['ut'], 1.1 * speed_to_kill
mass_start = seen['tlm/vessel']['mass']


def burn_over():
    craft = seen['tlm/vessel']
    exhaust_velocity = (craft['isp'] or 300) * 9.80665
    delta_v_done = exhaust_velocity * math.log(mass_start / craft['mass'])
    return flight()['speed'] < 30 or delta_v_done > delta_v_budget or not lab('lamp_xp_null').get('on') and \
        seen['tlm/time']['ut'] - burn_started > 5 and pointer()[0] is not None and max(map(abs, pointer())) > 15


wait(burn_over, 120)
pin('eng', 'throttle', 0)
check('braking burn: speed over the ground under 30 m/s', flight()['speed'] < 30, (flight(), pointer()))
note(f"after the braking burn: radar {flight()['radar']:.0f} m, V/S {flight()['vs']:.1f} m/s, H/S {flight()['hs']:.1f} m/s")

# ---------- free fall ----------
pin('lab', 'gear', 1)
check('GEAR (landing panel) → KSP, LED steady', wait(lambda: seen['tlm/vessel'].get('gear') and lab('led_gear') == {'on': True, 'blink': False}, 10))
wait(lambda: flight()['vs'] < -15, 60)

pin('lab', 'xp_mode', XP_MODE['DRIFT'])
time.sleep(1.0)
drift_right, drift_up = pointer()
check('DRIFT: SAS on retrograde → hardly any speed across the axis', abs(drift_right) < 5 and abs(drift_up) < 5,
      (drift_right, drift_up, flight()['speed']))

# ---------- the final braking: from 1.3 times the height needed to stop at full thrust ----------
def braking_height():
    now, craft = flight(), seen['tlm/vessel']
    gravity = 6.5138398e10 / (200000.0 + now['alt']) ** 2
    deceleration = craft['thrust_avail'] / craft['mass'] - gravity
    return now['speed'] ** 2 / (2 * deceleration) if deceleration > 0 else float('inf')


check('falling to the braking height', wait(lambda: flight()['radar'] <= 1.3 * braking_height(), 240), flight())
radar_at_start, speed_at_start = flight()['radar'], flight()['speed']
pin('eng', 'throttle', 1.0)
check('full thrust stops the fall', wait(lambda: flight()['speed'] < 6 or flight()['radar'] < 3, 60), flight())
pin('eng', 'throttle', 0.15)
radar_stopped = flight()['radar']
note(f'braking from {radar_at_start:.0f} m and {speed_at_start:.0f} m/s; nearly stopped at {radar_stopped:.0f} m')
check('stopped above the ground', radar_stopped > 5 and seen['tlm/vessel']['situation'] != 'landed', radar_stopped)

# ---------- final descent and touchdown ----------
hover_throttle = None
touchdown_speed = None
hover_start = (seen['tlm/time']['ut'], number('lab', 'disp_hover'))
deadline = time.time() + 240
while time.time() < deadline:
    now, craft = flight(), seen['tlm/vessel']
    if craft.get('contact') or craft['situation'] == 'landed':
        break
    touchdown_speed = now['vs']
    gravity = 6.5138398e10 / (200000.0 + now['alt']) ** 2
    hover_throttle = gravity * craft['mass'] / max(craft['thrust_avail'], 1.0)
    wanted_vertical_speed = -max(1.5, min(15.0, now['radar'] / 8))
    throttle = hover_throttle + 0.08 * (wanted_vertical_speed - now['vs'])
    cli.publish('panel/eng/in/throttle', json.dumps({'v': round(max(0.0, min(1.0, throttle)), 3)}), qos=1, retain=True)
    time.sleep(0.1)
hover_end = (seen['tlm/time']['ut'], number('lab', 'disp_hover'))
pin('eng', 'throttle', 0); pin('eng', 'eng_arm', 0)
pin('eng', 'sas_mode', SAS_MODE['stability'])
if None not in (hover_start[1], hover_end[1]) and hover_end[0] - hover_start[0] > 10:
    spent, elapsed = hover_start[1] - hover_end[1], hover_end[0] - hover_start[0]
    note(f'HOVER TIME {hover_start[1]:.0f} s → {hover_end[1]:.0f} s over {elapsed:.0f} s of descent near the hover')
    check('HOVER TIME drains at about a second per second near the hover', 0.7 * elapsed <= spent <= 1.5 * elapsed,
          (spent, elapsed))
check('touchdown: contact', wait(lambda: seen['tlm/vessel'].get('contact'), 5), seen.get('tlm/vessel'))
check('touchdown slower than 4 m/s', touchdown_speed is not None and touchdown_speed > -4, touchdown_speed)
time.sleep(6)
check('landed and upright', seen['tlm/vessel']['situation'] == 'landed' and seen['tlm/attitude']['pitch'] > 65,       # Mun slopes reach 15° and more
      (seen['tlm/vessel']['situation'], seen['tlm/attitude']['pitch']))
pin('lab', 'xp_mode', 0)
print('all passed' if not fails else f'{len(fails)} FAILED')
sys.exit(1 if fails else 0)
