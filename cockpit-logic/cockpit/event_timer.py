"""The manual event timer: a stopwatch on mission time, or a countdown from a preset value."""
from dataclasses import dataclass

PRESET_SECOND_STEP = 10
PRESET_MINUTES_WRAP = 100


@dataclass
class EventTimer:
    running: bool = False
    started_at: float | None = None     # mission time at the last START
    elapsed_before: float = 0.0         # seconds counted before the last START
    preset: float = 0.0                 # countdown start value, seconds

    def start(self, mission_time):
        if not self.running:
            self.running, self.started_at = True, mission_time

    def stop(self, mission_time):
        if self.running:
            self.running, self.elapsed_before = False, self.elapsed(mission_time)

    def reset(self):
        self.running, self.started_at, self.elapsed_before, self.preset = False, None, 0.0, 0.0

    def add_preset_minute(self):
        if not self.running:
            minutes, seconds = divmod(self.preset, 60)
            self.preset, self.elapsed_before = ((minutes + 1) % PRESET_MINUTES_WRAP) * 60 + seconds, 0.0

    def add_preset_seconds(self):
        if not self.running:
            minutes, seconds = divmod(self.preset, 60)
            self.preset, self.elapsed_before = minutes * 60 + (seconds + PRESET_SECOND_STEP) % 60, 0.0

    def elapsed(self, mission_time):
        if self.running and mission_time is not None:
            return self.elapsed_before + mission_time - self.started_at
        return self.elapsed_before

    def countdown(self, mission_time):
        """(seconds left, reached zero). At zero the timer stops itself; "reached zero" stays true until RESET."""
        remaining = self.preset - self.elapsed(mission_time)
        if remaining > 0:
            return remaining, False
        if self.running:
            self.running, self.elapsed_before = False, self.preset
        return 0.0, self.preset > 0
