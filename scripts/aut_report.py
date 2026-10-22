#!/usr/bin/env python3
"""Headless `aut`: JSON for scripting, sync without the TUI.

`aut json` exists so the board's numbers can be checked from a shell or piped into
something else. It prints the same snapshot the TUI draws — one code path, so the
two cannot disagree.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time

from aut_db import WINDOWS
from aut_sources import BY_KEY, SOURCES, Snapshot, snapshots


def _as_dict(snap: Snapshot) -> dict:
    return {
        "key": snap.key,
        "label": snap.label,
        "status": snap.status,
        "note": snap.note,
        "tokens": snap.tokens,
        "tokens_real": snap.tokens_real,
        "cost": snap.cost,
        "cost_unit": snap.cost_unit,
        "sessions": snap.sessions,
        "calls": snap.calls,
        "buckets": snap.buckets,
        "top_models": [{"model": name, "tokens": tokens} for name, tokens in snap.top_models],
        "top_projects": [{"project": name, "tokens": tokens} for name, tokens in snap.top_projects],
        "last_event_ms": snap.last_event_ms,
        "db_path": str(snap.db_path) if snap.db_path else None,
        "db_size": snap.db_size,
    }


def cmd_json(args: argparse.Namespace) -> int:
    payload = {
        "generated_at_ms": int(time.time() * 1000),
        "window_days": args.days,
        "sources": [_as_dict(snap) for snap in snapshots(args.days)],
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


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
        code = subprocess.call(source.sync_argv())
        if code != 0:
            failed += 1
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aut", description="headless views over the usage trackers")
    sub = parser.add_subparsers(dest="cmd", required=True)

    js = sub.add_parser("json", help="print the combined snapshot as JSON")
    js.add_argument("--days", type=int, default=7,
                    help="window in days: 1, 7, 30, or 0 for all time")
    js.set_defaults(func=cmd_json)

    sy = sub.add_parser("sync", help="run each tracker's own sync command")
    sy.add_argument("keys", nargs="*", help="cbut / ocut / qcut (default: all three)")
    sy.set_defaults(func=cmd_sync)

    args = parser.parse_args(argv)
    valid = {days for days, _ in WINDOWS}
    if getattr(args, "days", 7) not in valid:
        args.days = 7
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
