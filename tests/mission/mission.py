"""Full mission to the Mun and back, flown from the cockpit's panels, in KSP.

    .venv/bin/python tests/mission/mission.py <phase> [<phase> …]

Craft: AcapelloCams (the claude save's VAB): Mastodon first stage, Skiff second stage, the M.E.M. lander under a
fairing, CSM (Mk1-3, SM-25 with a Cheetah), window cameras cm_left/right and lm_left/right for STATION. Crew of two
(TAC Life Support: 90 h of supplies for one, 45 h for two). Every phase starts from the save the one before it made
(`full-<name>`), so a phase can be flown again. Logs in tmp/mission/.
"""
import math, sys, time
from cockpit import Cockpit, Abort, run, clock_seconds, EVENT_SOURCE, SPEED_REF

CRAFT = 'AcapelloCams IU'
CREW = ['Orvan Kerman', 'Vallock Kerman']        # two pilots (both have SAS)
PARKING_APO_KM = 80.0
WAIT_FOR_CSM = False         # the CSM comes down to the LM (the LM's Δv after the landing is too short)
LM_ORBIT_KM = 12.0
LANDED_SAVE = 'landed2'


def launch():
    """Pad to parking orbit: ATTITUDE HOLD flies the pitch programme, STAGE on FLAMEOUT, LES and fairing out of
    the atmosphere, cutoff on the apoapsis, then the SOLO CIRC PAD."""
    c = Cockpit('launch')
    sc = c.sc
    try:
        on_pad = sc.active_vessel
    except Exception:           # not in the flight scene
        on_pad = None
    if not (on_pad and on_pad.name == CRAFT and on_pad.situation.name == 'pre_launch'
            and sorted(k.name for k in on_pad.crew) == sorted(CREW)):
        sc.launch_vessel('VAB', CRAFT, 'LaunchPad', recover=True, crew=CREW)     # a refused crew stops the test
        time.sleep(10)
    vessel = sc.active_vessel
    vessel.control.throttle = 0.0
    c.zero_inputs()
    c.wait(lambda: c.tlm('vessel').get('name') == vessel.name and c.tlm('vessel').get('situation') == 'pre_launch', 20)
    time.sleep(3)
    c.log(f'on the pad: {vessel.name}, crew {[k.name for k in vessel.crew]}; CREW {c.text("sys", "disp_crew")}, '
          f'CM {c.text("sys", "disp_cm_crew")} LM {c.text("sys", "disp_lm_crew")}, stage {c.text("eng", "disp_stage")}, '
          f'stage Δv {c.text("eng", "disp_dv")}, NEXT STAGE {c.next_stage()}, EC {c.text("sys", "disp_ec")} '
          f'{c.text("sys", "disp_ec_rate")}/s, food {c.text("sys", "disp_ls_food")} h')
    c.check('NEXT STAGE on the pad: ENGINES and CLAMPS', sorted(c.next_stage()) == ['CLAMPS', 'ENGINES'], c.next_stage())
    c.check('STATION: controls in the CM', c.lit('sys', 'lamp_stn_cm'), c.out('sys', 'lamp_stn_cm'))
    c.report_alarms()
    c.save('pad')

    # ---------- liftoff on ATTITUDE HOLD ----------
    c.pin('eng', 'sas', 0)
    c.hold(90, 90)
    c.pin('eng', 'hold', 1)
    c.pin('eng', 'eng_arm', 1)
    c.pin('eng', 'throttle', 1.0)
    c.stage(['ENGINES', 'CLAMPS'], 'liftoff')
    if not c.wait(lambda: (c.num('eng', 'disp_speed') or 0) > 5, 15):
        raise Abort('no liftoff')
    c.log(f'LIFTOFF: TWR {c.text("eng", "disp_twr")}, engines burning {c.text("eng", "disp_eng_on")}')

    def pitch_for(alt_m):
        return max(3.0, 90.0 - 87.0 * math.sqrt(max(0.0, alt_m - 1000) / 55000.0))

    les_gone = fairing_gone = False
    deadline, next_note = time.time() + 900, 0
    while time.time() < deadline:
        alt = c.num('eng', 'disp_alt') or 0.0
        speed = c.num('eng', 'disp_speed') or 0.0
        target_pitch = 90.0 if speed < 60 else pitch_for(alt)
        # below 30 km keep the nose within 4° of the velocity (the fairing and LES are long levers)
        prograde = (c.tlm('attitude').get('prograde') or {})
        if speed >= 60 and alt < 30000 and prograde.get('pitch') is not None:
            c.stand_in('prograde marker read from tlm/attitude (the FDAI ball shows it; no figure on a panel)')
            target_pitch = max(prograde['pitch'] - 4.0, min(prograde['pitch'] + 4.0, target_pitch))
        c.hold(target_pitch, 90)
        if c.lit('eng', 'cw_flameout') or (c.num('eng', 'disp_eng_on') or 0) == 0:
            c.stage(why='flameout on the ascent')
            time.sleep(1.0)
        # the tower and the fairing go once out of the thick air, when NEXT STAGE says that is what STAGE does
        # (the first stage drops before them: stage 10 comes first)
        if alt > 60000 and not les_gone and 'SOLIDS' in c.next_stage():
            c.stage(['SOLIDS'], 'launch escape tower')
            les_gone = True
        elif alt > 62000 and les_gone and not fairing_gone and c.next_stage() == ['FAIRING']:
            c.stage(['FAIRING'], 'fairing')
            fairing_gone = True
        apo = c.num('solo', 'disp_apo')
        if apo is not None and apo >= PARKING_APO_KM:
            break
        if time.time() > next_note:
            c.log(f'  ascent: alt {alt:.0f} m, speed {speed:.0f}, pitch {c.text("eng", "disp_att_pitch")} (hold '
                  f'{c.text("eng", "disp_hold_pitch")}, LED {c.out("eng", "led_hold")}), Q {c.text("eng", "disp_q")} kPa, '
                  f'G {c.text("eng", "disp_g")}, APO {apo} km, stage {c.text("eng", "disp_stage")} Δv {c.text("eng", "disp_dv")}')
            next_note = time.time() + 10
        time.sleep(0.2)
    else:
        raise Abort('apoapsis never reached the parking altitude')
    c.press('eng', 'eng_cutoff')
    c.pin('eng', 'throttle', 0.0)
    c.log(f'MECO on APO: {c.orbit_text()}, alt {c.text("eng", "disp_alt")} m')
    c.check('CUTOFF lamp lit after the button', c.wait(lambda: (c.tlm('vessel').get('thrust') or 0) == 0, 3),
            c.tlm('vessel').get('thrust'))
    c.hold(0, 90)
    c.wait(lambda: (c.num('eng', 'disp_alt') or 0) > 70500, 300)
    if not les_gone and 'SOLIDS' in c.next_stage():
        c.stage(['SOLIDS'], 'launch escape tower'); les_gone = True
    if les_gone and not fairing_gone and c.next_stage() == ['FAIRING']:
        c.stage(['FAIRING'], 'fairing'); fairing_gone = True
    c.pin('eng', 'hold', 0)
    c.pin('eng', 'sas', 1)
    c.sas_mode('prograde')
    c.log(f'out of the atmosphere: {c.orbit_text()}')
    c.save('coast')

    # ---------- circularise: SOLO CIRC ----------
    status = c.request_pad('fd_circ')
    c.check('CIRC PAD at apoapsis', status.get('ok') and 'CIRC' in status.get('text', ''), status)
    c.fly_pad()
    c.pin('eng', 'sas', 1)
    c.sas_mode('stability')
    time.sleep(2)
    orbit = sc.active_vessel.orbit
    c.log(f'PARKING ORBIT on the panel: {c.orbit_text()}; KSP {orbit.apoapsis_altitude / 1e3:.1f} × '
          f'{orbit.periapsis_altitude / 1e3:.1f} km, e {orbit.eccentricity:.4f}')
    c.check('in orbit (periapsis above 70 km)', orbit.periapsis_altitude > 70000, orbit.periapsis_altitude)
    c.log(f'stage {c.text("eng", "disp_stage")}, stage Δv {c.text("eng", "disp_dv")} m/s, NEXT STAGE {c.next_stage()}, '
          f'EC {c.text("sys", "disp_ec")} ({c.text("sys", "disp_ec_rate")}/s), food {c.text("sys", "disp_ls_food")} h')
    c.report_alarms()
    c.save('lko')


