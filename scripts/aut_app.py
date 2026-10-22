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
import asyncio
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
from textual.widgets import (Button, DataTable, Footer, Input, Select, Static,
                             TabbedContent, TabPane)

import aut_model as model
from aut_chart import pct, share_bar
from aut_db import DAY_MS, fmt_age, fmt_tokens, sparkline
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

# A tracker's sync parses every log it has not seen yet, so it can be slow — but
# a sync that never returns must not wedge the board.
SYNC_TIMEOUT_S = 300

# One colour per source, used by every tab. Scanning for "which tool" should be a
# colour match, not a word match.
SOURCE_STYLE = {"cbut": "cyan", "ocut": "yellow", "qcut": "magenta"}


def origin_label(per_source: dict[str, int]) -> str:
    """Which trackers put a row on the board, as one short tag.

    A merged row is the sum of several tools, so the number alone does not say
    where it came from. Kept to nine columns ("cbut+ocut") because it sits in a
    card beside the model name.
    """
    keys = [s.key for s in SOURCES if per_source.get(s.key)]
    if not keys:
        return "—"
    if len(keys) == len(SOURCES):
        return "all"
    return "+".join(keys)


HELP = """
  tab / shift+tab  next / previous tab    1 - 6  jump to a tab
  s                cycle the sort order   /      filter rows
  d                date range             esc    clear the filter
  g                Tokens: by model / model × tracker / tracker
  enter            open the selected row's detail
  r                sync the three trackers now (runs their own sync)
  ?                this help               q      quit

  The caption above each table names the sort (s) and, on Tokens, the
  grouping (g) — so neither has to be pressed to find out what it did.
  Dashboard: up/down picks a model; enter opens Tokens filtered by it.
  Sources: enter opens that tracker's own TUI; q there returns to aut.
  There is no 'a' key: the trackers use it for "installed but never used",
  which has no cross-tool equivalent here.
"""

def _clip(text: str, width: int) -> str:
    """Exactly `width` cells, with the cut marked.

    A panel row is laid out by arithmetic, so a name one cell too long is not a
    cosmetic problem: it wraps the row and the number below it reads as another
    entry.
    """
    if width <= 0:
        return ""
    return text if len(text) <= width else text[: width - 1] + "…"


