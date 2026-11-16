"""Two-body orbits: what a flight dynamics officer works with. Pure functions, SI units, angles in radians.

An orbit is given by its elements at a moment (`Elements`): semi-major axis, eccentricity, inclination, longitude
of the ascending node, argument of periapsis, true anomaly, the universal time they hold at, and μ of the body.
Positions are in the body's inertial frame, the one KSP's elements refer to: x towards the reference direction,
z along the body's rotation axis.
"""
import math
from dataclasses import dataclass, replace

TWO_PI = 2 * math.pi


@dataclass(frozen=True)
class Elements:
    a: float            # semi-major axis, m
    e: float            # eccentricity
    i: float            # inclination
    lan: float          # longitude of the ascending node
    argp: float         # argument of periapsis
    nu: float           # true anomaly at `ut`
    ut: float           # universal time, s
    mu: float           # gravitational parameter of the body, m³/s²

    @property
    def closed(self):
        return self.e < 1

    @property
    def mean_motion(self):
        return math.sqrt(self.mu / abs(self.a) ** 3)

    @property
    def period(self):
        return TWO_PI / self.mean_motion if self.closed else math.inf

    def radius_at(self, nu):
        return self.a * (1 - self.e ** 2) / (1 + self.e * math.cos(nu))

    def speed_at_radius(self, radius):
        """Vis-viva."""
        return math.sqrt(self.mu * (2 / radius - 1 / self.a))

    @property
    def apoapsis_radius(self):
        return self.a * (1 + self.e) if self.closed else math.inf

    @property
    def periapsis_radius(self):
        return self.a * (1 - self.e)

    def normal(self):
        """Unit vector perpendicular to the orbit's plane, along the angular momentum."""
        return (math.sin(self.i) * math.sin(self.lan), -math.sin(self.i) * math.cos(self.lan), math.cos(self.i))

    def direction_at(self, nu):
        """Unit vector from the body's centre to the point at true anomaly `nu`."""
        u = self.argp + nu                                  # argument of latitude
        cos_lan, sin_lan, cos_i = math.cos(self.lan), math.sin(self.lan), math.cos(self.i)
        return (cos_lan * math.cos(u) - sin_lan * math.sin(u) * cos_i,
                sin_lan * math.cos(u) + cos_lan * math.sin(u) * cos_i,
                math.sin(u) * math.sin(self.i))

    def true_anomaly_of(self, direction):
        """True anomaly of the point of the orbit in `direction` (a unit vector in the orbit's plane)."""
        p = self.direction_at(0.0)                          # towards periapsis
        q = self.direction_at(math.pi / 2)                  # 90° ahead of it
        return math.atan2(dot(direction, q), dot(direction, p)) % TWO_PI

    def time_to(self, nu):
        """Seconds from `ut` until the vessel is next at true anomaly `nu` (closed orbits only)."""
        mean_now, mean_then = mean_anomaly(self.nu, self.e), mean_anomaly(nu, self.e)
        return ((mean_then - mean_now) % TWO_PI) / self.mean_motion

    def at(self, ut):
        """The same orbit at another time: the true anomaly moved on (closed orbits only)."""
        mean = mean_anomaly(self.nu, self.e) + self.mean_motion * (ut - self.ut)
        return replace(self, nu=true_anomaly(mean % TWO_PI, self.e), ut=ut)


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def unit(vector):
    length = math.sqrt(dot(vector, vector))
    return tuple(x / length for x in vector)


def mean_anomaly(nu, e):
    eccentric = 2 * math.atan2(math.sqrt(1 - e) * math.sin(nu / 2), math.sqrt(1 + e) * math.cos(nu / 2))
    return (eccentric - e * math.sin(eccentric)) % TWO_PI


def true_anomaly(mean, e):
    """Kepler's equation, solved by Newton's method."""
    eccentric = mean if e < 0.8 else math.pi
    for _ in range(50):
        step = (eccentric - e * math.sin(eccentric) - mean) / (1 - e * math.cos(eccentric))
        eccentric -= step
        if abs(step) < 1e-12:
            break
    return (2 * math.atan2(math.sqrt(1 + e) * math.sin(eccentric / 2), math.sqrt(1 - e) * math.cos(eccentric / 2))) % TWO_PI


def hohmann(mu, r1, r2):
    """(Δv of the first burn, transfer time) from a circular orbit of radius r1 to radius r2."""
    transfer_a = (r1 + r2) / 2
    first_burn = math.sqrt(mu / r1) * (math.sqrt(2 * r2 / (r1 + r2)) - 1)
    return first_burn, math.pi * math.sqrt(transfer_a ** 3 / mu)


def phase_angle(own, other):
    """Angle from `own` to `other`, measured in the direction of motion (0 to 2π)."""
    here, there = own.direction_at(own.nu), other.direction_at(other.nu)
    angle = math.atan2(dot(cross(here, there), own.normal()), dot(here, there))
    return angle % TWO_PI