def tmi():
    """SOLO INJECT (Mun), flown on what is still burning: the first stage, then the Skiff. A flameout stages only
    when NEXT STAGE lights ENGINES (never the tower, the fairing or the CSM separation). Then tower and fairing."""
    c = Cockpit('tmi')
    c.load('lko')
    status = c.request_pad('fd_inject', body=0)
    c.check('INJECT PAD to the Mun', status.get('ok') and 'MUN' in status.get('text', ''), status)
    if not status.get('ok'):
        raise Abort(f'no injection PAD: {status}')

    def on_flameout():
        if 'ENGINES' in c.next_stage():
            c.stage(why='flameout during TMI: next engines')
            return None
        c.problem(f'TMI: out of propellant on stages with engines; NEXT STAGE {c.next_stage()}; '
                  f'Δv to go {c.text("cmp", "disp_vg")}')
        return 'stop'

    left, pad = c.fly_pad(on_flameout=on_flameout)
    time.sleep(2)
    vessel = c.sc.active_vessel
    nxt = vessel.orbit.next_orbit
    c.log(f'after TMI: {c.orbit_text()}; KSP next SOI {nxt.body.name if nxt else None}'
          + (f', Mun periapsis {nxt.periapsis_altitude / 1e3:.0f} km' if nxt else ''))
    c.check('TMI: the trajectory reaches the Mun', nxt is not None and nxt.body.name == 'Mun', nxt)
    if c.next_stage() == ['ENGINES', 'DECOUPLE']:
        c.stage(['ENGINES', 'DECOUPLE'], 'spent first stage, Skiff lit')
    c.pin('eng', 'sas', 1)
    c.sas_mode('stability')
    c.save('tmi')


def turn_to_port(c, tolerance=1.0, timeout=600):
    """Rotation stick on the RDV panel's YAW and PITCH errors (turn to face the target port), then SAS holds."""
    last, last_t = None, None
    deadline = time.time() + timeout
    steady_since = None
    while time.time() < deadline:
        yaw, pitch = c.num('rdv', 'disp_yaw'), c.num('rdv', 'disp_pitch')
        if yaw is None or pitch is None:
            time.sleep(0.2); continue
        now = time.time()
        rates = (0.0, 0.0)
        if last is not None and now > last_t:
            rates = ((yaw - last[0]) / (now - last_t), (pitch - last[1]) / (now - last_t))
        last, last_t = (yaw, pitch), now
        if abs(yaw) < tolerance and abs(pitch) < tolerance and abs(rates[0]) < 0.3 and abs(rates[1]) < 0.3:
            steady_since = steady_since or now
            if now - steady_since > 3:
                break
        else:
            steady_since = None
        # aim for a turn rate proportional to the error (at most 3 °/s), the stick pushes towards that rate
        def axis(error, rate):
            wanted = -max(-3.0, min(3.0, error / 5.0))
            command = 0.25 * (wanted - rate) * -1
            return max(-0.6, min(0.6, command)) if abs(error) > 0.3 or abs(rate) > 0.2 else 0.0
        c.stick('rot_yaw', axis(yaw, rates[0]))
        c.stick('rot_pitch', axis(pitch, rates[1]))
        time.sleep(0.15)
    c.sticks_centred()
    c.log(f'turned to the port: YAW {c.text("rdv", "disp_yaw")} PITCH {c.text("rdv", "disp_pitch")} '
          f'ROLL {c.text("rdv", "disp_roll")}')


def approach_and_dock(c, close_speed=0.15, timeout=1800):
    """RCS on the RDV panel: null RIGHT and UP (where the port is, in our axes) while closing on AXIAL at
    close_speed; hold the range when the attitude errors grow. Ends on DOCKED."""
    deadline, next_note = time.time() + timeout, 0
    while time.time() < deadline:
        if c.lit('rdv', 'lamp_docked'):
            break
        right, up, axial = c.num('rdv', 'disp_right'), c.num('rdv', 'disp_up'), c.num('rdv', 'disp_axial')
        vright, vup, vaxial = c.num('rdv', 'disp_vright'), c.num('rdv', 'disp_vup'), c.num('rdv', 'disp_vaxial')
        yaw, pitch = c.num('rdv', 'disp_yaw'), c.num('rdv', 'disp_pitch')
        if None in (right, up, axial, vright, vup, vaxial):
            c.stick('trans_right', 0); c.stick('trans_up', 0); c.stick('trans_fwd', 0)
            time.sleep(0.3); continue
        lateral = math.hypot(right, up)
        want_right = -max(-0.1, min(0.1, right / 15.0))
        want_up = -max(-0.1, min(0.1, up / 15.0))
        aligned = yaw is not None and pitch is not None and abs(yaw) < 5 and abs(pitch) < 5
        if not aligned or (lateral > 1.0 and axial < 8):
            want_axial = 0.0 if axial > 4 else 0.05          # off axis close in: back off a little
        else:
            want_axial = -close_speed if axial > 3 else -0.1
        gain = 4.0
        c.stick('trans_right', max(-1, min(1, gain * (vright - want_right))))
        c.stick('trans_up', max(-1, min(1, gain * (vup - want_up))))
        c.stick('trans_fwd', max(-1, min(1, gain * (vaxial - want_axial))))
        if time.time() > next_note:
            c.log(f'  approach: AXIAL {axial:.2f} m ({vaxial:+.2f}), RIGHT {right:+.2f} ({vright:+.2f}), '
                  f'UP {up:+.2f} ({vup:+.2f}), YAW {yaw} PITCH {pitch}, CAPTURE {c.lit("rdv", "lamp_capture")}')
            next_note = time.time() + 8
        if not aligned and yaw is not None and (abs(yaw) > 8 or abs(pitch) > 8):
            c.sticks_centred()
            turn_to_port(c, timeout=120)
        time.sleep(0.12)
    c.sticks_centred()
    return c.lit('rdv', 'lamp_docked')


def fly_around_and_dock(c, standoff=25.0, clearance=15.0, close_speed=0.15, timeout=3600):
    """Dock to a target port that may be turning slowly (an uncontrolled stack), from the RDV panel alone.

    Attitude: the rotation stick keeps YAW and PITCH (turn to face the port squarely) near zero, so the pilot's axes
    stay those of the port and RIGHT / UP are the offsets from its axis, AXIAL the distance out of it. Translation,
    by legs: off the axis by `clearance` while behind or beside the port; out to `standoff` in front of it; onto the
    axis; then in at `close_speed`, holding the range whenever the alignment or the centring is lost."""
    previous, previous_t = None, None
    deadline, next_note, leg = time.time() + timeout, 0, None
    clamp = lambda x, a: max(-a, min(a, x))
    while time.time() < deadline:
        if c.lit('rdv', 'lamp_docked'):
            break
        figures = [c.num('rdv', name) for name in ('disp_yaw', 'disp_pitch', 'disp_right', 'disp_up', 'disp_axial',
                                                     'disp_vright', 'disp_vup', 'disp_vaxial')]
        if None in figures:
            c.sticks_centred(); time.sleep(0.3); continue
        yaw, pitch, right, up, axial, vright, vup, vaxial = figures
        now = time.time()
        yaw_rate = pitch_rate = 0.0
        if previous is not None and now - previous_t > 0.05:
            yaw_rate = (yaw - previous[0]) / (now - previous_t)
            pitch_rate = (pitch - previous[1]) / (now - previous_t)
        previous, previous_t = (yaw, pitch), now
        # --- attitude: a turn rate proportional to the error, at most 2 °/s
        def turn(error, rate):
            wanted = -clamp(error / 4.0, 2.0)
            if abs(error) < 0.4 and abs(rate) < 0.15:
                return 0.0
            return clamp(0.3 * (rate - wanted), 0.5)
        c.stick('rot_yaw', turn(yaw, yaw_rate))
        c.stick('rot_pitch', turn(pitch, pitch_rate))
        aligned = abs(yaw) < 4 and abs(pitch) < 4
        # --- translation legs
        lateral = math.hypot(right, up)
        if axial < standoff - 3 and leg != 'final':
            leg = 'around'
            # keep (or get) `clearance` off the axis, in the direction we already are; move out along the axis
            direction = (right / lateral, up / lateral) if lateral > 0.5 else (0.0, 1.0)
            target_right, target_up = direction[0] * clearance, direction[1] * clearance
            target_axial = standoff if lateral > clearance * 0.7 else axial      # first off the axis, then out
        elif leg != 'final':
            leg = 'centre'
            target_right = target_up = 0.0
            target_axial = standoff
            if lateral < 0.3 and abs(vright) < 0.03 and abs(vup) < 0.03 and aligned:
                leg = 'final'
        if leg == 'final':
            target_right = target_up = 0.0
            target_axial = None
        want_right = clamp((target_right - right) / 25.0, 0.3)
        want_up = clamp((target_up - up) / 25.0, 0.3)
        if target_axial is not None:
            want_axial = clamp((target_axial - axial) / 40.0, 0.4)
        elif not aligned or lateral > max(0.4, 0.08 * axial):
            want_axial = 0.0                    # hold the range until aligned and centred again
            if lateral > 2.0 and axial < 10:
                want_axial = 0.05
        else:
            want_axial = -close_speed if axial > 3 else -0.1
        gain = 4.0
        # each display's rate against the rate wanted: moving right makes the port's RIGHT offset shrink, moving
        # forward (into the port) makes AXIAL shrink, so the command is the rate surplus, the same form for all three
        c.stick('trans_right', clamp(gain * (vright - want_right), 1))
        c.stick('trans_up', clamp(gain * (vup - want_up), 1))
        c.stick('trans_fwd', clamp(gain * (vaxial - want_axial), 1))
        if now > next_note:
            c.log(f'  {leg}: AXIAL {axial:+.1f} ({vaxial:+.2f}) RIGHT {right:+.2f} ({vright:+.2f}) UP {up:+.2f} '
                  f'({vup:+.2f}) YAW {yaw:+.1f} PITCH {pitch:+.1f} RANGE {c.text("rdv", "disp_range")} '
                  f'CAPTURE {c.lit("rdv", "lamp_capture")} RCS ΔV {c.text("sys", "disp_rcs_dv")}')
            next_note = now + 10
        time.sleep(0.12)
    c.sticks_centred()
    return c.lit('rdv', 'lamp_docked')


