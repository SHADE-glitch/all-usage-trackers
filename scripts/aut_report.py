#!/usr/bin/env python3
"""Headless `aut`: JSON for scripting, a skills table, sync without the TUI.

`aut json` exists so the board's numbers can be checked from a shell or piped into
something else. `aut skills` is the Skills tab without the terminal, for a
maintenance pass or a cron report. Both read through the same model functions as
the TUI, so the two cannot disagree about what a number means; each source is
read inside one transaction, so one source's numbers come from one moment.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime

import aut_model as model
from aut_db import WINDOWS, fmt_age
from aut_sources import BY_KEY, SOURCES, SYNC_TIMEOUT_S, Snapshot, snapshots
from aut_windows import RANGE_LABELS, bounds_of


def _as_dict(snap: Snapshot) -> dict:
    return {
        "key": snap.key,
        "label": snap.label,
        "status": snap.status,
        "note": snap.note,
        "tokens": snap.tokens,
        "tokens_real": snap.tokens_real,
        "sessions": snap.sessions,
        "calls": snap.calls,
        "buckets": snap.buckets,
        "top_models": [{"model": name, "tokens": tokens} for name, tokens in snap.top_models],
        "top_projects": [{"project": name, "tokens": tokens} for name, tokens in snap.top_projects],
        "last_event_ms": snap.last_event_ms,
        "db_path": str(snap.db_path) if snap.db_path else None,
        "db_size": snap.db_size,
    }


def _window(days: int) -> tuple[int | None, int]:
    """The same window the board would use for this many days.

    The board works in local calendar days, so `--days 1` here must mean "today"
    and not "the last 24 hours" — otherwise the JSON and the TUI disagree about
    a number they both claim to have read from the same index.
    """
    key = "all" if days <= 0 else f"{days}d"
    try:
        return bounds_of(key, int(time.time() * 1000))
    except KeyError:
        return None, int(time.time() * 1000)


def cmd_json(args: argparse.Namespace) -> int:
    start, end = _window(args.days)
    payload = {
        "generated_at_ms": int(time.time() * 1000),
        "window_days": args.days,
        "window_start_ms": start,
        "window_end_ms": end,
        "sources": [
            _as_dict(snap)
            for snap in snapshots(args.days, since_ms=start, end_ms=end)
        ],
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def cmd_skills(args: argparse.Namespace) -> int:
    start, end = _window(args.days)
    with model.read_session():
        rows = model.entity_rows("skills", start, end)
        read_states = model.skill_read_states()
    rows.sort(key=lambda row: (-(row.calls + (row.reads or 0)),
                               row.name.casefold()))

    label = RANGE_LABELS.get("all" if args.days <= 0 else f"{args.days}d",
                             f"{args.days} days")
    if start is None:
        span = f"{label} · all recorded calls"
    else:
        span = (f"{label} · {datetime.fromtimestamp(start / 1000):%Y-%m-%d %H:%M}"
                f" → {datetime.fromtimestamp(end / 1000):%Y-%m-%d %H:%M}")
    print(f"aut skills · {span}")

    if rows:
        name_w = max(len("skill"), *(len(row.name) for row in rows))
        print(f"{'skill':<{name_w}}  {'calls':>6}  {'reads':>6}  {'cbut':>6}"
              f"  {'ocut':>6}  {'qcut':>6}  {'ok':>4}  {'fail':>4}  {'avg':>6}"
              f"  {'last used':>9}")
        for row in rows:
            per = ["—" if not row.per_source.get(key) else f"{row.per_source[key]:,}"
                   for key in ("cbut", "ocut", "qcut")]
            reads = "—" if row.reads is None else f"{row.reads:,}"
            print(f"{row.name:<{name_w}}  {row.calls:>6,}"
                  f"  {reads:>6}"
                  f"  {per[0]:>6}  {per[1]:>6}  {per[2]:>6}"
                  f"  {row.ok:>4,}  {row.fail:>4,}  {_fmt_avg(row.avg_ms):>6}"
                  f"  {fmt_age(row.last_used):>9}")
        calls = sum(row.calls for row in rows)
        unavailable = [key for key, state in read_states.items()
                       if state not in ("ok", "missing")]
        if unavailable:
            tail = ("direct reads unavailable: "
                    + ", ".join(f"{key} ({read_states[key]})"
                                for key in unavailable))
        else:
            tail = f"{sum(row.reads or 0 for row in rows):,} reads"
        print(f"\n{len(rows)} skills · {calls:,} calls · {tail}")
    else:
        print("no skill calls in this window")

    states = " · ".join(f"{source.key} {_source_state(source)}" for source in SOURCES)
    print(f"sources: {states}")
    return 0


def _fmt_avg(ms: float | None) -> str:
    """The TUI's duration cell, without importing the TUI."""
    if ms is None:
        return "—"
    if ms >= 60_000:
        return f"{ms / 60_000:.1f}m"
    if ms >= 1000:
        return f"{ms / 1000:.1f}s"
    return f"{ms:.0f}ms"


def _source_state(source) -> str:
    """Missing, error, or ok — a source that read nothing must say why."""
    if not source.db_path.is_file():
        return "missing"
    error = model.source_errors().get(source.key)
    return f"error ({error})" if error else "ok"


def cmd_sync(args: argparse.Namespace) -> int:
    keys = args.keys or [source.key for source in SOURCES]
    failed = 0
    for key in keys:
        source = BY_KEY.get(key)
        if source is None:
            print(f"aut: unknown source {key!r} (known: {', '.join(BY_KEY)})", file=sys.stderr)
            failed += 1
            continue
        print(f"aut: syncing {source.label}", flush=True)
        try:
            code = subprocess.run(source.sync_argv(),
                                  timeout=SYNC_TIMEOUT_S).returncode
        except subprocess.TimeoutExpired:
            # The same ceiling the board gives a sync: a hung child must not
            # hold a scripted caller forever.
            print(f"aut: {source.binary} sync timed out after {SYNC_TIMEOUT_S}s",
                  file=sys.stderr)
            failed += 1
            continue
        except FileNotFoundError:
            # A tracker that is not installed is a normal state on a machine that
            # only uses one of them — report it, do not traceback.
            print(f"aut: {source.binary} is not on PATH — install that tracker first",
                  file=sys.stderr)
            failed += 1
            continue
        if code != 0:
            failed += 1
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aut", description="headless views over the usage trackers")
    sub = parser.add_subparsers(dest="cmd", required=True)

    js = sub.add_parser("json", help="print the combined snapshot as JSON")
    js.add_argument("--days", type=int, default=7, choices=[d for d, _ in WINDOWS],
                    help="window in days: 1, 7, 30, or 0 for all time")
    js.set_defaults(func=cmd_json)

    sy = sub.add_parser("sync", help="run each tracker's own sync command")
    sy.add_argument("keys", nargs="*", help="cbut / ocut / qcut (default: all three)")
    sy.set_defaults(func=cmd_sync)

    sk = sub.add_parser("skills", help="print skill usage across the three trackers")
    sk.add_argument("--days", type=int, default=30,
                    choices=[d for d, _ in WINDOWS],
                    help="window in days: 1, 7, 30, or 0 for all time (default 30)")
    sk.set_defaults(func=cmd_skills)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
