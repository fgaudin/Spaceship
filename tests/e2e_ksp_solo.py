"""SOLO panel in KSP: each flight dynamics PAD requested, accepted, flown from the panels, and its outcome checked.

    .venv/bin/python tests/e2e_ksp_solo.py [circ] [plane] [rdv] [inject]

Needs the flight-dynamics service. Loads one save per request (names below). A burn is flown as a crew would:
ACCEPT the PAD, BURN ARM, SAS MNVR, WARP TO EVT up to the TIG, throttle up, the burn computer cuts off.
"""
import json, math, sys, time
import krpc
import paho.mqtt.client as mqtt

CASES = {
    'circ': 'lor3-selftest-coast',          # coasting to apoapsis after the ascent
    'plane': 'lor3-rdv-plane',              # chaser in orbit, target in another plane
    'rdv': 'lor3-rdv-pre-transfer',         # chaser and target in the same plane, apart
    'inject': 'lor3-selftest-pre-tmi',      # parking orbit, before the Mun injection
}
SAS_MANEUVER = 'sas_mnvr'               # the SAS MODE panel's MNVR button
MIN_BURN_S = 10.0
EVENT_SOURCE_TIG = 1
seen = {}
cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id='e2e-solo')
cli.on_message = lambda c, u, m: seen.__setitem__(m.topic, json.loads(m.payload or b'{}'))
cli.connect('localhost', 1883); cli.subscribe('#'); cli.loop_start()
conn = krpc.connect(name='e2e-solo')
sc = conn.space_center
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
        time.sleep(0.1)
    return False


def pin(panel, ctl, v, retain=True):
    cli.publish(f'panel/{panel}/in/{ctl}', json.dumps({'v': v}), qos=1, retain=retain); time.sleep(0.3)


def press(panel, ctl):
    pin(panel, ctl, 1, False); pin(panel, ctl, 0, False)


out = lambda panel, name: seen.get(f'panel/{panel}/out/{name}') or {}


def load(save, needs_target=False):
    sc.load(save)
    time.sleep(8)
    vessel = sc.active_vessel
    for panel, control, value in (('eng', 'cb_main', 1), ('eng', 'throttle', 0), ('eng', 'eng_arm', 0), ('eng', 'stage_arm', 0),
                                  ('eng', 'sas', 0), ('cmp', 'burn_arm', 0), ('sys', 'evt_src', 0),
                                  ('eng', 'thrust_lim', 1.0)):
        pin(panel, control, value)
    pin('eng', 'sas', 1)
    press('cmp', 'pad_clr')
    wait(lambda: seen['tlm/vessel']['name'] == vessel.name and 'lan' in seen['tlm/orbit'], 15)
    if needs_target:
        # KSP does not keep the target in a save: TGT ▸ on the RDV panel picks the nearest vessel
        press('rdv', 'tgt_next')
        wait(lambda: sc.target_vessel is not None and (seen.get('tlm/target') or {}).get('orbit'), 10)
        note(f"target: {sc.target_vessel.name if sc.target_vessel else None}")
    return vessel


def request(button):
    """Press a SOLO button; the PAD must come up blinking on the burn computer. Returns fd/status."""
    seen.pop('fd/status', None)
    press('solo', button)
    wait(lambda: 'fd/status' in seen, 5)
    status = seen.get('fd/status', {})
    if status.get('ok'):
        check(f'{button}: PAD read up, waiting on the burn computer ({status["text"]})',
              wait(lambda: out('cmp', 'lamp_uplink').get('on'), 5), out('cmp', 'lamp_uplink'))
    return status


def diagnose(phase):
    craft, orbit, pad = seen['tlm/vessel'], seen['tlm/orbit'], seen.get('cmp/pad', {})
    note(f"  {phase}: MET {seen['tlm/time']['met']:.0f} (TIG {pad.get('tig')}), warp {seen['tlm/time']['warp']}, "
         f"throttle {craft['throttle']}, thrust {craft['thrust'] / 1000:.0f} kN, computer {pad.get('state')}, "
         f"orbit e {orbit['e']:.4f} i {orbit['i']:.2f}°")


