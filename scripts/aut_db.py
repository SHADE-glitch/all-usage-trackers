"""Read-only data access shared by the adapters, the TUI and the JSON report.

Every connection is opened with ``mode=ro``. That is not politeness: the overview
must never be the thing that writes a tracker's database, and it must not take a
write lock while that tracker is syncing in another window.

Nothing in this module parses a log. The three trackers own collection; this layer
only reads the SQLite index each of them already built.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

# (days, label). 0 means "everything the database holds".
WINDOWS: tuple[tuple[int, str], ...] = ((1, "1d"), (7, "7d"), (30, "30d"), (0, "all"))

# The sparkline is a fixed-width glyph strip; past 30 days it would stop being
# readable, so a wider window shows its most recent 30 days and says so.
SPARK_DAYS = 30

BLOCKS = "▁▂▃▄▅▆▇█"

DAY_MS = 86_400_000


def open_ro(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2.0)
    conn.row_factory = sqlite3.Row
    return conn


def cutoff_ms(days: int, now_ms: int | None = None) -> int:
    """Start of the window, in epoch ms. 0 (all time) yields 0, not now."""
    if days <= 0:
        return 0
    now = int(time.time() * 1000) if now_ms is None else now_ms
    return now - days * DAY_MS


def spark_width(days: int) -> int:
    return SPARK_DAYS if days <= 0 else min(days, SPARK_DAYS)


def fmt_tokens(value: int | None) -> str:
    """A token count, scaled so the field stops growing.

    Two decimals at every scale, and the scale rises with the number: the board
    passed 21,000M this month, and a nine-character cell pushed the percentage
    beside it onto a second line. A field that tops out at "999.99B" leaves room
    for years of growth without another layout change.
    """
    if value is None:
        return "—"
    if value >= 1_000_000_000_000:
        return f"{value / 1_000_000_000_000:.2f}T"
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f}B"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    if value >= 1_000:
        return f"{value / 1_000:.0f}K"
    return str(value)


def fmt_age(ts_ms: int | None, now_ms: int | None = None) -> str:
    if ts_ms is None:
        return "never"
    now = int(time.time() * 1000) if now_ms is None else now_ms
    seconds = max(0, (now - ts_ms) // 1000)
    if seconds < 60:
        return f"{seconds}s ago"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < DAY_MS // 1000:
        return f"{seconds // 3600}h ago"
    return f"{seconds // (DAY_MS // 1000)}d ago"


def sparkline(values: list[int]) -> str:
    """One glyph per bucket, scaled to the busiest bucket in the strip."""
    if not values:
        return ""
    top = max(values)
    if top <= 0:
        return BLOCKS[0] * len(values)
    out = []
    for value in values:
        if value <= 0:
            out.append(BLOCKS[0])
            continue
        index = 1 + int((value / top) * (len(BLOCKS) - 2))
        out.append(BLOCKS[min(index, len(BLOCKS) - 1)])
    return "".join(out)
