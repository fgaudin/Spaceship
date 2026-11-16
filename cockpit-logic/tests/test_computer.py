import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cockpit import BurnComputer, Cockpit  # noqa: E402
from cockpit.messages import PanelOutputs  # noqa: E402
from test_logic import fed, topics  # noqa: E402

C = 'panel/cmp/out/'


def panel(computer, telemetry):
    """The computer's panel outputs, by output name."""
    wanted = {}
    computer.render(PanelOutputs(wanted, 'cmp'), telemetry, powered=True, lamp_test=False, telemetry_fresh=True)
    return {topic.split('/')[-1]: payload for topic, payload in wanted.items()}


def keys(c, seq):
    for k in seq.split():
        c.press_key(k)


def tlm(met, thrust=0.0, mass=10000.0):
    return {'tlm/time': {'met': met, 'ut': 1000 + met}, 'tlm/vessel': {'mass': mass, 'thrust': thrust, 'thrust_avail': 60000.0, 'isp': 345.0}}


def test_key_a_pad_field_by_field():
    c = BurnComputer()
    c.select_field('tig')
    keys(c, '1 3 0 4 5 ENTR')                 # 01:30:45, then the computer moves to PRO
    assert c.pad['tig'] == 5445 and c.selected_field == 'pro'
    keys(c, '1 2 . 5 ENTR ENTR - 3 ENTR')     # PRO 12.5, NRM kept, RAD −3
    assert c.pad['dv'] == [12.5, 0.0, -3.0] and c.selected_field is None and not c.entry_error
    out = panel(c, tlm(5000))
    assert out['disp_tig']['text'] == '01.30.45' and out['disp_pro']['text'] == '+12.5' and out['disp_rad']['text'] == '-3.0'
    assert out['disp_tfi']['text'] == '-07.25'


def test_bad_entries_light_err_and_change_nothing():
    c = BurnComputer()
    c.select_field('tig')
    keys(c, '0 1 7 5 0 0 ENTR')               # 75 minutes
    assert c.entry_error and c.pad['tig'] is None and c.selected_field == 'tig'
    c.select_field('pro'); c.select_field('pro')          # pressing the field again leaves it
    assert c.selected_field is None and not c.entry_error
    c.select_field('pro')
    keys(c, '1 . 2 3')                        # one decimal only
    assert c.entry_error and c.typed == '1.2'
    keys(c, 'CLR CLR')
    assert c.selected_field is None and c.pad['dv'][0] == 0.0


def test_uplink_waits_for_accept_and_clr_rejects():
    c = BurnComputer()
    c.receive_uplink({'tig_met': 600, 'dv': [10, 0, 0]})
    out = panel(c, tlm(0))
    assert not c.has_pad() and out['lamp_uplink'] == {'on': True, 'blink': True} and out['disp_pro'] == {'text': '+10.0', 'blank': False, 'blink': True}
    c.press_key('CLR')
    assert c.uplinked_pad is None and not c.has_pad()
    c.receive_uplink({'tig_met': 600, 'dv': [10, 0, 0]})
    c.accept_uplink()
    assert c.pad == {'tig': 600.0, 'dv': [10.0, 0.0, 0.0]} and c.revision == 1
    c.receive_uplink({'dv': [1]})
    assert c.entry_error and c.uplinked_pad is None


def test_counter_runs_on_game_time_and_cuts_off():
    c = BurnComputer()
    c.receive_uplink({'tig_met': 100, 'dv': [12, 0, 0]}); c.accept_uplink()
    for i in range(20):                       # thrust before BURN ARM is not counted
        c.count_delta_v(tlm(90 + i * 0.1, thrust=60000.0))
    assert c.delta_v_counted == 0
    c.arm(True)
    t, n = 100.0, 0
    while not c.cutoff and n < 1000:
        c.count_delta_v(tlm(t, thrust=60000.0)); t += 0.1; n += 1      # 6 m/s² → 12 m/s in 2 s
    assert c.cutoff and 1.9 <= t - 100.0 - 0.1 <= 2.1
    assert abs(c.delta_v_to_go()) < 0.5 and c.state(tlm(t)) == 'done'
    c.count_delta_v(tlm(t, thrust=60000.0))
    vg = c.delta_v_to_go()
    c.count_delta_v(tlm(t, thrust=60000.0))            # the clock does not move (pause): nothing counted
    assert c.delta_v_to_go() == vg


def test_burn_time_and_tig_lamp():
    c = BurnComputer()
    c.receive_uplink({'tig_met': 100, 'dv': [60, 0, 0]}); c.accept_uplink()
    assert abs(c.burn_time(tlm(0)) - 9.91) < 0.05              # 10 t, 60 kN, Isp 345 s
    assert panel(c, tlm(30))['lamp_tig']['on'] is False
    assert panel(c, tlm(50))['lamp_tig'] == {'on': True, 'blink': False}
    assert panel(c, tlm(95))['lamp_tig'] == {'on': True, 'blink': True}


