"""One mission clock for the whole flight: tlm/time "met" is UT − the launch's UT, whatever vessel is flown.

KSP keeps a mission time per vessel, and a vessel made by an undocking or a separation starts its own at 0: in the Mun
mission the lander's MET went from 08:33 to 00:00 at the undocking, so PADs keyed in MET (the burn computer, CAPCOM)
and Mission Control's history (mcc-data starts a new flight when MET goes back to 0) followed whichever vessel was
flown. The gateway now keeps the launch's UT itself and decides, each time it binds a vessel, whether that vessel is
part of the flight or starts another:

- on the pad (pre_launch) the launch is now: the clock follows the vessel until it leaves the ground;
- a vessel bound right after our own undock, staging or STATION switch, or whose name was flown in this flight, and
  whose own start is not earlier than the launch, is a fragment of the flight: the clock carries on;
- the same start as the flight's (a save of the same vessel loaded) carries on as well;
- anything else (another craft, a save from before the launch, a revert) starts a new flight from that vessel's own
  mission time.

The record (launch UT and the vessels' names) is published retained on `mission/clock`, so a restarted gateway carries
on. MET RESET (a 2 s press on the button next to MET) starts the clock again from the vessel flown, when it went wrong
(a save of another flight whose vessel had a name of this one, for instance)."""
import time

FRAGMENT_WINDOW_S = 20          # a vessel bound this long after our own undock, staging or switch is a fragment
SAME_START_S = 2.0              # starts closer than this are the same launch
NEW_FLIGHT, SAME_FLIGHT, ON_THE_PAD = 'new flight', 'same flight', 'on the pad'


class MissionClock:
    def __init__(self):
        self.launch_ut = None
        self.vessels = []           # names of the vessels flown in this flight
        self.split_at = None        # monotonic time of our own last undock, staging or STATION switch
        self.changed = False        # the record changed: publish it
        self.on_pad = False         # following the vessel on the pad, quietly (the record goes out at liftoff)

    # ---------- the record ----------
    def record(self):
        return {'launch_ut': self.launch_ut, 'vessels': list(self.vessels)}

    def restore(self, record):
        """The retained record, read back by a restarted gateway (before it binds a vessel)."""
        if self.launch_ut is None and record and record.get('launch_ut') is not None:
            self.launch_ut = float(record['launch_ut'])
            self.vessels = list(record.get('vessels') or [])

    def note_split(self, now=None):
        """Our own undock, staging or STATION switch: the next vessel bound is part of this flight."""
        self.split_at = time.monotonic() if now is None else now

    # ---------- deciding ----------
    def bind(self, name, universal_time, own_mission_time, situation, now=None):
        """A vessel was bound: carry on, or start a new flight. Returns NEW_FLIGHT, SAME_FLIGHT or ON_THE_PAD."""
        now = time.monotonic() if now is None else now
        own_start = universal_time - own_mission_time
        if situation == 'pre_launch':
            self._start(own_start, name)
            self.on_pad = True
            return ON_THE_PAD
        if self.launch_ut is not None and universal_time >= self.launch_ut:
            same_start = abs(own_start - self.launch_ut) < SAME_START_S
            after_our_split = self.split_at is not None and now - self.split_at < FRAGMENT_WINDOW_S
            fragment = own_start > self.launch_ut and (after_our_split or name in self.vessels)
            if same_start or fragment:
                if name not in self.vessels:
                    self.vessels.append(name)
                    self.changed = True
                return SAME_FLIGHT
        self._start(own_start, name)
        return NEW_FLIGHT

    def adopt(self, name, universal_time, own_mission_time):
        """The other capsule's vessel, seen nearby (after an undocking): part of this flight from then on, even if it
        is never flown before its own save is loaded. Not when it started before the launch (another flight's)."""
        if self.launch_ut is None or name in self.vessels:
            return
        if universal_time - own_mission_time >= self.launch_ut - SAME_START_S:
            self.vessels.append(name)
            self.changed = True

    def follow(self, universal_time, own_mission_time, situation):
        """Every cycle: on the pad the launch is now (KSP's MET stays 0 until the vessel leaves the ground). The
        record is published once, when it leaves: not on every cycle while the launch keeps moving."""
        if situation == 'pre_launch':
            self.launch_ut, self.on_pad = universal_time - own_mission_time, True
        elif self.on_pad:
            self.on_pad = False
            self.launch_ut, self.changed = universal_time - own_mission_time, True

    def reset(self, name, universal_time, own_mission_time):
        """MET RESET: the clock starts again from the vessel flown, a new flight. MET becomes that vessel's own
        mission time, not 0: a second reset on the same vessel gives the same launch and shows no change."""
        self._start(universal_time - own_mission_time, name)

    def met(self, universal_time):
        if self.launch_ut is None:
            return None
        return universal_time - self.launch_ut

    def _start(self, launch_ut, name):
        if self.launch_ut is None or abs(launch_ut - self.launch_ut) > 0.5:
            self.changed = True
        self.launch_ut = launch_ut
        if name is not None:
            if self.vessels != [name]:
                self.changed = True
            self.vessels = [name]
