"""The board: six tabs over the same three indexes.

The shape is the tracker family's — a top bar carrying the window, TabbedContent
in the middle, one table per tab, a status line at the bottom — because the point
of a fourth tool is to cost nothing to learn. What is new is only what a single
tracker cannot answer: a skill's calls across all three, a model's tokens across
all three, one timeline, and a dashboard that compares this window with the last.

Handing the terminal to a tracker's own TUI is still `suspend()` + its binary;
that lives on the Sources tab, where a row means a tool rather than a number.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

from rich.text import Text

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, DataTable, Input, Select, Static, TabbedContent, TabPane

import aut_model as model
from aut_db import fmt_age, fmt_tokens, sparkline
from aut_picker import (CustomWindow, DateRangeModal, RANGE_LABELS, bounds_of,
                        window_label)
from aut_sources import BY_KEY, SOURCES, snapshots

# Per-tab default window, the family's rule: the summary tabs open on today, the
# entity tabs on the week.
DEFAULT_RANGES = {
    "dashboard": "1d", "tools": "7d",
    # Skills are rare — a week is often one call each — so this tab opens on a
    # month. It is the one deliberate deviation from the family's 7-day default,
    # and the reason is the data, not taste.
    "skills": "30d",
    "tokens": "1d", "usage": "1d", "sources": "1d",
}

TAB_ORDER = ("dashboard", "tools", "skills", "tokens", "usage", "sources")

# One colour per source, used by every tab. Scanning for "which tool" should be a
# colour match, not a word match.
SOURCE_STYLE = {"cbut": "cyan", "ocut": "yellow", "qcut": "magenta"}

HELP = """
  tab / shift+tab   next / previous tab         1 - 6   jump to a tab
  s                 cycle the sort order        /       filter rows
  d                 date range                  esc     clear the filter
  enter             open the selected row's detail
  g                 Tokens only: group by model or by source
  r                 sync the three trackers now (runs their own sync)
  ?                 this help                  q       quit

  Sources tab: enter opens that tracker's own TUI; q there returns here.
  There is no 'a' key: the trackers use it for "installed but never used",
  which has no cross-tool equivalent here.