def td():
    """Transposition and docking: CSM off the stack, Cheetah lit, back off, turn round, dock to the M.E.M.'s port;
    then the extraction: STAGE fires the TD-06 under the lander."""
    c = Cockpit('td')
    c.load('tmi')
    c.pin('eng', 'sas', 1)
    c.sas_mode('stability')
    c.pin('eng', 'rcs', 0)
    time.sleep(3)
    for _ in range(3):                  # tower and fairing first, if still on
        time.sleep(2.0)
        preview = c.next_stage()
        if 'SOLIDS' in preview:
            c.stage(['SOLIDS'], 'launch escape tower')
        elif preview == ['FAIRING']:
            c.stage(['FAIRING'], 'fairing')
        else:
            break
    time.sleep(3)
    mass_stack = c.tlm('vessel').get('mass')
    c.stage(['DECOUPLE'], 'CSM separation (TS-25)')
    c.wait(lambda: c.tlm('vessel').get('mass', 0) < 0.8 * mass_stack, 10)
    c.log(f'CSM free: {c.tlm("vessel").get("name")} {c.tlm("vessel").get("mass", 0) / 1e3:.1f} t; STATION CM '
          f'{c.text("sys", "disp_cm_crew")} LM {c.text("sys", "disp_lm_crew")}, TUNNEL {c.lit("sys", "lamp_tunnel")}')
    c.check('STATION: TUNNEL off once apart', not c.lit('sys', 'lamp_tunnel'), c.out('sys', 'lamp_tunnel'))
    # the stack's Instrument Unit (RC-L01): is its SAS holding? (ground truth from kRPC)
    time.sleep(3)
    stack = next((v for v in c.sc.vessels if v != c.sc.active_vessel and
                  any(p.name == 'probeStackLarge' for p in v.parts.all)), None)
    if stack is None:
        c.problem('the stack with the Instrument Unit was not found after the separation')
    else:
        import math as _m
        spin = _m.degrees(_m.sqrt(sum(x * x for x in stack.angular_velocity(stack.orbit.body.non_rotating_reference_frame))))
        c.log(f'stack {stack.name!r}: SAS {stack.control.sas}, spin {spin:.2f} °/s')
        if not stack.control.sas:
            c.stand_in('the stack\'s SAS switched on through kRPC (proposed: a TGT SAS toggle on the RDV panel)')
            stack.control.sas = True
            time.sleep(1)
            c.log(f'stack SAS now {stack.control.sas}')
    # the Cheetah: stage 6 (the TD-06) is on the other vessel now
    for _ in range(3):
        preview = c.next_stage()
        if preview == ['ENGINES']:
            c.stage(['ENGINES'], 'SM engine (Cheetah)')
            break
        c.log(f'NEXT STAGE {preview or "dark"} at stage {c.text("eng", "disp_stage")}: nothing of ours, stage past it')
        c.stage(preview, 'an empty stage')
    c.check('the Cheetah is lit (white on the engine matrix)', 'w' in ''.join(c.out('eng', 'mx_eng').get('rows', [])),
            c.out('eng', 'mx_eng'))
    c.pin('eng', 'rcs', 1)
    c.check('RCS LED on', c.wait(lambda: c.lit('eng', 'led_rcs'), 5), c.out('eng', 'led_rcs'))
    # target the stack, then back away along the nose to about 25 m
    c.press('rdv', 'tgt_next')
    c.wait(lambda: c.text('rdv', 'txt_tgt') not in (None, 'NO TARGET'), 5)
    c.log(f'TARGET {c.text("rdv", "txt_tgt")!r}: RANGE {c.text("rdv", "disp_range")} m, CLOSING {c.text("rdv", "disp_closing")}')
    if c.text('rdv', 'txt_tgt') in (None, 'NO TARGET'):
        raise Abort('TGT ▸ found nothing to target: the lander stack is not a target')
    c.stick('trans_fwd', 1.0)
    time.sleep(4)
    c.stick('trans_fwd', 0.0)
    c.wait(lambda: (c.num('rdv', 'disp_range') or 0) > 25, 240)
    c.stick('trans_fwd', -1.0)
    c.wait(lambda: (c.num('rdv', 'disp_closing') or -1) > -0.05, 30)
    c.stick('trans_fwd', 0.0)
    c.log(f'backed off: RANGE {c.text("rdv", "disp_range")} m, CLOSING {c.text("rdv", "disp_closing")} m/s')
    # control from our nose port, target the lander's port, turn round
    c.pin('rdv', 'ctrl_port', 1)
    c.press('rdv', 'port_next')
    c.check('a docking port targeted (PORT LED)', c.wait(lambda: c.lit('rdv', 'led_port'), 5), c.out('rdv', 'led_port'))
    c.check('CTRL FROM PORT LED steady', c.wait(lambda: c.out('rdv', 'led_ctrl_port') == {'on': True, 'blink': False}, 5),
            c.out('rdv', 'led_ctrl_port'))
    dock_and_extract(c)


def dock_and_extract(c):
    docked = fly_around_and_dock(c)
    c.check('DOCKED', docked, c.out('rdv', 'lamp_docked'))
    if not docked:
        raise Abort('no docking')
    time.sleep(5)
    c.pin('rdv', 'ctrl_port', 0)
    c.log(f'docked: {c.tlm("vessel").get("name")} {c.tlm("vessel").get("mass", 0) / 1e3:.1f} t; STATION TUNNEL '
          f'{c.lit("sys", "lamp_tunnel")}, CM {c.text("sys", "disp_cm_crew")} LM {c.text("sys", "disp_lm_crew")}')
    c.check('STATION: TUNNEL lit when docked', c.wait(lambda: c.lit('sys', 'lamp_tunnel'), 15), c.out('sys', 'lamp_tunnel'))
    c.save('td-docked')
    # extraction
    preview = c.next_stage()
    c.log(f'extraction: NEXT STAGE {preview} at stage {c.text("eng", "disp_stage")}')
    if preview != ['DECOUPLE']:
        c.problem(f'after docking, STAGE would do {preview} (stage {c.text("eng", "disp_stage")}), not the TD-06 alone')
        raise Abort('extraction needs another way than STAGE')
    mass = c.tlm('vessel').get('mass')
    c.stage(['DECOUPLE'], 'extraction: TD-06 under the lander')
    c.check('extraction: the spent stage left', c.wait(lambda: c.tlm('vessel').get('mass', mass) < mass - 3000, 10),
            c.tlm('vessel').get('mass'))
    c.stick('trans_fwd', -1.0); time.sleep(3); c.stick('trans_fwd', 0.0)
    c.pin('eng', 'rcs', 0)
    c.log(f'CSM+LM: {c.tlm("vessel").get("mass", 0) / 1e3:.1f} t, stage {c.text("eng", "disp_stage")}, '
          f'stage Δv {c.text("eng", "disp_dv")}, RCS ΔV {c.text("sys", "disp_rcs_dv")}, NEXT STAGE {c.next_stage()}')
    c.press('rdv', 'tgt_clear')
    c.save('extracted')