def fly_pad():
    """ACCEPT, arm, point, warp to the TIG, burn until the computer cuts off. Returns the Δv left to go."""
    press('cmp', 'pad_accept')
    wait(lambda: seen['cmp/pad']['tig'] is not None, 5)
    pad = seen['cmp/pad']
    # A crew flies a small burn on a low THRUST LIMIT, so that it lasts long enough for the burn computer's cutoff
    # (about 0.1 s of thrust) to be accurate: here, at least 10 s.
    craft = seen['tlm/vessel']
    full_thrust_seconds = craft['mass'] * math.hypot(*pad['dv']) / max(craft['thrust_avail'], 1.0)
    limit = 1.0 if full_thrust_seconds >= MIN_BURN_S else max(0.05, round(full_thrust_seconds / MIN_BURN_S / 0.05) * 0.05)
    if limit < 1.0:
        note(f'  {full_thrust_seconds:.1f} s at full thrust: THRUST LIMIT {limit * 100:.0f} %')
        pin('eng', 'thrust_lim', limit)
    pin('cmp', 'burn_arm', 1)
    press('eng', SAS_MANEUVER)
    wait(lambda: float(out('cmp', 'disp_att').get('text', '99')) < 3, 120)
    pin('sys', 'evt_src', EVENT_SOURCE_TIG)
    # Warp until the TIG is close (WARP TO EVT stops a minute before; KSP may stop it earlier, near a body).
    deadline = time.time() + 1800
    while time.time() < deadline and pad['tig'] - seen['tlm/time']['met'] > 90:
        if seen['tlm/time']['warp'] == 1:
            press('sys', 'warp_to')
        diagnose('warping')
        time.sleep(5)
    wait(lambda: float(out('cmp', 'disp_att').get('text', '99')) < 3, 60)
    while seen['tlm/time']['met'] < pad['tig'] and time.time() < deadline:
        time.sleep(0.1)
    if seen['tlm/time']['met'] < pad['tig']:
        check('reached the TIG', False, (seen['tlm/time']['met'], pad['tig']))
        return None
    pin('eng', 'eng_arm', 1); pin('eng', 'stage_arm', 1); pin('eng', 'throttle', 1.0)
    deadline, next_note = time.time() + 600, 0
    while time.time() < deadline and not out('cmp', 'lamp_cutoff').get('on'):
        if out('eng', 'cw_flameout').get('on'):
            note(f"FLAMEOUT → STAGE (stage {seen['tlm/vessel']['stage']})")
            press('eng', 'stage'); time.sleep(2)
        if time.time() > next_note:
            craft = seen['tlm/vessel']
            note(f"  burning: to go {out('cmp', 'disp_vg').get('text')}, thrust {craft['thrust'] / 1000:.0f} kN, "
                 f"throttle {craft['throttle']}, stage {craft['stage']}, state {seen['cmp/pad']['state']}")
            next_note = time.time() + 5
        time.sleep(0.1)
    pin('eng', 'throttle', 0); pin('cmp', 'burn_arm', 0); pin('eng', 'eng_arm', 0); pin('eng', 'stage_arm', 0)
    pin('eng', 'thrust_lim', 1.0)
    pin('sys', 'evt_src', 0)
    time.sleep(2)
    return out('cmp', 'disp_vg').get('text')


wanted = [name for name in sys.argv[1:] if name in CASES] or list(CASES)

if 'circ' in wanted:
    vessel = load(CASES['circ'])
    orbit = vessel.orbit
    mu, apoapsis = orbit.body.gravitational_parameter, orbit.apoapsis
    expected = math.sqrt(mu / apoapsis) - math.sqrt(mu * (2 / apoapsis - 1 / orbit.semi_major_axis))
    status = request('fd_circ')
    check('CIRC: at apoapsis', status.get('text', '').startswith('CIRC APO'), status)
    check('CIRC: Δv as computed from KSP\'s own orbit (within 1 m/s)', abs(seen['pad/uplink']['dv'][0] - expected) < 1,
          (seen.get('pad/uplink'), expected))
    left = fly_pad()
    orbit = vessel.orbit
    note(f'after the burn: {orbit.apoapsis_altitude / 1000:.1f} × {orbit.periapsis_altitude / 1000:.1f} km, e {orbit.eccentricity:.4f}, to go {left}')
    check('CIRC flown: eccentricity under 0.01', orbit.eccentricity < 0.01, orbit.eccentricity)

if 'plane' in wanted:
    vessel = load(CASES['plane'], needs_target=True)
    target = sc.target_vessel
    if target is None:
        check('PLANE: the save has a target', False)
    else:
        before = math.degrees(vessel.orbit.relative_inclination(target.orbit))
        status = request('fd_plane')
        check('PLANE: towards the target', status.get('text', '').startswith('PLANE TGT'), status)
        fly_pad()
        after = math.degrees(vessel.orbit.relative_inclination(target.orbit))
        note(f'relative inclination {before:.2f}° → {after:.3f}°')
        check('PLANE flown: relative inclination under 0.1°', after < 0.1, after)

if 'rdv' in wanted:
    vessel = load(CASES['rdv'], needs_target=True)
    target = sc.target_vessel
    if target is None:
        check('RDV: the save has a target', False)
    else:
        status = request('fd_rdv')
        check('RDV: transfer PAD', status.get('text', '').startswith('RDV'), status)
        if status.get('ok'):
            fly_pad()
            approach = min(each.distance for each in vessel.orbit.closest_approaches(target.orbit, 2))
            note(f'closest approach after the transfer burn: {approach / 1000:.2f} km')
            check('RDV flown: closest approach under 5 km', approach < 5000, approach)

if 'inject' in wanted:
    vessel = load(CASES['inject'])
    pin('solo', 'fd_body', 0)
    status = request('fd_inject')
    check('INJECT: Mun transfer PAD', status.get('text', '').startswith('INJ MUN'), status)
    if status.get('ok'):
        fly_pad()
        next_orbit = vessel.orbit.next_orbit
        body = next_orbit.body.name if next_orbit is not None else None
        note(f'after the burn: apoapsis {vessel.orbit.apoapsis_altitude / 1000:.0f} km, next SOI: {body}')
        check('INJECT flown: the trajectory reaches the Mun', body == 'Mun', body)

print('all passed' if not fails else f'{len(fails)} FAILED')
sys.exit(1 if fails else 0)