"""

HINT = "tab switch · s sort · / filter · d date · enter detail · g group · r sync · ? help · q quit"


def _shorten(path: str) -> str:
    home = str(Path.home())
    return "~" + path[len(home):] if path.startswith(home) else path


def _human_size(size: int) -> str:
    if size <= 0:
        return "—"
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    return f"{size / 1024:.0f} KB"


def _avg(ms: float | None) -> str:
    if ms is None:
        return "—"
    if ms >= 1000:
        return f"{ms / 1000:.1f}s"
    return f"{ms:.0f}ms"


def _delta(now: int, prev: int | None) -> Text:
    """A change against the previous window, or nothing when there is no base."""
    if prev is None:
        return Text("—", style="dim")
    if prev <= 0:
        return Text("new", style="green")
    pct = (now - prev) / prev * 100
    arrow = "↑" if pct >= 0 else "↓"
    style = "red" if pct >= 0 else "green"   # more tokens is not "good"
    return Text(f"{arrow}{abs(pct):.0f}%", style=style)


class HelpScreen(ModalScreen[None]):
    BINDINGS = [Binding("escape,q,question_mark,enter", "dismiss", "close")]

    def compose(self) -> ComposeResult:
        with Vertical(id="help-box"):
            yield Static("[b]aut[/b] — keys", id="help-title")
            yield Static(HELP.strip("\n"))

    def action_dismiss(self) -> None:
        self.dismiss()


class Pane(Vertical):
    """Every tab answers the same four questions; the base says so."""

    TAB_KEY = ""

    def reload(self, window) -> None:
        raise NotImplementedError

    def action_sort(self) -> None:
        pass

    def action_open_filter(self) -> None:
        pass

    def clear_filter(self) -> None:
        pass

    def open_selected(self) -> None:
        pass

    def group_toggle(self) -> None:
        pass

    def status(self) -> str:
        return ""


class TablePane(Pane):
    """A table, a filter, a sort order — the shape five of the six tabs share."""

    COLUMNS: tuple[str, ...] = ()
    COLUMN_WIDTHS: tuple[int | None, ...] = ()
    SORT_FIELDS: tuple[tuple[str, str], ...] = ()   # (label, attribute)

    DEFAULT_CSS = """
    TablePane { height: 1fr; }
    TablePane #filter { display: none; height: 1; margin: 0 1; }
    TablePane #filter.-on { display: block; }
    TablePane #note { height: 1; padding: 0 1; color: $text-muted; }
    TablePane DataTable { height: 1fr; }
    """

    def __init__(self) -> None:
        super().__init__()
        self.window = None
        self.needle = ""
        self.sort_index = 0
        self._rows: list = []

    def compose(self) -> ComposeResult:
        yield Input(placeholder="filter…", id="filter")
        yield DataTable(id="table", cursor_type="row", zebra_stripes=True)
        yield Static("", id="note")

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        if self.COLUMN_WIDTHS:
            for name, width in zip(self.COLUMNS, self.COLUMN_WIDTHS):
                table.add_column(name, width=width)
        else:
            table.add_columns(*self.COLUMNS)

    # subclasses implement these three
    def fetch(self, window) -> list:
        raise NotImplementedError

    def cells(self, row) -> tuple:
        raise NotImplementedError

    def matches(self, row, needle: str) -> bool:
        return needle in " ".join(str(c) for c in self.cells(row)).lower()

    def note(self, window, rows: list) -> str:
        return ""

    def sort_key(self):
        if not self.SORT_FIELDS:
            return None
        return self.SORT_FIELDS[self.sort_index][1]

    def reload(self, window) -> None:
        self.window = window
        rows = self.fetch(window)
        if self.needle:
            rows = [r for r in rows if self.matches(r, self.needle)]
        key = self.sort_key()
        if key:
            rows.sort(key=lambda r: (getattr(r, key) is None, getattr(r, key)), reverse=True)
        self._rows = rows

        table = self.query_one(DataTable)
        cursor = max(0, table.cursor_row)
        table.clear(columns=False)
        for row in rows:
            table.add_row(*self.cells(row))
        if rows:
            table.move_cursor(row=min(cursor, len(rows) - 1))
        self.query_one("#note", Static).update(self.note(window, rows))

    def action_sort(self) -> None:
        if not self.SORT_FIELDS:
            return
        self.sort_index = (self.sort_index + 1) % len(self.SORT_FIELDS)
        self.reload(self.window)

    def action_open_filter(self) -> None:
        box = self.query_one("#filter", Input)
        box.add_class("-on")
        box.focus()

    def clear_filter(self) -> None:
        box = self.query_one("#filter", Input)
        if box.has_class("-on"):
            box.value = ""
            box.remove_class("-on")
            self.needle = ""
            self.query_one(DataTable).focus()
            self.reload(self.window)

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "filter":
            return
        self.needle = event.value.strip().lower()
        self.reload(self.window)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.open_selected()

    def selected(self):
        table = self.query_one(DataTable)
        if not self._rows:
            return None
        index = table.cursor_row
        return self._rows[index] if 0 <= index < len(self._rows) else None

    def sort_label(self) -> str:
        if not self.SORT_FIELDS:
            return ""
        return self.SORT_FIELDS[self.sort_index][0]

    def status(self) -> str:
        bits = [f"{len(self._rows)} rows"]
        if self.sort_label():
            bits.append(f"sort {self.sort_label()}")
        if self.needle:
            bits.append(f"filter {self.needle!r}")
        return " · ".join(bits)


class TokensPane(TablePane):
    TAB_KEY = "tokens"
    COLUMNS = ("source", "model", "provider", "input", "output", "cache r",
               "cache w", "total", "req", "last used")
    SORT_FIELDS = (("tokens", "total"), ("requests", "requests"),
                   ("recent", "last_used"), ("name", "model"))

    def __init__(self) -> None:
        super().__init__()
        self.by_source = False

    def fetch(self, window):
        start, end = bounds_of(window, model.now_ms())
        rows = model.token_rows(start, end)
        return model.by_source(rows) if self.by_source else rows

    def cells(self, row):
        return (
            Text(row.label, style=SOURCE_STYLE.get(row.source, "")),
            row.model,
            row.provider or "—",
            fmt_tokens(row.input),
            fmt_tokens(row.output),
            fmt_tokens(row.cache_read),
            fmt_tokens(row.cache_write),
            fmt_tokens(row.total),
            f"{row.requests:,}",
            fmt_age(row.last_used),
        )

    def group_toggle(self) -> None:
        self.by_source = not self.by_source
        self.reload(self.window)

    def note(self, window, rows) -> str:
        grouped = "by source" if self.by_source else "by model"
        total = sum(r.total for r in rows)
        return (f"{grouped} · total {fmt_tokens(total)} · "
                "total is each host's own column (cache included where the host reports it)")

    def open_selected(self) -> None:
        row = self.selected()
        if row is None or row.model == "(all models)":
            return
        self.app.push_screen(ModelScreen(row.model, row.source, self.window))


class EntityPane(TablePane):
    """Skills and Tools: one row per name, one column per source."""

    SORT_FIELDS = (("calls", "calls"), ("recent", "last_used"), ("name", "name"))

    def __init__(self, kind: str) -> None:
        super().__init__()
        self.kind = kind
        self.TAB_KEY = kind
        self.COLUMNS = ("name", "total", "cbut", "ocut", "qcut", "ok", "fail",
                        "avg", "last used")

    def fetch(self, window):
        start, end = bounds_of(window, model.now_ms())
        return model.entity_rows(self.kind, start, end)

    def cells(self, row):
        def per(key):
            value = row.per_source.get(key)
            if not value:
                return Text("—", style="dim")
            return Text(str(value), style=SOURCE_STYLE.get(key, ""))

        return (row.name, str(row.calls), per("cbut"), per("ocut"), per("qcut"),
                str(row.ok), str(row.fail) if row.fail else Text("0", style="dim"),
                _avg(row.avg_ms), fmt_age(row.last_used))

    def note(self, window, rows) -> str:
        shared = sum(1 for r in rows if len([v for v in r.per_source.values() if v]) > 1)
        return (f"{len(rows)} {self.kind} · {shared} used by more than one tracker"
                " · ok = completed, fail = error/incomplete")

    def open_selected(self) -> None:
        row = self.selected()
        if row is not None:
            self.app.push_screen(EntityScreen(row.name, self.kind, self.window))


class UsagePane(TablePane):
    TAB_KEY = "usage"
    COLUMNS = ("when", "source", "model", "tokens", "project", "session")
    COLUMN_WIDTHS = (10, 10, 24, 8, 30, 10)
    SORT_FIELDS = (("time", "ts"), ("tokens", "total"), ("source", "source"))

    def fetch(self, window):
        start, end = bounds_of(window, model.now_ms())
        return model.call_rows(start, end)

    def cells(self, row):
        return (
            fmt_age(row.ts),
            Text(row.label, style=SOURCE_STYLE.get(row.source, "")),
            row.model or "—",
            fmt_tokens(row.total),
            _shorten(row.project) or "—",
            row.session[:8] or "—",
        )

    def note(self, window, rows) -> str:
        return f"{len(rows)} most recent calls across the three trackers"



class DashboardPane(Pane):
    TAB_KEY = "dashboard"

    DEFAULT_CSS = """
    DashboardPane { height: 1fr; padding: 0 1; }
    DashboardPane #kpi { height: 4; }
    DashboardPane #chart { height: auto; max-height: 12; }
    DashboardPane #tops { height: 1fr; }
    DashboardPane .top { width: 1fr; padding: 0 1; }
    """

    def __init__(self) -> None:
        super().__init__()
        self.window = None

    def compose(self) -> ComposeResult:
        yield Static(id="kpi")
        yield Static(id="chart")
        with Horizontal(id="tops"):
            yield Static(id="top-models", classes="top")
            yield Static(id="top-skills", classes="top")

    def reload(self, window) -> None:
        self.window = window
        start, end = bounds_of(window, model.now_ms())
        k = model.kpis(start, end)
        window_labels, _ = model.daily_tokens(start, end)
        # A one-day window draws one bar, which says nothing. The chart keeps a
        # week of context and says so in its title; the KPI strip above stays
        # scoped to the chosen window.
        chart_start = start
        if len(window_labels) < 7:
            # A whole-week boundary, not "now minus 7×24h": the latter spans
            # eight calendar dates and draws eight bars.
            chart_start = bounds_of("7d", end)[0]
        labels, series = model.daily_tokens(chart_start, end)
        rows = model.token_rows(start, end)
        skills = model.entity_rows("skills", start, end)

        delta = _delta(k.tokens, k.prev_tokens)
        kpi = Text()
        kpi.append(fmt_tokens(k.tokens), style="bold")
        kpi.append(" tokens   ")
        kpi.append_text(delta)
        days_word = "day" if k.active_days == 1 else "days"
        kpi.append(f"   {k.sessions:,} sessions   {k.calls:,} calls   "
                   f"{k.active_days} active {days_word}\n")
        split = "   ".join(
            f"{s.label} {fmt_tokens(k.per_source.get(s.key, 0))}"
            for s in SOURCES if s.key in k.per_source
        )
        kpi.append(split or "no data in this window", style="dim")
        self.query_one("#kpi", Static).update(kpi)

        chart = Text()
        context = " · context" if len(labels) > len(window_labels) else ""
        chart.append(f"tokens per day · {len(labels)}d{context}\n", style="bold")
        for source in SOURCES:
            values = series.get(source.key)
            if not values:
                continue
            chart.append(f"  {source.label:<10}", style=SOURCE_STYLE.get(source.key, ""))
            chart.append(sparkline(values) + "  ")
            chart.append(f"{fmt_tokens(sum(values))}\n", style="dim")
        if len(series) > 1:
            combined = [sum(v[i] for v in series.values()) for i in range(len(labels))]
            chart.append("  all        ", style="bold")
            chart.append(sparkline(combined) + "  ")
            chart.append(f"{fmt_tokens(sum(combined))}\n", style="dim")
        self.query_one("#chart", Static).update(chart or Text("no tokens recorded in this window"))

        self.query_one("#top-models", Static).update(
            self._top("models", [(r.model, r.total, r.label) for r in
                                sorted(rows, key=lambda r: r.total, reverse=True)[:6]])
        )
        self.query_one("#top-skills", Static).update(
            self._top("skills", [(r.name, r.calls, ",".join(
                k for k, v in r.per_source.items() if v)) for r in
                sorted(skills, key=lambda r: r.calls, reverse=True)[:6]], unit="calls")
        )

    def _top(self, title, items, unit="tokens") -> Text:
        out = Text(f"top {title}\n", style="bold")
        if not items:
            out.append("  nothing in this window", style="dim")
            return out
        width = max(len(str(name)) for name, _, _ in items)
        for name, value, meta in items:
            shown = fmt_tokens(value) if unit == "tokens" else f"{value:,}"
            out.append(f"  {str(name):<{width}}  {shown:>7}  ", style="")
            out.append(f"{meta}\n", style="dim")
        return out

    def status(self) -> str:
        return ""


class SourcesPane(Pane):
    """The old board: health, and the way into each tracker's own TUI."""

    TAB_KEY = "sources"

    DEFAULT_CSS = """
    SourcesPane { height: 1fr; }
    SourcesPane DataTable { height: 1fr; }
    SourcesPane #note { height: 1; padding: 0 1; color: $text-muted; }
    """

    COLUMNS = ("source", "tokens", "sessions", "7d trend", "last seen", "state", "index")

    def __init__(self) -> None:
        super().__init__()
        self.window = None
        self._snaps: list = []
        self._trend: dict = {}

    def compose(self) -> ComposeResult:
        yield DataTable(id="table", cursor_type="row", zebra_stripes=True)
        yield Static(id="note")

    def on_mount(self) -> None:
        self.query_one(DataTable).add_columns(*self.COLUMNS)

    def reload(self, window) -> None:
        self.window = window
        start, end = bounds_of(window, model.now_ms())
        days = 0 if start is None else max(1, round((end - start) / 86_400_000))
        self._snaps = snapshots(days)
        # The trend column is always a week, even when the numbers are today's:
        # a one-bar "trend" is not a trend.
        self._trend = {s.key: s.buckets for s in snapshots(7)}
        table = self.query_one(DataTable)
        cursor = max(0, table.cursor_row)
        table.clear(columns=False)
        for snap in self._snaps:
            live = snap.status in ("ok", "idle")
            table.add_row(
                Text(snap.label, style=SOURCE_STYLE.get(snap.key, "")),
                fmt_tokens(snap.tokens),
                str(snap.sessions) if live else "—",
                sparkline(self._trend.get(snap.key, snap.buckets)),
                fmt_age(snap.last_event_ms),
                Text(snap.status, style="green" if live else "red"),
                _human_size(snap.db_size),
            )
        if self._snaps:
            table.move_cursor(row=min(cursor, len(self._snaps) - 1))
        self.query_one("#note", Static).update(
            "enter opens that tracker's own TUI · r syncs all three"
        )

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.open_selected()

    def open_selected(self) -> None:
        table = self.query_one(DataTable)
        index = table.cursor_row
        if 0 <= index < len(self._snaps):
            self.app.open_tracker(self._snaps[index].key)

    def status(self) -> str:
        return "enter opens a tracker"