def plan_node(c, ut, periapsis_of, target_m, components=('radial', 'prograde'), tolerance_m=2000, start=None):
    """Mission Control's flight dynamics, standing in: a maneuver node at `ut`, its Δv adjusted (secant steps, one
    component at a time) until periapsis_of(node) is target_m. The node is left in place: the burn computer loads
    a node made in the map view as its PAD. Returns the node."""
    c.stand_in('the mid-course / return PAD is computed by Mission Control (kRPC maneuver node search), not on board')
    vessel = c.sc.active_vessel
    node = vessel.control.add_node(ut, *(start or (0.0, 0.0, 0.0)))
    for _ in range(4):
        for component in components:
            for _ in range(12):
                value = periapsis_of(node)
                if value is None:
                    setattr(node, component, getattr(node, component) + 2.0)
                    continue
                error = value - target_m
                if abs(error) < tolerance_m:
                    break
                step = 0.5
                setattr(node, component, getattr(node, component) + step)
                after = periapsis_of(node)
                setattr(node, component, getattr(node, component) - step)
                if after is None or after == value:
                    break
                slope = (after - value) / step
                change = max(-50.0, min(50.0, -error / slope))
                setattr(node, component, getattr(node, component) + change)
        value = periapsis_of(node)
        if value is not None and abs(value - target_m) < tolerance_m:
            break
    c.log(f'node planned: UT {node.ut:.0f}, prograde {node.prograde:.2f}, normal {node.normal:.2f}, radial '
          f'{node.radial:.2f} m/s → periapsis {periapsis_of(node)}')
    return node


def mun_periapsis(node):
    nxt = node.orbit.next_orbit
    if nxt is None or nxt.body.name != 'Mun':
        return None
    return nxt.periapsis_altitude


def td_dock():
    """Carry on the transposition from where the CSM is now (no save loaded)."""
    c = Cockpit('td')
    c.pin('eng', 'rcs', 1)
    if not c.lit('rdv', 'led_port'):
        c.press('rdv', 'port_next')
    dock_and_extract(c)


def no_staging(c):
    """A flameout handler that never stages: with CSM and LM docked, the next STAGE lights the LM's Terrier too."""
    def handler():
        c.problem(f'thrust lost during a CSM burn: NEXT STAGE {c.next_stage()}, Δv to go {c.text("cmp", "disp_vg")}')
        return 'stop'
    return handler


def mcc():
    """Mid-course correction to a 30 km Mun periapsis: a node from Mission Control, loaded by the burn computer."""
    c = Cockpit('mcc')
    c.load('extracted')
    vessel = c.sc.active_vessel
    nxt = vessel.orbit.next_orbit
    c.log(f'before MCC: next SOI {nxt.body.name if nxt else None}, Mun periapsis '
          f'{nxt.periapsis_altitude / 1e3 if nxt else float("nan"):.0f} km')
    c.press('cmp', 'pad_clr')
    node = plan_node(c, c.sc.ut + 600, mun_periapsis, 30000)
    loaded = c.wait(lambda: c.seen.get('cmp/pad', {}).get('tig') is not None and
                    abs(sum(x * x for x in c.seen['cmp/pad']['dv']) ** 0.5 -
                        (node.prograde ** 2 + node.normal ** 2 + node.radial ** 2) ** 0.5) < 0.2, 15)
    c.check('the node made in the map view is loaded as the PAD', loaded, c.seen.get('cmp/pad'))
    c.log(f'PAD from the node: TIG {c.text("cmp", "disp_tig")}, Δv {c.text("cmp", "disp_pro")} / '
          f'{c.text("cmp", "disp_nrm")} / {c.text("cmp", "disp_rad")}, burn {c.text("cmp", "disp_tb")} s')
    c.fly_pad(accept=False, on_flameout=no_staging(c))
    time.sleep(2)
    nxt = c.sc.active_vessel.orbit.next_orbit
    c.log(f'after MCC: Mun periapsis {nxt.periapsis_altitude / 1e3 if nxt else float("nan"):.1f} km')
    c.check('MCC: Mun periapsis 15–60 km', nxt is not None and 15000 < nxt.periapsis_altitude < 60000,
            nxt.periapsis_altitude if nxt else None)
    for each in c.sc.active_vessel.control.nodes:
        each.remove()
    c.pin('eng', 'sas', 1)
    c.sas_mode('stability')
    c.save('mcc')


def loi():
    """Coast to the Mun (WARP TO EVT on SOI), then SOLO CIRC: circular at periapsis."""
    c = Cockpit('loi')
    c.load('mcc')
    c.warp_to_event('SOI', 30, timeout=7200)
    c.wait(lambda: c.text('solo', 'txt_body') == 'MUN', 300)
    c.check('NAVIGATION: body MUN after the SOI change', c.text('solo', 'txt_body') == 'MUN', c.text('solo', 'txt_body'))
    time.sleep(5)
    c.log(f'in the Mun SOI: {c.orbit_text()}; speeds V/S {c.text("eng", "disp_vs")} H/S {c.text("eng", "disp_hs")}')
    c.save('mun-soi')
    status = c.request_pad('fd_circ')
    c.check('CIRC at the Mun: PAD at periapsis', status.get('ok') and 'PERI' in status.get('text', ''), status)
    if not status.get('ok'):
        raise Abort(f'no LOI PAD: {status}')
    c.fly_pad(on_flameout=no_staging(c))
    time.sleep(3)
    orbit = c.sc.active_vessel.orbit
    c.log(f'MUN ORBIT on the panel: {c.orbit_text()}; KSP {orbit.apoapsis_altitude / 1e3:.1f} × '
          f'{orbit.periapsis_altitude / 1e3:.1f} km around {orbit.body.name}')
    c.check('in Mun orbit, periapsis above 8 km', orbit.body.name == 'Mun' and orbit.periapsis_altitude > 8000
            and orbit.eccentricity < 0.1, (orbit.periapsis_altitude, orbit.eccentricity))
    c.pin('eng', 'sas', 1)
    c.sas_mode('stability')
    c.log(f'stage Δv {c.text("eng", "disp_dv")}, food {c.text("sys", "disp_ls_food")} h, EC {c.text("sys", "disp_ec")}')
    c.save('loi')


def station_to(c, station):
    """Turn STATION to 'cm' or 'lm'; wait for the blackout and the power-up; True once that capsule has the controls."""
    lamp = f'lamp_stn_{station}'
    before = (c.text('sys', 'disp_cm_crew'), c.text('sys', 'disp_lm_crew'))
    c.pin('sys', 'station', 0 if station == 'cm' else 1)
    blinked = c.wait(lambda: c.out('sys', 'led_xfer').get('blink'), 5)
    ok = c.wait(lambda: c.lit('sys', lamp) and not c.out('sys', 'led_xfer').get('on'), 40)
    time.sleep(3)
    c.log(f'STATION {station.upper()}: TRANSFER blinked {blinked}; crew CM {before[0]}→{c.text("sys", "disp_cm_crew")}, '
          f'LM {before[1]}→{c.text("sys", "disp_lm_crew")}; flying {c.tlm("vessel").get("name")!r}')
    return ok


