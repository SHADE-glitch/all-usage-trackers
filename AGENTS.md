# AGENTS.md

Guidance for AI coding agents working in this repository.

> **Dimension.** A — open source (strict), per `CONVENTIONS.md` §0; the shared rules live once in
> `~/.agents/standards/STANDARD.md` and the dimension-A detail in
> `~/.agents/standards/dimensions/a.md`. Neither is restated here.

## What this is

One **read-only** board over the local usage trackers: `cbut` (CodeBuddy), `ocut`
(OpenCode) and `qcut` (Qoder CN). Three layers, in dependency order:

1. `scripts/aut_sources.py` — one adapter per tracker. Each knows where its
   `usage.db` lives, how to normalise its token column, and how to launch it.
   This is the only file that knows a schema, and the only file to edit when a
   tracker changes one.
2. `scripts/aut_db.py` — read-only SQLite access, window arithmetic, formatting.
3. `scripts/aut_app.py` (Textual board) and `scripts/aut_report.py` (`aut json`,
   `aut sync`).

`bin/aut` is a bash dispatcher. **It is bash on purpose**: it must still run and
print a useful error when the venv is missing or broken.

This repository is public.

## Hard rules

- **Never parse a tracker's logs.** The three trackers own collection; this repo
  reads their SQLite index. A second parser is a second truth and will drift.
- **Never write.** Every connection is `file:...?mode=ro`. `s` / `S` shell out to
  the tracker's own `sync`; the board itself stays a reader.
- **Never invent a number.** A source that reported credits but no token shows
  `—`; a schema that moved shows `error` in that row and leaves the other two
  working. `0` is a claim, and it must be true.
- **Do not show money.** Tokens are the unit. The three trackers report credits,
  credits and dollars respectively; a single cost column would merge three units.
- **Keep the three TUIs untouched.** Going deeper is `suspend()` + the tracker's
  own binary, never a re-implementation of its views.

## Commands

```bash
./install.sh                                  # venv + ~/.local/bin/aut symlink
python3 -m unittest discover -s scripts/tests # stdlib unittest; pytest discovers them too
./bin/aut json --days 7                       # the same numbers, as JSON
./bin/aut cbut                                # jump straight into one tracker
```

## Layout

```
bin/aut                 bash dispatcher: tui | cbut/ocut/qcut | json | sync | --help
scripts/aut_sources.py  the adapters (SOURCES) and the Snapshot shape
scripts/aut_db.py       read-only connections, windows, sparkline, formatting
scripts/aut_app.py      the Textual board
scripts/aut_report.py   headless json / sync
scripts/tests/          adapters against temp databases; one board smoke test
```

## Recording conventions

Commit subjects are English. The CHANGELOG records the non-feature commits — the
repairs, the guards, the withdrawals — and states what was true as of its commit,
not current state.