class CallsTable(Vertical):
    """A plain list of calls, used by both detail screens."""

    DEFAULT_CSS = """
    CallsTable { height: 1fr; }
    CallsTable DataTable { height: 1fr; }
    """

    COLUMNS = ("when", "source", "model", "tokens", "project", "session")

    def __init__(self, rows) -> None:
        super().__init__()
        self._rows = rows

    def compose(self) -> ComposeResult:
        yield DataTable(id="calls", cursor_type="row", zebra_stripes=True)

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns(*self.COLUMNS)
        for row in self._rows:
            table.add_row(
                fmt_age(row.ts),
                Text(row.label, style=SOURCE_STYLE.get(row.source, "")),
                row.model or "—",
                fmt_tokens(row.total),
                _shorten(row.project) or "—",
                row.session[:8] or "—",
            )


class ModelScreen(Screen[None]):
    BINDINGS = [Binding("escape,q", "app.pop_screen", "Back")]

    DEFAULT_CSS = """
    ModelScreen #head { height: 4; padding: 1 1 0 1; }
    """

    def __init__(self, model_name: str, source: str, window) -> None:
        super().__init__()
        # 'name' is a Textual DOMNode property; using it here raises at mount.
        self.model_name = model_name
        self.source = source
        self.window = window

    def compose(self) -> ComposeResult:
        start, end = bounds_of(self.window, model.now_ms())
        calls = model.model_calls(self.source, self.model_name, start, end)
        labels, series = model.model_daily(self.source, self.model_name, start, end)
        total = sum(c.total for c in calls)
        head = Text()
        head.append(f"{self.model_name}\n", style="bold")
        head.append(f"{BY_KEY[self.source].label} · {window_label(self.window)} · "
                    f"{len(calls)} calls · {fmt_tokens(total)} tokens\n")
        head.append(sparkline(series) + f"  {len(labels)}d\n")
        yield Static(head, id="head")
        yield CallsTable(calls)


