"""Coast home and re-enter (TM-18): warp out of the Mun's SOI and down to 90 km, drop the Poodle stage, hold the heat
shield forward (SAS retrograde, surface), deploy the parachute below 5 km under 280 m/s, wait for splashdown.

    .venv/bin/python selftest/flight/entry.py
"""
import json, math, os, time
from common import Kio, Log, DATA, save, warp_to


def main():
    log = Log('entry')
    k = Kio('entry')
    sc = k.sc
    v = sc.active_vessel
    if v.orbit.body.name == 'Mun':
        warp_to(k, sc.ut + v.orbit.time_to_soi_change + 30, log)
        time.sleep(2)
    o = v.orbit
    kerbin = o.body
    log(f'{kerbin.name} orbit: periapsis {o.periapsis_altitude:.0f} m in {o.time_to_periapsis:.0f} s, e {o.eccentricity:.4f}, '
        f'i {math.degrees(o.inclination):.2f}°')
    save(k, 'selftest-kerbin-soi', log)
    nrf = kerbin.non_rotating_reference_frame
    R = kerbin.equatorial_radius
    # time when the altitude falls through 90 km (bisection on the predicted path, before periapsis)
    t_p = sc.ut + o.time_to_periapsis
    alt_at = lambda t: math.sqrt(sum(x * x for x in o.position_at(t, nrf))) - R
    lo, hi = sc.ut, t_p
    for _ in range(60):
        mid = (lo + hi) / 2
        if alt_at(mid) > 90000:
            lo = mid
        else:
            hi = mid
    warp_to(k, lo, log)
    time.sleep(1)
    ctl = v.control
    # drop the service stage: the decoupler next to the heat shield (explicit: on Mun LOR the TD-25 and the chute share
    # a stage, so staging would open the chute at 90 km); fall back to staging (Kerbal X: the Poodle stage)
    sep = [p for p in v.parts.all if p.decoupler is not None and not p.decoupler.decoupled and
           any(q is not None and q.title.startswith('Heat Shield') for q in [p.parent, *p.children])]
    if sep:
        sep[0].decoupler.decouple()
        log(f'service stage dropped ({sep[0].title})')
    else:
        ctl.activate_next_stage()
    time.sleep(1)
    v = sc.active_vessel
    ctl = v.control
    log(f'Poodle stage dropped: mass {v.mass / 1e3:.3f} t, stage {ctl.current_stage}')
    ctl.sas = True
    time.sleep(0.2)
    ctl.speed_mode = sc.SpeedMode.surface
    ctl.sas_mode = sc.SASMode.retrograde
    fl = v.flight(kerbin.reference_frame)
    alt, spd, g, temp = k.stream(fl, 'mean_altitude'), k.stream(fl, 'speed'), k.stream(fl, 'g_force'), None
    sit = k.stream(v, 'situation')
    max_g, chute, last_row, t0 = 0.0, False, 0, sc.ut
    while True:
        h, s, gg = alt(), spd(), g()
        max_g = max(max_g, gg)
        now = sc.ut
        if now - last_row >= 1:
            last_row = now
            log.row(t=now - t0, h=h, v=s, g=gg)
        if not chute and h < 5000 and s < 280:
            for p in v.parts.parachutes:
                p.deploy()
            chute = True
            log(f'CHUTE at {h:.0f} m, {s:.0f} m/s; max g so far {max_g:.1f}')
            sc.physics_warp_factor = 3
        if sit().name in ('splashed', 'landed'):
            break
        if h < 2000 and not chute and s > 280:
            log(f'too fast for the chute at {h:.0f} m: {s:.0f} m/s')
        time.sleep(0.1)
    sc.physics_warp_factor = 0
    log(f'SPLASHDOWN/LANDING: situation {v.situation.name}, speed {spd():.1f} m/s, max g {max_g:.1f}, '
        f'lat {fl.latitude:.3f}, lon {fl.longitude:.3f}, crew {[c.name for c in v.crew]}')
    save(k, 'selftest-home', log)
    json.dump({'situation': v.situation.name, 'max_g': max_g, 'lat': fl.latitude, 'lon': fl.longitude},
              open(os.path.join(DATA, 'entry-result.json'), 'w'), indent=1)
    k.close()


if __name__ == '__main__':
    main()