def undock_lm():
    """In Mun orbit: STATION to LM (the crew goes across), UNDOCK, back away, light the Terrier (STAGE)."""
    c = Cockpit('undock')
    c.load('loi')
    c.check('TUNNEL lit while docked', c.lit('sys', 'lamp_tunnel'), c.out('sys', 'lamp_tunnel'))
    c.check('STATION LM: controls in the lander', station_to(c, 'lm'), c.out('sys', 'lamp_stn_lm'))
    c.check('the crew went across', c.text('sys', 'disp_lm_crew') not in (None, '0'), c.text('sys', 'disp_lm_crew'))
    c.log(f'before undocking: NEXT STAGE {c.next_stage()} at stage {c.text("eng", "disp_stage")}')
    c.pin('eng', 'sas', 1)
    c.sas_mode('stability')
    mass = c.tlm('vessel').get('mass')
    c.pin('rdv', 'undock_arm', 1)
    c.press('rdv', 'undock')
    c.check('UNDOCK: the lander is on its own', c.wait(lambda: c.tlm('vessel').get('mass', mass) < mass * 0.5, 15),
            c.tlm('vessel').get('mass'))
    c.pin('rdv', 'undock_arm', 0)
    time.sleep(3)
    c.log(f'lander: {c.tlm("vessel").get("name")!r} {c.tlm("vessel").get("mass", 0) / 1e3:.2f} t, STATION LM '
          f'{c.lit("sys", "lamp_stn_lm")}, TUNNEL {c.lit("sys", "lamp_tunnel")}, DOCKED {c.lit("rdv", "lamp_docked")}')
    # back away a little on RCS, then the Terrier
    c.pin('eng', 'rcs', 1)
    c.stick('trans_fwd', -1.0); time.sleep(3); c.stick('trans_fwd', 0.0)
    c.pin('eng', 'rcs', 0)
    if 'ENGINES' in c.next_stage():
        c.stage(c.next_stage(), 'the lander\'s Terrier')
    c.check('the Terrier is lit (white on the matrix)', 'w' in ''.join(c.out('eng', 'mx_eng').get('rows', [])),
            c.out('eng', 'mx_eng'))
    c.log(f'lander stage Δv {c.text("eng", "disp_dv")}, HOVER TIME {c.text("eng", "disp_hover")} s, '
          f'RCS ΔV {c.text("sys", "disp_rcs_dv")}, EC {c.text("sys", "disp_ec")} ({c.text("sys", "disp_ec_rate")}/s)')
    c.wait(lambda: (c.num('rdv', 'disp_range') or 0) > 200 or True, 1)
    c.save('lm-undocked')


def land():
    """Brake out of orbit on SAS RETRO (SPEED REF SURF), fall, final burn from the FLIGHT DATA · LANDING figures."""
    c = Cockpit('land')
    c.load('lm-undocked')
    c.pin('eng', 'alt_ref', 1)                       # ALT above the ground
    c.pin('eng', 'speed_ref', SPEED_REF['orbit']); c.pin('eng', 'speed_ref', SPEED_REF['surface'])
    c.check('SPEED REF SURF taken (LED steady)', c.wait(lambda: c.out('eng', 'led_speed_ref') == {'on': True, 'blink': False}
                                                       and c.tlm('vessel').get('speed_mode') == 'surface', 8),
            (c.out('eng', 'led_speed_ref'), c.tlm('vessel').get('speed_mode')))
    c.pin('eng', 'sas', 1)
    if not c.sas_mode('retrograde', 30):
        raise Abort('SAS RETRO not taken')
    c.wait(lambda: abs(c.num('eng', 'disp_att_pitch') - (c.tlm('attitude').get('prograde') or {}).get('pitch', 0) * -1) < 99, 1)
    time.sleep(20)                                  # let SAS settle on the marker
    c.log(f'on retrograde: ALT {c.text("eng", "disp_alt")} m, H/S {c.text("eng", "disp_hs")}, V/S {c.text("eng", "disp_vs")}, '
          f'HOVER {c.text("eng", "disp_hover")} s, stage Δv {c.text("eng", "disp_dv")}')
    # braking burn: kill the horizontal speed (the burn computer is not used: the target is a speed, not a Δv)
    c.pin('eng', 'eng_arm', 1)
    c.pin('eng', 'throttle', 1.0)
    start_dv = c.num('eng', 'disp_dv')
    c.wait(lambda: (c.num('eng', 'disp_hs') or 999) < 25 or (c.num('eng', 'disp_vs') or 0) < -60, 300, step=0.05)
    c.pin('eng', 'throttle', 0.0)
    c.log(f'braked: H/S {c.text("eng", "disp_hs")}, V/S {c.text("eng", "disp_vs")}, ALT {c.text("eng", "disp_alt")} m, '
          f'Δv used {start_dv - (c.num("eng", "disp_dv") or 0):.0f} m/s')
    c.pin('eng', 'gear', 1)
    c.check('GEAR: legs down, LED steady', c.wait(lambda: c.out('eng', 'led_gear') == {'on': True, 'blink': False}, 10),
            c.out('eng', 'led_gear'))
    c.stand_in('available deceleration (thrust/mass) read from tlm/vessel: with the engine off the panels show TWR 0')

    def braking_height():
        craft = c.tlm('vessel')
        orbit = c.tlm('orbit')
        alt_sea = c.tlm('flight').get('alt', 0)
        g = orbit.get('mu', 6.5138398e10) / (orbit.get('radius', 200000.0) + alt_sea) ** 2
        decel = (craft.get('thrust_avail') or 0) / craft['mass'] - g
        speed = math.hypot(c.num('eng', 'disp_vs') or 0, c.num('eng', 'disp_hs') or 0)
        return speed ** 2 / (2 * decel) if decel > 0 else float('inf')

    next_note = 0
    while (c.num('eng', 'disp_alt') or 1e9) > 1.25 * braking_height() + 50:
        if time.time() > next_note:
            c.log(f'  falling: ALT {c.text("eng", "disp_alt")} m, V/S {c.text("eng", "disp_vs")}, H/S {c.text("eng", "disp_hs")}, '
                  f'IMPACT {c.text("eng", "disp_impact")} s, braking height {braking_height():.0f} m')
            next_note = time.time() + 10
        time.sleep(0.05)
    c.log(f'final braking from ALT {c.text("eng", "disp_alt")} m at V/S {c.text("eng", "disp_vs")}')
    c.pin('eng', 'throttle', 1.0, settle=0.0)
    c.wait(lambda: abs(c.num('eng', 'disp_vs') or 99) < 8 or (c.num('eng', 'disp_alt') or 0) < 15, 120, step=0.05)
    # descent on V/S: aim for −alt/8, at least −1.5 m/s, with a throttle around the hover
    hover_start = (c.met(), c.num('eng', 'disp_hover'))
    touchdown_vs, deadline = None, time.time() + 300
    while time.time() < deadline:
        if c.lit('eng', 'lamp_contact') or c.tlm('vessel').get('situation') == 'landed':
            break
        alt, vs = c.num('eng', 'disp_alt'), c.num('eng', 'disp_vs')
        craft, orbit = c.tlm('vessel'), c.tlm('orbit')
        if alt is None or vs is None:
            time.sleep(0.05); continue
        touchdown_vs = vs
        g = orbit.get('mu', 6.5138398e10) / (orbit.get('radius', 200000.0) + c.tlm('flight').get('alt', 0)) ** 2
        hover = g * craft['mass'] / max(craft.get('thrust_avail') or 1.0, 1.0)
        wanted = -max(1.5, min(15.0, alt / 8.0))
        c.pin('eng', 'throttle', round(max(0.0, min(1.0, hover + 0.1 * (wanted - vs))), 3), settle=0.0)
        if time.time() > next_note:
            c.log(f'  descent: ALT {alt:.0f} V/S {vs:+.1f} H/S {c.text("eng", "disp_hs")} DRIFT {c.text("eng", "disp_drift_right")}/'
                  f'{c.text("eng", "disp_drift_up")} lamps SINK {c.lit("eng", "lamp_td_sink")} DRIFT {c.lit("eng", "lamp_td_drift")} '
                  f'UPRIGHT {c.lit("eng", "lamp_td_upright")} GEAR {c.lit("eng", "lamp_td_gear")} HOVER {c.text("eng", "disp_hover")}')
            next_note = time.time() + 5
        time.sleep(0.08)
    c.pin('eng', 'throttle', 0.0)
    c.pin('eng', 'eng_arm', 0)
    c.sas_mode('stability')
    time.sleep(8)
    craft = c.tlm('vessel')
    c.log(f'TOUCHDOWN at V/S {touchdown_vs} m/s; situation {craft.get("situation")}, CONTACT {c.lit("eng", "lamp_contact")}, '
          f'pitch {c.text("eng", "disp_att_pitch")}, at {c.text("solo", "disp_lat")}° {c.text("solo", "disp_lon")}° '
          f'({c.text("sci", "txt_biome")}), stage Δv left {c.text("eng", "disp_dv")} m/s')
    c.check('landed, upright, slower than 3 m/s', craft.get('situation') == 'landed' and (touchdown_vs or -99) > -3
            and (c.num('eng', 'disp_att_pitch') or 0) > 70, (craft.get('situation'), touchdown_vs, c.text('eng', 'disp_att_pitch')))
    crew = [k.name for k in c.sc.active_vessel.crew]
    c.log(f'crew aboard: {crew}')
    # a crew report from the surface (SCIENCE)
    for _ in range(10):
        if c.text('sci', 'txt_sci') == 'CREW REPORT':
            break
        c.press('sci', 'sci_next')
    c.press('sci', 'sci_run')
    time.sleep(3)
    c.log(f'SCIENCE: {c.text("sci", "txt_sci")} in {c.text("sci", "txt_biome")}: data {c.lit("sci", "led_sci_data")}, '
          f'value {c.text("sci", "disp_sci_value")}')
    c.save('landed')


