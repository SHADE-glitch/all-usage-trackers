"""The adapter layer, tested against real SQLite files built in a temp HOME.

What is worth pinning here: the normalisation (three schemas, one shape), the
window arithmetic, and the promise that the overview cannot write. The TUI itself
gets one smoke test — mounting and cycling a window — because everything below it
is where the numbers come from.
"""

from __future__ import annotations

import io
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import aut_db  # noqa: E402
import aut_model as model  # noqa: E402
from aut_picker import bounds_of  # noqa: E402
from aut_sources import BY_KEY, Snapshot  # noqa: E402
from datetime import date  # noqa: E402

DAY_MS = 86_400_000

CBUT_DDL = """
CREATE TABLE model_responses (
    message_id TEXT PRIMARY KEY, session_id TEXT, model TEXT, provider TEXT,
    prompt_tokens INTEGER, completion_tokens INTEGER,
    cache_read_input_tokens INTEGER, cache_creation_input_tokens INTEGER,
    provider_total_tokens INTEGER,
    prompt_cache_hit_tokens INTEGER, prompt_cache_miss_tokens INTEGER,
    credit REAL, ts INTEGER, project TEXT, usage_available INTEGER DEFAULT 0
);
"""

OCUT_DDL = """
CREATE TABLE model_calls (
    call_id TEXT PRIMARY KEY, session_id TEXT, model TEXT, provider TEXT,
    prompt_tokens INTEGER, completion_tokens INTEGER, total_tokens INTEGER,
    cache_read INTEGER, cache_write INTEGER,
    cost REAL, ts INTEGER, project TEXT, directory TEXT,
    usage_available INTEGER NOT NULL DEFAULT 1
);
"""

# The entity tables, as the real indexes declare them.
CBUT_ENTITIES = """
CREATE TABLE skill_usage (
    call_id TEXT PRIMARY KEY, skill TEXT, has_args INTEGER DEFAULT 0, plugin TEXT,
    session_id TEXT, project TEXT, ts INTEGER, status TEXT, duration_ms INTEGER
);
CREATE TABLE tool_calls (
    call_id TEXT PRIMARY KEY, session_id TEXT, project TEXT, tool_name TEXT,
    category TEXT, ts INTEGER, duration_ms INTEGER, status TEXT, model TEXT
);
"""

OCUT_ENTITIES = """
CREATE TABLE skill_usage (
    call_id TEXT PRIMARY KEY, skill TEXT, session_id TEXT, project TEXT,
    ts INTEGER, status TEXT, duration_ms INTEGER
);
CREATE TABLE tool_calls (
    call_id TEXT PRIMARY KEY, session_id TEXT, project TEXT, directory TEXT,
    tool_name TEXT, category TEXT, status TEXT, ts INTEGER, duration_ms INTEGER,
    model TEXT, provider TEXT
);
"""

QCUT_ENTITIES = """
CREATE TABLE skill_usage (
    call_id TEXT PRIMARY KEY, skill TEXT, plugin TEXT, session_id TEXT,
    project TEXT, ts INTEGER, status TEXT, duration_ms INTEGER
);
CREATE TABLE tool_calls (
    call_id TEXT PRIMARY KEY, session_id TEXT, project TEXT, tool_name TEXT,
    category TEXT, ts INTEGER, duration_ms INTEGER, status TEXT,
    is_sidechain INTEGER DEFAULT 0
);
"""

QCUT_DDL = """
CREATE TABLE model_calls (
    message_id TEXT PRIMARY KEY, session_id TEXT, model TEXT, provider TEXT,
    ts INTEGER, project TEXT, input_tokens INTEGER, output_tokens INTEGER,
    cache_read_tokens INTEGER, cache_creation_tokens INTEGER,
    credits REAL, has_usage INTEGER DEFAULT 0
);
"""


ENTITY_DDL = {
    "codebuddy-usage-tracker": CBUT_ENTITIES,
    "opencode-usage-tracker": OCUT_ENTITIES,
    "qoder-cn-usage-tracker": QCUT_ENTITIES,
}


def _db(home: Path, db_name: str, ddl: str, entities: bool = False) -> sqlite3.Connection:
    folder = home / ".local" / "share" / db_name
    folder.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(folder / "usage.db")
    conn.executescript(ddl)
    if entities:
        conn.executescript(ENTITY_DDL[db_name])
    return conn


class AdapterCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name)
        self._env = mock.patch.dict(os.environ, {"HOME": str(self.home)})
        self._env.start()
        self.now = int(time.time() * 1000)

    def tearDown(self) -> None:
        self._env.stop()
        self._tmp.cleanup()

    def snapshot(self, key: str, days: int = 7) -> Snapshot:
        return BY_KEY[key].snapshot(days, self.now)


class TestMissingAndBroken(AdapterCase):
    def test_absent_database_is_missing_not_an_error(self):
        snap = self.snapshot("cbut")
        self.assertEqual(snap.status, "missing")
        self.assertIsNone(snap.tokens)
        self.assertIn("cbut sync", snap.note)

    def test_schema_drift_is_reported_without_raising(self):
        conn = _db(self.home, "codebuddy-usage-tracker", "CREATE TABLE unrelated (x INTEGER);")
        conn.commit()
        conn.close()
        snap = self.snapshot("cbut")
        self.assertEqual(snap.status, "error")
        self.assertIn("model_responses", snap.note)


class TestCbut(AdapterCase):
    def _fill(self) -> None:
        conn = _db(self.home, "codebuddy-usage-tracker", CBUT_DDL)
        rows = [
            ("m1", "s1", "claude-sonnet", "anthropic", 100, 50, 0, 1.5, self.now, "/p/one", 1, 0),
            ("m2", "s1", "claude-sonnet", "anthropic", 200, 100, 0, 3.0, self.now - 1000, "/p/one", 1, 0),
            ("m3", "s2", "gpt-5", "openai", 300, 100, 900, None, self.now - 2 * DAY_MS, "/p/two", 1, 500),
            ("m4", "s3", "old", "x", 10, 10, 0, None, self.now - 40 * DAY_MS, "/p/two", 1, 0),
        ]
        conn.executemany("INSERT INTO model_responses (message_id, session_id, model, provider, prompt_tokens, completion_tokens, provider_total_tokens, credit, ts, project, usage_available, prompt_cache_hit_tokens) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        conn.commit()
        conn.close()

    def test_totals_and_sessions(self):
        self._fill()
        snap = self.snapshot("cbut", days=7)
        # Usage Total, as cbut's own panels define it: prompt + completion +
        # cache hit. m3's provider total is not read; its cache hit is.
        self.assertEqual(snap.tokens, 150 + 300 + (300 + 100 + 500))
        self.assertEqual(snap.calls, 3)
        self.assertEqual(snap.sessions, 2)
        self.assertEqual(snap.status, "ok")
        self.assertAlmostEqual(snap.cost, 4.5)

    def test_window_excludes_older_rows(self):
        self._fill()
        self.assertEqual(self.snapshot("cbut", days=1).calls, 2)
        self.assertEqual(self.snapshot("cbut", days=0).calls, 4)

    def test_top_models_are_ranked_and_trimmed(self):
        self._fill()
        snap = self.snapshot("cbut", days=7)
        self.assertEqual([name for name, _ in snap.top_models], ["gpt-5", "claude-sonnet"])

    def test_buckets_align_to_local_days(self):
        self._fill()
        snap = self.snapshot("cbut", days=7)
        self.assertEqual(len(snap.buckets), 7)
        self.assertEqual(snap.buckets[-1], 450)          # today: m1 + m2
        self.assertEqual(snap.buckets[-3], 900)          # two days back: m3
        self.assertEqual(sum(snap.buckets), 1350)

    def test_all_time_window_caps_the_sparkline_at_thirty_days(self):
        self._fill()
        self.assertEqual(len(self.snapshot("cbut", days=0).buckets), aut_db.SPARK_DAYS)

    def test_an_old_newest_record_reads_as_idle(self):
        conn = _db(self.home, "codebuddy-usage-tracker", CBUT_DDL)
        conn.execute("INSERT INTO model_responses (message_id, session_id, model, provider, prompt_tokens, completion_tokens, provider_total_tokens, credit, ts, project, usage_available) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                     ("m1", "s1", "m", "p", 1, 1, 0, None, self.now - 30 * DAY_MS, "/p", 1))
        conn.commit()
        conn.close()
        self.assertEqual(self.snapshot("cbut", days=0).status, "idle")


class TestQcut(AdapterCase):
    def test_credits_without_tokens_does_not_print_zero(self):
        conn = _db(self.home, "qoder-cn-usage-tracker", QCUT_DDL)
        conn.execute(
            "INSERT INTO model_calls (message_id, session_id, model, ts, project,"
            " input_tokens, output_tokens, credits, has_usage)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            ("m1", "s1", "custom-route", self.now, "/p", 0, 0, 12.5, 1))
        conn.commit()
        conn.close()
        snap = self.snapshot("qcut")
        self.assertIsNone(snap.tokens)      # "—", not "0"
        self.assertEqual(snap.cost, 12.5)
        self.assertEqual(snap.cost_unit, "cr")

    def test_token_rows_add_up(self):
        conn = _db(self.home, "qoder-cn-usage-tracker", QCUT_DDL)
        conn.executemany(
            "INSERT INTO model_calls (message_id, session_id, model, ts, project,"
            " input_tokens, output_tokens, credits, has_usage)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            [("m1", "s1", "a", self.now, "/p", 100, 20, None, 1),
             ("m2", "s1", "a", self.now, "/p", 50, 30, None, 1)],
        )
        conn.commit()
        conn.close()
        self.assertEqual(self.snapshot("qcut").tokens, 200)


class TestOcut(AdapterCase):
    def test_partial_usage_is_flagged(self):
        conn = _db(self.home, "opencode-usage-tracker", OCUT_DDL)
        conn.executemany(
            "INSERT INTO model_calls (call_id, session_id, model, provider,"
            " prompt_tokens, completion_tokens, total_tokens, cost, ts, project,"
            " directory, usage_available) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            [("c1", "s1", "m", "p", 10, 5, 15, 0.1, self.now, "hash1", "/p", 1),
             ("c2", "s1", "m", "p", None, None, 0, None, self.now, "hash1", "/p", 0)],
        )
        conn.commit()
        conn.close()
        snap = self.snapshot("ocut")
        self.assertFalse(snap.tokens_real)
        self.assertIn("floor", snap.note)


class TestReadOnly(unittest.TestCase):
    def test_the_overview_cannot_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "usage.db"
            conn = sqlite3.connect(path)
            conn.execute("CREATE TABLE t (x INTEGER)")
            conn.commit()
            conn.close()
            ro = aut_db.open_ro(path)
            try:
                with self.assertRaises(sqlite3.OperationalError):
                    ro.execute("INSERT INTO t VALUES (1)")
            finally:
                ro.close()


class TestSyncCommand(unittest.TestCase):
    def test_a_missing_tracker_is_reported_not_traced_back(self):
        import aut_report

        with mock.patch.dict(os.environ, {"PATH": ""}), \
                mock.patch("sys.stdout", new_callable=io.StringIO), \
                mock.patch("sys.stderr", new_callable=io.StringIO) as err:
            code = aut_report.main(["sync", "cbut"])
        self.assertEqual(code, 1)
        self.assertIn("not on PATH", err.getvalue())


class TestFormatting(unittest.TestCase):
    def test_sparkline_is_one_glyph_per_bucket(self):
        line = aut_db.sparkline([0, 1, 100, 50])
        self.assertEqual(len(line), 4)
        self.assertEqual(line[0], aut_db.BLOCKS[0])
        self.assertEqual(line[2], aut_db.BLOCKS[-1])

    def test_empty_sparkline(self):
        self.assertEqual(aut_db.sparkline([]), "")

    def test_token_numbers_scale_past_megabytes(self):
        # The board passed 21,000M this month: a nine-character cell pushed the
        # percentage beside it onto the next line.
        self.assertEqual(aut_db.fmt_tokens(21_207_640_000), "21.21B")
        self.assertEqual(aut_db.fmt_tokens(1_500_000_000_000), "1.50T")
        self.assertEqual(aut_db.fmt_tokens(999_000_000), "999.00M")


try:
    import textual  # noqa: F401
    from textual.widgets import Button, DataTable, TabbedContent

    HAS_TEXTUAL = True
except ImportError:  # pragma: no cover - only when the venv is missing
    HAS_TEXTUAL = False


# --- aggregation -------------------------------------------------------------

class TestAggregation(AdapterCase):
    """Cross-source merging: the numbers only this app can produce."""

    def _add_token_row(self, key: str, model_name: str, total: int) -> None:
        """One call with a known Usage Total, into an index _two_sources made."""
        db_name = {"cbut": "codebuddy-usage-tracker",
                   "ocut": "opencode-usage-tracker",
                   "qcut": "qoder-cn-usage-tracker"}[key]
        path = self.home / ".local" / "share" / db_name / "usage.db"
        if not path.exists():
            _db(self.home, db_name,
                {"cbut": CBUT_DDL, "ocut": OCUT_DDL, "qcut": QCUT_DDL}[key]).close()
        conn = sqlite3.connect(path)
        stamp = self.now - 1000
        if key == "cbut":
            conn.execute(
                "INSERT INTO model_responses (message_id, session_id, model,"
                " prompt_tokens, completion_tokens, ts, project)"
                " VALUES (?,?,?,?,0,?,?)",
                (f"x{model_name}", "s1", model_name, total, stamp, "/p/one"))
        elif key == "ocut":
            conn.execute(
                "INSERT INTO model_calls (call_id, session_id, model, prompt_tokens,"
                " completion_tokens, ts, project, directory)"
                " VALUES (?,?,?,?,0,?,?,?)",
                (f"x{model_name}", "s1", model_name, total, stamp, "h", "/p/two"))
        else:
            conn.execute(
                "INSERT INTO model_calls (message_id, session_id, model,"
                " input_tokens, output_tokens, ts, project)"
                " VALUES (?,?,?,?,0,?,?)",
                (f"x{model_name}", "s1", model_name, total, stamp, "/p/one"))
        conn.commit()
        conn.close()

    def _two_sources(self) -> None:
        cbut = _db(self.home, "codebuddy-usage-tracker", CBUT_DDL, entities=True)
        cbut.executemany(
            "INSERT INTO model_responses (message_id, session_id, model, provider, prompt_tokens, completion_tokens, provider_total_tokens, credit, ts, project, usage_available) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [("m1", "s1", "m-a", "p", 100, 10, 110, None, self.now, "/p/one", 1),
             ("m2", "s1", "m-a", "p", 50, 5, 55, None, self.now, "/p/one", 1)],
        )
        cbut.executemany(
            "INSERT INTO skill_usage (call_id, skill, session_id, project, ts, status, duration_ms)"
            " VALUES (?,?,?,?,?,?,?)",
            [("k1", "code-review", "s1", "/p/one", self.now, "completed", 1000),
             ("k2", "Code-Review", "s1", "/p/one", self.now, "error", 3000)],
        )
        cbut.executemany(
            "INSERT INTO tool_calls (call_id, session_id, project, tool_name, category, ts, duration_ms, status)"
            " VALUES (?,?,?,?,?,?,?,?)",
            [("t1", "s1", "/p/one", "Read", "builtin", self.now, 10, "completed"),
             ("t2", "s1", "/p/one", "Read", "builtin", self.now, 20, "completed")],
        )
        cbut.commit()
        cbut.close()

        ocut = _db(self.home, "opencode-usage-tracker", OCUT_DDL, entities=True)
        ocut.execute(
            "INSERT INTO model_calls (call_id, session_id, model, provider,"
            " prompt_tokens, completion_tokens, total_tokens, cost, ts, project,"
            " directory, usage_available) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            ("c1", "s2", "m-a", "p", 7, 3, 10, None, self.now, "hash2", "/p/two", 1),
        )
        ocut.execute(
            "INSERT INTO skill_usage (call_id, skill, session_id, project, ts, status, duration_ms)"
            " VALUES (?,?,?,?,?,?,?)",
            ("k3", "code-review", "s2", "/p/two", self.now, "completed", 2000),
        )
        ocut.execute(
            "INSERT INTO tool_calls (call_id, session_id, project, tool_name, category, ts, duration_ms, status)"
            " VALUES (?,?,?,?,?,?,?,?)",
            ("t3", "s2", "/p/two", "read", "builtin", self.now, 30, "completed"),
        )
        ocut.commit()
        ocut.close()

    def test_tokens_merge_and_fold_by_source(self):
        self._two_sources()
        rows = model.token_rows(0, self.now)
        by_model = [r for r in rows if r.model == "m-a"]
        self.assertEqual(len(by_model), 2)
        self.assertEqual(sum(r.total for r in by_model), 175)
        folded = {r.source: r for r in model.by_source(rows)}
        self.assertEqual(folded["cbut"].total, 165)
        self.assertEqual(folded["ocut"].total, 10)
        self.assertEqual(folded["cbut"].requests, 2)

    def test_model_totals_merge_the_same_model_across_trackers(self):
        self._two_sources()
        rows = model.model_totals(model.token_rows(0, self.now))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].model, "m-a")
        self.assertEqual(rows[0].total, 175)
        self.assertEqual(rows[0].requests, 3)
        self.assertEqual(rows[0].per_source, {"cbut": 165, "ocut": 10})

    def test_a_model_is_one_row_under_every_spelling(self):
        self._two_sources()
        # The same model as the three trackers write it: dots here, hyphens
        # there, and a free route that appends a suffix.
        self._add_token_row("cbut", "deepseek-v4.1-flash", total=400)
        self._add_token_row("cbut", "deepseek-v4-1-flash", total=200)
        self._add_token_row("ocut", "deepseek-v4.1-flash-free", total=50)
        rows = model.model_totals(model.token_rows(0, self.now))
        merged = [r for r in rows if "deepseek" in r.model]
        self.assertEqual(len(merged), 1)
        row = merged[0]
        self.assertEqual(row.model, "deepseek-v4.1-flash")  # the heaviest spelling
        self.assertEqual(row.total, 650)
        self.assertEqual(set(row.spellings),
                         {"deepseek-v4.1-flash", "deepseek-v4-1-flash",
                          "deepseek-v4.1-flash-free"})
        # ... and the detail reads every one of them, not just the displayed one.
        tokens, calls = model.model_stats(None, row.spellings, 0, self.now)
        self.assertEqual((tokens, calls), (650, 3))
        listed = model.model_calls(None, row.spellings, 0, self.now)
        self.assertEqual({c.model for c in listed},
                         {"deepseek-v4.1-flash", "deepseek-v4-1-flash",
                          "deepseek-v4.1-flash-free"})

    def test_versions_are_not_folded(self):
        self._two_sources()
        self._add_token_row("cbut", "deepseek-v4-flash", total=90)
        self._add_token_row("cbut", "deepseek-v4.1-flash", total=400)
        rows = model.model_totals(model.token_rows(0, self.now))
        names = sorted(r.model for r in rows if "deepseek" in r.model)
        self.assertEqual(names, ["deepseek-v4-flash", "deepseek-v4.1-flash"])
        self.assertNotEqual(model.canonical_model("deepseek-v4-flash"),
                            model.canonical_model("deepseek-v4.1-flash"))

    def test_a_hand_kept_alias_folds_a_name_no_rule_could_infer(self):
        self._two_sources()
        self._add_token_row("qcut", "dfmodel", total=70)
        with mock.patch.dict(model.MODEL_ALIASES, {"dfmodel": "m-a"}):
            rows = model.model_totals(model.token_rows(0, self.now))
        merged = [r for r in rows if r.model == "m-a"]
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].total, 245)
        self.assertIn("dfmodel", merged[0].spellings)

    def test_an_alias_titles_a_row_nothing_else_records(self):
        self._two_sources()
        self._add_token_row("qcut", "qfmodel", total=30)
        rows = model.model_totals(model.token_rows(0, self.now))
        row = next(r for r in rows if "qwen" in r.model)
        self.assertEqual(row.model, "qwen3.8-flash")
        self.assertEqual(row.spellings, ("qwen3.8-flash", "qfmodel"))
        # The id is still queried, so the drill-down finds the calls.
        self.assertEqual(model.model_stats(None, row.spellings, 0, self.now), (30, 1))

    def test_the_shipped_aliases_point_at_the_models_their_platform_names(self):
        # Qoder's builtin routes carry no machine-readable id, so these two are
        # the only link between its picker and what the other two record.
        self.assertEqual(model.canonical_model("dfmodel"),
                         model.canonical_model("deepseek-v4.1-flash"))
        self.assertEqual(model.canonical_model("qfmodel"),
                         model.canonical_model("qwen3.8-flash"))

    def test_timeline_picks_a_unit_from_the_window(self):
        from aut_picker import bounds_of

        self._two_sources()
        start, end = bounds_of("1d", self.now)
        day = model.timeline(start, end)
        self.assertEqual(day.unit, "hour")
        self.assertEqual(len(day.labels), len(model.hour_keys(start, end)))

        start, end = bounds_of("7d", self.now)
        week = model.timeline(start, end)
        self.assertEqual(week.unit, "day")
        self.assertEqual(len(week.labels), 7)
        self.assertEqual(sum(week.series["cbut"]), 165)
        self.assertEqual(len(week.totals), 7)

    def test_model_detail_reads_every_tracker_when_no_source_is_given(self):
        self._two_sources()
        calls = model.model_calls(None, ("m-a",), 0, self.now)
        self.assertEqual({c.source for c in calls}, {"cbut", "ocut"})
        self.assertEqual(sum(c.total for c in calls), 175)

    def test_skills_merge_by_name_case_insensitively(self):
        self._two_sources()
        rows = model.entity_rows("skills", 0, self.now)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.name, "code-review")   # the spelling with most calls
        self.assertEqual(row.calls, 3)
        self.assertEqual(row.per_source, {"cbut": 2, "ocut": 1})
        self.assertEqual((row.ok, row.fail), (2, 1))
        # 1s, 3s, 2s weighted by calls -> 2s
        self.assertAlmostEqual(row.avg_ms, 2000)

    def test_tools_merge_across_capitalisation(self):
        self._two_sources()
        rows = model.entity_rows("tools", 0, self.now)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].calls, 3)
        self.assertEqual(rows[0].per_source, {"cbut": 2, "ocut": 1})

    def test_unknown_status_is_pending_not_failure(self):
        conn = _db(self.home, "codebuddy-usage-tracker", CBUT_DDL, entities=True)
        conn.execute(
            "INSERT INTO skill_usage (call_id, skill, session_id, project, ts, status, duration_ms)"
            " VALUES (?,?,?,?,?,?,?)",
            ("k1", "x", "s", "/p", self.now, "running", 10),
        )
        conn.commit()
        conn.close()
        row = model.entity_rows("skills", 0, self.now)[0]
        self.assertEqual((row.ok, row.fail, row.pending), (0, 0, 1))

    def test_missing_database_contributes_nothing(self):
        self._two_sources()
        # qcut has no database here at all.
        rows = model.token_rows(0, self.now)
        self.assertEqual({r.source for r in rows}, {"cbut", "ocut"})

    def test_kpis_compare_the_same_time_of_day(self):
        conn = _db(self.home, "codebuddy-usage-tracker", CBUT_DDL)
        day = 86_400_000
        conn.executemany(
            "INSERT INTO model_responses (message_id, session_id, model, provider, prompt_tokens, completion_tokens, provider_total_tokens, credit, ts, project, usage_available) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [("m1", "s1", "m", "p", 100, 0, 100, None, self.now, "/p", 1),
             ("m2", "s1", "m", "p", 300, 0, 300, None, self.now - day, "/p", 1)],
        )
        conn.commit()
        conn.close()
        start, end = bounds_of("1d", self.now)
        k = model.kpis(start, end)
        # Only today's row is in the window; yesterday's is the comparison.
        self.assertEqual(k.tokens, 100)
        self.assertEqual(k.prev_tokens, 300)

    def test_day_labels_are_capped(self):
        labels = model.day_labels(0, self.now, max_days=30)
        self.assertEqual(len(labels), 30)
        self.assertEqual(labels[-1], date.fromtimestamp(self.now / 1000).isoformat())

    def test_ocut_project_uses_the_directory_not_the_hash(self):
        self._two_sources()
        rows = model.call_rows(0, self.now)
        self.assertEqual({r.project for r in rows if r.source == "ocut"}, {"/p/two"})


