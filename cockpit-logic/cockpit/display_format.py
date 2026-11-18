"""Text for 7-segment displays. A decimal point shares its digit, so "12.5" takes three digits."""
import math


def fit_number(value, decimals, digits, signed=False):
    """`value` with at most `decimals` decimals, dropping decimals until it fits in `digits` digits.
    A sign takes one digit. Dashes when there is no value; EEE when even the whole number does not fit."""
    if value is None or not math.isfinite(value):
        return '-' * digits
    for kept_decimals in range(decimals, -1, -1):
        shown = round(value, kept_decimals) or 0.0      # no "-0.0" for a tiny negative value
        text = f'{shown:+.{kept_decimals}f}' if signed else f'{shown:.{kept_decimals}f}'
        if len(text.replace('.', '')) <= digits:
            return text
    return 'E' * digits


def format_event_time(seconds):
    """Event timer: -mm.ss before the event, mm.ss after it; hours as hHmm past 99 minutes."""
    magnitude = abs(seconds)
    sign = '-' if seconds < 0 else ''
    if magnitude >= 6000:
        return f'{sign}{int(magnitude // 3600)}H{int(magnitude // 60 % 60):02d}'
    return f'{sign}{int(magnitude // 60):02d}.{int(magnitude % 60):02d}'


def format_mission_time(seconds):
    """Mission elapsed time as hh.mm.ss (hours wrap at 100)."""
    seconds = max(0, int(seconds))
    return f'{seconds // 3600 % 100:02d}.{seconds // 60 % 60:02d}.{seconds % 60:02d}'


def format_time_to(seconds, digits=7):
    """A countdown as hh.mm.ss, the hours growing to fill the display. Dashes when unknown or already past."""
    if seconds is None or not math.isfinite(seconds) or seconds < 0:
        return '-' * digits
    seconds = int(seconds)
    text = f'{seconds // 3600:02d}.{seconds // 60 % 60:02d}.{seconds % 60:02d}'
    return text if len(text.replace('.', '')) <= digits else 'E' * digits
