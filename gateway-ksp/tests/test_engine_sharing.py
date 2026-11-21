"""Which capsule's side an engine is on, docked: the parts are names here, the chains run from a part to the root."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ksp.engine_sharing import sides

# CSM (root: the CM) docked nose to nose with the lander: the lander's port is the child of the CM's port.
#   cm ─ cm_port ─ lm_port ─ mem ─ tank ─ terrier          cm ─ sm ─ cheetah
CM = ['cm']
CHEETAH = ['cheetah', 'sm', 'cm']
LM = ['mem', 'lm_port', 'cm_port', 'cm']
TERRIER = ['terrier', 'tank', 'mem', 'lm_port', 'cm_port', 'cm']


def test_each_engine_goes_with_its_capsule():
    assert sides({'cm': CM, 'lm': LM}, [CHEETAH, TERRIER], ['lm_port']) == ['cm', 'lm']


def test_the_lander_as_the_root():
    # the craft built with the lander's pod as the root: the CM side hangs under the joint instead
    cm = ['cm', 'cm_port', 'lm_port', 'mem']
    cheetah = ['cheetah', 'sm', 'cm', 'cm_port', 'lm_port', 'mem']
    terrier = ['terrier', 'tank', 'mem']
    assert sides({'cm': cm, 'lm': ['mem']}, [cheetah, terrier], ['cm_port']) == ['cm', 'lm']


def test_a_joint_that_does_not_split_the_capsules_is_ignored():
    # another docked port pair, under the lander only (a docked probe): both capsules on the same side of it
    probe_engine = ['ant', 'probe_port', 'mem', 'lm_port', 'cm_port', 'cm']
    assert sides({'cm': CM, 'lm': LM}, [probe_engine, CHEETAH], ['probe_port', 'lm_port']) == ['lm', 'cm']


def test_no_joint_no_side():
    assert sides({'cm': CM, 'lm': LM}, [CHEETAH], []) == [None]
