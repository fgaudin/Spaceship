"""The mission clock across launches, undockings, vessel switches, save loads and gateway restarts."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ksp.mission_clock import MissionClock, NEW_FLIGHT, SAME_FLIGHT, ON_THE_PAD

LAUNCH = 90000.0


def flown(clock, now=0.0):
    """Launch at LAUNCH: on the pad, then off the ground."""
    assert clock.bind('Acapello', LAUNCH - 30, 0.0, 'pre_launch', now) == ON_THE_PAD
    clock.follow(LAUNCH - 10, 0.0, 'pre_launch')
    clock.follow(LAUNCH, 0.0, 'pre_launch')
    clock.follow(LAUNCH + 1, 1.0, 'flying')
    return clock


def test_the_launch_sets_the_clock_once():
    clock = MissionClock()
    clock.bind('Acapello', LAUNCH - 30, 0.0, 'pre_launch', 0)
    clock.changed = False
    clock.follow(LAUNCH - 10, 0.0, 'pre_launch')
    assert not clock.changed                      # quiet on the pad
    clock.follow(LAUNCH, 0.0, 'pre_launch')
    clock.follow(LAUNCH + 1, 1.0, 'flying')
    assert clock.changed and clock.launch_ut == LAUNCH and clock.met(LAUNCH + 100) == 100


def test_an_undocked_lander_keeps_the_mission_clock():
    clock = flown(MissionClock())
    clock.note_split(now=1000)
    # the lander after the undocking: its own MET is 0
    assert clock.bind('Acapello Lander', LAUNCH + 30000, 0.0, 'orbiting', now=1005) == SAME_FLIGHT
    assert clock.met(LAUNCH + 30000) == 30000
    # switching back to the CSM, and to the lander again much later (no command of ours: its name is known)
    assert clock.bind('Acapello', LAUNCH + 31000, 31000, 'orbiting', now=2000) == SAME_FLIGHT
    assert clock.bind('Acapello Lander', LAUNCH + 40000, 10000, 'landed', now=9000) == SAME_FLIGHT
    assert clock.launch_ut == LAUNCH


def test_a_restarted_gateway_carries_on():
    old = flown(MissionClock())
    old.vessels.append('Acapello Lander')
    new = MissionClock()
    new.restore(old.record())
    # the lander's save: its own MET counts from the undocking
    assert new.bind('Acapello Lander', LAUNCH + 50000, 20000, 'orbiting', now=5) == SAME_FLIGHT
    assert new.met(LAUNCH + 50000) == 50000


def test_another_craft_or_an_earlier_save_starts_a_new_flight():
    clock = flown(MissionClock())
    assert clock.bind('Target', LAUNCH + 500, 7000, 'orbiting', now=100) == NEW_FLIGHT   # launched before ours
    assert clock.launch_ut == LAUNCH + 500 - 7000
    clock = flown(MissionClock())
    assert clock.bind('Acapello', LAUNCH - 3000, 500, 'orbiting', now=100) == NEW_FLIGHT  # a save from before


def test_a_revert_to_the_launch_starts_again_on_the_pad():
    clock = flown(MissionClock())
    assert clock.bind('Acapello', LAUNCH + 20, 0.0, 'pre_launch', now=100) == ON_THE_PAD
    clock.follow(LAUNCH + 60, 0.0, 'pre_launch')
    clock.follow(LAUNCH + 61, 1.0, 'flying')
    assert clock.launch_ut == LAUNCH + 60


def test_met_reset_starts_from_the_vessel_flown():
    clock = flown(MissionClock())
    clock.changed = False
    clock.reset('Lander', LAUNCH + 9000, 4000.0)
    assert clock.changed and clock.launch_ut == LAUNCH + 5000 and clock.vessels == ['Lander']


def test_the_other_capsule_is_adopted_before_it_is_flown():
    clock = flown(MissionClock())
    clock.adopt('Acapello Lander', LAUNCH + 30000, 0.0)              # seen apart right after the undocking
    clock.adopt('Target', LAUNCH + 30000, 90000.0)                    # another flight's craft, launched before ours
    assert clock.vessels == ['Acapello', 'Acapello Lander']
    later = MissionClock()
    later.restore(clock.record())
    # its own save, never flown in between: still this flight
    assert later.bind('Acapello Lander', LAUNCH + 40000, 10000, 'orbiting', now=0) == SAME_FLIGHT