def phase_ahead_deg(sc, chaser, target):
    """Angle the target leads the chaser by, around the body, in the target's orbit plane (−180..180)."""
    frame = target.orbit.body.non_rotating_reference_frame
    p_t, v_t = target.position(frame), target.velocity(frame)
    p_c = chaser.position(frame)
    normal = [p_t[1] * v_t[2] - p_t[2] * v_t[1], p_t[2] * v_t[0] - p_t[0] * v_t[2], p_t[0] * v_t[1] - p_t[1] * v_t[0]]
    dot = lambda a, b: sum(x * y for x, y in zip(a, b))
    n_len = math.sqrt(dot(normal, normal))
    normal = [x / n_len for x in normal]
    p_c = [x - dot(p_c, normal) * n for x, n in zip(p_c, normal)]      # into the target's plane
    cross = [p_c[1] * p_t[2] - p_c[2] * p_t[1], p_c[2] * p_t[0] - p_c[0] * p_t[2], p_c[0] * p_t[1] - p_c[1] * p_t[0]]
    return math.degrees(math.atan2(dot(cross, normal), dot(p_c, p_t)))


def target_csm(c):
    for _ in range(6):
        c.press('rdv', 'tgt_next')
        time.sleep(1.0)
        if c.sc.target_vessel is not None and any(p.name == 'mk1-3pod' for p in c.sc.target_vessel.parts.all):
            break
    c.log(f'TARGET {c.text("rdv", "txt_tgt")!r}, RANGE {c.text("rdv", "disp_range")} (KM {c.lit("rdv", "led_km")})')
    return c.sc.target_vessel


def mun_ascent():
    """Liftoff timed on the CSM, ATTITUDE HOLD into its plane, cutoff on APO 20 km, SOLO CIRC."""
    c = Cockpit('mun-ascent')
    c.load(LANDED_SAVE)
    c.pin('eng', 'rcs', 1)          # the M.E.M. has no reaction wheel
    lm = c.sc.active_vessel
    csm = target_csm(c)
    if csm is None:
        raise Abort('the CSM cannot be targeted from the surface')
    c.stand_in('liftoff timing: the CSM\'s phase angle from kRPC (the panels give range only)')
    wanted_phase = -8.0
    if WAIT_FOR_CSM and abs(phase_ahead_deg(c.sc, lm, csm) - wanted_phase) > 3:
        c.log(f'waiting for the CSM: phase {phase_ahead_deg(c.sc, lm, csm):.1f}°, liftoff at {wanted_phase}°')
        for _ in range(3):
            c.press('sys', 'warp_up')
        while True:
            phase = phase_ahead_deg(c.sc, lm, csm)
            gap_deg = (phase - wanted_phase) % 360           # degrees still to go (the CSM is coming round)
            gap_deg = 360 - gap_deg if gap_deg > 180 and False else gap_deg
            if c.tlm('time').get('warp', 1) > 1 and (wanted_phase - phase) % 360 < 25:
                c.press('sys', 'warp_stop')
            if abs(((phase - wanted_phase) + 180) % 360 - 180) < 1.0:
                break
            if c.tlm('time').get('warp', 1) <= 1 and (wanted_phase - phase) % 360 > 30:
                for _ in range(3):
                    c.press('sys', 'warp_up')
            time.sleep(0.5)
        c.press('sys', 'warp_stop')
        c.wait(lambda: c.tlm('time').get('warp', 1) <= 1, 20)
    orbit = c.tlm('target').get('orbit') or {}
    incl = orbit.get('i', 0.0)
    lat = c.num('solo', 'disp_lat') or 0.0
    c.stand_in('launch azimuth from the target\'s inclination on tlm/target (not on a panel)')
    heading = math.degrees(math.asin(max(-1.0, min(1.0, math.cos(math.radians(incl)) / math.cos(math.radians(lat)))))) % 360
    c.log(f'LIFTOFF window: CSM phase {phase_ahead_deg(c.sc, lm, csm):.1f}°, CSM i {incl:.1f}°, lat {lat}°, heading {heading:.0f}°')
    c.pin('eng', 'sas', 0)
    c.hold(90, heading)
    c.pin('eng', 'hold', 1)
    c.pin('eng', 'thrust_lim', 1.0)
    c.pin('eng', 'alt_ref', 1)                       # ALT above the ground for the liftoff
    c.pin('eng', 'eng_arm', 1)
    c.pin('eng', 'throttle', 1.0)
    c.check('liftoff from the Mun', c.wait(lambda: (c.num('eng', 'disp_vs') or 0) > 3, 15), c.text('eng', 'disp_vs'))
    c.pin('eng', 'gear', 0)
    c.pin('eng', 'alt_ref', 0)                       # ALT above the sea for the climb
    c.pin('eng', 'speed_ref', SPEED_REF['target']); c.pin('eng', 'speed_ref', SPEED_REF['orbit'])
    orbit = c.tlm('orbit')
    mu, radius = orbit.get('mu', 6.5138398e10), orbit.get('radius', 200000.0)
    site_alt = c.tlm('flight').get('alt', 0) - c.tlm('flight').get('radar', 0)
    target_alt = site_alt + 7500.0 if site_alt + 7500 > LM_ORBIT_KM * 1000 - 1000 else LM_ORBIT_KM * 1000 - 1000
    c.log(f'direct ascent: site at {site_alt:.0f} m, climb towards {target_alt:.0f} m, burn until PERI >= {LM_ORBIT_KM - 2.5} km')
    next_note, dark_since, burned_out = 0, None, False
    while True:
        radar = c.tlm('flight').get('radar', 0)          # (terrain clearance: stand-in, ALT shows the sea height)
        vs, hs, twr = c.num('eng', 'disp_vs'), c.num('eng', 'disp_hs'), c.num('eng', 'disp_twr')
        if twr is not None and twr <= 0 and radar > 200:
            dark_since = dark_since or time.time()
            if time.time() - dark_since > 1.5:
                c.log(f'burnout (TWR 0): {c.orbit_text()}')
                burned_out = True
                break
            time.sleep(0.1); continue
        dark_since = None
        if None in (vs, hs, twr) or twr <= 0:
            time.sleep(0.1); continue
        alt = c.num('eng', 'disp_alt') or 0              # ALT REF on SEA: the true height
        g = mu / (radius + alt) ** 2
        wanted_vs = max(-15.0, min(60.0, (target_alt - alt) / 25.0))
        if radar < 1500:
            wanted_vs = max(wanted_vs, 10.0 if radar > 100 else 40.0)
        lift = (g - hs * hs / (radius + alt) + 0.3 * (wanted_vs - vs)) / (twr * g)
        pitch = 90.0 if radar < 60 else math.degrees(math.asin(max(-0.2, min(1.0, lift))))
        c.hold(pitch, heading)
        peri, apo = c.num('solo', 'disp_peri'), c.num('solo', 'disp_apo')
        if peri is not None and peri >= LM_ORBIT_KM - 2.5:
            break
        if apo is not None and apo >= LM_ORBIT_KM + 8:
            c.log(f'APO past {LM_ORBIT_KM + 8:.0f} km: cutoff, circularise at the apoapsis')
            break
        if c.lit('eng', 'cw_flameout') or (c.num('eng', 'disp_dv') or 1) <= 0:
            c.problem(f'the LM ran dry on the climb: {c.orbit_text()}')
            break
        if time.time() > next_note:
            c.log(f'  climb: ALT {radar:.0f} m (ground), V/S {vs:+.1f} (want {wanted_vs:+.0f}), H/S {hs:.0f}, TWR {twr}, '
                  f'pitch {c.text("eng", "disp_att_pitch")} (hold {pitch:.0f}), {c.orbit_text()}, stage Δv {c.text("eng", "disp_dv")}')
            next_note = time.time() + 4
        time.sleep(0.1)
    c.press('eng', 'eng_cutoff')
    c.pin('eng', 'throttle', 0.0)
    c.pin('eng', 'thrust_lim', 1.0)
    c.hold(0, heading)
    time.sleep(2)
    c.log(f'cutoff: {c.orbit_text()}, stage Δv {c.text("eng", "disp_dv")}')
    c.pin('eng', 'hold', 0)
    c.pin('eng', 'sas', 1)
    c.sas_mode('prograde')
    if burned_out and (c.num('solo', 'disp_peri') or -999) < LM_ORBIT_KM - 3:
        # out of propellant short of orbit: the RCS, forward along the nose on SAS PRO, at the apoapsis
        c.log(f'short of orbit: {c.orbit_text()}, RCS ΔV {c.text("sys", "disp_rcs_dv")}; coasting to APO')
        time.sleep(15)
        if (c.num('solo', 'disp_apo') or 1e9) < 100:
            c.warp_to_event('APO', 70, timeout=1800)
        else:
            c.problem('apoapsis beyond 100 km after the ascent: no warp')
            raise Abort('ascent overshot')
        c.wait(lambda: (c.event_in() or 0) < 40, 120)
        c.pin('eng', 'rcs', 1)
        c.stick('trans_fwd', 1.0)
        ok = c.wait(lambda: (c.num('solo', 'disp_peri') or -999) >= LM_ORBIT_KM - 3.5 or
                    (c.num('sys', 'disp_rcs_dv') or 0) <= 0.5, 600)
        c.stick('trans_fwd', 0.0)
        c.pin('eng', 'rcs', 0)
        c.log(f'after the RCS burn: {c.orbit_text()}, RCS ΔV {c.text("sys", "disp_rcs_dv")}')
        c.check('LM in orbit on its RCS', (c.num('solo', 'disp_peri') or -999) > 7.5, c.orbit_text())
        c.save('lm-orbit')
        return
    status = c.request_pad('fd_circ')
    c.check('CIRC PAD after the Mun ascent', status.get('ok'), status)
    c.fly_pad(on_flameout=no_staging(c))
    c.log(f'LM orbit: {c.orbit_text()}, stage Δv {c.text("eng", "disp_dv")}')
    c.save('lm-orbit')


