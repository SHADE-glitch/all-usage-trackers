"""Window arithmetic and typed date entry — no Textual, no terminal.

The tabs and the headless report must agree on what a window means, and the
report is documented as pure standard library: it has to run where Textual is
not installed. So the presets, the custom-window shape, the date/time parsers
and `bounds_of` live here, and `aut_picker` imports them for its modal. Nothing
in this module imports Textual.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import NamedTuple


# Presets. `None` days means "no lower bound".
USAGE_RANGES = {"1d": 1, "2d": 2, "3d": 3, "7d": 7, "14d": 14, "30d": 30,
                "all": None}
RANGE_LABELS = {"1d": "Today", "2d": "2 days", "3d": "3 days", "7d": "7 days",
                "14d": "14 days", "30d": "30 days", "all": "All time"}


DATE_DISPLAY_FMT = "%m/%d/%Y"
TIME_DISPLAY_FMT = "%H:%M"
# The date is split by hand rather than through a table of strptime formats:
# a yearless "%m-%d" parse is deprecated in 3.14 (the default year is ambiguous
# and leap day cannot resolve), so the missing year is filled in explicitly.
_DATE_SPLIT = re.compile(r"[-/.]")
_TIME_FORMATS = ("%I:%M %p", "%I:%M%p", "%I %p", "%I%p", "%H:%M", "%H:%M:%S")

class CustomWindow(NamedTuple):
    """An absolute window chosen in the date picker (as opposed to a preset).

    ``start_ms`` of ``None`` means no lower bound (all time). ``follow_now``
    keeps the end pinned to the current time on every refresh; otherwise the
    window is the fixed ``[start_ms, end_ms]`` span. Times are epoch
    milliseconds, the same unit as every other bound in this module.
    """

    start_ms: int | None
    end_ms: int | None
    follow_now: bool = False


def _short_time(ms) -> str:
    return datetime.fromtimestamp(ms / 1000).strftime("%m-%d %H:%M")


def window_label(value) -> str:
    """A short label for a window value: a preset's name, or a custom span.

    A ``follow_now`` end reads as ``now`` rather than a timestamp, so the label
    does not go stale between refreshes. Kept free of a clock argument on
    purpose: the label depends only on what was chosen, never on the time it is
    read.
    """
    if not isinstance(value, CustomWindow):
        return RANGE_LABELS.get(value, str(value))
    if value.start_ms is None:
        return "all → now" if value.follow_now else f"all → {_short_time(value.end_ms)}"
    start = _short_time(value.start_ms)
    if value.follow_now:
        return f"{start} → now"
    return f"{start} → {_short_time(value.end_ms)}"


# --- typed date / time entry (the date picker) ------------------------------
# The picker lets a date and a time be *typed* as well as clicked, so the two
# strings a person types are normalised before anything compares them: "10-01"
# and "10-1" are the same day, "9:5 AM" and "09:05 AM" the same minute. That is
# the whole point — the display format is a suggestion, not a syntax to match.
#
# Month-first is assumed for the ambiguous two-field date form (the picker shows
# MM/DD/YYYY), and a leading four-digit field is read as the year. Both the date
# and the time are displayed in the same form the rest of the app prints them:
# a 24-hour clock, so midnight reads "00:00" rather than "12:00 AM". An am/pm
# marker is still *accepted* on input ("12:00 AM" is midnight) — the display
# format is a suggestion, not a syntax to match.
DATE_DISPLAY_FMT = "%m/%d/%Y"
TIME_DISPLAY_FMT = "%H:%M"
# The date is split by hand rather than through a table of strptime formats:
# a yearless "%m-%d" parse is deprecated in 3.14 (the default year is ambiguous
# and leap day cannot resolve), so the missing year is filled in explicitly.
_DATE_SPLIT = re.compile(r"[-/.]")
_TIME_FORMATS = ("%I:%M %p", "%I:%M%p", "%I %p", "%I%p", "%H:%M", "%H:%M:%S")


def parse_date(text: str, default_year: int) -> datetime:
    """A typed date -> ``datetime`` at local midnight. Raises ``ValueError``.

    ``10-01``, ``10/1`` and ``10.01`` all mean the same day once ``default_year``
    fills in the missing year; a four-digit leading field is the year
    (``2026-10-01``). The month comes first in the ambiguous two-field form, and
    a two-digit trailing year uses the same 69/70 pivot as ``%y``.
    """
    s = (text or "").strip()
    fields = _DATE_SPLIT.split(s)
    if len(fields) == 2:
        year, (month, day) = str(default_year), fields
    elif len(fields) == 3:
        first, second, third = fields
        if len(first) == 4:                       # YYYY-MM-DD
            year, month, day = first, second, third
        else:                                     # MM-DD-YYYY / MM-DD-YY
            month, day, year = first, second, third
            if len(year) == 2:
                year = ("19" if int(year) >= 69 else "20") + year
    else:
        raise ValueError(f"unrecognised date: {text!r}")
    try:
        return datetime(int(year), int(month), int(day))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"unrecognised date: {text!r}") from exc


def parse_time(text: str):
    """A typed time -> ``(hour, minute)`` in 24-hour form. Raises ``ValueError``.

    An am/pm marker makes it 12-hour ("9:5 PM" == "09:05 PM"); without one it is
    24-hour ("21:05"). ``12:00 AM`` is midnight, ``12:00 PM`` noon.
    """
    s = (text or "").strip()
    if not s:
        raise ValueError("empty time")
    for fmt in _TIME_FORMATS:
        try:
            dt = datetime.strptime(s, fmt)
        except ValueError:
            continue
        return dt.hour, dt.minute
    raise ValueError(f"unrecognised time: {text!r}")


def format_date(value: datetime) -> str:
    """A datetime's date as the picker displays it (``MM/DD/YYYY``)."""
    return value.strftime(DATE_DISPLAY_FMT)


