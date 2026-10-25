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

import contextlib
import contextvars
import re
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

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

# One model reaches the board under more than one name: the provider's id keeps
# its dots ("deepseek-v4.1-flash") in one tracker and loses them
# ("deepseek-v4-1-flash") in another, and a free route appends "-free". Those
# are one model and one number. Only the merged views fold them — every record
# keeps the spelling its tracker wrote.
#
# Names that cannot be inferred from the string itself belong here by hand,
# keyed by the folded name, valued by the model it stands for. Nothing is
# guessed by similarity: gpt-5.6-luna and gpt-5.6-terra are different models.
MODEL_ALIASES: dict[str, str] = {
    # Qoder's builtin routes report an internal id and nothing else: its
    # provider_id column is NULL for every one of them (checked against the real
    # index), so the label in its model picker is the only source of truth.
    # DeepSeek-Flash is "DeepSeek-V4.1-Flash-1017" there, i.e. the model cbut
    # and ocut already record; Qwen3.8-Flash is Qoder-only so far.
    "dfmodel": "deepseek-v4.1-flash",
    "qfmodel": "qwen3.8-flash",
}


def _folded(name: str) -> str:
    out = re.sub(r"[._\s]+", "-", name.strip().casefold())
    return re.sub(r"-{2,}", "-", out).strip("-")


def canonical_model(name: str) -> str:
    """The key that two spellings of one model share.

    Punctuation and the free-route suffix, nothing else: versions are not
    folded, so deepseek-v4-flash stays apart from deepseek-v4.1-flash.
    """
    key = _folded(name)
    return re.sub(r"-free$", "", _folded(MODEL_ALIASES.get(key, key)))


# --- rows -------------------------------------------------------------------

@dataclass(slots=True)
class TokenRow:
    source: str
    label: str
    model: str
    provider: str
    input: int | None
    output: int | None
    cache_read: int | None
    cache_write: int | None
    total: int | None
    requests: int
    last_used: int | None
    # False when any call in the row reported no usage: the total is then a
    # floor, not an exact sum. None total means no token figure at all.
    tokens_real: bool = True


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
    # Every spelling the case-fold merged, the displayed one first. The detail
    # queries all of them, so a merged row and its drill-down agree.
    spellings: tuple[str, ...] = ()
    # Calls with a measured duration. The average's denominator is this, not
    # calls: a NULL duration is not a zero-millisecond call.
    measured_calls: int = 0


@dataclass(slots=True)
class CallRow:
    ts: int
    source: str
    label: str
    model: str
    project: str
    session: str
    total: int | None
    count: int = 1
    # Entity detail rows carry a status and a duration instead of a model and a
    # token total; the table chooses its columns from these fields.
    status: str = ""
    duration_ms: int | None = None


@dataclass(slots=True)
class Kpis:
    tokens: int | None = None
    sessions: int = 0
    calls: int = 0
    active_days: int = 0
    per_source: dict[str, int | None] = field(default_factory=dict)
    prev_tokens: int | None = None
    prev_sessions: int | None = None
    tokens_real: bool = True


# --- plumbing ---------------------------------------------------------------

def _where(start_ms: int | None, end_ms: int):
    """A bound pair usable with one parameter repeated twice for NULL = all time."""
    return "(? IS NULL OR ts >= ?) AND ts <= ?", (start_ms, start_ms, end_ms)


# The connections `read_session()` opened for the current block, if any. A
# ContextVar rather than a global so a second task's reload cannot inherit this
# one's snapshot.
_READ_SESSION: contextvars.ContextVar[dict[str, sqlite3.Connection] | None] = \
    contextvars.ContextVar("aut_read_session", default=None)