def rendezvous(load=True):
    """SOLO PLANE and RDV TGT towards the CSM, then the terminal phase on the RDV panel to about 100 m."""
    c = Cockpit('rdv')
    if load:
        c.load('lm-orbit')
        time.sleep(15)
    c.pin('eng', 'rcs', 1)          # the M.E.M. has no reaction wheel
    csm = target_csm(c)
    status = c.request_pad('fd_plane')
    if status.get('ok') and 'PLANE' in status.get('text', ''):
        pad = c.seen.get('pad/uplink', {})
        if pad and math.hypot(*pad.get('dv', [0, 0, 0])) > 1.0:
            c.fly_pad(on_flameout=no_staging(c))
        else:
            c.press('cmp', 'pad_clr')
            c.log('plane change under 1 m/s: skipped')
    status = c.request_pad('fd_rdv')
    c.check('RDV TGT PAD', status.get('ok'), status)
    if not status.get('ok'):
        raise Abort(f'no rendezvous PAD: {status}')
    c.fly_pad(on_flameout=no_staging(c))
    approach = min(each.distance for each in c.sc.active_vessel.orbit.closest_approaches(csm.orbit, 1)) \
        if hasattr(c.sc.active_vessel.orbit, 'closest_approaches') else None
    c.log(f'after the transfer burn: RANGE {c.text("rdv", "disp_range")} KM {c.lit("rdv", "led_km")}, closest approach {approach}')
    c.save('rdv-transfer')
    terminal_phase(c)
    c.save('rdv-near')


def range_m(c):
    shown = c.num('rdv', 'disp_range')
    if shown is None:
        return None
    return shown * 1000 if c.lit('rdv', 'led_km') else shown


def terminal_phase(c, stop_at=120.0):
    """Kill the relative speed (SAS RETRO on SPEED REF TGT), point at the CSM (SAS TGT), burn towards it at
    about range/200, coast; again, until within stop_at metres and nearly still."""
    c.pin('eng', 'speed_ref', SPEED_REF['orbit']); c.pin('eng', 'speed_ref', SPEED_REF['target'])
    c.wait(lambda: c.tlm('vessel').get('speed_mode') == 'target', 8)
    c.stand_in('relative speed (not only the closing component) read from tlm/target rel_v: not on the RDV panel')
    c.pin('eng', 'eng_arm', 1)

    def burn_until(done, limit, timeout=120):
        c.pin('eng', 'thrust_lim', limit)
        c.pin('eng', 'throttle', 1.0, settle=0.0)
        c.wait(done, timeout, step=0.05)
        c.pin('eng', 'throttle', 0.0)

    # wait until close enough that the closing speed matters: time to go under 3 minutes
    while True:
        rng, closing = range_m(c), c.num('rdv', 'disp_closing') or 0
        if rng is None:
            time.sleep(1); continue
        if rng < 3000 or (closing > 0 and rng / closing < 180):
            break
        if c.tlm('time').get('warp', 1) <= 1 and (closing <= 0 or rng / closing > 600):
            c.press('sys', 'warp_up'); c.press('sys', 'warp_up')
        elif c.tlm('time').get('warp', 1) > 1 and closing > 0 and rng / closing < 400:
            c.press('sys', 'warp_stop')
        time.sleep(1)
    c.press('sys', 'warp_stop')
    for leg in range(25):
        rng = range_m(c)
        rel = c.tlm('target').get('rel_v', 0)
        c.log(f'  terminal {leg}: RANGE {rng:.0f} m, CLOSING {c.text("rdv", "disp_closing")}, rel speed {rel:.2f} m/s')
        if rng < stop_at and rel < 0.3:
            break
        # 1. kill the relative speed
        if rel > 0.3:
            c.sas_mode('retrograde', 30)
            time.sleep(12)
            burn_until(lambda: c.tlm('target').get('rel_v', 99) < 0.2, 0.05 if rel < 15 else 0.3)
        if rng < stop_at:
            continue
        # 2. towards the target at range/200 (at most 20 m/s), then coast to a tenth of the range left
        c.sas_mode('target', 30)
        time.sleep(12)
        wanted = max(0.8, min(20.0, rng / 200.0))
        burn_until(lambda: (c.num('rdv', 'disp_closing') or 0) >= wanted, 0.05 if wanted < 5 else 0.3)
        c.wait(lambda: (range_m(c) or 0) < max(stop_at * 0.8, rng * 0.25), 900)
    c.pin('eng', 'thrust_lim', 1.0)
    c.pin('eng', 'eng_arm', 0)
    c.sas_mode('stability')
    c.log(f'station keeping: RANGE {c.text("rdv", "disp_range")} m, CLOSING {c.text("rdv", "disp_closing")}, '
          f'stage Δv {c.text("eng", "disp_dv")}, RCS ΔV {c.text("sys", "disp_rcs_dv")}')


def land_efficient(start='lm-undocked'):
    """DOI keyed on the burn computer (periapsis ~8 km), then a powered descent braking near the ground:
    ATTITUDE HOLD retrograde, pitch from the vertical balance; vertical descent once H/S is small.
    start='lm-doi': from the save after the DOI."""
    c = Cockpit('land2')
    c.load(start)
    time.sleep(20)                  # the first seconds after a load lose panel inputs (seen on the keypad)
    c.pin('eng', 'rcs', 1)          # the M.E.M. has no reaction wheel: no RCS, no torque (SAS and HOLD cannot turn it)
    orbit = c.tlm('orbit')
    mu, radius = orbit.get('mu', 6.5138398e10), orbit.get('radius', 200000.0)
    if start == 'lm-undocked':
        doi(c, mu, radius)
    descend(c, mu, radius)


