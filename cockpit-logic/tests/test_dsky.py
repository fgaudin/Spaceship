"""DSKY logic, alone and inside the cockpit (P30 → P40 → Δv cutoff on the throttle)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cockpit.dsky import Dsky, reg  # noqa: E402
from cockpit import Cockpit  # noqa: E402

TLM = {'tlm/time': {'met': 3600 + 120.0}, 'tlm/flight': {'alt': 80000.0, 'vs': 1.2, 'speed': 2279.0, 'lat': 0.1, 'lon': -74.5},
       'tlm/orbit': {'apo': 81000.0, 'peri': 79000.0, 't_apo': 754.0}, 'tlm/attitude': {'pitch': 0, 'heading': 90, 'roll': 0}}


def keys(d, seq, now=0.0, tlm=TLM):
    for k in seq.split():
        d.key(k, now, tlm)


def disp(d, now=0.0, tlm=TLM):
    o = d.render(now, tlm)
    return {k: v.get('text') for k, v in o.items() if k.endswith('_disp')}, o


def test_register_format():
    assert reg(123.4, 1) == '+0123.4'
    assert reg(-5.25, 1) == '-0005.2' or reg(-5.25, 1) == '-0005.3'
    assert reg(123456.0, 1) == '+99999'              # five digits: it saturates
    assert reg(None) == ''


def test_v16_n62_monitor_and_v06_freezes():
    d = Dsky()
    keys(d, 'VERB 1 6 NOUN 6 2 ENTR')
    t, _ = disp(d)
    assert (t['dsky_verb_disp'], t['dsky_noun_disp']) == ('16', '62')
    assert t['dsky_r1_disp'] == '+02279' and t['dsky_r3_disp'] == '+0080.0'
    keys(d, 'VERB 0 6 NOUN 6 2 ENTR')
    moved = {**TLM, 'tlm/flight': {**TLM['tlm/flight'], 'speed': 2300.0}}
    t, _ = disp(d, tlm=moved)
    assert t['dsky_r1_disp'] == '+02279'                      # V06: the value at ENTR, not live


def test_bad_verb_lights_opr_err_and_rset_clears():
    d = Dsky()
    keys(d, 'VERB 5 5 ENTR')
    _, o = disp(d)
    assert o['dsky_opr_err']['on'] and o['dsky_opr_err']['blink']
    keys(d, 'RSET')
    _, o = disp(d)
    assert not o['dsky_opr_err']['on']


def test_p30_load_tig_and_dv_then_p40_cutoff():
    d = Dsky()
    keys(d, 'VERB 3 7 ENTR 3 0 ENTR')
    t, o = disp(d)
    assert t['dsky_prog_disp'] == '30' and (t['dsky_verb_disp'], t['dsky_noun_disp']) == ('06', '33')
    assert o['dsky_verb_disp']['blink']                         # flashing: waiting for the crew
    keys(d, 'VERB 2 5 ENTR 1 ENTR 3 ENTR 0 0 0 0 0 ENTR')      # TIG = 1:03:00.00 MET (V25 N33)
    assert d.pad['tig'] == 3780.0
    keys(d, 'PRO')                                             # → V06 N81
    assert d.noun == 81
    keys(d, 'VERB 2 5 ENTR + 2 9 4 ENTR + 0 ENTR + 0 ENTR')   # Δv 29.4 m/s prograde
    assert d.pad['dv'] == [29.4, 0.0, 0.0]
    keys(d, 'PRO PRO')                                         # N81 → N42 → done
    assert d.prog == 0
    keys(d, 'VERB 3 7 ENTR 4 0 ENTR')
    assert (d.prog, d.verb, d.noun) == (40, 16, 40)
    # TIG − 4 s: V99 asks for engine enable
    tlm = {**TLM, 'tlm/time': {'met': 3776.0}, 'tlm/vessel': {'mass': 4000.0, 'thrust': 0.0}}
    d.step_time(0.0, tlm)
    assert d.verb == 99 and d.flash
    keys(d, 'PRO', tlm=tlm)
    assert d.enabled and d.verb == 16
    # burn: 6 kN on 4 t = 1.5 m/s² → 29.4 m/s in 19.6 s
    t = 0.0
    burn = {**tlm, 'tlm/vessel': {'mass': 4000.0, 'thrust': 6000.0}}
    while not d.cutoff and t < 30:
        t += 0.1
        d.step_time(t, burn)
    assert d.cutoff and 19.4 < t < 19.8
    txt, o = disp(d, now=t, tlm=burn)
    assert txt['dsky_r2_disp'] == '+0000.0' and o['dsky_vel']['on']


def test_p40_without_pad_is_a_program_alarm():
    d = Dsky()
    keys(d, 'VERB 3 7 ENTR 4 0 ENTR')
    _, o = disp(d)
    assert d.prog == 0 and o['dsky_prog']['on']


def test_uplink_loads_the_pad():
    d = Dsky()
    d.uplink({'tig_met': 5000, 'dv': [10.0, -1.0, 0.5]}, 1.0)
    _, o = disp(d, now=2.0)
    assert d.pad == {'tig': 5000.0, 'dv': [10.0, -1.0, 0.5]} and o['dsky_uplink']['on']
    _, o = disp(d, now=5.0)
    assert not o['dsky_uplink']['on']


def test_key_rel_restores_the_program_display():
    d = Dsky()
    keys(d, 'VERB 3 7 ENTR 3 0 ENTR')
    keys(d, 'VERB 1 6 NOUN 3 6 ENTR')            # the crew looks at MET meanwhile
    _, o = disp(d)
    assert o['dsky_key_rel']['on'] and d.noun == 36
    keys(d, 'KREL')
    assert (d.verb, d.noun, d.flash) == (6, 33, True)


def _feed(c, t, met, thrust=0.0):
    c.handle('gateway/status', {'connected': True}, t)
    c.handle('tlm/time', {'met': met}, t)
    c.handle('tlm/attitude', {'pitch': 0, 'heading': 90, 'roll': 0}, t)
    return c.handle('tlm/vessel', {'mass': 4000.0, 'thrust': thrust, 'thrust_avail': 6000.0}, t)


def test_cockpit_cuts_the_throttle_at_dsky_cutoff_until_the_lever_is_idle():
    c = Cockpit()
    _feed(c, 0.0, 100.0)
    c.handle('panel/eng/in/eng_arm', {'v': 1}, 0.0)
    c.handle('dsky/uplink', {'tig_met': 103.0, 'dv': [3.0, 0, 0]}, 0.0)
    for k in 'VERB 3 7 ENTR 4 0 ENTR PRO'.split():
        c.handle('panel/dsky/in/key', {'v': k}, 0.0)
    _feed(c, 0.1, 99.0)                          # TIG − 4 s → V99
    c.handle('panel/dsky/in/key', {'v': 'PRO'}, 0.1)
    out = c.handle('panel/eng/in/throttle', {'v': 1.0}, 0.2)
    assert any(m.topic == 'cmd/throttle' and m.payload['v'] == 1.0 for m in out)
    t, cut = 0.2, []
    while t < 5:
        t += 0.1
        cut += [m for m in _feed(c, t, 99.0 + t, thrust=6000.0) if m.topic == 'cmd/throttle']
        if cut:
            break
    assert cut and cut[-1].payload['v'] == 0.0 and 1.9 < t < 2.3     # 3 m/s at 1.5 m/s²
    # lever still forward: stays at 0; back to idle, then forward again: the engine answers
    assert not [m for m in c.handle('panel/eng/in/throttle', {'v': 0.9}, t) if m.payload.get('v')]
    c.handle('panel/eng/in/throttle', {'v': 0.0}, t + 1)
    out = c.handle('panel/eng/in/throttle', {'v': 0.5}, t + 2)
    assert any(m.topic == 'cmd/throttle' and m.payload['v'] == 0.5 for m in out)


def test_sys_panel_stage_dv_twr_and_event_timer():
    c = Cockpit()
    c.handle('gateway/status', {'connected': True}, 0.0)
    c.handle('tlm/time', {'met': 600.0, 'warp': 1}, 0.0)
    c.handle('tlm/orbit', {'body': 'Kerbin', 't_apo': 125.0}, 0.0)
    c.handle('tlm/flight', {'alt': 0.0}, 0.0)
    c.handle('tlm/resources', {'stage': {'LiquidFuel': {'amount': 180, 'max': 180}, 'Oxidizer': {'amount': 220, 'max': 220}},
                                'total': {'ElectricCharge': {'amount': 150, 'max': 200}}}, 0.0)
    out = c.handle('tlm/vessel', {'mass': 4000.0, 'thrust': 0.0, 'thrust_avail': 60000.0, 'isp': 345.0}, 0.0)
    o = {m.topic.split('/')[-1]: m.payload for m in out if m.topic.startswith('panel/sys/out/')}
    # 400 units × 5 kg = 2 t of 4 t: Δv = 345 g0 ln 2 = 2345 m/s; TWR = 60 kN / (4 t × 9.81) = 1.53
    assert o['disp_dv']['text'] == '2345' and o['disp_twr']['text'] == '1.53'
    out = c.handle('panel/sys/in/evt_src', {'v': 2}, 0.1)         # APO: counts down to apoapsis
    o = {m.topic.split('/')[-1]: m.payload for m in out if m.topic.startswith('panel/sys/out/')}
    assert o['disp_evt']['text'] == '-02.05'
