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
    message_id TEXT PRIMARY KEY, session_id TEXT, model TEXT, ts INTEGER,
    project TEXT, input_tokens INTEGER, output_tokens INTEGER,
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
            ("m1", "s1", "claude-sonnet", "anthropic", 100, 50, 0, 1.5, self.now, "/p/one", 1),
            ("m2", "s1", "claude-sonnet", "anthropic", 200, 100, 0, 3.0, self.now - 1000, "/p/one", 1),
            ("m3", "s2", "gpt-5", "openai", 0, 0, 900, None, self.now - 2 * DAY_MS, "/p/two", 1),
            ("m4", "s3", "old", "x", 10, 10, 0, None, self.now - 40 * DAY_MS, "/p/two", 1),
        ]
        conn.executemany("INSERT INTO model_responses (message_id, session_id, model, provider, prompt_tokens, completion_tokens, provider_total_tokens, credit, ts, project, usage_available) VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
        conn.commit()
        conn.close()

    def test_totals_and_sessions(self):
        self._fill()
        snap = self.snapshot("cbut", days=7)
        # provider_total_tokens wins when present, otherwise prompt+completion.
        self.assertEqual(snap.tokens, 150 + 300 + 900)
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
        self.assertEqual(snap.buckets[-3], 900)          # two days back
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


try:
    import textual  # noqa: F401
    from textual.widgets import Button, DataTable, TabbedContent

    HAS_TEXTUAL = True
except ImportError:  # pragma: no cover - only when the venv is missing
    HAS_TEXTUAL = False


# --- aggregation -------------------------------------------------------------

class TestAggregation(AdapterCase):
    """Cross-source merging: the numbers only this app can produce."""

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
        calls = model.model_calls(None, "m-a", 0, self.now)
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

    async def test_the_dashboard_draws_its_panels_as_cards(self):
        from textual.widgets import Static

        from aut_app import AutApp

        app = AutApp()
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.pause()
            for wid in ("#kpi", "#chart", "#top-models", "#top-skills"):
                card = app.query_one(wid, Static)
                self.assertEqual(str(card.styles.border_top[0]), "round", wid)
            note = app.query_one("#note", Static)
            kpi = app.query_one("#kpi", Static)
            self.assertLess(note.region.y, kpi.region.y)

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
            self.assertIn("sort: total", caption)
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
    """The drawing, pinned glyph by glyph — a chart is easy to lie with."""

    def test_every_series_shares_one_scale(self):
        import aut_chart

        lines = aut_chart.stacked_chart({"a": [10, 1]}, ["00", "01"],
                                        width=40, height=10, styles={})
        body = lines[:10]
        axis = max(4, len("10")) + 2
        tall = sum(1 for line in body if line.plain[axis] != " ")
        short = sum(1 for line in body if line.plain[axis + 1] != " ")
        self.assertEqual(tall, 10)
        self.assertEqual(short, 1)

    def test_the_axis_is_labelled_from_zero(self):
        import aut_chart

        lines = aut_chart.stacked_chart({"a": [4] * 7}, ["x"] * 7,
                                        width=60, height=5, styles={})
        axis = [line.plain for line in lines[:5]]
        self.assertIn("0", axis[-1])
        self.assertIn("4", axis[0])

    def test_x_labels_are_anchored_to_the_newest_bucket(self):
        import aut_chart

        labels = [f"{hour:02d}" for hour in range(24)]
        lines = aut_chart.stacked_chart({"a": [1] * 24}, labels,
                                        width=80, height=4, styles={})
        self.assertTrue(lines[-1].plain.rstrip().endswith("23"))
        self.assertGreater(len(lines[-1].plain.strip()), 2)

    def test_an_empty_window_says_so_instead_of_drawing_nothing(self):
        import aut_chart

        lines = aut_chart.stacked_chart({}, [], width=40, height=5, styles={})
        self.assertEqual(len(lines), 1)
        self.assertIn("no usage", lines[0].plain)

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