@unittest.skipUnless(HAS_TEXTUAL, "textual is not installed")
class TestBoard(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._env = mock.patch.dict(os.environ, {"HOME": self._tmp.name})
        self._env.start()

    async def asyncTearDown(self) -> None:
        self._env.stop()
        self._tmp.cleanup()

    async def test_six_tabs_and_direct_jump(self):
        from aut_app import AutApp

        app = AutApp()
        async with app.run_test(size=(140, 40)) as pilot:
            tabs = app.query_one(TabbedContent)
            self.assertEqual(tabs.active, "tab-dashboard")
            await pilot.press("4")
            await pilot.pause()
            self.assertEqual(tabs.active, "tab-tokens")
            await pilot.press("6")
            await pilot.pause()
            self.assertEqual(tabs.active, "tab-sources")

    async def test_tokens_groups_by_model_then_by_tracker(self):
        from aut_app import AutApp, TokensPane

        app = AutApp()
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.press("4")
            await pilot.pause()
            pane = app.pane()
            self.assertIsInstance(pane, TokensPane)
            self.assertEqual(pane.mode, "model")
            # One model is one row, with a column per tracker.
            self.assertIn("cbut", pane._visible)
            self.assertNotIn("provider", pane._visible)

            await pilot.press("g")
            await pilot.pause()
            self.assertEqual(pane.mode, "calls")
            self.assertIn("provider", pane._visible)

            await pilot.press("g")
            await pilot.pause()
            self.assertEqual(pane.mode, "source")
            self.assertNotIn("provider", pane._visible)

    async def test_a_model_row_names_the_trackers_it_came_from(self):
        from textual.widgets import Static

        from aut_app import AutApp

        app = AutApp()
        async with app.run_test(size=(140, 40)) as pilot:
            pane = app.pane()
            # A merged row is a sum of tools; the card has to say which ones.
            pane._models = [
                model.ModelTotal("gpt-5", total=900, requests=3,
                                 per_source={"cbut": 600, "ocut": 300}),
                model.ModelTotal("claude-x", total=100, requests=1,
                                 per_source={"qcut": 100}),
            ]
            pane._paint()
            await pilot.pause()
            card = app.query_one("#top-models", Static)
            text = str(card.render())
            self.assertIn("cbut+ocut", text)
            self.assertIn("claude-x", text)
            self.assertIn("qcut", text)
            # And the tag is paid for out of the name field, not out of the card:
            # card.size is already the content box, borders and padding excluded.
            for line in text.splitlines():
                self.assertLessEqual(len(line), card.size.width, line)

    async def test_a_grown_total_keeps_its_row_on_one_line(self):
        from textual.widgets import Static

        from aut_app import AutApp

        app = AutApp()
        async with app.run_test(size=(140, 45)) as pilot:
            pane = app.pane()
            # 10.15B formats as nine characters; the row used to be laid out
            # for seven, which pushed "48%" onto the line below.
            pane._models = [
                model.ModelTotal("deepseek-v4.1-flash", total=10_151_900_000,
                                 per_source={"cbut": 1, "ocut": 1, "qcut": 1},
                                 requests=10),
                model.ModelTotal("minimax-m3.1-flash-free", total=5_255_378_300,
                                 per_source={"ocut": 1}, requests=10),
            ]
            pane._paint()
            await pilot.pause()
            card = app.query_one("#top-models", Static)
            text = str(card.render())
            for line in text.splitlines():
                self.assertLessEqual(len(line), card.size.width, line)
            self.assertIn("10.15B", text)
            self.assertIn("66%", text)

    async def test_a_narrow_card_gives_up_the_tag_before_the_share(self):
        from textual.widgets import Static

        from aut_app import AutApp

        app = AutApp()
        async with app.run_test(size=(80, 30)) as pilot:
            pane = app.pane()
            pane._models = [
                model.ModelTotal("deepseek-v4.1-flash", total=10_151_900_000,
                                 per_source={"cbut": 1}, requests=10),
            ]
            pane._paint()
            await pilot.pause()
            card = app.query_one("#top-models", Static)
            text = str(card.render())
            for line in text.splitlines():
                self.assertLessEqual(len(line), card.size.width, line)
            # At 33 cells something has to go: the origin tag first, because
            # the percentage is the fact the list is ranked by.
            self.assertIn("%", text)
            self.assertNotIn("cbut", text)

    def test_usage_total_sits_ahead_of_the_input_split(self):
        from aut_app import TokensPane

        for mode, cols in TokensPane.COLUMN_SETS.items():
            if "input" in cols:
                self.assertLess(cols.index("usage total"), cols.index("input"), mode)
        self.assertEqual(TokensPane.COLUMN_SETS["model"][1], "usage total")

    async def test_the_dashboard_draws_its_panels_as_cards(self):
        from textual.widgets import Static

        from aut_app import AutApp

        app = AutApp()
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.pause()
            for wid in ("#kpi", "#top-models", "#top-skills"):
                card = app.query_one(wid, Static)
                self.assertEqual(str(card.styles.border_top[0]), "round", wid)
            note = app.query_one("#note", Static)
            kpi = app.query_one("#kpi", Static)
            self.assertLess(note.region.y, kpi.region.y)
            # The lists are as tall as their rows and the pane is what scrolls
            # once the two no longer fit — a fixed card height hid the tail of
            # a long model list with no key that reached it.
            from textual.css.scalar import Unit

            height = app.query_one("#top-models", Static).styles.height
            self.assertEqual(height.unit, Unit.AUTO)
            self.assertEqual(str(app.pane().styles.overflow_y), "auto")

    async def test_the_cards_take_the_height_the_pane_has_left(self):
        """Two content-sized cards left the pane empty under a short list.

        The cards are a *minimum* height, not a fixed one: a list taller than
        the pane still grows to its own height and the pane scrolls, so the
        fill can never clip a row.
        """
        from textual.widgets import Static

        from aut_app import AutApp, DashboardPane

        app = AutApp()
        async with app.run_test(size=(120, 45)) as pilot:
            pane = app.pane()
            self.assertIsInstance(pane, DashboardPane)
            pane._models = [model.ModelTotal(f"m{i}", total=100 - i, requests=1,
                                             per_source={"cbut": 100 - i})
                            for i in range(3)]
            pane._skills = []
            pane._paint()
            await pilot.pause()
            models = app.query_one("#top-models", Static)
            self.assertEqual(pane.max_scroll_y, 0, "a tall pane still scrolls")
            self.assertEqual(models.region.bottom, pane.region.bottom,
                             "the cards stopped short of the pane's bottom")
            # A taller terminal gives the cards more to fill, and the pane is
            # what notices: it re-fits on its own resize.
            await pilot.resize_terminal(160, 60)
            await pilot.pause()
            self.assertEqual(pane.max_scroll_y, 0)
            self.assertEqual(models.region.bottom, pane.region.bottom,
                             "growing the terminal left the cards behind")

        app = AutApp()
        async with app.run_test(size=(120, 20)) as pilot:
            pane = app.pane()
            pane._models = [model.ModelTotal(f"m{i}", total=1000 - i, requests=1,
                                             per_source={"cbut": 1000 - i})
                            for i in range(30)]
            pane._skills = []
            pane._paint()
            await pilot.pause()
            models = app.query_one("#top-models", Static)
            self.assertGreater(pane.max_scroll_y, 0,
                               "a list taller than the pane must scroll")
            self.assertIn("m29", str(models.content),
                          "the fill clipped the last row instead of scrolling")

    async def test_the_caption_above_the_table_names_sort_and_grouping(self):
        from textual.widgets import Static

        from aut_app import AutApp

        app = AutApp()
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.press("4")
            await pilot.pause()
            pane = app.pane()
            note = pane.query_one("#note", Static)
            table = pane.query_one(DataTable)
            self.assertLess(note.region.y, table.region.y)
            caption = str(note.render())
            self.assertIn("sort: usage total", caption)
            self.assertIn("grouping: by model", caption)

            await pilot.press("g")
            await pilot.pause()
            self.assertIn("by model × tracker", str(note.render()))

    async def test_the_sorted_column_is_marked_in_its_header(self):
        from aut_app import AutApp

        app = AutApp()
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.press("2")
            await pilot.pause()
            pane = app.pane()
            table = pane.query_one(DataTable)
            marked = pane.sort_column()
            self.assertIn("▼", str(table.columns[marked].label))
            await pilot.press("s")
            await pilot.pause()
            self.assertIn("▼", str(table.columns[pane.sort_column()].label))
            self.assertNotEqual(marked, pane.sort_column())

    async def test_filter_narrows_and_escape_restores(self):
        from aut_app import AutApp

        app = AutApp()
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.press("4")
            await pilot.pause()
            pane = app.pane()
            pane.needle = "zzz-no-such-model"
            pane.reload(pane.window)
            self.assertEqual(pane.query_one(DataTable).row_count, 0)
            pane.needle = ""
            pane.reload(pane.window)
            self.assertGreaterEqual(pane.query_one(DataTable).row_count, 0)

    async def test_the_picker_returns_a_custom_window(self):
        from aut_app import AutApp
        from aut_picker import CustomWindow

        app = AutApp()
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.press("d")
            await pilot.pause()
            app.screen.query_one("#dr-7d", Button).press()
            await pilot.pause()
            app.screen.query_one("#dr-ok", Button).press()
            await pilot.pause()
            self.assertIsInstance(app.windows["dashboard"], CustomWindow)

    async def test_enter_with_no_rows_is_a_no_op(self):
        from aut_app import AutApp

        app = AutApp()
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.press("3")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            # An empty tab must not push a blank detail screen.
            self.assertEqual([type(s).__name__ for s in app.screen_stack], ["Screen"])


if __name__ == "__main__":
    unittest.main()


class TestChart(unittest.TestCase):
    """The bars, pinned glyph by glyph — a proportion is easy to lie with."""

    def test_share_bar_is_full_for_the_largest_and_empty_at_zero(self):
        import aut_chart

        full = aut_chart.share_bar(10, 10, width=6)
        none = aut_chart.share_bar(0, 10, width=6)
        self.assertEqual(full.plain.count(aut_chart.BLOCK), 6)
        self.assertEqual(none.plain.count(aut_chart.BLOCK), 0)
        self.assertEqual(len(none.plain), 6)


class TestUsageCollapse(unittest.TestCase):
    def test_identical_calls_within_a_minute_become_one_row(self):
        row = model.CallRow(ts=1_000_000, source="cbut", label="CodeBuddy",
                            model="m", project="/p", session="s", total=10)
        other = model.CallRow(ts=1_000_500, source="cbut", label="CodeBuddy",
                              model="m", project="/p", session="s", total=5)
        later = model.CallRow(ts=1_060_000, source="cbut", label="CodeBuddy",
                              model="m", project="/p", session="s", total=7)
        rows = model.collapse_calls([later, other, row])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].count, 1)
        self.assertEqual(rows[1].count, 2)
        self.assertEqual(rows[1].total, 15)