def format_time(hour: int, minute: int) -> str:
    """``(hour, minute)`` as the picker shows it (24-hour, e.g. ``00:00``)."""
    return datetime(2000, 1, 1, hour, minute).strftime(TIME_DISPLAY_FMT)


def parse_datetime(date_text: str, time_text: str, default_year: int):
    """A typed ``(date, time)`` pair -> epoch ms, or ``None`` for a blank date.

    A blank time means midnight. Raises ``ValueError`` on a bad date or time, so
    the caller can tell "all time" (``None``) apart from "I mistyped" (an error).
    """
    if not (date_text or "").strip():
        return None
    day = parse_date(date_text, default_year)
    hour, minute = parse_time(time_text) if (time_text or "").strip() else (0, 0)
    return int(day.replace(hour=hour, minute=minute).timestamp() * 1000)


def bounds_of(value, now_ms: int):
    """``(start_ms, end_ms)`` for any window value, preset or custom.

    One place that knows how a window becomes a pair of bounds, so the TUI's
    tabs and the picker's prefill cannot drift apart. ``follow_now`` resolves
    its end to ``now_ms`` here, which is why the caller must pass a fresh clock.
    """
    if isinstance(value, CustomWindow):
        return value.start_ms, (int(now_ms) if value.follow_now else value.end_ms)
    if value is None:
        return None, int(now_ms)
    return window_bounds(value, now_ms)


def window_bounds(range_key: str, now_ms: int):
    """``(start_ms, end_ms)`` for a whole-calendar-day window ending at ``now_ms``.

    The window is a whole number of **local** calendar days: ``"1d"`` runs from
    today's local 00:00 to ``now_ms``, ``"2d"`` from yesterday's 00:00, and so
    on. It never uses "now minus N hours", so the bounds are stable through the
    day and match what a person means by "today" / "the last 2 days".

    ``start_ms`` is ``None`` for ``"all"`` (no lower bound).
    """
    days = USAGE_RANGES[range_key]
    end = int(now_ms)
    if days is None:
        return None, end
    midnight = datetime.fromtimestamp(end / 1000).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    start = midnight - timedelta(days=days - 1)
    return int(start.timestamp() * 1000), end
