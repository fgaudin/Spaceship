"""Dress rehearsal: pad to parking orbit in KSP, flown the way a crew would from the panels.

    .venv/bin/python tests/rehearsal_ksp_ascent.py --save <a save with the launcher on the pad>

Loads the save. The "pilot" below only reads panel outputs and only acts through panel inputs. Where it needs
something the panels do not give, it says so with a GAP line; the stand-in it uses is named for what will replace
it: FDAI (the attitude ball on glass, here tlm/attitude). The pitch kick is flown on the hand controller's topics
(panel/hc/in/*), which the USB joysticks will publish. Every caution and warning that comes on is logged, to spot
nuisance alarms.

The flight plan is the self-test's: kick 10° east at 8 s, follow prograde, cut off when the apoapsis reaches 80 km,
circularise at apoapsis with the burn computer.
"""
import json, math, sys, time
import krpc
import paho.mqtt.client as mqtt

SAVE = sys.argv[sys.argv.index('--save') + 1]
KERBIN_MU, KERBIN_RADIUS_KM = 3.5316e12, 600.0
TARGET_APOAPSIS_KM = 80.0
# where the pilot reads each figure: ASCENT (eng) for the altitude and the surface speed, ORBIT (solo bus) for the apsides
DISPLAYS = {'ALT': ('eng', 'disp_alt'), 'VEL': ('eng', 'disp_speed'), 'APO': ('solo', 'disp_apo'), 'PERI': ('solo', 'disp_peri')}
SAS_MODE = {'stability': 0, 'prograde': 1, 'maneuver': 9}
EVENT_SOURCE = {'MAN': 0, 'TIG': 1, 'APO': 2}

seen = {}
alarms_seen = {}                # legend → mission time it first came on
start = time.time()


def on_message(client, userdata, message):
    payload = json.loads(message.payload or b'{}')
    seen[message.topic] = payload
    if message.topic == 'cw/state':
        for legend in payload.get('active', []):
            if legend not in alarms_seen:
                alarms_seen[legend] = seen.get('tlm/time', {}).get('met')


cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id='rehearsal')
cli.on_message = on_message
cli.connect('localhost', 1883); cli.subscribe('#'); cli.loop_start()
conn = krpc.connect(name='rehearsal')
sc = conn.space_center
sc.load(SAVE)
time.sleep(8)
vessel = sc.active_vessel
gaps, problems = [], []


def log(text):
    print(f'{time.time() - start:6.1f} s  {text}', flush=True)


def gap(text):
    if text not in gaps:
        gaps.append(text)
        log('GAP: ' + text)


def problem(text):
    problems.append(text)
    log('PROBLEM: ' + text)


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
    cli.publish(f'panel/{panel}/in/{ctl}', json.dumps({'v': v}), qos=1, retain=retain); time.sleep(0.25)


def press(panel, ctl):
    pin(panel, ctl, 1, False); pin(panel, ctl, 0, False)


def out(panel, name):
    return seen.get(f'panel/{panel}/out/{name}') or {}


def number(panel, name):
    try:
        return float(out(panel, name).get('text'))
    except (TypeError, ValueError):
        return None


def read_display(figure):
    """Read a figure on its own display, as the pilot would."""
    return number(*DISPLAYS[figure])


def clock_seconds(text):
    """'hh.mm.ss' or '-mm.ss' → seconds."""
    sign = -1 if text.startswith('-') else 1
    seconds = 0
    for part in text.lstrip('-').split('.'):
        seconds = seconds * 60 + int(part)
    return sign * seconds


def key_in(field_button, text):
    press('cmp', field_button)
    for character in text:
        pin('cmp', 'key', character, retain=False)
    pin('cmp', 'key', 'ENTR', retain=False)


def stage_on_flameout():
    """FLAMEOUT caution → STAGE, then give the new engine list a moment."""
    if out('eng', 'cw_flameout').get('on'):
        press('eng', 'stage')
        log(f"FLAMEOUT → STAGE (stage display {out('eng', 'disp_stage').get('text')}, burning {out('eng', 'disp_eng_on').get('text')})")
        time.sleep(1.5)


# ---------- before launch ----------
for panel, control, value in (('eng', 'cb_main', 1), ('eng', 'throttle', 0), ('eng', 'eng_arm', 0), ('eng', 'stage_arm', 0),
                              ('eng', 'sas', 0), ('eng', 'rcs', 0), ('eng', 'sas_mode', 0), ('eng', 'abort_arm', 0),
                              ('sys', 'evt_src', EVENT_SOURCE['MAN']),
                              ('cmp', 'burn_arm', 0), ('sys', 'evt_down', 0)):
    pin(panel, control, value)
press('cmp', 'pad_clr')
if not wait(lambda: seen['tlm/vessel']['name'] == vessel.name and read_display('ALT') is not None, 15):
    problem('no telemetry on the panels after loading the save')
log(f"on the pad: stage {out('eng', 'disp_stage').get('text')}, engines to ignite {''.join(out('eng', 'mx_eng').get('rows', [])).count('w')}, "
    f"TWR {out('eng', 'disp_twr').get('text')}, stage Δv {out('eng', 'disp_dv').get('text')}")