def doi(c, mu, radius):
    apo, peri = c.num('solo', 'disp_apo'), c.num('solo', 'disp_peri')
    r_here = radius + 1000 * (apo + peri) / 2
    v_circ = math.sqrt(mu / r_here)
    r_low = radius + 8000.0
    v_after = math.sqrt(mu * (2 / r_here - 2 / (r_here + r_low)))
    dv = v_after - v_circ
    tig = c.met() + 150
    c.log(f'DOI by hand: {c.orbit_text()}, Δv {dv:.1f} m/s retrograde at MET {tig:.0f}')
    c.press('cmp', 'pad_clr')
    c.key_pad(tig, dv)
    c.check('DOI PAD keyed (ERR lamp dark)', not c.lit('cmp', 'lamp_err') and abs((c.num('cmp', 'disp_pro') or 0) - round(dv, 1)) < 0.15,
            (c.text('cmp', 'disp_pro'), c.lit('cmp', 'lamp_err')))
    if 'ENGINES' in c.next_stage():
        c.stage(c.next_stage(), 'the Terrier')
    c.fly_pad(accept=False, on_flameout=no_staging(c))
    time.sleep(2)
    c.log(f'after DOI: {c.orbit_text()}, T PERI {c.text("solo", "disp_t_peri")}')
    c.save('lm-doi')


def descend(c, mu, radius):
    # ---- coast to the periapsis
    c.pin('eng', 'eng_arm', 0)
    c.pin('eng', 'alt_ref', 1)
    c.pin('eng', 'speed_ref', SPEED_REF['orbit']); c.pin('eng', 'speed_ref', SPEED_REF['surface'])
    c.warp_to_event('PERI', 100, timeout=3600)
    c.pin('eng', 'gear', 1)
    c.wait(lambda: (c.event_in() or 0) < 25 or (c.num('eng', 'disp_alt') or 1e9) < 5000, 200)
    # ---- powered descent: thrust retrograde, pitch from the vertical balance
    c.stand_in('braking heading: retrograde from the prograde marker on tlm/attitude')
    c.pin('eng', 'sas', 0)
    prograde = c.tlm('attitude').get('prograde') or {}
    heading = (prograde.get('heading', 90.0) + 180.0) % 360
    c.hold(0, heading)
    c.pin('eng', 'hold', 1)
    time.sleep(6)
    c.pin('eng', 'eng_arm', 1)
    c.pin('eng', 'throttle', 1.0)
    c.log(f'PDI: ALT {c.text("eng", "disp_alt")} m, H/S {c.text("eng", "disp_hs")}, V/S {c.text("eng", "disp_vs")}, heading {heading:.0f}')
    next_note = 0
    while True:
        radar = c.num('eng', 'disp_alt') or 0
        vs, hs, twr = c.num('eng', 'disp_vs'), c.num('eng', 'disp_hs'), c.num('eng', 'disp_twr')
        if None in (vs, hs, twr) or twr <= 0:
            time.sleep(0.1); continue
        if hs < 15:
            break
        alt = c.tlm('flight').get('alt', 0)
        g = mu / (radius + alt) ** 2
        wanted_vs = -max(2.0, min(40.0, radar / 60.0))
        lift = (g - hs * hs / (radius + alt) + 0.4 * (wanted_vs - vs)) / (twr * g)
        pitch = math.degrees(math.asin(max(-0.3, min(1.0, lift))))
        prograde = c.tlm('attitude').get('prograde') or {}
        if prograde.get('heading') is not None:
            heading = (prograde['heading'] + 180.0) % 360
        c.hold(pitch, heading)
        if time.time() > next_note:
            c.log(f'  braking: ALT {radar:.0f} m, V/S {vs:+.1f} (want {wanted_vs:+.0f}), H/S {hs:.0f}, pitch {c.text("eng", "disp_att_pitch")} '
                  f'(hold {pitch:.0f}), HOVER {c.text("eng", "disp_hover")} s, IMPACT {c.text("eng", "disp_impact")}')
            next_note = time.time() + 4
        if radar < 150 and vs < -8:
            c.problem('too low and sinking during the braking: going vertical')
            break
        time.sleep(0.1)
    # ---- vertical: SAS RETRO (surface), throttle on V/S
    c.pin('eng', 'hold', 0)
    c.pin('eng', 'sas', 1)
    c.sas_mode('retrograde', 10)
    c.log(f'vertical: ALT {c.text("eng", "disp_alt")} m, H/S {c.text("eng", "disp_hs")}, V/S {c.text("eng", "disp_vs")}')
    # free fall, then full thrust from 1.3 times the stopping height (hovering costs 1.63 m/s every second)
    c.pin('eng', 'throttle', 0.0)

    def stopping_height():
        craft = c.tlm('vessel')
        g = mu / (radius + c.tlm('flight').get('alt', 0)) ** 2
        decel = (craft.get('thrust_avail') or 0) / craft['mass'] - g
        speed = abs(c.num('eng', 'disp_vs') or 0)
        return speed * speed / (2 * decel) if decel > 0 else float('inf')

    c.wait(lambda: (c.num('eng', 'disp_alt') or 1e9) <= 1.3 * stopping_height() + 60, 600, step=0.05)
    c.log(f'suicide burn from ALT {c.text("eng", "disp_alt")} m at V/S {c.text("eng", "disp_vs")} (stopping height {stopping_height():.0f} m)')
    c.pin('eng', 'throttle', 1.0, settle=0.0)
    c.wait(lambda: abs(c.num('eng', 'disp_vs') or 99) < 6 or (c.num('eng', 'disp_alt') or 0) < 30, 120, step=0.05)
    touchdown_vs = None
    deadline = time.time() + 60 + (c.num('eng', 'disp_alt') or 3000) / 1.5    # never cut the engine in the air
    while True:
        if time.time() > deadline:
            c.problem(f'vertical descent slower than planned: ALT {c.text("eng", "disp_alt")}, still descending')
            deadline = time.time() + 120
        if c.lit('eng', 'lamp_contact') or c.tlm('vessel').get('situation') == 'landed':
            break
        alt, vs = c.num('eng', 'disp_alt'), c.num('eng', 'disp_vs')
        craft = c.tlm('vessel')
        if alt is None or vs is None:
            time.sleep(0.05); continue
        touchdown_vs = vs
        g = mu / (radius + c.tlm('flight').get('alt', 0)) ** 2
        hover = g * craft['mass'] / max(craft.get('thrust_avail') or 1.0, 1.0)
        wanted = -max(1.5, min(10.0, alt / 8.0))
        c.pin('eng', 'throttle', round(max(0.0, min(1.0, hover + 0.1 * (wanted - vs))), 3), settle=0.0)
        if time.time() > next_note:
            c.log(f'  descent: ALT {alt:.0f} V/S {vs:+.1f} H/S {c.text("eng", "disp_hs")} lamps SINK {c.lit("eng", "lamp_td_sink")} '
                  f'DRIFT {c.lit("eng", "lamp_td_drift")} UPRIGHT {c.lit("eng", "lamp_td_upright")} GEAR {c.lit("eng", "lamp_td_gear")}')
            next_note = time.time() + 4
        time.sleep(0.08)
    c.pin('eng', 'throttle', 0.0)
    c.pin('eng', 'eng_arm', 0)
    c.sas_mode('stability')
    time.sleep(8)
    craft = c.sc.active_vessel
    lf = craft.resources.amount('LiquidFuel')
    c.log(f'TOUCHDOWN at V/S {touchdown_vs}; {craft.situation.name}, pitch {c.text("eng", "disp_att_pitch")}, '
          f'at {c.text("solo", "disp_lat")}° {c.text("solo", "disp_lon")}° ({c.text("sci", "txt_biome")}), LF {lf:.1f}, '
          f'stage Δv {c.text("eng", "disp_dv")}')
    c.check('landed, upright, slower than 3 m/s', craft.situation.name == 'landed' and (touchdown_vs or -99) > -3, (craft.situation.name, touchdown_vs))
    c.save('landed2')


if __name__ == '__main__':
    run({'launch': launch, 'tmi': tmi, 'td': td, 'td_dock': td_dock, 'mcc': mcc, 'loi': loi, 'undock': undock_lm, 'land': land, 'land2': land_efficient, 'pdi': lambda: land_efficient('lm-doi'), 'mun_ascent': mun_ascent, 'rdv': rendezvous, 'rdv_here': lambda: rendezvous(load=False)}, sys.argv)
