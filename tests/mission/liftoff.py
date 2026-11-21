"""SOLO liftoff in KSP: from a landed save with the CSM in orbit, RDV TGT gives the liftoff PAD (TIG, azimuth, cutoff
apoapsis); the direct ascent is flown from the panels on it (HEADING on ATTITUDE HOLD, cutoff on APO), CIRC at the
apoapsis, then what the planner's model predicted is measured: the ascent's time and arc, and how far the CSM is.

    .venv/bin/python tests/mission/liftoff.py [save]      # default: full-landed

Needs gateway-ksp and flight-dynamics; replaces the game's flight with the save. Flown 2026-11-21: the CSM 3.8°
(15 km) behind at the apoapsis, with a cutoff 5 km short (fixed since: the cutoff anticipation was too long). The
M.E.M. of full-landed has 642 m/s for a 645 m/s PAD: it reaches orbit with nothing left to close in."""
import math, os, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tests', 'mission'))
sys.path.insert(0, os.path.join(ROOT, 'flight-dynamics'))
SAVE = sys.argv[1] if len(sys.argv) > 1 else 'landed'
APO_RISE_LEAD_S = 0.1           # cut off this long ahead of the apoapsis's rise (0.35 s cut 5 km short at TWR 11)
from cockpit import Cockpit, Abort  # noqa: E402
from mission import target_csm, phase_ahead_deg  # noqa: E402
import planner  # noqa: E402

c = Cockpit('liftoff')
c.load(SAVE)
c.pin('eng', 'rcs', 1)                  # the M.E.M. has no reaction wheel
c.pin('solo', 'mcc_mode', 0)
lm = c.sc.active_vessel
csm = target_csm(c)
if csm is None:
    raise Abort('no CSM to target')
time.sleep(3)

status = c.request_pad('fd_rdv')
if not status.get('ok') or not status.get('text', '').startswith('LIFT'):
    raise Abort(f'no liftoff PAD: {status}')
azimuth = int(status['text'].split()[1][2:])
cutoff_apo_km = float(status['text'][status['text'].index('AP') + 2:])
c.press('cmp', 'pad_accept')
time.sleep(1)
pad = dict(c.seen['cmp/pad'])
met_now = c.tlm('time')['met']
c.log(f'LIFTOFF PAD: TIG MET {pad["tig"]:.0f} (in {pad["tig"] - met_now:.0f} s), Δv {pad["dv"]}, azimuth {azimuth}, '
      f'stage Δv {c.text("eng", "disp_dv")}, CSM lead now {phase_ahead_deg(c.sc, lm, csm):.1f}°')

# the planner's figures, from the same telemetry, to compare with the flight
telemetry = {topic: payload for topic, payload in c.seen.items() if topic.startswith('tlm/') or topic == 'mcc/bodies'}
body = planner.body_of(telemetry, 'Mun')
site_radius = body['radius'] + c.tlm('flight')['alt'] - c.tlm('flight')['radar']
target_a = c.tlm('target')['orbit']['a']
_, model_time, model_angle = planner.ascent(telemetry, body['mu'], site_radius, target_a - planner.APO_UNDER_TARGET_M)
wanted_lead = 0.0
c.log(f'model: cutoff on APO {cutoff_apo_km} km, ascent {model_time:.0f} s over {math.degrees(model_angle):.1f}°, '
      f'the CSM at the apoapsis with us')

# to the liftoff on the EVENT TIMER (TIG)
c.warp_to_event('TIG', 25, timeout=4 * 3600)
c.check('event timer counts down to the liftoff', c.event_in() is not None, c.text('sys', 'disp_evt'))
c.pin('eng', 'sas', 0)
c.hold(90, azimuth)
c.pin('eng', 'hold', 1)
c.pin('eng', 'thrust_lim', 1.0)
c.pin('eng', 'alt_ref', 1)
c.pin('eng', 'speed_ref', 0)
c.wait(lambda: (c.event_in() or 0) <= 0.3, 60, step=0.05)
frame = lm.orbit.body.non_rotating_reference_frame
liftoff_ut, liftoff_pos = c.sc.ut, lm.position(frame)
c.log(f'LIFTOFF at TIG: CSM lead {phase_ahead_deg(c.sc, lm, csm):.1f}°')
c.pin('eng', 'eng_arm', 1)
c.pin('eng', 'throttle', 1.0)
c.check('liftoff', c.wait(lambda: (c.num('eng', 'disp_vs') or 0) > 3, 15), c.text('eng', 'disp_vs'))
c.pin('eng', 'gear', 0)
c.pin('eng', 'alt_ref', 0)