before_launch_alarms = list(seen.get('cw/state', {}).get('active', []))
alarms_seen.clear()                 # what came on during the save load is not this flight's
if before_launch_alarms:
    log(f'alarms on the pad: {before_launch_alarms}')

# ---------- liftoff and pitch kick ----------
pin('eng', 'sas', 1); pin('eng', 'eng_arm', 1); pin('eng', 'stage_arm', 1); pin('eng', 'throttle', 1.0)
press('eng', 'stage')
if not wait(lambda: (read_display('VEL') or 0) > 5, 15):
    problem('no liftoff')
log('LIFTOFF')
wait(lambda: clock_seconds(out('eng', 'disp_met')['text']) >= 8, 30)
gap('FDAI: pitch and heading are only on the glass attitude ball')


def stick(axis, value):
    cli.publish(f'panel/hc/in/{axis}', json.dumps({'v': value}), qos=1)


def east_of_north(heading):
    """Heading as an angle from east, −180..180."""
    return (heading - 90 + 180) % 360 - 180


# Push the stick toward east, as a pilot reading the attitude ball would. Which mix of pitch and yaw that is depends
# on how the rocket is rolled on the pad; the ball's reading comes from kRPC here (the FDAI stand-in). Vessel frame:
# x right, y forward (the nose), z down; + pitch moves the nose toward −z, + yaw toward +x.
KICK_STICK = 0.25
KICK_RELEASE_AT_PITCH = 84.0      # let go early: the turn carries on while SAS takes over
gap('FDAI stand-in: which way to push the stick for east is read from kRPC (the attitude ball will show it)')
right_axis = sc.transform_direction((1, 0, 0), vessel.reference_frame, vessel.surface_reference_frame)
up_axis = sc.transform_direction((0, 0, -1), vessel.reference_frame, vessel.surface_reference_frame)
east_of = lambda direction: direction[2]                # surface frame: x up, y north, z east
pitch_part, yaw_part = east_of(up_axis), east_of(right_axis)
scale = KICK_STICK / max(abs(pitch_part), abs(yaw_part), 1e-6)
stick('rot_pitch', round(pitch_part * scale, 3)); stick('rot_yaw', round(yaw_part * scale, 3))
kick = None
if wait(lambda: seen['tlm/attitude']['pitch'] <= 87.0, 8) and abs(east_of_north(seen['tlm/attitude']['heading'])) < 45:
    kick = ('rot_pitch/rot_yaw', 1)
else:
    stick('rot_pitch', 0.0); stick('rot_yaw', 0.0)
if kick is None:
    problem(f"the stick did not tip the nose east: pitch {seen['tlm/attitude']['pitch']:.1f}, heading {seen['tlm/attitude']['heading']:.0f}")
else:
    wait(lambda: seen['tlm/attitude']['pitch'] <= KICK_RELEASE_AT_PITCH, 20)
    stick('rot_pitch', 0.0); stick('rot_yaw', 0.0)
    log(f"pitch kick on the stick (pitch {pitch_part * scale:+.2f}, yaw {yaw_part * scale:+.2f}): pitch {seen['tlm/attitude']['pitch']:.0f}°, "
        f"heading {seen['tlm/attitude']['heading']:.0f}°, speed {read_display('VEL')} m/s")
import threading


def attitude_log(seconds):
    """One line every 2 s: nose and velocity direction, SAS, to see what the rocket does after the kick."""
    until = time.time() + seconds
    while time.time() < until:
        attitude, craft = seen['tlm/attitude'], seen['tlm/vessel']
        prograde = attitude.get('prograde') or {}
        log(f"  nose {attitude['pitch']:5.1f}° {attitude['heading']:5.1f}°  prograde {prograde.get('pitch', 0):5.1f}° "
            f"{prograde.get('heading', 0):5.1f}°  SAS {craft['sas']} {craft['sas_mode']}  alt {read_alt():.0f} m")
        time.sleep(2)


read_alt = lambda: seen['tlm/flight']['alt']
threading.Thread(target=attitude_log, args=(50,), daemon=True).start()
# SAS (stability) holds the kicked attitude; follow the velocity vector once it has come down to the nose
wait(lambda: (seen['tlm/attitude']['prograde'] or {}).get('pitch', 90) <= seen['tlm/attitude']['pitch'] + 0.5, 30)
pin('eng', 'sas_mode', SAS_MODE['prograde'])
if not wait(lambda: seen['tlm/vessel']['sas'] and seen['tlm/vessel']['sas_mode'] == 'prograde', 6):
    problem(f"SAS did not go to prograde after the stick was released: {seen['tlm/vessel'].get('sas')}, {seen['tlm/vessel'].get('sas_mode')}")
log('gravity turn: SAS MODE PRO')

# ---------- ascent: stage on FLAMEOUT, cut off on the apoapsis ----------
deadline = time.time() + 240
while time.time() < deadline:
    stage_on_flameout()
    apoapsis = read_display('APO')
    if apoapsis is not None and apoapsis >= TARGET_APOAPSIS_KM:
        break
    time.sleep(0.05)