@contextlib.contextmanager
def read_session():
    """One read transaction per source for everything inside the block.

    A tab's reload asks several questions — the KPIs, the model rows, the
    skills, the newest call. Answered one at a time, a tracker syncing in
    between can serve the first from before its commit and the last from
    after, and the screen then holds two different moments that look like one
    picture. Inside this block each source is read through one connection in
    one read transaction, so a screen is a snapshot. Cross-source consistency
    is still not claimed: the three indexes commit independently.
    """
    conns: dict[str, sqlite3.Connection] = {}
    for source in SOURCES:
        path = source.db_path
        if not path.is_file():
            continue
        try:
            conn = open_ro(path)
            conn.execute("BEGIN")
        except sqlite3.Error:
            continue
        conns[source.key] = conn
    token = _READ_SESSION.set(conns)
    try:
        yield conns
    finally:
        _READ_SESSION.reset(token)
        for conn in conns.values():
            conn.close()


def _connect(source: Source) -> sqlite3.Connection | None:
    """A connection to read one source from.

    Inside `read_session()` this is the session's own connection, so every
    question a screen asks is answered from one snapshot; outside it, the
    caller gets a connection it must close.
    """
    session = _READ_SESSION.get()
    if session is not None:
        return session.get(source.key)
    path = source.db_path
    if not path.is_file():
        return None
    try:
        return open_ro(path)
    except sqlite3.Error:
        return None


def _close(conn: sqlite3.Connection) -> None:
    """Close a connection unless `read_session()` owns it."""
    if _READ_SESSION.get() is None:
        conn.close()


# What the merges could not read, by (source, query). A column that only this
# layer names has no other way to surface: the source's own snapshot can be
# fine while the tab it feeds is empty. Sources reads this so "contributes
# nothing" never looks like "ok".
_ERRORS: dict[tuple[str, str], str] = {}


def source_errors() -> dict[str, str]:
    """Sources whose merge query failed, and the reason. Empty when all is well."""
    out: dict[str, str] = {}
    for (key, _query), message in _ERRORS.items():
        out.setdefault(key, message)
    return out


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
        except sqlite3.Error as exc:
            # A schema that moved is reported by the Sources tab, not by a
            # traceback in the middle of an aggregate — but it is still
            # reported: the key is the query, so a repaired index clears it.
            _ERRORS[(source.key, fn.__qualname__)] = str(exc)
            continue
        else:
            _ERRORS.pop((source.key, fn.__qualname__), None)
        finally:
            _close(conn)
    return out


def _classify(status) -> str:
    value = (status or "").strip().lower()
    if value in OK_STATUSES:
        return "ok"
    if value in FAIL_STATUSES:
        return "fail"
    return "pending"


def _opt_int(value) -> int | None:
    """SQL NULL means "not reported"; it must not become a zero."""
    return int(value) if value is not None else None


def _sum_opt(left: int | None, right: int | None) -> int | None:
    """Add two optional counts; an unknown part makes the sum unknown too."""
    if left is None or right is None:
        return None
    return left + right


# --- tokens -----------------------------------------------------------------

