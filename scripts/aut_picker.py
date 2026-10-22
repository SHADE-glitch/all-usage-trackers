"""The custom date-range picker, ported from the tracker family.

Copied rather than re-invented on purpose: the three trackers all open this same
79x30 picker, and a fourth, different one would be a fourth set of habits. The
code below is theirs; the only change is that the helpers it called through a
module alias now live in this module.

Kept in its own file so `aut_app` stays about the board and this stays about one
modal.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import NamedTuple

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Input, Static

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

class TimeInput(Input):
    """A clock field you can scrub as well as type.

    Typing is the fast path (``00:00`` and ``9:5 PM`` are both understood);
    ↑/↓ and the mouse wheel step the value, so it can be nudged without the
    keyboard. The step is a per-instance count of minutes, set by the picker's
    step selector, so one key press can move a minute, ten, or an hour. The
    value is re-rendered through ``format_time``, so what stays in the field
    is always the canonical 24-hour ``HH:MM``.
    """

    BINDINGS = [
        Binding("up", "nudge_up", "Later", show=False),
        Binding("down", "nudge_down", "Earlier", show=False),
    ]
    STEP = 1  # minutes per nudge, until the picker's step selector says otherwise

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.step = self.STEP

    def action_nudge_up(self) -> None:
        self._nudge(self.step)

    def action_nudge_down(self) -> None:
        self._nudge(-self.step)

    def on_mouse_scroll_up(self, event) -> None:
        self._nudge(self.step)
        event.stop()

    def on_mouse_scroll_down(self, event) -> None:
        self._nudge(-self.step)
        event.stop()

    def _nudge(self, minutes: int) -> None:
        try:
            hour, minute = parse_time(self.value)
        except ValueError:
            # An empty or half-typed field nudges from *now*, so the first ↑/↓
            # yields a valid time instead of an error.
            now = datetime.now()
            hour, minute = now.hour, now.minute
        total = (hour * 60 + minute + minutes) % (24 * 60)
        self.value = format_time(total // 60, total % 60)
        self.cursor_position = len(self.value)


class DateRangeModal(ModalScreen):
    """The custom date-range picker, laid out like cbut's: chips, cards, grids.

    Left column: cbut's six shortcut chips, an editable START TIME and END TIME (a
    date plus a 24-hour time each), a quick-time row under each card, a
    nudge-step selector and the "end follows now" switch. Right column: a month
    calendar whose ‹ › step the month (and, at the year's ends, the year), with
    a 24-cell hour grid below it. Clicking a card makes it active; a day or an
    hour then writes into the active card — start and end are picked the same
    way, and the calendar and the grid are the two halves of one clock.

    Opened from the top bar's 📅 control or the Select's "Custom…". Confirm
    dismisses with a ``CustomWindow``; Cancel or Esc dismisses with ``None``.
    A blank start date means all time.
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel")]
    CELLS = 42                       # 6 rows × 7 columns covers any month
    DOW = ("S", "M", "T", "W", "T", "F", "S")
    # (chip label, widget id, preset key) — cbut's six shortcuts, unchanged.
    # "Today" and "1d" both name the single whole calendar day the model calls
    # "1d". The Select also offers 2 days and 3 days, but cbut's picker does not
    # repeat every Select option as a chip: six height-3 chips take 52 of the
    # 53-cell column, and a seventh would clip "All time". Those two ranges stay
    # one click away in the Select and reachable here through the calendar.
    PRESETS = (
        ("Today", "dr-today", "1d"),
        ("1d", "dr-1d", "1d"),
        ("7d", "dr-7d", "7d"),
        ("14d", "dr-14d", "14d"),
        ("30d", "dr-30d", "30d"),
        ("All time", "dr-all", "all"),
    )
    # The quick-time row under each card. The start card offers the day's edges
    # and the common halves; the end card also offers ``now``, which is the same
    # thing as ticking "follows current time" — the two ends of one choice, one
    # click each.
    QUICK_START = ("00:00", "06:00", "12:00", "18:00", "23:59")
    QUICK_END = ("now", "00:00", "12:00", "23:59")
    # The nudge selector: (label, minutes). ↑/↓ and the wheel move by the
    # selected step, so a day's edge is reachable without typing.
    STEPS = (("1m", 1), ("10m", 10), ("1h", 60))
    HOURS = 24

    DEFAULT_CSS = """
    DateRangeModal { align: center middle; overflow: auto; }
    /* The roomy cbut layout: height-3 preset chips, a blank row between the
       cards, and the default bordered checkbox. Width budget, so the picker
       fits an 80-column terminal: 1 border + 1 padding + 53 (left column, of
       which cbut's six preset chips use 52) + 1 margin + 21 (7 day cells of 3,
       and 6 hour cells of 3) + 1 padding + 1 border = 79. The day and hour
       cells are Statics, not Buttons: a Button renders a two-digit label as one
       digit at width 3. On a shorter terminal the screen scrolls rather than
       crushing the layout; the tests assert the roomy geometry at 80x30. */
    #dr-box { width: auto; height: auto; border: round $primary;
              background: $surface; padding: 1 1; }
    #dr-left { width: 53; height: auto; }
    #dr-presets { height: auto; }
    .dr-card { border: round $panel; height: auto; padding: 0 1; margin-top: 1; }
    .dr-card.-active { border: round $accent; background: $boost; }
    .dr-card-title { color: $text-muted; text-style: bold; }
    .dr-fields { height: auto; }
    #dr-start-date, #dr-end-date { width: 1fr; margin: 0 1 0 0; }
    /* An Input spends 6 cells on its border and its 0-2 padding, so 16 is what
       a 5-cell "23:59" needs with room to type over it. */
    #dr-start-time, #dr-end-time { width: 16; }
    /* The quick-time rows: one cell tall, so five chips + four chips cost two
       rows rather than six. 5 × (5 + 2 padding + 1 margin) = 40 ≤ 57. */
    #dr-start-quick, #dr-end-quick { height: auto; }
    #dr-follow { height: auto; }
    #dr-nudge { height: auto; }
    /* A bare Static in a Horizontal takes the whole row and pushes the buttons
       past the column (and off the modal), so the label is pinned to its own
       cells. */
    #dr-nudge .dr-card-title { width: 7; }
    #dr-actions { height: auto; align-horizontal: right; }
    #dr-cal { width: 21; height: auto; margin-left: 1; }
    #dr-cal-head { height: auto; align: center middle; }
    #dr-cal-month { width: 1fr; text-align: center; text-style: bold; }
    #dr-cal-grid { grid-size: 7; grid-gutter: 0; height: auto; }
    /* 6 columns of 3 = 18 of the 21 available, so the 24 hours land in 4 rows
       under the month. */
    #dr-hour-grid { grid-size: 6; grid-gutter: 0; height: auto; margin-top: 1; }
    /* Every rule that touches a Button is scoped by an id: Button's own
       `Button:ansi.-style-default` selector outranks a bare class, so
       `.dr-day { border: none }` would silently lose and the calendar would
       render with tall borders and no room for the number. */
    /* cbut's preset chips: three rows tall, a cell of padding each side, and a
       cell of air between them. The six chips use 52 of the 53-cell column, so
       "All time" keeps its full label. */
    #dr-presets Button { width: auto; min-width: 0; height: 3; border: none;
                         padding: 0 1; margin: 0 1 0 0; background: $boost;
                         color: $foreground; }
    #dr-start-quick Button, #dr-end-quick Button {
                         width: auto; min-width: 0; height: 1; border: none;
                         padding: 0 1; margin: 0 1 0 0; background: $boost;
                         color: $foreground; }
    #dr-nudge Button { width: auto; min-width: 0; height: 1; border: none;
                       padding: 0 1; margin: 0 1 0 0; background: $boost;
                       color: $foreground; }
    /* -selected, not -active: Button uses -active for its own 0.2s pressed
       effect and strips it on a timer, so the chosen step flickered off. */
    #dr-nudge Button.-selected { background: $accent; color: $text;
                                 text-style: bold; }
    #dr-actions Button { width: auto; min-width: 0; margin-left: 1; }
    #dr-cal-head Button { width: auto; min-width: 0; border: none;
                          background: $surface; color: $foreground; }
    #dr-cal-grid .dr-dow { text-align: center; color: $text-muted; }
    /* 3, not 4: a Static renders "30" at width 3, where a Button shows " 3 ".
       The clicks are read from the cell id in on_click. */
    #dr-cal-grid .dr-day { width: 3; height: 1; text-align: center;
                           background: $surface; color: $foreground; }
    #dr-cal-grid .dr-day.-other { color: $text-disabled; }
    #dr-cal-grid .dr-day.-today { color: $accent; text-style: bold; }
    #dr-cal-grid .dr-day.-selected { background: $accent; color: $text;
                                     text-style: bold; }
    #dr-hour-grid .dr-hour { width: 3; height: 1; text-align: center;
                             background: $surface; color: $foreground; }
    #dr-hour-grid .dr-hour.-selected { background: $accent; color: $text;
                                       text-style: bold; }
    """

    def __init__(self, current, now_ms: int, id: str | None = None):
        super().__init__(id=id)
        self._current = current
        self._now = now_ms
        self._active = "start"       # which card the calendar writes into
        self._step = self.STEPS[0][1]   # minutes per ↑/↓ nudge
        self._view = datetime.fromtimestamp(now_ms / 1000).date().replace(day=1)
        # What we last wrote into each field, so a *user* edit can be told from
        # our own prefill/preset write (both post Input.Changed).
        self._written = {}

    def compose(self) -> ComposeResult:
        with Horizontal(id="dr-box"):
            with Vertical(id="dr-left"):
                with Horizontal(id="dr-presets"):
                    for label, wid, _key in self.PRESETS:
                        yield Button(label, id=wid)
                with Vertical(id="dr-start-card", classes="dr-card"):
                    yield Static("START TIME", classes="dr-card-title")
                    with Horizontal(classes="dr-fields"):
                        yield Input(placeholder="MM/DD/YYYY", id="dr-start-date")
                        yield TimeInput(placeholder="00:00", id="dr-start-time")
                    with Horizontal(id="dr-start-quick"):
                        for i, label in enumerate(self.QUICK_START):
                            yield Button(label, id=f"dr-start-quick-{i}")
                with Vertical(id="dr-end-card", classes="dr-card"):
                    yield Static("END TIME", classes="dr-card-title")
                    with Horizontal(classes="dr-fields"):
                        yield Input(placeholder="MM/DD/YYYY", id="dr-end-date")
                        yield TimeInput(placeholder="00:00", id="dr-end-time")
                    with Horizontal(id="dr-end-quick"):
                        for i, label in enumerate(self.QUICK_END):
                            yield Button(label, id=f"dr-end-quick-{i}")
                yield Checkbox("End time follows current time", True,
                               id="dr-follow")
                with Horizontal(id="dr-nudge"):
                    yield Static("step", classes="dr-card-title")
                    for label, minutes in self.STEPS:
                        yield Button(label, id=f"dr-step-{minutes}")
                with Horizontal(id="dr-actions"):
                    yield Button("Cancel", id="dr-cancel")
                    yield Button("Confirm", variant="primary", id="dr-ok")
            with Vertical(id="dr-cal"):
                with Horizontal(id="dr-cal-head"):
                    yield Button("‹", id="dr-prev")
                    yield Static("", id="dr-cal-month")
                    yield Button("›", id="dr-next")
                with Grid(id="dr-cal-grid"):
                    for dow in self.DOW:
                        yield Static(dow, classes="dr-dow")
                    for i in range(self.CELLS):
                        # A Static, not a Button: a Button renders the two-digit
                        # label "30" as " 3 " at a 3-cell width, and widening
                        # every cell to 4 would not fit the calendar beside the
                        # cards. The day is read from the cell id in on_click.
                        yield Static("", id=f"dr-day-{i}", classes="dr-day")
                with Grid(id="dr-hour-grid"):
                    for h in range(self.HOURS):
                        # Zero-padded id and label: the id is parsed back with
                        # rsplit("-", 1), so an id the label does not match
                        # would be a second spelling to keep in step.
                        yield Static(f"{h:02d}", id=f"dr-hour-{h:02d}",
                                     classes="dr-hour")

    def on_mount(self) -> None:
        self._prefill()
        self.query_one("#dr-box").border_subtitle = "Supports both date and time"
        self._set_active("start")
        self._render_steps()

    # -- prefill from the tab's current window ------------------------------

    def _prefill(self) -> None:
        cur = self._current
        follow = True
        if isinstance(cur, CustomWindow):
            start, end, follow = cur.start_ms, cur.end_ms, cur.follow_now
        else:
            start, end = window_bounds(cur if cur is not None else "all",
                                          self._now)
        self._set_field("#dr-start", start)
        # A following end shows *now*; a fixed one shows the stored bound.
        self._set_field("#dr-end", self._now if follow else end)
        self.query_one("#dr-follow", Checkbox).value = follow
        anchor = start if start is not None else self._now
        self._view = datetime.fromtimestamp(anchor / 1000).date().replace(day=1)

    def _set_field(self, prefix: str, ms_value) -> None:
        date_in = self.query_one(f"{prefix}-date", Input)
        time_in = self.query_one(f"{prefix}-time", Input)
        if ms_value is None:
            date_in.value = time_in.value = ""
        else:
            dt = datetime.fromtimestamp(ms_value / 1000)
            date_in.value = format_date(dt)
            time_in.value = format_time(dt.hour, dt.minute)
        self._written[date_in.id] = date_in.value
        self._written[time_in.id] = time_in.value
        self._render_hours()

    def _follows_now(self) -> bool:
        return self.query_one("#dr-follow", Checkbox).value

    # -- the calendar --------------------------------------------------------

    def _grid_start(self) -> date:
        """The date in cell 0: the first day of the view, back to Sunday."""
        lead = (self._view.weekday() + 1) % 7      # Sunday-first column
        return self._view - timedelta(days=lead)

    def _day_at(self, index: int) -> date:
        return self._grid_start() + timedelta(days=index)

    def _active_date(self):
        """The active card's typed date, or ``None`` if it is blank/bad."""
        try:
            return parse_date(
                self.query_one(f"#dr-{self._active}-date", Input).value,
                self._view.year).date()
        except ValueError:
            return None

    def _render_calendar(self) -> None:
        today = datetime.fromtimestamp(self._now / 1000).date()
        chosen = self._active_date()
        self.query_one("#dr-cal-month", Static).update(
            self._view.strftime("%B %Y"))
        for i in range(self.CELLS):
            day = self._day_at(i)
            cell = self.query_one(f"#dr-day-{i}", Static)
            cell.update(str(day.day))
            cell.set_class(day.month != self._view.month, "-other")
            cell.set_class(day == today, "-today")
            cell.set_class(day == chosen, "-selected")

    def _step_month(self, delta: int) -> None:
        month = self._view.month + delta
        year = self._view.year + (month - 1) // 12
        self._view = date(year, (month - 1) % 12 + 1, 1)
        self._render_calendar()

    # -- the hour grid -------------------------------------------------------

    def _active_time(self):
        """The active card's typed time as ``(hour, minute)``, or ``None``."""
        try:
            return parse_time(
                self.query_one(f"#dr-{self._active}-time", Input).value)
        except ValueError:
            return None

    def _render_hours(self) -> None:
        """Mark the active card's hour in the 24-cell grid."""
        parsed = self._active_time()
        hour = parsed[0] if parsed else None
        for h in range(self.HOURS):
            # The same zero padding the cells are built with: an id written two
            # ways is a second spelling to keep in step, and this one broke the
            # whole modal the moment the cells gained it.
            self.query_one(f"#dr-hour-{h:02d}", Static).set_class(
                h == hour, "-selected")

    def _pick_hour(self, hour: int) -> None:
        """Write a clicked hour into the active card, keeping its minute.

        The grid is the calendar's other half: the day cells set the date, these
        set the hour, and both land in whichever card is active.
        """
        parsed = self._active_time()
        minute = parsed[1] if parsed else 0
        self._write_time(self._active, format_time(hour, minute))

    def _write_time(self, card: str, value: str) -> None:
        """Set one card's time field, and fix the end if that is the card."""
        if card == "end":
            # A chosen end time means a fixed end, not "now".
            self.query_one("#dr-follow", Checkbox).value = False
        self.query_one(f"#dr-{card}-time", Input).value = value
        self._written[f"dr-{card}-time"] = value
        self._render_hours()

    def _pick_day(self, index: int) -> None:
        """Write a clicked day into the active card."""
        day = self._day_at(index)
        if self._active == "end":
            # Choosing an end date means a fixed end, not "now".
            self.query_one("#dr-follow", Checkbox).value = False
        self.query_one(f"#dr-{self._active}-date", Input).value = format_date(day)
        self._written[f"dr-{self._active}-date"] = format_date(day)
        if (day.year, day.month) != (self._view.year, self._view.month):
            self._view = day.replace(day=1)
        self._render_calendar()

    def _set_active(self, which: str) -> None:
        self._active = which
        self.query_one("#dr-start-card").set_class(which == "start", "-active")
        self.query_one("#dr-end-card").set_class(which == "end", "-active")
        self._render_calendar()
        self._render_hours()

    # -- presets -------------------------------------------------------------

    def _apply_preset(self, key: str) -> None:
        start, _ = window_bounds(key, self._now)
        self._set_field("#dr-start", start)
        self.query_one("#dr-follow", Checkbox).value = True
        if start is not None:
            self._view = datetime.fromtimestamp(start / 1000).date().replace(day=1)
        self._render_calendar()

    def _apply_quick(self, card: str, label: str) -> None:
        """A quick-time chip: ``now`` re-follows the clock, a time fixes it."""
        if label == "now":
            self._set_field("#dr-end", self._now)
            self.query_one("#dr-follow", Checkbox).value = True
            self._render_hours()
            return
        hour, minute = parse_time(label)
        self._write_time(card, format_time(hour, minute))

    # -- nudge step ----------------------------------------------------------

    def _set_step(self, minutes: int) -> None:
        self._step = minutes
        for wid in ("#dr-start-time", "#dr-end-time"):
            self.query_one(wid, TimeInput).step = minutes
        self._render_steps()

    def _render_steps(self) -> None:
        for _label, minutes in self.STEPS:
            self.query_one(f"#dr-step-{minutes}", Button).set_class(
                minutes == self._step, "-selected")

    # -- confirm -------------------------------------------------------------

    def _confirm(self) -> None:
        follow = self._follows_now()
        year = self._view.year
        try:
            start = parse_datetime(
                self.query_one("#dr-start-date", Input).value,
                self.query_one("#dr-start-time", Input).value, year)
            end = None if follow else parse_datetime(
                self.query_one("#dr-end-date", Input).value,
                self.query_one("#dr-end-time", Input).value, year)
        except ValueError:
            self.notify("Dates are MM/DD/YYYY, times HH:MM (24-hour)",
                        severity="error")
            return
        if not follow and end is None:
            self.notify("Set an end date, or tick 'End follows current time'",
                        severity="error")
            return
        if start is not None and end is not None and end < start:
            self.notify("End is before start", severity="error")
            return
        self.dismiss(CustomWindow(start, end, follow))

    def action_cancel(self) -> None:
        self.dismiss(None)

    # -- events --------------------------------------------------------------

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        if event.checkbox.id == "dr-follow" and event.value:
            # Ticking "follows current time" puts the end back on now.
            self._set_field("#dr-end", self._now)

    def on_input_changed(self, event: Input.Changed) -> None:
        # A *user* edit of an end field means a fixed end, so drop the follow
        # switch. Our own prefill/preset writes are ignored by matching the
        # value we recorded.
        wid = event.input.id or ""
        if wid.endswith("-time"):
            self._render_hours()      # a typed hour re-marks the grid
        if not wid.startswith("dr-end") or not self._follows_now():
            return
        if self._written.get(wid) == event.value:
            return
        self.query_one("#dr-follow", Checkbox).value = False

    def on_click(self, event) -> None:
        # A calendar day and an hour cell are Statics, so their clicks arrive
        # here rather than as a Button.Pressed — read the index from the id.
        wid = getattr(event.widget, "id", "") or ""
        if wid.startswith("dr-day-"):
            self._pick_day(int(wid.rsplit("-", 1)[1]))
            return
        if wid.startswith("dr-hour-"):
            self._pick_hour(int(wid.rsplit("-", 1)[1]))
            return
        # Clicking anywhere on a card makes it the calendar's target.
        node = event.widget
        while node is not None:
            if getattr(node, "has_class", None) and node.has_class("dr-card"):
                self._set_active(
                    "start" if node.id == "dr-start-card" else "end")
                return
            node = getattr(node, "parent", None)

    def on_descendant_focus(self, event) -> None:
        wid = getattr(event.control, "id", "") or ""
        if wid.startswith("dr-start"):
            self._set_active("start")
        elif wid.startswith("dr-end"):
            self._set_active("end")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        preset = next((key for _l, wid, key in self.PRESETS if wid == bid), None)
        if preset is not None:
            self._apply_preset(preset)
        elif bid.startswith("dr-start-quick-"):
            self._apply_quick("start", self.QUICK_START[int(bid.rsplit("-", 1)[1])])
        elif bid.startswith("dr-end-quick-"):
            self._apply_quick("end", self.QUICK_END[int(bid.rsplit("-", 1)[1])])
        elif bid.startswith("dr-step-"):
            self._set_step(int(bid.rsplit("-", 1)[1]))
        elif bid == "dr-prev":
            self._step_month(-1)
        elif bid == "dr-next":
            self._step_month(1)
        elif bid == "dr-cancel":
            self.dismiss(None)
        elif bid == "dr-ok":
            self._confirm()