orbit = c.tlm('orbit')
mu, radius = orbit.get('mu'), orbit.get('radius')
site_alt = c.tlm('flight').get('alt', 0) - c.tlm('flight').get('radar', 0)
target_alt = site_alt + planner.CUTOFF_ABOVE_SITE_M
next_note, last_apo = 0, None
while True:
    radar = c.tlm('flight').get('radar', 0)
    vs, hs, twr = c.num('eng', 'disp_vs'), c.num('eng', 'disp_hs'), c.num('eng', 'disp_twr')
    if None in (vs, hs, twr) or twr <= 0:
        if c.lit('eng', 'cw_flameout'):
            c.problem(f'flameout on the climb: {c.orbit_text()}')
            break
        time.sleep(0.1); continue
    alt = c.num('eng', 'disp_alt') or 0
    g = mu / (radius + alt) ** 2
    wanted_vs = max(-15.0, min(60.0, (target_alt - alt) / 25.0))
    if radar < 1500:
        wanted_vs = max(wanted_vs, 10.0 if radar > 100 else 40.0)
    lift = (g - hs * hs / (radius + alt) + 0.3 * (wanted_vs - vs)) / (twr * g)
    pitch = 90.0 if radar < 60 else math.degrees(math.asin(max(-0.2, min(1.0, lift))))
    c.hold(pitch, azimuth)
    apo = c.num('solo', 'disp_apo')
    if apo is not None:
        # cut off ahead of the apoapsis's rise (with TWR 11 it ran 10 km past between two looks)
        rising = 0.0 if last_apo is None else max(0.0, (apo - last_apo[0]) / max(0.05, time.time() - last_apo[1]))
        last_apo = (apo, time.time())
        if apo + rising * APO_RISE_LEAD_S >= cutoff_apo_km:
            break
    if time.time() > next_note:
        c.log(f'  climb: ALT {radar:.0f} m, V/S {vs:+.1f}, H/S {hs:.0f}, pitch {c.text("eng", "disp_att_pitch")}, '
              f'{c.orbit_text()}, stage Δv {c.text("eng", "disp_dv")}')
        next_note = time.time() + 4
    time.sleep(0.1)
c.press('eng', 'eng_cutoff')
c.pin('eng', 'throttle', 0.0)
cutoff_ut = c.sc.ut
time.sleep(2)
c.log(f'cutoff {cutoff_ut - liftoff_ut:.0f} s after liftoff at {c.tlm("flight").get("alt", 0):.0f} m: {c.orbit_text()}, '
      f'stage Δv {c.text("eng", "disp_dv")}')
c.pin('eng', 'hold', 0)
c.pin('eng', 'sas', 1)
c.sas_mode('prograde')

status = c.request_pad('fd_circ')
if not status.get('ok'):
    raise Abort(f'no CIRC PAD: {status}')
c.fly_pad()
insertion_ut, insertion_pos = c.sc.ut, lm.position(frame)
dot = lambda a, b: sum(x * y for x, y in zip(a, b))
arc = math.degrees(math.acos(max(-1, min(1, dot(liftoff_pos, insertion_pos) /
                                        math.sqrt(dot(liftoff_pos, liftoff_pos) * dot(insertion_pos, insertion_pos))))))
lead = phase_ahead_deg(c.sc, lm, csm) % 360
c.log(f'INSERTION: {c.orbit_text()}, stage Δv {c.text("eng", "disp_dv")}; ascent {insertion_ut - liftoff_ut:.0f} s '
      f'over {arc:.1f}° (model {model_time:.0f} s, {math.degrees(model_angle):.1f}°); CSM lead {lead:.1f}° '
      f'(wanted {wanted_lead % 360:.1f}°, off by {((lead - wanted_lead + 180) % 360) - 180:+.1f}°); '
      f'RANGE {c.text("rdv", "disp_range")} (KM {c.lit("rdv", "led_km")}), CLOSING {c.text("rdv", "disp_closing")}')

status = c.request_pad('fd_rdv')
if status.get('ok'):
    time.sleep(1)
    uplink = c.seen.get('pad/uplink', {})
    wait = uplink.get('tig_met', 0) - c.tlm('time')['met']
    c.log(f'RDV PAD after the insertion: {status["text"]}, TIG in {wait:.0f} s')
c.save('liftoff-orbit')
c.report_alarms()