def token_rows(start_ms: int | None, end_ms: int) -> list[TokenRow]:
    def query(conn, source, where, params):
        rows = conn.execute(
            f"SELECT COALESCE(model, '(unknown)'), COALESCE(provider, ''),"
            f" SUM({source.expr_input}), SUM({source.expr_output}),"
            f" SUM({source.expr_cache_read}), SUM({source.expr_cache_write}),"
            f" SUM({source.expr_total}), COUNT(*), MAX(ts), AVG({source.real_col}),"
            f" SUM(CASE WHEN {source.expr_total} IS NULL THEN 1 ELSE 0 END)"
            f" FROM {source.table} WHERE {where}"
            f" GROUP BY model, provider",
            params,
        ).fetchall()
        out = []
        for r in rows:
            unknown = int(r[10] or 0)
            total = None if unknown else _opt_int(r[6])
            real_avg = r[9]
            out.append(TokenRow(
                source=source.key, label=source.label,
                model=str(r[0]), provider=str(r[1] or ""),
                input=_opt_int(r[2]), output=_opt_int(r[3]),
                cache_read=_opt_int(r[4]), cache_write=_opt_int(r[5]),
                total=total, requests=int(r[7] or 0),
                last_used=int(r[8]) if r[8] is not None else None,
                tokens_real=(total is not None and unknown == 0
                             and (real_avg is None or float(real_avg) >= 0.999)),
            ))
        return out

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
                tokens_real=row.tokens_real,
            )
            continue
        target.input = _sum_opt(target.input, row.input)
        target.output = _sum_opt(target.output, row.output)
        target.cache_read = _sum_opt(target.cache_read, row.cache_read)
        target.cache_write = _sum_opt(target.cache_write, row.cache_write)
        target.total = _sum_opt(target.total, row.total)
        target.requests += row.requests
        target.tokens_real = target.tokens_real and row.tokens_real
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
            f" AVG(duration_ms), MAX(ts), COUNT(duration_ms)"
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
        measured = int(r[6] or 0)
        target.measured_calls += measured
        if r[4] is not None and measured:
            # Weighted by measured calls only, so a NULL duration is not a
            # zero-millisecond call in the denominator.
            weight = target.measured_calls - measured
            total_ms = (target.avg_ms or 0.0) * weight + float(r[4]) * measured
            target.avg_ms = total_ms / target.measured_calls
        if r[5] is not None:
            ts = int(r[5])
            target.last_used = ts if target.last_used is None else max(target.last_used, ts)

    for merge_key, row in merged.items():
        seen = spellings[merge_key]
        row.name = max(seen.items(), key=lambda kv: kv[1])[0]
        row.spellings = (row.name, *(name for name in seen if name != row.name))
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
                    total=_opt_int(r[4]))
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
            f" COUNT(DISTINCT session_id), AVG({source.real_col}),"
            f" SUM(CASE WHEN {source.expr_total} IS NULL THEN 1 ELSE 0 END)"
            f" FROM {source.table} WHERE {where}",
            params,
        ).fetchone()
        dates = conn.execute(
            f"SELECT DISTINCT date(ts/1000,'unixepoch','localtime')"
            f" FROM {source.table} WHERE {where}",
            params,
        ).fetchall()
        return [(source.key, row, {str(r[0]) for r in dates})]

    active_dates: set[str] = set()
    unknown = False
    seen = False
    total = 0
    for key, row, dates in _per_source(start_ms, end_ms, query):
        seen = True
        row_calls = int(row[1] or 0)
        # No calls in this window is a real zero; calls whose token columns are
        # all NULL are unknown and make the merged total unknown.
        unknown_row = int(row[4] or 0)
        tokens = (None if unknown_row
                  else (0 if row_calls == 0 else _opt_int(row[0])))
        if tokens is None:
            unknown = True
        else:
            total += tokens
        out.per_source[key] = tokens
        out.calls += row_calls
        out.sessions += int(row[2] or 0)
        active_dates |= dates
        out.tokens_real = out.tokens_real and (
            tokens is not None
            and (row[3] is None or float(row[3]) >= 0.999))
    out.tokens = None if not seen or unknown else total
    # Active days are the union of the days any tracker saw a call, not the
    # busiest single tracker's count: two trackers used on different days are
    # two active days.
    out.active_days = len(active_dates)

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

def _model_in(names: tuple[str, ...]) -> tuple[str, tuple[str, ...]]:
    """`model IN (?,?)` for every spelling a merged row stands for.

    ``(unknown)`` is the display label for SQL NULL, not a model named that;
    the detail has to ask for ``model IS NULL`` or it lists nothing.
    """
    clauses = []
    params = []
    for name in names:
        if name == "(unknown)":
            clauses.append("model IS NULL")
        else:
            clauses.append("model = ?")
            params.append(name)
    return f"({' OR '.join(clauses)})", tuple(params)


def _entity_in(name_col: str, names: tuple[str, ...]) -> tuple[str, tuple[str, ...]]:
    """The same NULL-aware match for a skill or tool name column."""
    clauses = []
    params = []
    for name in names:
        if name == "(unknown)":
            clauses.append(f"{name_col} IS NULL")
        else:
            clauses.append(f"{name_col} = ?")
            params.append(name)
    return f"({' OR '.join(clauses)})", tuple(params)


