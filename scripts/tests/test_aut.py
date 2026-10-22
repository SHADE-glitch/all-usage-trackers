"""The adapter layer, tested against real SQLite files built in a temp HOME.

What is worth pinning here: the normalisation (three schemas, one shape), the
window arithmetic, and the promise that the overview cannot write. The TUI itself
gets one smoke test — mounting and cycling a window — because everything below it
is where the numbers come from.
"""

from __future__ import annotations

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
from aut_sources import BY_KEY, Snapshot  # noqa: E402

DAY_MS = 86_400_000

CBUT_DDL = """
CREATE TABLE model_responses (
    message_id TEXT PRIMARY KEY, session_id TEXT, model TEXT, provider TEXT,
    prompt_tokens INTEGER, completion_tokens INTEGER, provider_total_tokens INTEGER,
    credit REAL, ts INTEGER, project TEXT, usage_available INTEGER DEFAULT 0
);
"""

OCUT_DDL = """
CREATE TABLE model_calls (
    call_id TEXT PRIMARY KEY, session_id TEXT, model TEXT, provider TEXT,
    prompt_tokens INTEGER, completion_tokens INTEGER, total_tokens INTEGER,
    cost REAL, ts INTEGER, project TEXT, usage_available INTEGER NOT NULL DEFAULT 1
);
"""

QCUT_DDL = """
CREATE TABLE model_calls (
    message_id TEXT PRIMARY KEY, session_id TEXT, model TEXT, ts INTEGER,
    project TEXT, input_tokens INTEGER, output_tokens INTEGER,
    credits REAL, has_usage INTEGER DEFAULT 0
);
"""


def _db(home: Path, db_name: str, ddl: str) -> sqlite3.Connection:
    folder = home / ".local" / "share" / db_name
    folder.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(folder / "usage.db")
    conn.executescript(ddl)
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
        conn.executemany("INSERT INTO model_responses VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
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
        conn.execute("INSERT INTO model_responses VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                     ("m1", "s1", "m", "p", 1, 1, 0, None, self.now - 30 * DAY_MS, "/p", 1))
        conn.commit()
        conn.close()
        self.assertEqual(self.snapshot("cbut", days=0).status, "idle")


class TestQcut(AdapterCase):
    def test_credits_without_tokens_does_not_print_zero(self):
        conn = _db(self.home, "qoder-cn-usage-tracker", QCUT_DDL)
        conn.execute("INSERT INTO model_calls VALUES (?,?,?,?,?,?,?,?,?)",
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
            "INSERT INTO model_calls VALUES (?,?,?,?,?,?,?,?,?)",
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
            "INSERT INTO model_calls VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [("c1", "s1", "m", "p", 10, 5, 15, 0.1, self.now, "/p", 1),
             ("c2", "s1", "m", "p", None, None, 0, None, self.now, "/p", 0)],
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
    from textual.widgets import DataTable

    HAS_TEXTUAL = True
except ImportError:  # pragma: no cover - only when the venv is missing
    HAS_TEXTUAL = False


@unittest.skipUnless(HAS_TEXTUAL, "textual is not installed")
class TestBoard(unittest.IsolatedAsyncioTestCase):
    async def test_board_mounts_and_cycles_windows(self):
        from aut_app import AutApp

        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict(os.environ, {"HOME": tmp}):
            app = AutApp(days=7)
            async with app.run_test() as pilot:
                table = app.query_one(DataTable)
                self.assertEqual(table.row_count, 3)
                await pilot.press("w")
                self.assertEqual(app.days, 30)
                await pilot.press("w")
                self.assertEqual(app.days, 0)      # all time
                await pilot.press("w")
                self.assertEqual(app.days, 1)      # wraps back to 1d


if __name__ == "__main__":
    unittest.main()
