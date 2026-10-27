"""test_family_contract.py — the board and the three trackers must read one number.

The cross-repo golden fixture pins each tracker's own answer to one fixed input
set. That leaves the seam untested: the board reads the same rows through its own
adapters, and a disagreement at that seam is exactly what shipped — six rows out
of 44,473 carried no usage block, and one unmeasured row in a group blanked the
whole CodeBuddy column for a day (D-008).

So this file reads the fixture's rows through *aut's* code and compares against
the numbers the trackers themselves computed. Nothing here re-derives an
expectation: every number compared comes from the fixture, which the tracker's own
expression produced. A failure means aut and the tracker disagree, and the test
names the row.

The second half pins the one table all four repositories copy verbatim:
`USAGE_RANGES`. A preset added on one side and not the other makes "7d" mean two
different things, and neither repository fails on its own.
"""

from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# No _hermetic tripwire here: the board has no such module. Isolation comes from
# AdapterCase, which points HOME at a temp dir, so every ~/.local/share/<db> path
# the adapters build lands inside it.
from test_aut import (  # noqa: E402
    CBUT_DDL, OCUT_DDL, QCUT_DDL, AdapterCase, _db,
)

import aut_model as model  # noqa: E402
import aut_windows as windows  # noqa: E402
from aut_windows import bounds_of  # noqa: E402

HERE = Path(__file__).resolve().parent
GOLDEN = json.loads((HERE / "fixtures" / "cross_repo_golden.json").read_text(encoding="utf-8"))
USAGE = GOLDEN["usage_total"]
NOW_MS = int(datetime.fromisoformat(USAGE["now"]).timestamp() * 1000)
PROVIDER = USAGE["provider"]

DB_NAME = {"cbut": "codebuddy-usage-tracker",
           "ocut": "opencode-usage-tracker",
           "qcut": "qoder-cn-usage-tracker"}
DDL = {"cbut": CBUT_DDL, "ocut": OCUT_DDL, "qcut": QCUT_DDL}


def ms(iso: str) -> int:
    return int(datetime.fromisoformat(iso).timestamp() * 1000)


def cbut_row(row):
    """cbut stores the whole prompt and the cache hit beside it."""
    return (row["id"], "s1", row["model"], PROVIDER, row["input_full"], row["output"],
            row["cache_hit"], None, ms(row["ts"]), "/p",
            1 if row["reports_usage"] else 0)


def ocut_row(row):
    """ocut reports an UNCACHED prompt, so the whole prompt is split back out.

    Same arithmetic as ocut's own golden test: prompt = input_full - hit - write,
    with a NULL input_full leaving every prompt part NULL.
    """
    hit, write = row["cache_hit"], row["cache_write"]
    prompt = None if row["input_full"] is None \
        else row["input_full"] - (hit or 0) - (write or 0)
    return (row["id"], "s1", row["model"], PROVIDER, prompt, row["output"], hit, write,
            ms(row["ts"]), "/p", "/p", 1 if row["reports_usage"] else 0)


def qcut_row(row):
    """qcut names the prompt input_tokens and the hit cache_read_tokens."""
    return (row["id"], "s1", row["model"], PROVIDER, row["input_full"], row["output"],
            row["cache_hit"], None, ms(row["ts"]), "/p",
            1 if row["reports_usage"] else 0)


SQL = {
    "cbut": ("INSERT INTO model_responses (message_id, session_id, model, provider,"
             " prompt_tokens, completion_tokens, prompt_cache_hit_tokens, credit, ts,"
             " project, usage_available) VALUES (?,?,?,?,?,?,?,?,?,?,?)", cbut_row),
    "ocut": ("INSERT INTO model_calls (call_id, session_id, model, provider,"
             " prompt_tokens, completion_tokens, cache_read, cache_write, ts, project,"
             " directory, usage_available) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", ocut_row),
    "qcut": ("INSERT INTO model_calls (message_id, session_id, model, provider,"
             " input_tokens, output_tokens, cache_read_tokens, credits, ts, project,"
             " has_usage) VALUES (?,?,?,?,?,?,?,?,?,?,?)", qcut_row),
}


class FamilyContract:
    """One tracker's index, built from the fixture, read through aut.

    A plain mixin, not a TestCase: the base carries no key, so collecting it
    would run every test three extra times against an empty tracker name.
    """

    key = ""

    def build(self) -> None:
        conn = _db(self.home, DB_NAME[self.key], DDL[self.key])
        sql, shape = SQL[self.key]
        conn.executemany(sql, [shape(row) for row in USAGE["rows"]])
        conn.commit()
        conn.close()

    def names(self) -> tuple[str, ...]:
        """The spellings the fixture uses, minus the NULL model.

        A NULL model has no name to look up; the rollup test covers it as the
        (unknown) group aut folds it into.
        """
        return tuple(sorted({row["model"] for row in USAGE["rows"] if row["model"]}))

    def test_every_row_matches_the_trackers_own_total(self):
        """One row, one number -- no window in the way.

        The end sits one millisecond past now so even w1 (which is exactly at
        now, and therefore in no preset) is visible: this test asks what each
        row contributes on its own, and window membership is the next test.
        """
        self.build()
        calls = model.model_calls(self.key, self.names(), None, NOW_MS + 1, limit=10_000)
        got = {(call.model, call.ts): call.total for call in calls}
        for row in USAGE["rows"]:
            if row["model"] is None:
                continue
            with self.subTest(row=row["id"], meaning=row["meaning"]):
                self.assertEqual(got.get((row["model"], ms(row["ts"]))),
                                 row["expect"][self.key])

    def test_every_window_matches_the_trackers_own_aggregate(self):
        self.build()
        for case in USAGE["windows"]:
            with self.subTest(window=case["key"]):
                start, end = bounds_of(case["key"], NOW_MS)
                k = model.kpis(start, end)
                self.assertEqual(k.per_source.get(self.key),
                                 case["usage_total"][self.key])
                self.assertEqual(k.calls, case["requests"])

    def test_every_model_group_matches_the_trackers_own_rollup(self):
        self.build()
        rows = model.token_rows(None, NOW_MS)
        got = {(row.model, row.provider): (row.total, row.requests) for row in rows}
        for group in USAGE["model_groups"]:
            # aut folds a NULL model into "(unknown)" so the row survives the
            # merge; the fixture keeps it NULL, which is how the trackers
            # themselves group it.
            name = group["model"] if group["model"] is not None else "(unknown)"
            with self.subTest(model=group["model"]):
                self.assertEqual(got.get((name, group["provider"])),
                                 (group["usage_total"][self.key], group["requests"]))


class TestCbut(FamilyContract, AdapterCase):
    key = "cbut"


class TestOcut(FamilyContract, AdapterCase):
    key = "ocut"


class TestQcut(FamilyContract, AdapterCase):
    key = "qcut"


class TestSharedPresets(unittest.TestCase):
    def test_the_preset_table_is_the_one_the_trackers_carry(self):
        """USAGE_RANGES is copied verbatim into all four repositories.

        The presets a tracker accepts and the presets the board offers must be one
        table, or "7d" means two different things. The table lives in the fixture
        so the four copies cannot drift quietly; the trackers assert the same
        table from their own side.
        """
        self.assertEqual(windows.USAGE_RANGES, GOLDEN["family_contract"]["ranges"])


if __name__ == "__main__":
    unittest.main()