def model_calls(source_key: str | None, names: tuple[str, ...], start_ms: int | None,
                end_ms: int, limit: int = 200) -> list[CallRow]:
    """Every call of one model, newest first.

    source_key=None means every tracker: one model is often used through more
    than one tool, and the interesting number is the sum, not each half. The
    names are the spellings the merged row folded; each call keeps its own.
    """
    if source_key is None:
        targets = list(SOURCES)
    else:
        target = next((s for s in SOURCES if s.key == source_key), None)
        targets = [target] if target is not None else []

    where, params = _where(start_ms, end_ms)
    out: list[CallRow] = []
    for source in targets:
        conn = _connect(source)
        if conn is None:
            continue
        clause, wanted = _model_in(names)
        try:
            rows = conn.execute(
                f"SELECT ts, {source.expr_project}, COALESCE(session_id, ''),"
                f" {source.expr_total}, model FROM {source.table}"
                f" WHERE {where} AND {clause} ORDER BY ts DESC LIMIT ?",
                (*params, *wanted, limit),
            ).fetchall()
        except sqlite3.Error:
            continue
        finally:
            _close(conn)
        out.extend(CallRow(ts=int(r[0]), source=source.key, label=source.label,
                           model=str(r[4] or ""), project=str(r[1]),
                           session=str(r[2]), total=_opt_int(r[3])) for r in rows)
    out.sort(key=lambda r: r.ts, reverse=True)
    return out[:limit]


def model_daily(source_key: str | None, names: tuple[str, ...], start_ms: int | None,
                end_ms: int) -> tuple[list[str], list[int]]:
    """One model's tokens per day, summed across every tracker when key is None."""
    if source_key is None:
        targets = list(SOURCES)
    else:
        target = next((s for s in SOURCES if s.key == source_key), None)
        targets = [target] if target is not None else []

    labels = day_labels(start_ms, end_ms)
    where, params = _where(start_ms, end_ms)
    totals = {label: 0 for label in labels}
    for source in targets:
        conn = _connect(source)
        if conn is None:
            continue
        clause, wanted = _model_in(names)
        try:
            rows = conn.execute(
                f"SELECT date(ts/1000,'unixepoch','localtime') AS d, SUM({source.expr_total})"
                f" FROM {source.table} WHERE {where} AND {clause} GROUP BY d",
                (*params, *wanted),
            ).fetchall()
        except sqlite3.Error:
            continue
        finally:
            _close(conn)
        for row in rows:
            key = str(row[0])
            if key in totals:
                totals[key] += int(row[1] or 0)
    return labels, [totals[label] for label in labels]


def entity_calls(kind: str, names: str | tuple[str, ...], start_ms: int | None,
                 end_ms: int, limit: int = 200) -> list[CallRow]:
    """Every recorded call of one skill or tool, newest first.

    ``names`` is every spelling the merged row stands for. Querying only the
    displayed one made a two-tracker row show half its calls.
    """
    table, name_col = ENTITY_TABLES[kind]
    wanted = (names,) if isinstance(names, str) else tuple(names)
    clause, wanted_params = _entity_in(name_col, wanted)
    where, params = _where(start_ms, end_ms)
    out: list[CallRow] = []
    for source in SOURCES:
        conn = _connect(source)
        if conn is None:
            continue
        try:
            rows = conn.execute(
                f"SELECT ts, COALESCE(project, ''), COALESCE(session_id, ''),"
                f" COALESCE(status, ''), duration_ms"
                f" FROM {table} WHERE {where} AND {clause}"
                f" ORDER BY ts DESC LIMIT ?",
                (*params, *wanted_params, limit),
            ).fetchall()
        except sqlite3.Error:
            continue
        finally:
            _close(conn)
        for r in rows:
            out.append(CallRow(ts=int(r[0]), source=source.key, label=source.label,
                               model="", project=str(r[1]), session=str(r[2]),
                               total=None, status=str(r[3]),
                               duration_ms=_opt_int(r[4])))
    out.sort(key=lambda r: r.ts, reverse=True)
    return out[:limit]

