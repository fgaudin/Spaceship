"""Survey: the Kerbin profile (bodies) and the active vessel's stages, written to selftest/data/.

    .venv/bin/python selftest/survey.py
"""
import json, math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kio import Kio

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
G0 = 9.80665


def body_profile(b):
    d = {
        'name': b.name, 'mu': b.gravitational_parameter, 'R': b.equatorial_radius,
        'rotational_period': b.rotational_period, 'rotational_speed': b.rotational_speed,
        'soi': b.sphere_of_influence if math.isfinite(b.sphere_of_influence) else None, 'mass': b.mass, 'surface_gravity': b.surface_gravity,
        'has_atmosphere': b.has_atmosphere,
    }
    if b.has_atmosphere:
        d['atmosphere_depth'] = b.atmosphere_depth
        # pressure and density profile, for TM-5's scale-height fit
        d['atmosphere'] = [{'h': h, 'p': b.pressure_at(h), 'rho': b.density_at(h)}
                           for h in range(0, int(b.atmosphere_depth) + 1, 2500)]
    o = b.orbit
    if o is not None:
        d['orbit'] = {'parent': o.body.name, 'a': o.semi_major_axis, 'e': o.eccentricity,
                      'i': o.inclination, 'lan': o.longitude_of_ascending_node,
                      'argp': o.argument_of_periapsis, 'M0': o.mean_anomaly_at_epoch, 'epoch': o.epoch,
                      'period': o.period}
    return d


def vessel_profile(v):
    parts = v.parts
    stages = {}
    for p in parts.all:
        s = stages.setdefault(p.decouple_stage, {'parts': [], 'mass': 0.0, 'dry': 0.0})
        s['parts'].append(p.title)
        s['mass'] += p.mass
        s['dry'] += p.dry_mass
    engines = []
    for e in parts.engines:
        p = e.part
        lim = e.thrust_limit                    # the craft's thrust limiter (Kerbal 1-5: Swivel 60 %, Hammers 40 %)
        engines.append({'title': p.title, 'stage': p.stage, 'decouple_stage': p.decouple_stage, 'thrust_limit': lim,
                        'max_thrust_vac': e.max_vacuum_thrust * lim, 'max_thrust_asl': e.kerbin_sea_level_specific_impulse and
                        e.max_vacuum_thrust * lim * e.kerbin_sea_level_specific_impulse / e.vacuum_specific_impulse,
                        'isp_vac': e.vacuum_specific_impulse, 'isp_asl': e.kerbin_sea_level_specific_impulse,
                        'propellants': e.propellant_names, 'throttle_locked': e.throttle_locked})
    return {'name': v.name, 'mass': v.mass, 'dry_mass': v.dry_mass, 'current_stage': v.control.current_stage,
            'crew': [c.name for c in v.crew], 'stages': stages, 'engines': engines,
            'part_count': len(parts.all)}


def main():
    k = Kio('survey')
    sc = k.sc
    os.makedirs(DATA, exist_ok=True)
    bodies = {b.name: body_profile(b) for b in sc.bodies.values()}
    with open(os.path.join(DATA, 'bodies.json'), 'w') as f:
        json.dump(bodies, f, indent=1)
    v = sc.active_vessel
    vp = vessel_profile(v)
    with open(os.path.join(DATA, 'vessel.json'), 'w') as f:
        json.dump(vp, f, indent=1)
    for n in ('Kerbin', 'Mun'):
        b = bodies[n]
        print(f"{n}: mu={b['mu']:.6e} R={b['R']:.0f} Trot={b['rotational_period']:.1f} SOI={b['soi']:.4e}"
              + (f" atm={b['atmosphere_depth']:.0f}" if b['has_atmosphere'] else '')
              + (f" a={b['orbit']['a']:.4e} e={b['orbit']['e']} i={b['orbit']['i']}" if n == 'Mun' else ''))
    print(vp['name'], 'mass', round(vp['mass']), 'parts', vp['part_count'], 'stage', vp['current_stage'])
    k.close()


if __name__ == '__main__':
    main()
