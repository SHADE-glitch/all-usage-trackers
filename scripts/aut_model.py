"""Cross-tool aggregation: the rows every tab draws.

Pure functions over (start_ms, end_ms) -> rows. No Textual import, so every
number the board shows is testable without a terminal — which matters here more
than usual, because the whole point of this app is numbers no single tracker can
produce.

Two rules hold throughout:

* A source whose database is missing contributes nothing and is skipped. It never
  becomes a zero row, which would read as "used nothing" instead of "not indexed
  here".
* Statuses are mapped to ok / fail / pending exactly once, in this module, from
  the values the three hosts actually write (verified against the real indexes:
  "completed"; "error" / "incomplete" / "cancelled"; everything else is pending,
  and pending is not a failure).
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field
from datetime import date, timedelta

from aut_db import open_ro
from aut_sources import SOURCES, Source

OK_STATUSES = ("completed", "ok", "success", "done")
FAIL_STATUSES = ("error", "failed", "incomplete", "cancelled", "canceled")

# Which table each entity tab reads, and the column that names the entity.
ENTITY_TABLES = {
    "skills": ("skill_usage", "skill"),
    "tools": ("tool_calls", "tool_name"),
}

DAY_MS = 86_400_000


# --- rows -------------------------------------------------------------------

@dataclass(slots=True)
class TokenRow:
    source: str
    label: str
    model: str
    provider: str
    input: int
    output: int
    cache_read: int
    cache_write: int
    total: int
    requests: int
    last_used: int | None


@dataclass(slots=True)
class EntityRow:
    name: str
    per_source: dict[str, int] = field(default_factory=dict)
    calls: int = 0
    ok: int = 0
    fail: int = 0
    pending: int = 0
    avg_ms: float | None = None
    last_used: int | None = None


@dataclass(slots=True)
class CallRow:
    ts: int
    source: str
    label: str
    model: str
    project: str
    session: str
    total: int


@dataclass(slots=True)
class Kpis:
    tokens: int = 0
    sessions: int = 0
    calls: int = 0
    active_days: int = 0
    per_source: dict[str, int] = field(default_factory=dict)
    prev_tokens: int | None = None
    prev_sessions: int | None = None


# --- plumbing ---------------------------------------------------------------

def _where(start_ms: int | None, end_ms: int):
    """A bound pair usable with one parameter repeated twice for NULL = all time."""
    return "(? IS NULL OR ts >= ?) AND ts <= ?", (start_ms, start_ms, end_ms)


def _connect(source: Source) -> sqlite3.Connection | None:
    path = source.db_path
    if not path.is_file():
        return None
    try:
        return open_ro(path)
    except sqlite3.Error:
        return None


def _per_source(start_ms, end_ms, fn):
    """Run fn(conn, source, where, params) for every readable source."""
    out = []
    where, params = _where(start_ms, end_ms)
    for source in SOURCES:
        conn = _connect(source)
        if conn is None:
            continue
        try:
            out.extend(fn(conn, source, where, params))
        except sqlite3.Error:
            # A schema that moved is reported by the Sources tab, not by a
            # traceback in the middle of an aggregate.
            continue
        finally:
            conn.close()
    return out


def _classify(status) -> str:
    value = (status or "").strip().lower()
    if value in OK_STATUSES:
        return "ok"
    if value in FAIL_STATUSES:
        return "fail"
    return "pending"


# --- tokens -----------------------------------------------------------------

def token_rows(start_ms: int | None, end_ms: int) -> list[TokenRow]:
    def query(conn, source, where, params):
        rows = conn.execute(
            f"SELECT COALESCE(model, '(unknown)'), COALESCE(provider, ''),"
            f" SUM({source.expr_input}), SUM({source.expr_output}),"
            f" SUM({source.expr_cache_read}), SUM({source.expr_cache_write}),"
            f" SUM({source.expr_total}), COUNT(*), MAX(ts)"
            f" FROM {source.table} WHERE {where}"
            f" GROUP BY model, provider",
            params,
        ).fetchall()
        return [
            TokenRow(
                source=source.key, label=source.label,
                model=str(r[0]), provider=str(r[1] or ""),
                input=int(r[2] or 0), output=int(r[3] or 0),
                cache_read=int(r[4] or 0), cache_write=int(r[5] or 0),
                total=int(r[6] or 0), requests=int(r[7] or 0),
                last_used=int(r[8]) if r[8] is not None else None,
            )
            for r in rows
        ]

    return _per_source(start_ms, end_ms, query)


def by_source(rows: list[TokenRow]) -> list[TokenRow]:
    """Fold model rows into one row per source, keeping the same shape."""
    folded: dict[str, TokenRow] = {}
    for row in rows:
        target = folded.get(row.source)
        if target is None:
            folded[row.source] = TokenRow(
                source=row.source, label=row.label, model="(all models)",
                provider="", input=row.input, output=row.output,
                cache_read=row.cache_read, cache_write=row.cache_write,
                total=row.total, requests=row.requests, last_used=row.last_used,
            )
            continue
        target.input += row.input
        target.output += row.output
        target.cache_read += row.cache_read
        target.cache_write += row.cache_write
        target.total += row.total
        target.requests += row.requests
        if row.last_used and (target.last_used is None or row.last_used > target.last_used):
            target.last_used = row.last_used
    return list(folded.values())


# --- entities (skills / tools) ----------------------------------------------

def entity_rows(kind: str, start_ms: int | None, end_ms: int) -> list[EntityRow]:
    table, name_col = ENTITY_TABLES[kind]
    ok_list = ", ".join(f"'{s}'" for s in OK_STATUSES)
    fail_list = ", ".join(f"'{s}'" for s in FAIL_STATUSES)

    def query(conn, source, where, params):
        rows = conn.execute(
            f"SELECT COALESCE({name_col}, '(unknown)'), COUNT(*),"
            f" SUM(CASE WHEN lower(COALESCE(status,'')) IN ({ok_list}) THEN 1 ELSE 0 END),"
            f" SUM(CASE WHEN lower(COALESCE(status,'')) IN ({fail_list}) THEN 1 ELSE 0 END),"
            f" AVG(duration_ms), MAX(ts)"
            f" FROM {table} WHERE {where} GROUP BY {name_col}",
            params,
        ).fetchall()
        return [(source.key, r) for r in rows]

    # Tools are spelled differently per host ("Read" in cbut, "read" in ocut).
    # Merging is case-insensitive, and the row keeps the spelling the most calls
    # used — so one tool is one row instead of two that each look half-used.
    # Only case is folded: "Bash" and "shell" stay apart, because whether they
    # are the same tool is a guess this file must not make.
    merged: dict[str, EntityRow] = {}
    spellings: dict[str, dict[str, int]] = {}
    for key, r in _per_source(start_ms, end_ms, query):
        name = str(r[0])
        calls = int(r[1] or 0)
        merge_key = name.casefold()
        target = merged.get(merge_key)
        if target is None:
            target = merged[merge_key] = EntityRow(name=name)
            spellings[merge_key] = {}
        seen = spellings[merge_key]
        seen[name] = seen.get(name, 0) + calls
        target.per_source[key] = target.per_source.get(key, 0) + calls
        target.calls += calls
        target.ok += int(r[2] or 0)
        target.fail += int(r[3] or 0)
        target.pending += calls - int(r[2] or 0) - int(r[3] or 0)
        if r[4] is not None:
            # Weighted by calls, so a 5-call average does not outweigh 500 calls.
            weight = target.calls - calls
            total_ms = (target.avg_ms or 0.0) * weight + float(r[4]) * calls
            target.avg_ms = total_ms / target.calls if target.calls else None
        if r[5] is not None:
            ts = int(r[5])
            target.last_used = ts if target.last_used is None else max(target.last_used, ts)

    for merge_key, row in merged.items():
        row.name = max(spellings[merge_key].items(), key=lambda kv: kv[1])[0]
    return list(merged.values())


# --- timeline ---------------------------------------------------------------

def call_rows(start_ms: int | None, end_ms: int, limit: int = 300) -> list[CallRow]:
    def query(conn, source, where, params):
        rows = conn.execute(
            f"SELECT ts, COALESCE(model, ''), {source.expr_project},"
            f" COALESCE(session_id, ''), {source.expr_total}"
            f" FROM {source.table} WHERE {where} ORDER BY ts DESC LIMIT ?",
            (*params, limit),
        ).fetchall()
        return [
            CallRow(ts=int(r[0]), source=source.key, label=source.label,
                    model=str(r[1]), project=str(r[2]), session=str(r[3]),
                    total=int(r[4] or 0))
            for r in rows
        ]

    rows = _per_source(start_ms, end_ms, query)
    rows.sort(key=lambda r: r.ts, reverse=True)
    return rows[:limit]


# --- dashboard --------------------------------------------------------------

def day_labels(start_ms: int | None, end_ms: int, max_days: int = 30) -> list[str]:
    """Local calendar days covered by the window, newest last, capped."""
    end_day = date.fromtimestamp(end_ms / 1000)
    if start_ms is None:
        start_day = end_day - timedelta(days=max_days - 1)
    else:
        start_day = date.fromtimestamp(start_ms / 1000)
    span = (end_day - start_day).days + 1
    if span > max_days:
        start_day = end_day - timedelta(days=max_days - 1)
        span = max_days
    return [(start_day + timedelta(days=i)).isoformat() for i in range(span)]


def daily_tokens(start_ms: int | None, end_ms: int) -> tuple[list[str], dict[str, list[int]]]:
    """Per-source tokens per local day, aligned to one shared label list."""
    labels = day_labels(start_ms, end_ms)
    series: dict[str, list[int]] = {}

    def query(conn, source, where, params):
        rows = conn.execute(
            f"SELECT date(ts/1000,'unixepoch','localtime') AS d,"
            f" SUM({source.expr_total}) FROM {source.table}"
            f" WHERE {where} GROUP BY d",
            params,
        ).fetchall()
        return [(source.key, r) for r in rows]

    buckets: dict[str, dict[str, int]] = {}
    for key, r in _per_source(start_ms, end_ms, query):
        buckets.setdefault(key, {})[str(r[0])] = int(r[1] or 0)

    for source in SOURCES:
        day_map = buckets.get(source.key)
        if day_map is None:
            continue
        series[source.key] = [day_map.get(label, 0) for label in labels]
    return labels, series


def kpis(start_ms: int | None, end_ms: int, _delta: bool = True) -> Kpis:
    out = Kpis()

    def query(conn, source, where, params):
        row = conn.execute(
            f"SELECT SUM({source.expr_total}), COUNT(*),"
            f" COUNT(DISTINCT session_id),"
            f" COUNT(DISTINCT date(ts/1000,'unixepoch','localtime'))"
            f" FROM {source.table} WHERE {where}",
            params,
        ).fetchone()
        return [(source.key, row)]

    for key, row in _per_source(start_ms, end_ms, query):
        tokens = int(row[0] or 0)
        out.tokens += tokens
        out.per_source[key] = tokens
        out.calls += int(row[1] or 0)
        out.sessions += int(row[2] or 0)
        out.active_days = max(out.active_days, int(row[3] or 0))

    # The delta compares against the window of the same length immediately
    # before this one. "All time" has nothing before it, so it reports no delta
    # rather than a meaningless zero.
    if start_ms is not None and _delta:
        # Shift by whole calendar days, so "today so far" is compared with the
        # same time of day yesterday — not with the evening before, which is
        # what shifting by the elapsed milliseconds would do.
        span_days = max(1, round((end_ms - start_ms) / DAY_MS))
        prev = kpis(start_ms - span_days * DAY_MS, end_ms - span_days * DAY_MS,
                    _delta=False)
        out.prev_tokens = prev.tokens
        out.prev_sessions = prev.sessions
    return out


def now_ms() -> int:
    return int(time.time() * 1000)

# --- detail screens ---------------------------------------------------------

def model_calls(source_key: str, name: str, start_ms: int | None, end_ms: int,
                limit: int = 200) -> list[CallRow]:
    """Every call of one model on one source, newest first."""
    source = next((s for s in SOURCES if s.key == source_key), None)
    if source is None:
        return []
    conn = _connect(source)
    if conn is None:
        return []
    where, params = _where(start_ms, end_ms)
    try:
        rows = conn.execute(
            f"SELECT ts, {source.expr_project}, COALESCE(session_id, ''),"
            f" {source.expr_total} FROM {source.table}"
            f" WHERE {where} AND model = ? ORDER BY ts DESC LIMIT ?",
            (*params, name, limit),
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        conn.close()
    return [CallRow(ts=int(r[0]), source=source.key, label=source.label,
                    model=name, project=str(r[1]), session=str(r[2]),
                    total=int(r[3] or 0)) for r in rows]


def model_daily(source_key: str, name: str, start_ms: int | None,
                end_ms: int) -> tuple[list[str], list[int]]:
    source = next((s for s in SOURCES if s.key == source_key), None)
    if source is None:
        return [], []
    conn = _connect(source)
    if conn is None:
        return [], []
    where, params = _where(start_ms, end_ms)
    labels = day_labels(start_ms, end_ms)
    try:
        rows = conn.execute(
            f"SELECT date(ts/1000,'unixepoch','localtime') AS d, SUM({source.expr_total})"
            f" FROM {source.table} WHERE {where} AND model = ? GROUP BY d",
            (*params, name),
        ).fetchall()
    except sqlite3.Error:
        return labels, [0] * len(labels)
    finally:
        conn.close()
    by_day = {str(r[0]): int(r[1] or 0) for r in rows}
    return labels, [by_day.get(label, 0) for label in labels]


def entity_calls(kind: str, name: str, start_ms: int | None, end_ms: int,
                 limit: int = 200) -> list[CallRow]:
    """Every recorded call of one skill or tool, newest first."""
    table, name_col = ENTITY_TABLES[kind]
    where, params = _where(start_ms, end_ms)
    out: list[CallRow] = []
    for source in SOURCES:
        conn = _connect(source)
        if conn is None:
            continue
        try:
            rows = conn.execute(
                f"SELECT ts, COALESCE(project, ''), COALESCE(session_id, ''),"
                f" COALESCE(status, ''), COALESCE(duration_ms, 0)"
                f" FROM {table} WHERE {where} AND {name_col} = ?"
                f" ORDER BY ts DESC LIMIT ?",
                (*params, name, limit),
            ).fetchall()
        except sqlite3.Error:
            continue
        finally:
            conn.close()
        for r in rows:
            out.append(CallRow(ts=int(r[0]), source=source.key, label=source.label,
                               model=str(r[3]), project=str(r[1]),
                               session=str(r[2]), total=int(r[4] or 0)))
    out.sort(key=lambda r: r.ts, reverse=True)
    return out[:limit]