class EntityScreen(Screen[None]):
    BINDINGS = [Binding("escape,q", "app.pop_screen", "Back")]

    DEFAULT_CSS = """
    EntityScreen #head { height: 3; padding: 1 1 0 1; }
    """

    def __init__(self, entity_name: str, kind: str, window) -> None:
        super().__init__()
        self.entity_name = entity_name
        self.kind = kind
        self.window = window

    def compose(self) -> ComposeResult:
        start, end = bounds_of(self.window, model.now_ms())
        rows = model.entity_calls(self.kind, self.entity_name, start, end)
        head = Text()
        head.append(f"{self.entity_name}\n", style="bold")
        head.append(f"{self.kind} · {window_label(self.window)} · {len(rows)} calls\n")
        yield Static(head, id="head")
        yield CallsTable(rows)


class AutApp(App[None]):
    TITLE = "aut"
    SUB_TITLE = "all usage trackers"

    CSS = """
    Screen { background: $surface; }
    #bar { dock: top; height: 1; background: $panel; color: $foreground; }
    #bar #title { width: 1fr; padding: 0 1; content-align: left middle; }
    #bar #custom { width: auto; min-width: 0; height: 1; border: none;
                   padding: 0 1; background: $panel; color: $accent;
                   text-style: bold; }
    #bar #custom:hover { background: $boost; }
    #bar #range { width: 24; }
    #bar SelectCurrent { border: none; padding: 0 1; background: $panel;
                         color: $accent; }
    #status { dock: bottom; height: 1; padding: 0 1; background: $boost; }
    #hint { dock: bottom; height: 1; padding: 0 1; color: $text-muted; }
    TabbedContent { height: 1fr; }
    #help-box { width: 74; height: auto; padding: 1 2; background: $panel;
                border: round $accent; margin: 2 4; }
    #help-title { padding: 0 0 1 0; }
    """

    BINDINGS = [
        Binding("q", "quit", "quit"),
        Binding("r", "sync", "sync"),
        Binding("s", "sort", "sort"),
        Binding("slash", "filter", "filter"),
        Binding("d", "date_range", "date"),
        Binding("g", "group", "group"),
        Binding("enter", "open_row", "open"),
        Binding("tab", "next_tab", "next tab", priority=True),
        Binding("shift+tab", "prev_tab", "prev tab", priority=True),
        Binding("1", "goto_tab(0)", "1", show=False),
        Binding("2", "goto_tab(1)", "2", show=False),
        Binding("3", "goto_tab(2)", "3", show=False),
        Binding("4", "goto_tab(3)", "4", show=False),
        Binding("5", "goto_tab(4)", "5", show=False),
        Binding("6", "goto_tab(5)", "6", show=False),
        Binding("question_mark", "help", "help"),
        Binding("escape", "clear_filter", "clear", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.windows = dict(DEFAULT_RANGES)
        self._synced_ms = int(time.time() * 1000)

    def compose(self) -> ComposeResult:
        with Horizontal(id="bar"):
            yield Static("[b]aut[/b] · all usage trackers", id="title")
            yield Button("📅 Custom…", id="custom")
            yield Select(
                [(RANGE_LABELS[k], k) for k in ("1d", "2d", "3d", "7d", "14d", "30d", "all")],
                value="1d", allow_blank=False, id="range",
            )
        with TabbedContent(initial="tab-dashboard"):
            with TabPane("Dashboard", id="tab-dashboard"):
                yield DashboardPane()
            with TabPane("Tools", id="tab-tools"):
                yield EntityPane("tools")
            with TabPane("Skills", id="tab-skills"):
                yield EntityPane("skills")
            with TabPane("Tokens", id="tab-tokens"):
                yield TokensPane()
            with TabPane("Usage", id="tab-usage"):
                yield UsagePane()
            with TabPane("Sources", id="tab-sources"):
                yield SourcesPane()
        yield Static(id="status")
        yield Static(HINT, id="hint")

    def on_mount(self) -> None:
        self.reload_active()
        self._focus_table()

    def _focus_table(self) -> None:
        """Keep the keyboard on the data, not on the top bar's button.

        Without this the first focusable widget (the custom-range button) holds
        focus, and pressing enter opens the calendar instead of the selected row.
        """
        try:
            self.pane().query_one(DataTable).focus()
        except Exception:
            pass

    # -- plumbing ----------------------------------------------------------

    def pane(self) -> Pane:
        active = self.query_one(TabbedContent).active
        key = active.replace("tab-", "")
        for pane in self.query(Pane):
            if pane.TAB_KEY == key:
                return pane
        raise RuntimeError(f"no pane for {active}")

    def reload_active(self) -> None:
        pane = self.pane()
        window = self.windows.get(pane.TAB_KEY, "1d")
        pane.reload(window)
        self._update_bar(window)

    def _update_bar(self, window) -> None:
        label = window_label(window)
        try:
            button = self.query_one("#custom", Button)
            # The Select can only name a preset; the button is what names a
            # custom span, so the bar never says "Today" while showing a week.
            button.label = (f"📅 {label} ▾" if isinstance(window, CustomWindow)
                            else "📅 Custom…")
            button.refresh(layout=True)
        except Exception:
            pass
        try:
            select = self.query_one("#range", Select)
            if isinstance(window, str) and select.value != window:
                select.value = window
        except Exception:
            pass
        parts = [f"[b]{label}[/b]"]
        pane_status = self.pane().status()
        if pane_status:
            parts.append(pane_status)
        parts.append(f"synced {fmt_age(self._synced_ms)}")
        self.query_one("#status", Static).update("   ·   ".join(parts))

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        self.reload_active()
        self._focus_table()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id != "range" or event.value in (None, Select.BLANK):
            return
        self.windows[self.pane().TAB_KEY] = str(event.value)
        self.reload_active()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "custom":
            self.action_date_range()

    # -- actions -----------------------------------------------------------

    def action_sync(self) -> None:
        for source in SOURCES:
            if shutil.which(source.binary) is None:
                self.notify(f"{source.binary} is not on PATH", severity="warning")
                continue
            with self.suspend():
                print(f"aut: syncing {source.label}", flush=True)
                subprocess.call(source.sync_argv())
        self._synced_ms = int(time.time() * 1000)
        self.reload_active()

    def action_sort(self) -> None:
        self.pane().action_sort()
        self.query_one("#status", Static).update(self.pane().status())

    def action_filter(self) -> None:
        self.pane().action_open_filter()

    def action_clear_filter(self) -> None:
        self.pane().clear_filter()

    def action_open_row(self) -> None:
        self.pane().open_selected()

    def action_group(self) -> None:
        self.pane().group_toggle()

    def action_date_range(self) -> None:
        key = self.pane().TAB_KEY
        current = self.windows.get(key, "1d")
        now = model.now_ms()

        def apply(result) -> None:
            if result is None:
                return
            self.windows[key] = result
            self.reload_active()

        self.push_screen(DateRangeModal(current, now), apply)

    def action_next_tab(self) -> None:
        self._cycle_tab(1)

    def action_prev_tab(self) -> None:
        self._cycle_tab(-1)

    def _cycle_tab(self, step: int) -> None:
        tabs = self.query_one(TabbedContent)
        current = tabs.active.replace("tab-", "")
        index = TAB_ORDER.index(current) if current in TAB_ORDER else 0
        target = TAB_ORDER[(index + step) % len(TAB_ORDER)]
        tabs.active = f"tab-{target}"

    def action_goto_tab(self, index: int) -> None:
        self.query_one(TabbedContent).active = f"tab-{TAB_ORDER[index]}"

    def action_help(self) -> None:
        self.push_screen(HelpScreen())

    def open_tracker(self, key: str) -> None:
        source = BY_KEY[key]
        if shutil.which(source.binary) is None:
            self.notify(f"{source.binary} is not on PATH — install that tracker first",
                        severity="error", timeout=6)
            return
        with self.suspend():
            print(f"aut: {source.label} — press q to come back", flush=True)
            subprocess.call(source.launch_argv())
        self.reload_active()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aut", description="overview of the local usage trackers")
    parser.add_argument("--days", type=int, default=None, help="initial window in days (1/7/30)")
    args = parser.parse_args(argv)
    app = AutApp()
    if args.days in (1, 2, 3, 7, 14, 30):
        for key in DEFAULT_RANGES:
            app.windows[key] = f"{args.days}d"
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
