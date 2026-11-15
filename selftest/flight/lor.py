"""Lunar-orbit rendezvous steps that are not burns.

    .venv/bin/python selftest/flight/lor.py undock      # in Mun orbit: lander leaves the orbiter, drops its adapter, engine on
    .venv/bin/python selftest/flight/lor.py crew        # after the return docking: lander crew into the Mk1-3, lander jettisoned

Vessel names: 'Orbiter' (Mk1-3 command module + service module), 'Lander' (Kerbal 1-5 stack with legs).
"""
import sys, time
from common import Kio, Log, save


def ports_between(v):
    """The docked port pair joining the orbiter and the lander: ports whose neighbour across the dock is a port too."""
    out = []
    for d in v.parts.docking_ports:
        if d.state.name == 'docked' and d.docked_part is not None and d.docked_part.docking_port is not None:
            out.append(d)
    return out


def side_of(port):
    """'orbiter' or 'lander': the side of the dock this port is on (search the part tree from it, crossing anything but the
    dock itself; the pods' own port assemblies contain editor-docked pairs, which must be crossed)."""
    partner = port.docked_part
    block = {port.part._object_id, partner._object_id} if partner is not None else {port.part._object_id}
    seen, todo = set(), [port.part]
    while todo:
        p = todo.pop()
        if p._object_id in seen:
            continue
        seen.add(p._object_id)
        if p.title.startswith('Mk1-3'):
            return 'orbiter'
        if p.title.startswith('Mk1 Command Pod'):
            return 'lander'
        for q in [p.parent, *p.children]:
            if q is None:
                continue
            if p._object_id in block and q._object_id in block:
                continue                      # do not cross the dock
            todo.append(q)
    return None


def undock():
    log = Log('lor-undock')
    k = Kio('lor-undock')
    sc = k.sc
    v = sc.active_vessel
    v.control.throttle = 0.0
    pair = ports_between(v)
    lp = [d for d in pair if side_of(d) == 'lander']
    if lp:
        log(f'undocking: {v.name} {v.mass / 1e3:.2f} t, crew {[c.name for c in v.crew]}')
        lp[0].undock()
        time.sleep(1.5)
    else:
        log('already undocked')
    # name by crew module (the vessel undock() returns is not always the new one)
    body = v.orbit.body
    lander = orbiter = None
    for w in sc.vessels:
        if w.orbit.body != body:
            continue
        titles = [p.title for p in w.parts.all if p.crew_capacity]
        if any(t.startswith('Mk1-3') for t in titles):
            orbiter = w
        elif any(t.startswith('Mk1 Command Pod') for t in titles) and w.crew:
            lander = w
    orbiter.name, lander.name = 'Orbiter', 'Lander'
    orbiter.control.sas = True
    orbiter.control.throttle = 0.0
    log(f"orbiter {orbiter.mass / 1e3:.2f} t {[c.name for c in orbiter.crew]}; lander {lander.mass / 1e3:.2f} t {[c.name for c in lander.crew]}")
    sc.active_vessel = lander
    time.sleep(2.0)
    L = sc.active_vessel
    L.control.throttle = 0.0
    # back away a little with RCS before anything else
    L.control.rcs = True
    L.control.forward = -1.0
    time.sleep(2.0)
    L.control.forward = 0.0
    # drop the launch adapter (the lander's bottom TD-12 keeps the adapter side) and light the lander's Terrier
    for p in L.parts.all:
        if p.decoupler is not None and p.title.startswith('TD-12'):
            near = [q for q in [p.parent, *p.children] if q is not None]
            if any(q.title.startswith('Rockomax Brand Adapter') for q in near):
                log('dropping the launch adapter')
                p.decoupler.decouple()
                time.sleep(1.0)
                break
    L = sc.active_vessel
    for e in L.parts.engines:
        e.active = True
    L.control.throttle = 0.0
    L.control.rcs = False
    L.control.sas = True
    log(f"lander: {len(L.parts.all)} parts, {L.mass / 1e3:.3f} t, F {L.available_thrust / 1e3:.0f} kN, "
        f"legs {len(L.parts.legs)}, crew {[c.name for c in L.crew]}")
    save(k, 'lor-undocked', log)
    k.close()


def crew():
    log = Log('lor-crew')
    k = Kio('lor-crew')
    sc = k.sc
    v = sc.active_vessel
    cm = [p for p in v.parts.all if p.title.startswith('Mk1-3')][0]
    pod = [p for p in v.parts.all if p.title.startswith('Mk1 Command Pod')]
    moved = []
    for p in pod:
        for c in list(p.crew):
            sc.transfer_crew(c, cm)
            moved.append(c.name)
            time.sleep(1.0)
    time.sleep(1.0)
    log(f"crew moved into the command module: {moved}; now {[c.name for c in cm.crew]}")
    v.parts.controlling = cm
    pair = ports_between(v)
    lp = [d for d in pair if side_of(d) == 'lander']
    if lp:
        spent = lp[0].undock()
        time.sleep(1.0)
        spent.name = 'Lander (spent)'
        log('lander jettisoned')
    o = sc.active_vessel
    o.name = 'Orbiter'
    o.control.throttle = 0.0
    o.control.sas = True
    log(f"orbiter {o.mass / 1e3:.3f} t, crew {[c.name for c in o.crew]}, F {o.available_thrust / 1e3:.0f} kN")
    save(k, 'lor-crew-home', log)
    k.close()


if __name__ == '__main__':
    {'undock': undock, 'crew': crew}.get(sys.argv[1] if len(sys.argv) > 1 else '', lambda: sys.exit(__doc__))()
