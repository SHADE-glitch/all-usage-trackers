"""One adapter per tracker.

Each adapter knows three things about its tracker and nothing else: where its
SQLite index lives, how to read a normalised snapshot out of it, and how to launch
it. Adding a fourth tracker means adding one entry to `SOURCES` — not touching the
TUI.

The schemas genuinely differ (cbut calls the table `model_responses` and the
columns `prompt/completion_tokens`; the other two call it `model_calls`), so the
normalisation lives here, in one SQL expression per source, rather than in the app.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from aut_db import DAY_MS, cutoff_ms, open_ro, spark_width

# A tracker nobody has opened in a week is not "broken" — it is idle. The two
# words are kept apart so a badge never implies a fault that is just no usage.
IDLE_AFTER_MS = 7 * DAY_MS


@dataclass(slots=True)
class Snapshot:
    key: str
    label: str
    status: str                     # ok | idle | missing | error
    note: str
    tokens: int | None = None
    tokens_real: bool = True
    cost: float | None = None
    cost_unit: str = ""
    sessions: int = 0
    calls: int = 0
    buckets: list[int] = field(default_factory=list)
    top_models: list[tuple[str, int]] = field(default_factory=list)
    top_projects: list[tuple[str, int]] = field(default_factory=list)
    last_event_ms: int | None = None
    db_path: Path | None = None
    db_size: int = 0


@dataclass(frozen=True, slots=True)
class Source:
    key: str
    label: str
    db_name: str
    binary: str
    table: str
    cost_expr: str
    real_col: str
    cost_unit: str
    # The same call table, named by the columns the tab-level aggregations need.
    # Keeping the six expressions here means a schema change is one edit in one
    # file, and `aut_model` never learns a column name.
    expr_input: str
    expr_output: str
    expr_cache_read: str
    expr_cache_write: str
    expr_total: str
    # OpenCode stores a hashed project id and the directory beside it, so the
    # path has to be named explicitly; the other two put the path in 'project'.
    expr_project: str

    @property
    def db_path(self) -> Path:
        return Path.home() / ".local" / "share" / self.db_name / "usage.db"

    def launch_argv(self) -> list[str]:
        return [self.binary]

    def sync_argv(self) -> list[str]:
        return [self.binary, "sync"]

    def snapshot(self, days: int, now_ms: int | None = None,
                 since_ms: int | None = None,
                 end_ms: int | None = None) -> Snapshot:
        now = int(time.time() * 1000) if now_ms is None else now_ms
        path = self.db_path
        if not path.is_file():
            return Snapshot(
                key=self.key,
                label=self.label,
                status="missing",
                note=f"no index at {path} — run `{self.binary} sync`",
                db_path=path,
            )

        size = path.stat().st_size
        try:
            conn = open_ro(path)
        except sqlite3.Error as exc:
            return Snapshot(
                key=self.key, label=self.label, status="error",
                note=f"cannot open {path}: {exc}", db_path=path, db_size=size,
            )

        try:
            return self._read(conn, days, now, path, size, since_ms, end_ms)
        except sqlite3.Error as exc:
            # A tracker that changed its schema is a real event, not a crash:
            # the row says so and the other two sources keep working.
            return Snapshot(
                key=self.key, label=self.label, status="error",
                note=f"{self.table}: {exc}", db_path=path, db_size=size,
            )
        finally:
            conn.close()

    def _read(self, conn: sqlite3.Connection, days: int, now: int,
              path: Path, size: int, since_ms: int | None = None,
              end_ms: int | None = None) -> Snapshot:
        # A caller with a calendar window (the Sources tab) passes its own start
        # and end, so this row and the KPI strip above it count the same calls.
        # A rolling "last 24h" here against a "since midnight" total above is
        # how two numbers on one screen end up disagreeing.
        end = now if end_ms is None else int(end_ms)
        since = cutoff_ms(days, end) if since_ms is None else since_ms
        total, cost, calls, sessions, real_avg, unknown = conn.execute(
            f"SELECT SUM({self.expr_total}), SUM({self.cost_expr}), COUNT(*),"
            f" COUNT(DISTINCT session_id), AVG({self.real_col}),"
            f" SUM(CASE WHEN {self.expr_total} IS NULL THEN 1 ELSE 0 END)"
            f" FROM {self.table} WHERE ts >= ? AND ts <= ?",
            (since, end),
        ).fetchone()

        # No rows in the window is a real zero; rows whose token columns are all
        # NULL are unknown. A route that reports credits instead of tokens
        # (qcut's BYOK routes) is the second case, and printing "0" there would
        # read as "used nothing", which is the opposite of the truth.
        unknown = int(unknown or 0)
        known_calls = int(calls or 0) - unknown
        if not calls:
            tokens_value: int | None = 0
        elif known_calls == 0:
            tokens_value = None
        else:
            # A partly reported window is a floor: the known rows are summed
            # and `tokens_real` says the total is not exact.
            tokens_value = int(total or 0)
        money = float(cost) if cost is not None else None
        if tokens_value == 0 and money:
            tokens_value = None

        # The last event is the index's own last event up to the window end, not
        # the last one inside the selected window: a tracker used last month is
        # idle, not "never". Bounding by `end` keeps a historical view from
        # seeing calls that happened after the window it is showing.
        last_ts = conn.execute(
            f"SELECT MAX(ts) FROM {self.table} WHERE ts <= ?", (end,)
        ).fetchone()[0]

        width = spark_width(days)
        bucket_since = end - width * DAY_MS
        rows = conn.execute(
            f"SELECT date(ts/1000,'unixepoch','localtime') AS d, SUM({self.expr_total})"
            f" FROM {self.table} WHERE ts >= ? AND ts <= ? GROUP BY d",
            (bucket_since, end),
        ).fetchall()
        by_day = {row[0]: int(row[1] or 0) for row in rows}
        today = date.fromtimestamp(end / 1000)
        buckets = [
            by_day.get((today - timedelta(days=width - 1 - i)).isoformat(), 0)
            for i in range(width)
        ]

        top_models = self._top(conn, "model", since, end)
        top_projects = self._top(conn, "project", since, end)

        tokens_real = (tokens_value is not None and unknown == 0
                       and (real_avg is None or float(real_avg) >= 0.999))
        status = "ok"
        if last_ts is not None and end - int(last_ts) > IDLE_AFTER_MS:
            status = "idle"

        note = "all recorded calls carried usage" if tokens_real else \
            "some calls reported no usage — the token total is a floor"

        return Snapshot(
            key=self.key, label=self.label, status=status, note=note,
            tokens=tokens_value, tokens_real=tokens_real,
            cost=money, cost_unit=self.cost_unit,
            sessions=int(sessions or 0), calls=int(calls or 0),
            buckets=buckets, top_models=top_models, top_projects=top_projects,
            last_event_ms=int(last_ts) if last_ts is not None else None,
            db_path=path, db_size=size,
        )

    def _top(self, conn: sqlite3.Connection, column: str, since: int,
             end: int) -> list[tuple[str, int]]:
        expr = self.expr_project if column == "project" else column
        rows = conn.execute(
            f"SELECT {expr}, SUM({self.expr_total}) AS t FROM {self.table}"
            f" WHERE ts >= ? AND ts <= ? AND {expr} IS NOT NULL AND {expr} != ''"
            f" GROUP BY {expr} ORDER BY t DESC LIMIT 3",
            (since, end),
        ).fetchall()
        return [(str(row[0]), int(row[1] or 0)) for row in rows]


SOURCES: tuple[Source, ...] = (
    Source(
        key="cbut",
        label="CodeBuddy",
        db_name="codebuddy-usage-tracker",
        binary="cbut",
        table="model_responses",
        cost_expr="credit",
        real_col="usage_available",
        cost_unit="cr",
        expr_input="prompt_tokens",
        expr_output="completion_tokens",
        expr_cache_read="COALESCE(cache_read_input_tokens, 0)",
        expr_cache_write="COALESCE(cache_creation_input_tokens, 0)",
        # Usage Total, as cbut's own panels define it: the full prompt plus the
        # output, plus the cache hit again (the display-only re-add the family
        # uses). NULL when the API parts are missing, exactly as cbut's own
        # expression says; a missing cache-hit column contributes 0.
        expr_total=(
            "CASE WHEN prompt_tokens IS NOT NULL AND completion_tokens IS NOT NULL"
            " THEN prompt_tokens + completion_tokens"
            " + COALESCE(prompt_cache_hit_tokens, 0) ELSE NULL END"
        ),
        expr_project="COALESCE(project, '')",
    ),
    Source(
        key="ocut",
        label="OpenCode",
        db_name="opencode-usage-tracker",
        binary="ocut",
        table="model_calls",
        cost_expr="cost",
        real_col="usage_available",
        cost_unit="$",
        expr_input="prompt_tokens",
        expr_output="completion_tokens",
        expr_cache_read="COALESCE(cache_read, 0)",
        expr_cache_write="COALESCE(cache_write, 0)",
        # Usage Total, as ocut's panels define it: ocut reports an *uncached*
        # prompt, so the full prompt is prompt + read + write, and the cache
        # read is re-added once more — the same shape as cbut's number. NULL
        # only when there is no completion, or no prompt part at all; a partly
        # reported row still contributes.
        expr_total=(
            "CASE WHEN completion_tokens IS NULL THEN NULL"
            " WHEN prompt_tokens IS NULL AND cache_read IS NULL"
            " AND cache_write IS NULL THEN NULL"
            " ELSE COALESCE(prompt_tokens, 0) + completion_tokens"
            " + 2 * COALESCE(cache_read, 0) + COALESCE(cache_write, 0) END"
        ),
        expr_project="COALESCE(NULLIF(directory, ''), project, '')",
    ),
    Source(
        key="qcut",
        label="Qoder CN",
        db_name="qoder-cn-usage-tracker",
        binary="qcut",
        table="model_calls",
        cost_expr="credits",
        real_col="has_usage",
        cost_unit="cr",
        expr_input="input_tokens",
        expr_output="output_tokens",
        expr_cache_read="COALESCE(cache_read_tokens, 0)",
        expr_cache_write="COALESCE(cache_creation_tokens, 0)",
        # Usage Total, as qcut's panels define it: input + output + cache read.
        # NULL when the API parts are missing — a BYOK route reports credits and
        # no tokens, and that is not the same fact as "used zero".
        expr_total=(
            "CASE WHEN input_tokens IS NOT NULL AND output_tokens IS NOT NULL"
            " THEN input_tokens + output_tokens"
            " + COALESCE(cache_read_tokens, 0) ELSE NULL END"
        ),
        # qcut's model_calls carries the path in 'project' only; 'cwd' lives on
        # its sessions table, not here.
        expr_project="COALESCE(project, '')",
    ),
)

BY_KEY = {source.key: source for source in SOURCES}


def snapshots(days: int, now_ms: int | None = None,
              since_ms: int | None = None,
              end_ms: int | None = None) -> list[Snapshot]:
    return [source.snapshot(days, now_ms, since_ms, end_ms) for source in SOURCES]