# --- timeline ---------------------------------------------------------------

@dataclass(slots=True)
class Timeline:
    """One chart's worth of numbers, already aligned to one label list."""
    unit: str                   # "hour" | "day"
    labels: list[str]           # short display labels, one per bucket
    series: dict[str, list[int]] = field(default_factory=dict)

    @property
    def totals(self) -> list[int]:
        if not self.series:
            return [0] * len(self.labels)
        return [sum(v[i] for v in self.series.values()) for i in range(len(self.labels))]


@dataclass(slots=True)
class ModelTotal:
    """One model across every tracker that used it."""
    model: str
    total: int | None = None
    per_source: dict[str, int | None] = field(default_factory=dict)
    requests: int = 0
    last_used: int | None = None
    # Every spelling folded into this row, the displayed one first. The detail
    # screen queries by these, so a merged row and its drill-down agree.
    spellings: tuple[str, ...] = ()
    tokens_real: bool = True


HOUR_MS = 3_600_000


def granularity(start_ms: int | None, end_ms: int) -> str:
    """Hours for a window of two days or less, days beyond that.

    The window decides the unit: a one-day chart draws one day. Mixing a week of
    context into a "today" chart is how a dashboard ends up meaning nothing.
    """
    if start_ms is None:
        return "day"
    return "hour" if (end_ms - start_ms) <= 2 * DAY_MS else "day"


