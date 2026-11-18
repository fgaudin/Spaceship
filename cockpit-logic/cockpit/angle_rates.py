"""How fast displayed angles change, in degrees per second: differentiated over game time and smoothed."""


class AngleRates:
    def __init__(self, smoothing):
        self.smoothing = smoothing      # weight of the newest sample
        self.rates = {}                 # angle name → °/s
        self.previous = None            # (time, {angle name: degrees})

    def track(self, angles, time):
        """`angles`: {name: degrees}, or None when there are none: start again when they come back."""
        if not angles or time is None:
            self.rates, self.previous = {}, None
            return
        if self.previous and time > self.previous[0]:
            elapsed = time - self.previous[0]
            for name, angle in angles.items():
                change = (angle - self.previous[1][name] + 180) % 360 - 180     # across ±180° the short way
                rate = change / elapsed
                old = self.rates.get(name)
                self.rates[name] = rate if old is None else old + (rate - old) * self.smoothing
        self.previous = (time, angles)