def _project(path: str, width: int = 36) -> Text:
    """A project path as one table cell.

    Most OpenCode sessions run from $HOME itself, so a column of identical "~"
    says nothing. The path is shown relative to home, and a bare home is dimmed
    so it reads as "no project" rather than as a name.
    """
    if not path:
        return Text("—", style="dim")
    home = str(Path.home())
    if path == home:
        return Text("~", style="dim")
    shown = "~" + path[len(home):] if path.startswith(home + "/") else path
    if len(shown) > width:
        head = shown[: max(1, width // 3)]
        shown = head + "…" + shown[-(width - len(head) - 1):]
    return Text(shown)


def _share_cell(value: int, total: int, key: str) -> Text:
    """A proportion bar plus its percentage, as one table cell."""
    out = share_bar(value, total, width=6, style=SOURCE_STYLE.get(key, "cyan"))
    out.append(f" {pct(value, total):>3}")
    return out


def _source_split(per: dict[str, int], total: int) -> Text:
    """One line naming each tracker's share of a merged total."""
    out = Text()
    for key, value in sorted(per.items(), key=lambda kv: kv[1], reverse=True):
        label = BY_KEY[key].label if key in BY_KEY else key
        if out:
            out.append("   ")
        out.append(f"{label} ", style=SOURCE_STYLE.get(key, ""))
        out.append(f"{fmt_tokens(value)} {pct(value, total)}", style="dim")
    return out


def _human_size(size: int) -> str:
    if size <= 0:
        return "—"
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    return f"{size / 1024:.0f} KB"


def _avg(ms: float | None) -> str:
    if ms is None:
        return "—"
    if ms >= 60_000:
        return f"{ms / 60_000:.1f}m"
    if ms >= 1000:
        return f"{ms / 1000:.1f}s"
    return f"{ms:.0f}ms"


def _delta(now: int, prev: int | None) -> Text:
    """A change against the previous window, or nothing when there is no base."""
    if prev is None:
        return Text("—", style="dim")
    if prev <= 0:
        return Text("new", style="green")
    change = (now - prev) / prev * 100
    arrow = "↑" if change >= 0 else "↓"
    style = "red" if change >= 0 else "green"   # more tokens is not "good"
    return Text(f"{arrow}{abs(change):.0f}%", style=style)


class Table(DataTable):
    """DataTable with a visible enter binding.

    Textual's own binding for enter is `show=False`, so the one key that opens
    a row's detail was the one key missing from the footer. The action is the
    same `select_cursor`; only its name and visibility change.
    """

    BINDINGS = [Binding("enter", "select_cursor", "Open")]


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


class TablePane(Pane):
    """A table, a filter, a sort order — the shape five of the six tabs share."""

    COLUMNS: tuple[str, ...] = ()
    # Widths by name, so a column can be dropped on a narrow terminal without
    # every other width shifting by one.
    COLUMN_WIDTHS: dict[str, int] = {}
    # (label, attribute, column). The column is what the header marks with a
    # marker, so the reader can see what s is sorting by without pressing it.
    SORT_FIELDS: tuple[tuple[str, str, str], ...] = ()

    DEFAULT_CSS = """
    TablePane { height: 1fr; }
    /* The state line sits above the table, as it does in the three trackers:
       "N rows · sort: total" is a caption for what follows, not a footnote. */
    TablePane #note { height: auto; padding: 0 1; color: $text-muted; }
    /* A one-row Input keeps its border and draws it as ▔/▁ over the text, so
       the border is removed rather than the row made taller: the filter is a
       strip above the table, not a form field. */
    TablePane #filter { display: none; height: 1; margin: 0 1; border: none;
                        background: $boost; }
    TablePane #filter.-on { display: block; }
    TablePane #filter:focus { background: $accent 20%; }
    TablePane DataTable { height: 1fr; }
    """

    def __init__(self) -> None:
        super().__init__()
        self.window = None
        self.needle = ""
        self.sort_index = 0
        self._rows: list = []
        self._visible: tuple[str, ...] = ()

    def compose(self) -> ComposeResult:
        yield Static("", id="note")
        yield Input(placeholder="filter…", id="filter")
        yield Table(id="table", cursor_type="row", zebra_stripes=True)

    def on_mount(self) -> None:
        self._paint_columns(self.app.size.width)

    def on_resize(self, event) -> None:
        # Crossing a width threshold re-lays the columns; a resize inside one
        # band costs nothing, so dragging a window edge does not re-query.
        if self._paint_columns(event.size.width):
            self.reload(self.window)

    def columns_for(self, width: int) -> tuple[str, ...]:
        """Which columns fit. A narrow terminal drops detail, never rows."""
        return self.COLUMNS

    def _paint_columns(self, width: int, force: bool = False) -> bool:
        cols = self.columns_for(width)
        if cols == self._visible and not force:
            return False
        self._visible = cols
        marker = self.sort_column()
        table = self.query_one(DataTable)
        table.clear(columns=True)
        for name in cols:
            width = self.COLUMN_WIDTHS.get(name)
            marked = bool(name) and name == marker
            # The marker needs two cells of its own or it is what gets clipped.
            table.add_column(f"{name} ▼" if marked else name,
                             width=width + 2 if (marked and width) else width,
                             key=name)
        return True

    # subclasses implement these three
    def fetch(self, window) -> list:
        raise NotImplementedError

    def cells(self, row) -> dict[str, object]:
        raise NotImplementedError

    def _before_render(self, rows: list) -> None:
        """Hook for a pane that needs a column total before drawing its rows."""

    def matches(self, row, needle: str) -> bool:
        values = self.cells(row).values()
        return needle in " ".join(str(v) for v in values).lower()

    def extra_note(self) -> str:
        """What this tab adds after "N rows · sort: …"."""
        return ""

    def note_text(self) -> Text:
        """The caption above the table.

        It names the sort on purpose: a silent reorder is indistinguishable from
        the data having changed, and `s` cycling three fields is invisible
        unless the line says which one is in force.
        """
        out = Text(f"{len(self._rows):,} rows")
        if self.needle:
            out.append(f" · filter {self.needle!r}")
        column = self.sort_column()
        out.append(f" · sort: {column} ▼ (s)" if column else " · sort: none")
        extra = self.extra_note()
        if extra:
            out.append(f" · {extra}")
        # The full set is whatever an unlimited terminal would show, which is not
        # COLUMNS for a pane whose columns depend on its mode.
        full = self.columns_for(10_000)
        hidden = [name for name in full if name not in self._visible]
        if hidden and self._visible:
            # Only when columns were dropped: a note that always says "nothing
            # hidden" costs a row to say nothing.
            out.append(f"\n{len(self._visible)} of {len(full)} columns · "
                       f"hidden: {', '.join(hidden)} · widen to see them")
        return out

    def sort_key(self):
        if not self.SORT_FIELDS:
            return None
        return self.SORT_FIELDS[self.sort_index][1]

    def sort_column(self) -> str:
        if not self.SORT_FIELDS:
            return ""
        return self.SORT_FIELDS[self.sort_index][2]

    def reload(self, window) -> None:
        self.window = window
        if not self._visible:
            self._paint_columns(self.app.size.width)
        rows = self.fetch(window)
        if self.needle:
            rows = [r for r in rows if self.matches(r, self.needle)]
        key = self.sort_key()
        if key:
            rows.sort(key=lambda r: (getattr(r, key) is None, getattr(r, key)), reverse=True)
        self._rows = rows
        self._before_render(rows)

        table = self.query_one(DataTable)
        cursor = max(0, table.cursor_row)
        table.clear(columns=False)
        for row in rows:
            cells = self.cells(row)
            table.add_row(*[cells.get(name, "") for name in self._visible])
        if rows:
            table.move_cursor(row=min(cursor, len(rows) - 1))
        self.query_one("#note", Static).update(self.note_text())

    def action_sort(self) -> None:
        if not self.SORT_FIELDS:
            return
        self.sort_index = (self.sort_index + 1) % len(self.SORT_FIELDS)
        # The header carries the marker, so the columns are repainted on every
        # change even though the visible set is the same.
        self._paint_columns(self.app.size.width, force=True)
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



class TokensPane(TablePane):
    """Token totals, with one model as one row by default.

    The same model is usually reached through more than one tracker, and the
    question "how much did this model cost me" has one answer, not three. So the
    default view merges by model name (case-folded) and puts each tracker in its
    own column; g cycles to the per-call-row and per-tracker views.
    """

    TAB_KEY = "tokens"

    MODES = ("model", "calls", "source")
    MODE_LABELS = {
        "model": "by model, all trackers merged",
        "calls": "by model × tracker",
        "source": "by tracker",
    }
    COLUMN_SETS = {
        "model": ("model", "usage total", "cbut", "ocut", "qcut", "req",
                  "last used"),
        # The total comes before the split it is made of: it is the number the
        # row is ranked by, and the four parts explain it rather than lead it.
        "calls": ("source", "model", "provider", "usage total", "input", "output",
                  "cache r", "cache w", "req", "last used"),
        "source": ("source", "usage total", "input", "output", "cache r",
                   "cache w", "req", "last used"),
    }
    COLUMN_WIDTHS = {"source": 10, "model": 28, "provider": 12, "req": 6,
                     "last used": 10, "cbut": 8, "ocut": 8, "qcut": 8,
                     "usage total": 12}
    SORT_FIELDS = (("usage total", "total", "usage total"),
                   ("requests", "requests", "req"),
                   ("recent", "last_used", "last used"), ("name", "model", "model"))

    # Below these widths the cache split is what pushes the model name out of
    # view — and the model is what the row is about.
    WIDE = 128
    MEDIUM = 108

    def __init__(self) -> None:
        super().__init__()
        self.mode = "model"

    def columns_for(self, width: int) -> tuple[str, ...]:
        base = self.COLUMN_SETS[self.mode]
        if width >= self.WIDE:
            return base
        if width >= self.MEDIUM:
            return tuple(c for c in base if c != "provider")
        return tuple(c for c in base if c not in ("provider", "cache r", "cache w"))

    def fetch(self, window):
        start, end = bounds_of(window, model.now_ms())
        rows = model.token_rows(start, end)
        if self.mode == "model":
            return model.model_totals(rows)
        if self.mode == "source":
            return model.by_source(rows)
        return rows

    def cells(self, row) -> dict[str, object]:
        if isinstance(row, model.ModelTotal):
            return {
                "model": row.model,
                "usage total": f"{fmt_tokens(row.total):>7}",
                "cbut": self._per(row, "cbut"),
                "ocut": self._per(row, "ocut"),
                "qcut": self._per(row, "qcut"),
                "req": f"{row.requests:,}",
                "last used": fmt_age(row.last_used),
            }
        return {
            "source": Text(row.label, style=SOURCE_STYLE.get(row.source, "")),
            "model": row.model,
            "provider": row.provider or Text("—", style="dim"),
            "input": f"{fmt_tokens(row.input):>8}",
            "output": f"{fmt_tokens(row.output):>8}",
            "cache r": f"{fmt_tokens(row.cache_read):>8}",
            "cache w": f"{fmt_tokens(row.cache_write):>8}",
            "usage total": f"{fmt_tokens(row.total):>8}",
            "req": f"{row.requests:>6,}",
            "last used": fmt_age(row.last_used),
        }

    @staticmethod
    def _per(item: model.ModelTotal, key: str):
        value = item.per_source.get(key)
        if not value:
            return Text(f"{'—':>7}", style="dim")
        # Padded here rather than by justify: a cell is rendered on its own, so
        # justify pads against the wrong width and the column stops lining up.
        return Text(f"{fmt_tokens(value):>7}", style=SOURCE_STYLE.get(key, ""))

    def group_toggle(self) -> None:
        index = self.MODES.index(self.mode)
        self.mode = self.MODES[(index + 1) % len(self.MODES)]
        self._paint_columns(self.app.size.width, force=True)
        self.reload(self.window)

    def extra_note(self) -> str:
        total = sum(r.total for r in self._rows)
        label = self.MODE_LABELS[self.mode]
        if self.size.width and self.size.width < 100:
            # The long label is what wraps the caption at 80 columns; the mode
            # is still named, without the clause explaining the merge.
            label = label.split(",")[0]
        return (f"grouping: {label} (g) · total {fmt_tokens(total)}")

    def open_selected(self) -> None:
        row = self.selected()
        if row is None:
            return
        if isinstance(row, model.ModelTotal):
            # Every spelling the row folded, so the drill-down totals the same.
            self.app.push_screen(ModelScreen(row.spellings or (row.model,),
                                             None, self.window))
        elif row.model != "(all models)":
            self.app.push_screen(ModelScreen((row.model,), row.source, self.window))


class EntityPane(TablePane):
    """Skills and Tools: one row per name, one column per source."""

    # Recent first: "what did I just use" is the question this tab gets asked
    # more often than "what did I use most". s still cycles to calls.
    SORT_FIELDS = (("recent", "last_used", "last used"), ("calls", "calls", "calls"),
                   ("name", "name", "name"))
    COLUMN_WIDTHS = {"name": 30, "calls": 22, "cbut": 7, "ocut": 7, "qcut": 7,
                     "ok": 6, "fail": 5, "avg": 6, "last used": 10}

    def __init__(self, kind: str) -> None:
        super().__init__()
        self.kind = kind
        self.TAB_KEY = kind
        self.COLUMNS = ("name", "calls", "cbut", "ocut", "qcut", "ok", "fail",
                        "avg", "last used")
        self._total_calls = 0
        self._max_calls = 0

    def fetch(self, window):
        start, end = bounds_of(window, model.now_ms())
        return model.entity_rows(self.kind, start, end)

    def _before_render(self, rows) -> None:
        self._total_calls = sum(r.calls for r in rows)
        # Bars are a magnitude chart (the busiest row fills the bar); the
        # percentage beside them is the share of the window.
        self._max_calls = max((r.calls for r in rows), default=0)

    def cells(self, row) -> dict[str, object]:
        def per(key):
            value = row.per_source.get(key)
            if not value:
                return Text(f"{'—':>6}", style="dim")
            return Text(f"{value:>6,}", style=SOURCE_STYLE.get(key, ""))

        calls = Text(f"{row.calls:>6} ")
        calls.append_text(share_bar(row.calls, self._max_calls, width=8))
        calls.append(f" {pct(row.calls, self._total_calls):>3}")
        return {
            "name": row.name,
            "calls": calls,
            "cbut": per("cbut"),
            "ocut": per("ocut"),
            "qcut": per("qcut"),
            "ok": str(row.ok),
            "fail": str(row.fail) if row.fail else Text("0", style="dim"),
            "avg": _avg(row.avg_ms),
            "last used": fmt_age(row.last_used),
        }

    def extra_note(self) -> str:
        shared = sum(1 for r in self._rows
                     if len([v for v in r.per_source.values() if v]) > 1)
        return f"{shared} used by more than one tracker"

    def open_selected(self) -> None:
        row = self.selected()
        if row is not None:
            self.app.push_screen(EntityScreen(row.name, self.kind, self.window, row.calls))


class UsagePane(TablePane):
    TAB_KEY = "usage"
    COLUMNS = ("when", "source", "model", "usage total", "project", "session")
    COLUMN_WIDTHS = {"when": 10, "source": 10, "model": 24, "usage total": 12,
                     "project": 36, "session": 9}
    SORT_FIELDS = (("time", "ts", "when"), ("usage total", "total", "usage total"),
                   ("source", "source", "source"))

    def __init__(self) -> None:
        super().__init__()
        self._raw = 0

    def fetch(self, window):
        start, end = bounds_of(window, model.now_ms())
        rows = model.call_rows(start, end)
        self._raw = len(rows)
        # Collapsing is a time-order courtesy: "the biggest calls" has to stay
        # one row per call or the ranking stops being a ranking.
        if self.sort_index == 0:
            rows = model.collapse_calls(rows)
        return rows

    def cells(self, row) -> dict[str, object]:
        tokens = Text()
        if row.count > 1:
            tokens.append(f"×{row.count} ", style="dim")
        tokens.append(fmt_tokens(row.total))
        return {
            "when": fmt_age(row.ts),
            "source": Text(row.label, style=SOURCE_STYLE.get(row.source, "")),
            "model": row.model or Text("—", style="dim"),
            "usage total": tokens,
            "project": _project(row.project, self.COLUMN_WIDTHS["project"]),
            "session": row.session[:8] or Text("—", style="dim"),
        }

    def extra_note(self) -> str:
        text = "newest calls from the three trackers"
        if self.sort_index == 0 and self._raw and self._raw != len(self._rows):
            text = f"{self._raw:,} calls, merged per minute"
        home = str(Path.home())
        if self._rows and all(not r.project or r.project == home for r in self._rows):
            text += " · all from ~"
        return text


class DashboardPane(Pane):
    """The screen that answers "where did the usage go, and is that more?".

    One window, three cards: the KPI strip, then the models and the skills that
    account for it, each ranked with its share so the reader does not have to
    divide two numbers. A model row also carries its origin — which tracker(s)
    the merged number came from. Every token on this screen is the Usage Total,
    the same number the Tokens and Usage tabs rank by.
    """

    TAB_KEY = "dashboard"
    can_focus = True

    DEFAULT_CSS = """
    DashboardPane { height: 1fr; padding: 0 1; overflow-y: auto; }
    DashboardPane #note { height: auto; color: $text-muted; }
    /* Rounded cards, as the three trackers draw their summary panels: title on
       the first row inside the border, values under it. */
    DashboardPane .card { border: round $primary; padding: 0 1; height: auto; }
    DashboardPane #kpi { height: 5; }
    /* Each list is as tall as its rows, and the pane scrolls once the two of
       them no longer fit: a fixed height hid every model past the tenth with no
       way to reach it. */
    DashboardPane #tops { height: auto; }
    DashboardPane #tops .card { width: 1fr; height: auto; }
    DashboardPane #tops .left { margin: 0 1 0 0; }
    """

    def __init__(self) -> None:
        super().__init__()
        self.window = None
        self._kpis = model.kpis(None, model.now_ms())
        self._models: list[model.ModelTotal] = []
        self._skills: list = []
        self._tops_rows = 0
        self._recent: list = []

    def compose(self) -> ComposeResult:
        yield Static(id="note")
        yield Static(id="kpi", classes="card")
        with Horizontal(id="tops"):
            yield Static(id="top-models", classes="card left")
            yield Static(id="top-skills", classes="card")

    # -- data ---------------------------------------------------------------

    def reload(self, window) -> None:
        self.window = window
        start, end = bounds_of(window, model.now_ms())
        self._kpis = model.kpis(start, end)
        self._models = model.model_totals(model.token_rows(start, end))
        self._skills = sorted(model.entity_rows("skills", start, end),
                              key=lambda r: (r.calls, r.last_used or 0), reverse=True)
        # One row, for the age in the caption; the list itself is gone.
        self._recent = model.call_rows(start, end, limit=1)
        self._paint()

    # -- drawing ------------------------------------------------------------

    def on_resize(self, event) -> None:
        # Repaint after the layout lands: the rows are sized to the cards'
        # measured width, and a child is not placed when the pane itself
        # resizes. Painting from on_resize directly would use the old width.
        if self.is_mounted:
            self.call_after_refresh(self._paint)

    def _width(self) -> int:
        """The pane's own width, falling back before the first measure."""
        return max(40, self.size.width or (self.app.size.width - 2) or 80)

    def _note_text(self) -> Text:
        out = Text(f"{len(self._models)} models · {len(self._skills)} skills in this window")
        if self._recent:
            out.append(f" · last call {fmt_age(self._recent[0].ts)}")
        return out

    def _paint(self) -> None:
        width = self._width()
        # The card's content box, less the column a scrollbar may take: the
        # pane's width is not what the text is drawn into.
        card = self.query_one("#kpi", Static)
        inner = max(24, (card.size.width or width - 4) - 1)
        self.query_one("#note", Static).update(self._note_text())
        self.query_one("#kpi", Static).update(self._kpi_text(inner))
        self._paint_tops(width)
        self._fit_cards()

    def _fit_cards(self) -> None:
        """Give the two list cards the height the pane has left.

        Both cards are content-sized, so a dashboard with five models ended a
        dozen rows above the status line. The spare height goes to the cards:
        their border grows to the bottom of the pane instead of leaving it
        empty. It is a *minimum*, so a list taller than the pane still grows to
        its own height and the pane scrolls exactly as before — nothing is
        clipped.
        """
        natural = self._tops_rows
        if not natural:
            return
        note = self.query_one("#note", Static)
        kpi = self.query_one("#kpi", Static)
        try:
            kpi_h = int(kpi.styles.height.value or 5)
        except Exception:  # not a plain scalar: fall back to the CSS value
            kpi_h = 5
        spare = (self.size.height - max(1, note.size.height) - kpi_h - natural)
        height = natural + max(0, spare)
        for wid in ("#top-models", "#top-skills"):
            self.query_one(wid, Static).styles.min_height = height

    def _kpi_text(self, width: int = 120) -> Text:
        k = self._kpis
        total = k.tokens or 0
        out = Text("Window\n", style="bold")
        out.append(fmt_tokens(total), style="bold")
        out.append(" usage total   ")
        out.append_text(_delta(k.tokens, k.prev_tokens))
        if k.prev_tokens is not None:
            out.append(f" vs {fmt_tokens(k.prev_tokens)}", style="dim")
        bits = [f"{k.sessions:,} sessions", f"{k.calls:,} calls"]
        if k.active_days:
            bits.append(f"{k.active_days} active "
                        f"{'day' if k.active_days == 1 else 'days'}")
        # Drop whole facts from the tail until the line fits, rather than
        # letting the last one wrap under the total: a wrapped fact reads as a
        # second headline.
        used = len(out.plain) - out.plain.rfind("\n") - 1
        while bits and used + 7 + sum(len(b) for b in bits) \
                + 3 * (len(bits) - 1) > width:
            bits.pop()
        if bits:
            out.append("   ·   " + " · ".join(bits))
        out.append("\n")
        if total <= 0:
            out.append("nothing recorded in this window", style="dim")
            return out
        first = True
        for source in SOURCES:
            value = k.per_source.get(source.key)
            if value is None:
                continue
            if not first:
                out.append("   ")
            first = False
            out.append(f"{source.label} ", style=SOURCE_STYLE.get(source.key, ""))
            if width >= 110:
                out.append_text(share_bar(value, total, width=8,
                                          style=SOURCE_STYLE.get(source.key, "cyan")))
                out.append(f" {fmt_tokens(value):>7}")
            else:
                out.append(f"{fmt_tokens(value)}")
            out.append(f" {pct(value, total):>3}")
        return out

    # Fixed parts of a ranked row, in cells. The name takes what is left; the
    # bar, then the percentage, are what give way when the numbers grow.
    ORIGIN_W = 9
    BAR_W = 6
    PCT_W = 4

    @classmethod
    def _row_widths(cls, budget: int, num_w: int, head_w: int,
                    tail_w: int) -> tuple[int, bool, bool, bool]:
        """Name width, and which of the origin, the bar and the share still fit.

        Widths come from the data, not from a guess: a nine-character total
        ("10151.90M") used to push the percentage onto the next line, where it
        read as a row of its own. Something has to give as the card narrows,
        in the order that costs the reader least: the bar (the percentage
        carries the same fact), then the origin tag, then the percentage.
        """
        for bar, share, head in ((True, True, True), (False, True, True),
                                 (False, True, False), (False, False, False)):
            fixed = (2 + num_w + (head_w + 1 if head and head_w else 0)
                     + (1 + cls.BAR_W if bar else 0)
                     + (1 + cls.PCT_W if share else 0) + tail_w)
            if budget - fixed >= 10:
                return budget - fixed, bar, share, head and bool(head_w)
        return max(0, budget - fixed), False, False, False

    def _paint_tops(self, width: int) -> None:
        models_card = self.query_one("#top-models", Static)
        skills_card = self.query_one("#top-skills", Static)
        # The card's own content box, less one column for the scrollbar the
        # pane may grow: the two cards split an odd column unevenly, and the
        # left one loses another when the pane starts scrolling. Sizing rows
        # from the pane's width is how a row ends up one cell too wide.
        fallback = max(30, (width - 1) // 2 - 4)
        models_w = max(24, (models_card.size.width or fallback) - 1)
        skills_w = max(24, (skills_card.size.width or fallback) - 1)

        total = sum(m.total for m in self._models)
        numbers = [fmt_tokens(m.total) for m in self._models]
        num_w = max([len(n) for n in numbers] + [7])
        name_w, bar, share, head = self._row_widths(models_w, num_w, self.ORIGIN_W, 0)

        models = Text()
        models.append(f"top models · {fmt_tokens(total)}\n", style="bold")
        if not self._models:
            models.append("  nothing in this window", style="dim")
        for item, number in zip(self._models, numbers):
            origin = origin_label(item.per_source)
            line = Text()
            line.append(f" {_clip(item.model, name_w):<{name_w}}")
            if head:
                line.append(f" {origin:<{self.ORIGIN_W}}",
                            style=SOURCE_STYLE.get(origin, "dim"))
            line.append(f" {number:>{num_w}}")
            if bar:
                line.append(" ")
                line.append_text(share_bar(item.total, self._models[0].total,
                                           width=self.BAR_W,
                                           style=self._model_style(item)))
            if share:
                line.append(f" {pct(item.total, total):>{self.PCT_W}}")
            line.append("\n")
            models.append_text(line)

        self.query_one("#top-models", Static).update(models)

        calls = sum(r.calls for r in self._skills)
        call_nums = [f"{r.calls:,}" for r in self._skills]
        ages = [fmt_age(r.last_used) for r in self._skills]
        num2 = max([len(n) for n in call_nums] + [6])
        age_w = max([len(a) for a in ages] + [8])
        name2, bar2, share2, _ = self._row_widths(skills_w, num2, 0, 2 + age_w)

        side = Text()
        side.append(f"top skills · {calls:,} calls\n", style="bold")
        if not self._skills:
            side.append("  none in this window · d widens it\n", style="dim")
        for item, number, age in zip(self._skills, call_nums, ages):
            line = Text()
            line.append(f" {_clip(item.name, name2):<{name2}}")
            line.append(f" {number:>{num2}}")
            if bar2:
                line.append(" ")
                line.append_text(share_bar(item.calls, self._skills[0].calls,
                                           width=self.BAR_W))
            if share2:
                line.append(f" {pct(item.calls, calls):>{self.PCT_W}}")
            line.append(f"  {age:<{age_w}}", style="dim")
            line.append("\n")
            side.append_text(line)
        self.query_one("#top-skills", Static).update(side)

        # The natural height of the row, for _fit_cards: the taller of the two
        # cards, counted the way the widget counts it — a trailing newline is a
        # line — plus the two rows of border.
        self._tops_rows = max(len(models.plain.split("\n")),
                              len(side.plain.split("\n"))) + 2

    @staticmethod
    def _model_style(item: model.ModelTotal) -> str:
        """Colour the bar by its source when only one source used the model."""
        if len(item.per_source) != 1:
            return "cyan"
        key = next(iter(item.per_source))
        return SOURCE_STYLE.get(key, "cyan")

    # -- keys ---------------------------------------------------------------



class SourcesPane(Pane):
    """Health of the three indexes, and the way into each tracker's own TUI."""

    TAB_KEY = "sources"

    DEFAULT_CSS = """
    SourcesPane { height: 1fr; }
    SourcesPane #note { height: auto; padding: 0 1; color: $text-muted; }
    SourcesPane DataTable { height: 1fr; }
    """

    COLUMNS = ("source", "tokens", "share", "sessions", "7d trend", "last seen",
               "state", "index")
    COLUMN_WIDTHS = {"source": 12, "tokens": 8, "share": 12, "sessions": 8,
                     "7d trend": 8, "last seen": 10, "state": 7, "index": 8}

    def __init__(self) -> None:
        super().__init__()
        self.window = None
        self._snaps: list = []
        self._trend: dict = {}
        self._visible: tuple[str, ...] = ()

    def compose(self) -> ComposeResult:
        yield Static(id="note")
        yield Table(id="table", cursor_type="row", zebra_stripes=True)

    def on_mount(self) -> None:
        self._paint_columns(self.app.size.width)

    def on_resize(self, event) -> None:
        if self._paint_columns(event.size.width):
            self.reload(self.window)

    def _paint_columns(self, width: int) -> bool:
        cols = tuple(c for c in self.COLUMNS if not (c == "index" and width < 108))
        if cols == self._visible:
            return False
        self._visible = cols
        table = self.query_one(DataTable)
        table.clear(columns=True)
        for name in cols:
            table.add_column(name, width=self.COLUMN_WIDTHS.get(name), key=name)
        return True

    # -- data ---------------------------------------------------------------

    def reload(self, window, only: str | None = None) -> None:
        """Reload every row, or — after a tracker's TUI hands the terminal back —
        only the row that was visited, in place, so the table does not flicker
        and the cursor stays where the reader left it."""
        self.window = window
        if not self._visible:
            self._paint_columns(self.app.size.width)
        start, end = bounds_of(window, model.now_ms())
        days = 0 if start is None else max(1, round((end - start) / DAY_MS))

        if only is not None and self._snaps:
            for index, snap in enumerate(self._snaps):
                if snap.key != only:
                    continue
                self._snaps[index] = BY_KEY[only].snapshot(days, since_ms=start)
                # The trend is always a week, even when the numbers are today's:
                # a one-bar trend is not a trend.
                self._trend[only] = BY_KEY[only].snapshot(7).buckets
                self._update_row(self._snaps[index])
                break
        else:
            self._snaps = snapshots(days, since_ms=start)
            self._trend = {s.key: s.buckets for s in snapshots(7)}
            self._fill()
        self._note()

    def _row(self, snap) -> dict[str, object]:
        total = sum(s.tokens or 0 for s in self._snaps)
        live = snap.status in ("ok", "idle")
        state = {"ok": "ok", "idle": "idle", "missing": "no db"}.get(snap.status, "error")
        return {
            "source": Text(snap.label, style=SOURCE_STYLE.get(snap.key, "")),
            "tokens": fmt_tokens(snap.tokens),
            "share": (Text("—", style="dim") if not snap.tokens
                      else _share_cell(snap.tokens, total, snap.key)),
            "sessions": str(snap.sessions) if live else Text("—", style="dim"),
            "7d trend": sparkline(self._trend.get(snap.key, snap.buckets)),
            "last seen": fmt_age(snap.last_event_ms),
            "state": Text(state, style="green" if snap.status == "ok"
                          else "yellow" if snap.status == "idle" else "red"),
            "index": _human_size(snap.db_size),
        }

    def _fill(self) -> None:
        table = self.query_one(DataTable)
        cursor = max(0, table.cursor_row)
        table.clear(columns=False)
        for snap in self._snaps:
            cells = self._row(snap)
            table.add_row(*[cells.get(c, "") for c in self._visible], key=snap.key)
        if self._snaps:
            table.move_cursor(row=min(cursor, len(self._snaps) - 1))

    def _update_row(self, snap) -> None:
        table = self.query_one(DataTable)
        cells = self._row(snap)
        for name in self._visible:
            try:
                table.update_cell(snap.key, name, cells.get(name, ""))
            except Exception:
                return

    def _note(self) -> None:
        problems = [f"{s.label}: {s.note}" for s in self._snaps
                    if s.status in ("missing", "error") or not s.tokens_real]
        text = (f"{len(self._snaps)} trackers · enter opens one in its own TUI "
                "· q there returns here")
        if problems:
            text += "\n" + " · ".join(problems)
        self.query_one("#note", Static).update(text)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.open_selected()

    def open_selected(self) -> None:
        table = self.query_one(DataTable)
        index = table.cursor_row
        if 0 <= index < len(self._snaps):
            self.app.open_tracker(self._snaps[index].key)


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
        yield Table(id="calls", cursor_type="row", zebra_stripes=True)

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns(*self.COLUMNS)
        for row in self._rows:
            table.add_row(
                fmt_age(row.ts),
                Text(row.label, style=SOURCE_STYLE.get(row.source, "")),
                row.model or "—",
                fmt_tokens(row.total),
                _project(row.project, 44),
                row.session[:8] or "—",
            )


class ModelScreen(Screen[None]):
    BINDINGS = [Binding("escape,q", "app.pop_screen", "Back")]

    DEFAULT_CSS = """
    /* Auto, not 4: a merged model adds the line naming its spellings. */
    ModelScreen #head { height: auto; padding: 1 1 0 1; }
    """

    def __init__(self, names: tuple[str, ...], source: str | None, window) -> None:
        super().__init__()
        # 'name' is a Textual DOMNode property; using it here raises at mount.
        # names[0] is the spelling that carried the most tokens; the rest are
        # the ones canonical_model folded into the same row.
        self.model_names = names
        self.model_name = names[0]
        self.source = source
        self.window = window

    def compose(self) -> ComposeResult:
        start, end = bounds_of(self.window, model.now_ms())
        names = self.model_names
        calls = model.model_calls(self.source, names, start, end)
        labels, series = model.model_daily(self.source, names, start, end)
        total, count = model.model_stats(self.source, names, start, end)
        head = Text()
        head.append(f"{self.model_name}\n", style="bold")
        if len(names) > 1:
            # Say what was folded: the row is a sum of these, and the records
            # below keep each call's own spelling.
            head.append("also recorded as ", style="dim")
            head.append(" · ".join(names[1:]), style="dim")
            head.append("\n")
        where = BY_KEY[self.source].label if self.source else "all trackers"
        head.append(f"{where} · {window_label(self.window)} · "
                    f"{count:,} calls · {fmt_tokens(total)} tokens")
        if count > len(calls):
            head.append(f"  ·  newest {len(calls)} below", style="dim")
        head.append("\n")
        if self.source is None:
            # Per-source totals from the aggregate, not from the 200 listed
            # rows: a split that adds up to 40M beside an 81M total is a lie
            # the reader cannot see.
            per: dict[str, int] = {}
            for source in SOURCES:
                value, seen = model.model_stats(source.key, names, start, end)
                if seen:
                    per[source.key] = value
            head.append_text(_source_split(per, total))
            head.append("\n")
        else:
            head.append(sparkline(series) + f"  {len(labels)}d\n")
        yield Static(head, id="head")
        yield CallsTable(calls)


class EntityScreen(Screen[None]):
    BINDINGS = [Binding("escape,q", "app.pop_screen", "Back")]

    DEFAULT_CSS = """
    EntityScreen #head { height: 3; padding: 1 1 0 1; }
    """

    def __init__(self, entity_name: str, kind: str, window,
                 total_calls: int | None = None) -> None:
        super().__init__()
        self.entity_name = entity_name
        self.kind = kind
        self.window = window
        self.total_calls = total_calls

    def compose(self) -> ComposeResult:
        start, end = bounds_of(self.window, model.now_ms())
        rows = model.entity_calls(self.kind, self.entity_name, start, end)
        count = self.total_calls if self.total_calls is not None else len(rows)
        head = Text()
        head.append(f"{self.entity_name}\n", style="bold")
        head.append(f"{self.kind} · {window_label(self.window)} · {count:,} calls")
        if count > len(rows):
            head.append(f"  ·  newest {len(rows)} below", style="dim")
        head.append("\n")
        yield Static(head, id="head")
        yield CallsTable(rows)


class AutApp(App[None]):
    TITLE = "aut"
    SUB_TITLE = "all usage trackers"
    # The footer is the key list here; a second, hidden one behind ^p is noise,
    # and the three trackers turn it off for the same reason.
    ENABLE_COMMAND_PALETTE = False

    CSS = """
    /* The screen keeps the theme's default background, as in the three
       trackers: $surface is rgb(30,30,30) against the theme's rgb(18,18,18),
       and a whole-screen $surface made aut the lighter one of the family. */
    #bar { dock: top; height: 1; background: $panel; color: $foreground; }
    #bar #title { width: 1fr; padding: 0 1; content-align: left middle; }
    #bar #custom { width: auto; min-width: 0; height: 1; border: none;
                   padding: 0 1; background: $panel; color: $accent;
                   text-style: bold; }
    #bar #custom:hover { background: $boost; }
    #bar #range { width: 24; }
    #bar SelectCurrent { border: none; padding: 0 1; background: $panel;
                         color: $accent; }
    /* In the flow, not docked: the tabs take 1fr, so this lands directly above
       the footer exactly as it does in the three trackers. */
    #status { height: 1; padding: 0 1; color: $text-muted; }
    TabbedContent { height: 1fr; }
    #help-box { width: 82; height: auto; padding: 1 2; background: $panel;
                border: round $accent; margin: 2 4; }
    #help-title { padding: 0 0 1 0; }
    """

    BINDINGS = [
        Binding("tab", "next_tab", "Next tab", priority=True),
        Binding("shift+tab", "prev_tab", "Prev tab", priority=True),
        Binding("q", "quit", "Quit"),
        Binding("r", "sync", "Sync now"),
        Binding("s", "sort", "Sort"),
        Binding("slash", "filter", "Filter"),
        Binding("d", "date_range", "Date"),
        Binding("g", "group", "Group"),
        Binding("1", "goto_tab(0)", "1", show=False),
        Binding("2", "goto_tab(1)", "2", show=False),
        Binding("3", "goto_tab(2)", "3", show=False),
        Binding("4", "goto_tab(3)", "4", show=False),
        Binding("5", "goto_tab(4)", "5", show=False),
        Binding("6", "goto_tab(5)", "6", show=False),
        Binding("question_mark", "help", "Help"),
        Binding("escape", "clear_filter", "Clear", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.windows = dict(DEFAULT_RANGES)
        self._synced_ms = int(time.time() * 1000)
        self._syncing = False
        self._sync_step = ""

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
        # Provenance, then the key footer: the window and the sort belong to the
        # tab and are named above its table, so this line says what was read and
        # when, not what the page is showing.
        yield Static(id="status")
        yield Footer()

    def on_mount(self) -> None:
        self.reload_active()
        self._focus_table()

    def _focus_table(self) -> None:
        """Keep the keyboard on the data, not on the top bar's button.

        Without this the first focusable widget (the custom-range button) holds
        focus, and pressing enter opens the calendar instead of the selected row.
        """
        pane = self.pane()
        try:
            pane.query_one(DataTable).focus()
        except Exception:
            # The dashboard has no table; it owns up/down/enter itself, so it
            # has to hold the focus or those keys go nowhere.
            pane.focus()

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
        parts = []
        total = 0
        missing = 0
        for source in SOURCES:
            path = source.db_path
            if path.is_file():
                total += path.stat().st_size
            else:
                missing += 1
        if self._syncing and self._sync_step:
            parts.append(f"[b]{self._sync_step}[/b]")
        parts.append(f"{len(SOURCES) - missing} of {len(SOURCES)} indexes")
        if total:
            parts.append(_human_size(total))
        if missing:
            parts.append(f"{missing} missing")
        if not self._syncing:
            parts.append(f"synced {fmt_age(self._synced_ms)}")
        self.query_one("#status", Static).update(" · ".join(parts))

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

    def check_action(self, action: str, parameters: tuple) -> bool:
        """Which bindings exist on the current tab.

        The footer is the key list, so a key that cannot do anything on this tab
        must not be in it: `s` on Sources and `g` on anything but Tokens are
        the obvious ones. Returning False also stops the key from firing, which
        is why the old "this tab has no sort order" notices are gone.
        """
        try:
            pane = self.pane()
        except Exception:
            return True
        if action == "sync":
            return not self._syncing
        if action == "sort":
            return bool(getattr(pane, "SORT_FIELDS", ()))
        if action == "group":
            return isinstance(pane, TokensPane)
        if action in ("filter", "clear_filter"):
            return isinstance(pane, TablePane)
        return True

    # -- actions -----------------------------------------------------------

    async def action_sync(self) -> None:
        """Run the three trackers' own sync without leaving the board.

        `r` used to suspend the TUI three times — once per tracker — so a sync
        read as a restart. The child process now runs behind the board with its
        output captured; the status line names the tracker being synced and the
        tab refreshes once at the end.
        """
        if self._syncing:
            return
        self._syncing = True
        self.refresh_bindings()      # hides "r" while it runs
        try:
            for index, source in enumerate(SOURCES, start=1):
                if shutil.which(source.binary) is None:
                    continue
                self._sync_step = f"syncing {source.label} {index}/{len(SOURCES)}"
                self._update_bar(self.windows.get(self.pane().TAB_KEY, "1d"))
                code, tail = await self._run_sync(source)
                if code != 0:
                    self.notify(f"{source.binary} sync exited {code}"
                                + (f": {tail}" if tail else ""),
                                severity="warning", timeout=8)
        finally:
            self._syncing = False
            self._sync_step = ""
            self._synced_ms = int(time.time() * 1000)
            self.refresh_bindings()
            self.reload_active()

    async def _run_sync(self, source) -> tuple[int, str]:
        """Run one tracker's sync; return (exit code, last line of output)."""
        try:
            proc = await asyncio.create_subprocess_exec(
                *source.sync_argv(),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except OSError as exc:
            return 127, str(exc)
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=SYNC_TIMEOUT_S)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return 124, f"timed out after {SYNC_TIMEOUT_S}s"
        lines = out.decode("utf-8", "replace").strip().splitlines()
        return proc.returncode or 0, (lines[-1] if lines else "")

    def action_sort(self) -> None:
        pane = self.pane()
        pane.action_sort()
        self._update_bar(self.windows.get(pane.TAB_KEY, "1d"))

    def action_filter(self) -> None:
        self.pane().action_open_filter()

    def action_clear_filter(self) -> None:
        self.pane().clear_filter()

    def action_group(self) -> None:
        pane = self.pane()
        pane.group_toggle()
        self._update_bar(self.windows.get(pane.TAB_KEY, "1d"))

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
        """Hand the terminal to a tracker's own TUI, then take it back.

        On return only the row that was visited is re-read, in place: the table
        keeps its cursor and scroll position, nothing else flickers, and the
        status line says where the numbers just came from.
        """
        source = BY_KEY[key]
        if shutil.which(source.binary) is None:
            self.notify(f"{source.binary} is not on PATH — install that tracker first",
                        severity="error", timeout=6)
            return
        with self.suspend():
            print(f"\naut → {source.label} · q there returns to aut\n", flush=True)
            subprocess.call(source.launch_argv())

        pane = self.pane()
        window = self.windows.get(pane.TAB_KEY, "1d")
        if isinstance(pane, SourcesPane):
            pane.reload(window, only=key)
        else:
            pane.reload(window)
        self._synced_ms = int(time.time() * 1000)
        self._update_bar(window)
        self._focus_table()


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