def hour_keys(start_ms: int, end_ms: int) -> list[datetime]:
    first = datetime.fromtimestamp(start_ms / 1000).replace(minute=0, second=0, microsecond=0)
    # Counted from the start of the first hour to the end of the window, so a
    # rolling 24h span yields 24 bars and a calendar day yields the hours that
    # have actually happened (00..13 at half past one).
    span = end_ms - int(first.timestamp() * 1000)
    count = max(1, -(-span // HOUR_MS))
    count = min(count, 48)
    return [first + timedelta(hours=i) for i in range(count)]


def timeline(start_ms: int | None, end_ms: int) -> Timeline:
    """Per-source tokens per bucket, on one shared axis."""
    unit = granularity(start_ms, end_ms)
    if unit == "hour" and start_ms is not None:
        stamps = hour_keys(start_ms, end_ms)
        keys = [s.strftime("%Y-%m-%dT%H") for s in stamps]
        labels = [f"{s.hour:02d}" for s in stamps]
        expr = "strftime('%Y-%m-%dT%H', ts/1000,'unixepoch','localtime')"
    else:
        unit = "day"
        keys = day_labels(start_ms, end_ms)
        labels = [k[5:] for k in keys]
        expr = "date(ts/1000,'unixepoch','localtime')"

    def query(conn, source, where, params):
        rows = conn.execute(
            f"SELECT {expr} AS b, SUM({source.expr_total}) FROM {source.table}"
            f" WHERE {where} GROUP BY b",
            params,
        ).fetchall()
        return [(source.key, r) for r in rows]

    buckets: dict[str, dict[str, int]] = {}
    for key, row in _per_source(start_ms, end_ms, query):
        buckets.setdefault(key, {})[str(row[0])] = int(row[1] or 0)

    out = Timeline(unit=unit, labels=labels)
    for source in SOURCES:
        day_map = buckets.get(source.key)
        if day_map is None:
            continue
        out.series[source.key] = [day_map.get(k, 0) for k in keys]
    return out


def model_totals(rows: list[TokenRow]) -> list[ModelTotal]:
    """Fold per-(source, model) rows into one row per model.

    The same model is often used through two trackers, and under two spellings
    even inside one (see canonical_model); showing it twice splits the number
    the reader came for. The row keeps the spelling that carried the most
    tokens, and remembers the rest so the detail screen can read them all.
    """
    merged: dict[str, ModelTotal] = {}
    spellings: dict[str, dict[str, int]] = {}
    for row in rows:
        key = canonical_model(row.model)
        target = merged.get(key)
        if target is None:
            target = merged[key] = ModelTotal(model=row.model, total=row.total)
            spellings[key] = {}
        else:
            target.total = _sum_opt(target.total, row.total)
        weight = row.total or 0
        spellings[key][row.model] = spellings[key].get(row.model, 0) + weight
        target.requests += row.requests
        target.tokens_real = target.tokens_real and row.tokens_real
        if row.last_used and (target.last_used is None or row.last_used > target.last_used):
            target.last_used = row.last_used
        if row.source in target.per_source:
            target.per_source[row.source] = _sum_opt(
                target.per_source[row.source], row.total)
        else:
            target.per_source[row.source] = row.total
    for key, target in merged.items():
        # The row is the model, not the platform's id for it: a spelling that is
        # itself an alias loses, then a free-route suffix, then token weight.
        ordered = sorted(spellings[key].items(),
                         key=lambda kv: (_folded(kv[0]) in MODEL_ALIASES,
                                         kv[0].casefold().endswith("-free"), -kv[1]))
        raw = [name for name, _ in ordered]
        # An alias names the model the platform's id stands for, so it wins the
        # title even when it never appears in a row (a Qoder-only model has no
        # other spelling). The id stays in the spellings, which the detail reads.
        alias = next((MODEL_ALIASES[_folded(n)] for n in raw
                      if _folded(n) in MODEL_ALIASES), None)
        target.model = alias or raw[0]
        target.spellings = (target.model, *(n for n in raw if n != target.model))
    return sorted(merged.values(),
                  key=lambda m: (m.total is not None, m.total or 0), reverse=True)


def collapse_calls(rows: list[CallRow], bucket_ms: int = 60_000) -> list[CallRow]:
    """Merge calls identical in every visible way within one minute.

    One agent turn writes a dozen rows that differ only by a millisecond
    timestamp. Printed one per line they bury the rows that matter; merged they
    read as "this model, 26 calls, 42K tokens".
    """
    out: list[CallRow] = []
    seen: dict[tuple, int] = {}
    for row in rows:
        key = (row.ts // bucket_ms, row.source, row.model, row.project, row.session)
        slot = seen.get(key)
        if slot is None:
            seen[key] = len(out)
            out.append(row)
            continue
        target = out[slot]
        target.total = _sum_opt(target.total, row.total)
        target.count += row.count
        target.ts = max(target.ts, row.ts)
    return out


def model_stats(source_key: str | None, names: tuple[str, ...], start_ms: int | None,
                end_ms: int) -> tuple[int, int]:
    """(tokens, calls) for one model — the whole window, not the first 200 rows.

    The detail screen lists the newest calls, which is a page, not a total; the
    header must not read 40M when the model used 81M.
    """
    if source_key is None:
        targets = list(SOURCES)
    else:
        target = next((s for s in SOURCES if s.key == source_key), None)
        targets = [target] if target is not None else []

    where, params = _where(start_ms, end_ms)
    tokens = 0
    unknown = False
    seen = False
    calls = 0
    for source in targets:
        conn = _connect(source)
        if conn is None:
            continue
        clause, wanted = _model_in(names)
        try:
            row = conn.execute(
                f"SELECT SUM({source.expr_total}), COUNT(*),"
                f" SUM(CASE WHEN {source.expr_total} IS NULL THEN 1 ELSE 0 END)"
                f" FROM {source.table} WHERE {where} AND {clause}",
                (*params, *wanted),
            ).fetchone()
        except sqlite3.Error:
            continue
        finally:
            _close(conn)
        seen = True
        row_calls = int(row[1] or 0)
        calls += row_calls
        unknown_row = int(row[2] or 0)
        value = (None if unknown_row
                 else (0 if row_calls == 0 else _opt_int(row[0])))
        if value is None:
            unknown = True
        else:
            tokens += value
    return (None if not seen or unknown else tokens), calls