def test_cockpit_mirrors_the_pad_to_a_node_and_cuts_the_throttle():
    c = Cockpit()
    fed(c, vessel={'isp': 345.0})
    c.handle('panel/eng/in/eng_arm', {'v': 1}, 1); c.handle('panel/eng/in/throttle', {'v': 1.0}, 1)
    c.handle('pad/uplink', {'tig_met': 200, 'dv': [5, 0, 0]}, 1)
    out = topics(c.handle('panel/cmp/in/pad_accept', {'v': 1}, 2))
    node = out['cmd/node']                    # MET 65, UT 100 in fed(): TIG at UT 235, plus half the burn time
    assert node['dv'] == [5.0, 0.0, 0.0] and 235 < node['ut'] < 236
    assert out['cmp/pad']['tig'] == 200.0
    c.handle('panel/cmp/in/burn_arm', {'v': 1}, 3)
    got = {}
    for i in range(40):
        c.handle('tlm/time', {'ut': 300 + i * 0.1, 'met': 200 + i * 0.1, 'warp': 1}, 4 + i * 0.1)
        got.update(topics(c.handle('tlm/vessel', {'mass': 10000.0, 'thrust': 100000.0, 'thrust_avail': 100000.0, 'isp': 345.0,
                                                  'stage': 3}, 4 + i * 0.1)))
        if c.burn_computer.cutoff:
            break
    assert c.burn_computer.cutoff and got['cmd/throttle'] == {'v': 0.0} and got['cmd/node'] == {'clear': True}
    assert got[C + 'lamp_cutoff']['on'] and got['panel/eng/out/lamp_cutoff']['on']
    # the throttle stays cut until the lever comes back to idle
    assert 'cmd/throttle' not in topics(c.handle('panel/eng/in/throttle', {'v': 0.8}, 9))
    c.handle('panel/eng/in/throttle', {'v': 0.0}, 10)
    assert topics(c.handle('panel/eng/in/throttle', {'v': 0.5}, 11))['cmd/throttle'] == {'v': 0.5}


def test_field_being_keyed_is_steady_with_a_cursor():
    c = BurnComputer()
    c.select_field('pro'); keys(c, '1 2')
    assert panel(c, tlm(0))['disp_pro'] == {'text': '12_', 'blank': False, 'blink': False}


def test_node_made_in_the_game_becomes_the_pad():
    c = Cockpit()
    fed(c, vessel={'isp': 345.0})                                # MET 65, UT 100; 12.5 t, 200 kN
    out = topics(c.handle('tlm/node', {'set': True, 'ut': 400.0, 'dv': [100.0, 0.0, -5.0], 'att_err': 3.0}, 1))
    assert c.burn_computer.pad['dv'] == [100.0, 0.0, -5.0] and 'cmd/node' not in out      # shown, and the game's node is left alone
    tb = c.burn_computer.burn_time(c.telemetry)
    assert abs(c.burn_computer.pad['tig'] - (365 - tb / 2)) < 0.1                         # TIG = node time − half the burn
    assert 'cmd/node' not in topics(c.tick(2))
    rev = c.burn_computer.revision
    c.handle('tlm/node', {'set': True, 'ut': 400.0, 'dv': [100.0, 0.0, -5.0], 'att_err': 3.0}, 3)
    assert c.burn_computer.revision == rev                                                     # same node: nothing reloaded
    c.handle('tlm/node', {'set': True, 'ut': 420.0, 'dv': [80.0, 0.0, 0.0], 'att_err': 3.0}, 4)    # dragged in map view
    assert c.burn_computer.pad['dv'] == [80.0, 0.0, 0.0]
    # a PAD keyed on the panel then replaces the game's node, and that node is not read back as a new one
    c.burn_computer.select_field('pro')
    for k in ('2', '0', 'ENTR'):
        out = topics(c.handle('panel/cmp/in/key', {'v': k}, 5))
    assert out['cmd/node']['dv'] == [20.0, 0.0, 0.0]
    rev = c.burn_computer.revision
    c.handle('tlm/node', {'set': True, 'ut': 420.0, 'dv': [80.0, 0.0, 0.0], 'att_err': 3.0}, 5.5)  # stale telemetry
    c.handle('tlm/node', {'set': True, 'ut': out['cmd/node']['ut'], 'dv': [20.0, 0.0, 0.0], 'att_err': 3.0}, 8)
    assert c.burn_computer.revision == rev
