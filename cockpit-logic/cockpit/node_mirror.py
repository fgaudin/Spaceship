"""Keeps the burn computer's PAD and the game's maneuver node the same maneuver, in both directions.

PAD → node: the PAD is mirrored to KSP as a node at the burn point (TIG + half the burn time), so that SAS can hold
the burn attitude (SAS MODE MNVR). The cockpit still owns the PAD and the Δv count; the node is an attitude reference.

Node → PAD: a node made or moved in the game's map view is loaded as the PAD (TIG = node time − half the burn time).
"""
from . import settings as S

NODE_COMMAND = 'cmd/node'


class NodeMirror:
    def __init__(self):
        self.mirrored_revision = 0      # PAD revision the game's node matches
        self.known_node = None          # {'ut', 'dv'} of the node last commanded, or last taken from the game

    def pad_to_node(self, cockpit):
        """Commands to send so that the game's node matches the PAD; nothing when it already does."""
        computer = cockpit.burn_computer
        if computer.revision == self.mirrored_revision:
            return []
        if not computer.has_pad() or computer.delta_v_total() == 0:
            self.mirrored_revision, self.known_node = computer.revision, None
            return cockpit.command(NODE_COMMAND, {'clear': True})
        universal_time = cockpit.clock.get('ut')
        time_from_ignition = computer.time_from_ignition(cockpit.telemetry)
        if time_from_ignition is None or universal_time is None or not cockpit.telemetry_is_fresh():
            return []                   # no clock yet: try again on the next tick
        self.mirrored_revision = computer.revision
        if time_from_ignition >= 0:     # TIG is in the past: KSP cannot hold a node there
            self.known_node = None
            return cockpit.command(NODE_COMMAND, {'clear': True})
        ignition_universal_time = universal_time - time_from_ignition
        burn_time = computer.burn_time(cockpit.telemetry) or 0.0
        self.known_node = {'ut': round(ignition_universal_time + burn_time / 2, 2),
                           'dv': [round(component, 2) for component in computer.pad['dv']]}
        return cockpit.command(NODE_COMMAND, dict(self.known_node))

    def node_to_pad(self, cockpit, node):
        """`node`: a tlm/node payload. Loads it as the PAD unless it is the node the cockpit already knows."""
        computer, clock = cockpit.burn_computer, cockpit.clock
        if not node.get('set') or computer.armed or clock.get('ut') is None or clock.get('met') is None:
            return
        if cockpit.seconds_since_command(NODE_COMMAND) < S.NODE_ECHO_DELAY_S:
            return                      # our own command may not be in the telemetry yet
        if self._is_known(node):
            return
        node_mission_time = clock['met'] + node['ut'] - clock['ut']
        computer.load(node_mission_time, node['dv'])
        burn_time = computer.burn_time(cockpit.telemetry) or 0.0
        computer.pad['tig'] = round(node_mission_time - burn_time / 2, 1)
        self.mirrored_revision = computer.revision      # the game already has this node: nothing to send back
        self.known_node = {'ut': node['ut'], 'dv': list(node['dv'])}

    def forget(self):
        """After the node was removed (burn cutoff)."""
        self.known_node = None

    def _is_known(self, node):
        known = self.known_node
        if not known:
            return False
        same_time = abs(known['ut'] - node['ut']) < S.NODE_SAME_TIME_S
        same_delta_v = all(abs(ours - theirs) < S.NODE_SAME_DELTA_V for ours, theirs in zip(known['dv'], node['dv']))
        return same_time and same_delta_v