else:
    problem('apoapsis never reached 80 km')
press('eng', 'eng_cutoff')
log(f"CUTOFF at apoapsis {read_display('APO')} km, altitude {read_display('ALT') / 1000:.1f} km, speed {read_display('VEL')} m/s")
pin('eng', 'throttle', 0)

# ---------- coast out of the atmosphere ----------
wait(lambda: (read_display('ALT') or 0) >= 70000, 180)
apoapsis, periapsis = read_display('APO'), read_display('PERI')
log(f'out of the atmosphere: apoapsis {apoapsis} km, periapsis {periapsis} km')

# ---------- the circularisation PAD, worked out as a crew would ----------
gap('circularisation Δv: nothing on the panels gives it; the crew works it out from APO and PERI (vis-viva), or '
    'Mission Control reads up a PAD')
radius_apoapsis = (KERBIN_RADIUS_KM + apoapsis) * 1000
semi_major_axis = (KERBIN_RADIUS_KM + (apoapsis + periapsis) / 2) * 1000
speed_at_apoapsis = math.sqrt(KERBIN_MU * (2 / radius_apoapsis - 1 / semi_major_axis))
delta_v = math.sqrt(KERBIN_MU / radius_apoapsis) - speed_at_apoapsis
key_in('f_pro', f'{delta_v:.1f}')
burn_time = number('cmp', 'disp_tb')
pin('sys', 'evt_src', EVENT_SOURCE['APO'])
time.sleep(0.6)
to_apoapsis = -clock_seconds(out('sys', 'disp_evt')['text'])
mission_time = clock_seconds(out('eng', 'disp_met')['text'])
gap('TIG: the crew adds MET, time to apoapsis and half the burn time by hand')
ignition_time = mission_time + to_apoapsis - burn_time / 2
key_in('f_tig', f'{int(ignition_time // 3600):02d}{int(ignition_time // 60 % 60):02d}{int(ignition_time % 60):02d}')
log(f"PAD keyed: Δv {out('cmp', 'disp_pro').get('text')} m/s, TIG {out('cmp', 'disp_tig').get('text')}, "
    f"burn {burn_time} s, time to apoapsis {to_apoapsis} s; entry error lamp {out('cmp', 'lamp_err').get('on')}")

# ---------- the burn ----------
pin('eng', 'sas_mode', SAS_MODE['maneuver'])
pin('sys', 'evt_src', EVENT_SOURCE['TIG'])
if not wait(lambda: (number('cmp', 'disp_att') or 99) < 3, 90):
    problem(f"not on the burn attitude: ATT ERR {out('cmp', 'disp_att').get('text')}, SAS mode {seen['tlm/vessel'].get('sas_mode')}")
log(f"on the burn attitude: ATT ERR {out('cmp', 'disp_att').get('text')}°, time to TIG {out('cmp', 'disp_tfi').get('text')}")
pin('cmp', 'burn_arm', 1)
wait(lambda: seen['cmp/pad']['state'] == 'armed', 5)
wait(lambda: seen['tlm/time']['met'] >= ignition_time, 300)
pin('eng', 'throttle', 1.0)
log(f"TIG: throttle up; TIG lamp {out('cmp', 'lamp_tig')}")
deadline = time.time() + 180
while time.time() < deadline and not out('cmp', 'lamp_cutoff').get('on'):
    stage_on_flameout()
    time.sleep(0.05)
if not out('cmp', 'lamp_cutoff').get('on'):
    problem('the burn computer never cut off')
pin('eng', 'throttle', 0); pin('cmp', 'burn_arm', 0)
log(f"cutoff by the computer: Δv to go {out('cmp', 'disp_vg').get('text')} m/s")
time.sleep(2)

# ---------- the orbit ----------
apoapsis, periapsis = read_display('APO'), read_display('PERI')
orbit = vessel.orbit
log(f'PARKING ORBIT on the panel: apoapsis {apoapsis} km, periapsis {periapsis} km; '
    f'in KSP: {orbit.apoapsis_altitude / 1000:.2f} / {orbit.periapsis_altitude / 1000:.2f} km, e {orbit.eccentricity:.4f}')
if periapsis is None or periapsis < 70:
    problem('not in orbit: periapsis under 70 km')
pin('eng', 'eng_arm', 0); pin('eng', 'stage_arm', 0); pin('eng', 'sas_mode', SAS_MODE['stability'])
pin('sys', 'evt_src', EVENT_SOURCE['MAN'])
press('cmp', 'pad_clr')

print('\nALARMS that came on (legend: mission time):')
for legend, at in sorted(alarms_seen.items(), key=lambda item: item[1] or 0):
    print(f'  {legend}: {at}')
print('\nGAPS:')
for text in gaps:
    print('  - ' + text)
print('\nPROBLEMS:' if problems else '\nno problems')
for text in problems:
    print('  - ' + text)
sys.exit(1 if problems else 0)
