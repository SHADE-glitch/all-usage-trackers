#!/usr/bin/env python3
"""The overview: one read-only board over the three trackers.

The board owns no data. It reads each tracker's SQLite index, draws a row per
source, and — when you ask to go deeper — hands the terminal over to that
tracker's own TUI and takes it back when you quit. That hand-off is `suspend()`,
which is why the three TUIs stay untouched and why returning needs no protocol:
their own `q` is the way back.
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
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Static

from aut_db import WINDOWS, fmt_age, fmt_tokens, sparkline
from aut_sources import BY_KEY, SOURCES, Snapshot, snapshots

STATE_TEXT = {"ok": "ok", "idle": "idle", "missing": "missing", "error": "error"}
STATE_STYLE = {"ok": "green", "idle": "yellow", "missing": "red", "error": "red"}

HELP = """
  ↑ ↓ / j k   move between sources
  enter       open that tracker's TUI (q returns here)
  1 2 3       open the first, second, third source
  s           sync the selected tracker
  S           sync all three, one after another
  w           cycle the window: 1d → 7d → 30d → all
  r           re-read the three databases
  ?           this help
  q           quit

  The board only reads. s and S write, and they do it
  through each tracker's own sync command.
"""

HINT = "enter open · 1 2 3 jump · s sync · S sync all · w window · r refresh · ? help · q quit"


def _shorten(path: Path | None) -> str:
    if path is None:
        return "—"
    text = str(path)
    home = str(Path.home())
    return "~" + text[len(home):] if text.startswith(home) else text


def _tokens_phrase(snap: Snapshot) -> str:
    """Tokens are the board's unit. A source that reported credits but no tokens
    says so, rather than borrowing a number it does not have."""
    if snap.tokens is None:
        return "no token reported"
    return f"{fmt_tokens(snap.tokens)} tokens"


def _human_size(size: int) -> str:
    if size <= 0:
        return "—"
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    return f"{size / 1024:.0f} KB"


class HelpScreen(ModalScreen[None]):
    BINDINGS = [
        Binding("escape,q,question_mark", "dismiss", "close"),
        Binding("enter", "dismiss", "close"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="help-box"):
            yield Static("[b]aut[/b] — keys and rules", id="help-title")
            yield Static(HELP.strip("\n"))

    def action_dismiss(self) -> None:
        self.dismiss()


class AutApp(App[None]):
    TITLE = "aut"
    SUB_TITLE = "all usage trackers"

    CSS = """
    Screen { background: $surface; }
    #bar { dock: top; height: 1; background: $boost; padding: 0 1; }
    #board { height: auto; max-height: 8; margin: 1 0 0 0; }
    #detail { height: 1fr; border: round $primary; padding: 1 2; margin: 1 0; }
    #hint { dock: bottom; height: 1; background: $boost; padding: 0 1; }
    #help-box { width: 62; height: auto; padding: 1 2; background: $panel;
                border: round $accent; margin: 2 4; }
    #help-title { padding: 0 0 1 0; }
    """

    BINDINGS = [
        Binding("enter", "open", "open"),
        Binding("1", "open_key('cbut')", "1", show=False),
        Binding("2", "open_key('ocut')", "2", show=False),
        Binding("3", "open_key('qcut')", "3", show=False),
        Binding("s", "sync", "sync"),
        Binding("S", "sync_all", "sync all"),
        Binding("w", "window", "window"),
        Binding("r", "refresh", "refresh"),
        Binding("question_mark", "help", "help"),
        Binding("q", "quit", "quit"),
    ]

    def __init__(self, days: int = 7) -> None:
        super().__init__()
        self.days = days
        self._selected = SOURCES[0].key
        self._snaps: dict[str, Snapshot] = {}
        self._refreshed_ms = int(time.time() * 1000)

    # -- layout ------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Static(id="bar")
        yield DataTable(id="board", cursor_type="row", zebra_stripes=True)
        yield Static(id="detail")
        yield Static(HINT, id="hint")

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("source", "tokens", "sessions", "trend", "last seen", "state")
        table.focus()
        self.reload()

    # -- data --------------------------------------------------------------

    def reload(self) -> None:
        table = self.query_one(DataTable)
        cursor = max(0, table.cursor_row)
        self._snaps = {snap.key: snap for snap in snapshots(self.days)}
        table.clear(columns=False)
        for source in SOURCES:
            snap = self._snaps[source.key]
            live = snap.status in ("ok", "idle")
            table.add_row(
                source.label,
                fmt_tokens(snap.tokens),
                str(snap.sessions) if live else "—",
                sparkline(snap.buckets),
                fmt_age(snap.last_event_ms),
                Text(STATE_TEXT[snap.status], style=STATE_STYLE[snap.status]),
                key=source.key,
            )
        if table.row_count:
            table.move_cursor(row=min(cursor, table.row_count - 1))
        self._refreshed_ms = int(time.time() * 1000)
        self._update_bar()
        self._render_detail()

    def _update_bar(self) -> None:
        label = next(name for days, name in WINDOWS if days == self.days)
        width = len(next(iter(self._snaps.values())).buckets) if self._snaps else 0
        trend = f"{width}d" if width else "—"
        self.query_one("#bar", Static).update(
            f"[b]aut[/b] · all usage trackers     window [b]{label}[/b]"
            f"     trend [b]{trend}[/b]"
            f"     refreshed {fmt_age(self._refreshed_ms)}"
        )

    def _render_detail(self) -> None:
        snap = self._snaps.get(self._selected)
        detail = self.query_one("#detail", Static)
        if snap is None:
            detail.update("")
            return

        models = " · ".join(
            f"{name} {fmt_tokens(tokens)}" for name, tokens in snap.top_models
        ) or "—"
        projects = " · ".join(
            f"{name} {fmt_tokens(tokens)}" for name, tokens in snap.top_projects
        ) or "—"

        lines = [
            f"[b]{snap.label}[/b] · last {next(n for d, n in WINDOWS if d == self.days)}"
            f" · {_tokens_phrase(snap)} · {snap.calls:,} calls · {snap.sessions:,} sessions",
            "",
            f"  models    {models}",
            f"  projects  {projects}",
            f"  index     {_shorten(snap.db_path)}  {_human_size(snap.db_size)}"
            f"  · newest record {fmt_age(snap.last_event_ms)}",
        ]
        if snap.status in ("missing", "error"):
            lines.append(f"  [red]{snap.note}[/red]")
        elif not snap.tokens_real:
            lines.append(f"  [yellow]{snap.note}[/yellow]")

        detail.update("\n".join(lines))

    # -- actions -----------------------------------------------------------

    def _run(self, argv: list[str], hint: str, reload: bool = True) -> int | None:
        if shutil.which(argv[0]) is None:
            self.notify(
                f"{argv[0]} is not on PATH — install that tracker first",
                severity="error", timeout=6,
            )
            return None
        with self.suspend():
            print(f"aut: {hint}", flush=True)
            try:
                rc = subprocess.call(argv)
            except OSError as exc:
                print(f"aut: {argv[0]}: {exc}", flush=True)
                rc = 1
        if reload:
            self.reload()
        if rc != 0:
            self.notify(f"{argv[0]} exited with status {rc}", severity="warning", timeout=6)
        return rc

    def action_open(self) -> None:
        self.action_open_key(self._selected)

    def action_open_key(self, key: str) -> None:
        source = BY_KEY.get(key)
        if source is None:
            return
        self._selected = key
        self._run(source.launch_argv(), f"{source.label} — press q to come back")

    def action_sync(self) -> None:
        source = BY_KEY[self._selected]
        self._run(source.sync_argv(), f"syncing {source.label}")

    def action_sync_all(self) -> None:
        for source in SOURCES:
            self._run(source.sync_argv(), f"syncing {source.label}", reload=False)
        self.reload()

    def action_window(self) -> None:
        index = next(i for i, (days, _) in enumerate(WINDOWS) if days == self.days)
        self.days = WINDOWS[(index + 1) % len(WINDOWS)][0]
        self.reload()

    def action_refresh(self) -> None:
        self.reload()

    def action_help(self) -> None:
        self.push_screen(HelpScreen())

    # -- events ------------------------------------------------------------

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.row_key.value:
            self._selected = str(event.row_key.value)
            self._render_detail()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        # DataTable claims "enter" for its own select_cursor action, so the
        # app-level binding never sees it while the board has focus. The message
        # is the path that actually fires.
        if event.row_key.value:
            self.action_open_key(str(event.row_key.value))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aut", description="overview of the local usage trackers")
    parser.add_argument("--days", type=int, default=7,
                        help="initial window: 1, 7, 30, or 0 for all time")
    args = parser.parse_args(argv)
    valid = {days for days, _ in WINDOWS}
    AutApp(args.days if args.days in valid else 7).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
