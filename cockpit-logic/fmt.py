"""Number formats for 7-segment displays (the decimal point shares a digit)."""
import math


def fit(x, dec, width, signed=False):
    """A number for a `width`-digit display (the sign takes one digit)."""
    if x is None or not math.isfinite(x):
        return '-' * width
    for d in range(dec, -1, -1):
        s = f'{x:+.{d}f}' if signed else f'{x:.{d}f}'
        if len(s.replace('.', '')) <= width:
            return s
    return 'E' * width


def fmt_evt(t):
    """Event timer: −mm.ss before the event, mm.ss after; hours as hH.mm past 99 minutes."""
    a = abs(t)
    sign = '-' if t < 0 else ''
    if a >= 6000:
        return f'{sign}{int(a // 3600)}H{int(a // 60 % 60):02d}'
    return f'{sign}{int(a // 60):02d}.{int(a % 60):02d}'


def fmt_met(s):
    s = max(0, int(s))
    h, m, sec = s // 3600, s // 60 % 60, s % 60
    return f'{h % 100:02d}.{m:02d}.{sec:02d}'


def fit7(x, dec):
    """Right-aligned number for a 7-digit display."""
    for d in range(dec, -1, -1):
        s = f'{x:.{d}f}'
        if len(s.replace('.', '')) <= 7:
            return s
    return 'E' if x > 0 else '-E'
