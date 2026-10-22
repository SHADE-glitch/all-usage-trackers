# AGENTS.md

Guidance for AI coding agents working in this repository.

> **Dimension.** A — open source (strict), per `CONVENTIONS.md` §0; the shared rules live once in
> `~/.agents/standards/STANDARD.md` and the dimension-A detail in
> `~/.agents/standards/dimensions/a.md`. Neither is restated here.

## What this is

A **read-only** six-tab board over the local usage trackers: `cbut` (CodeBuddy),
`ocut` (OpenCode) and `qcut` (Qoder CN). Layers, in dependency order:

1. `scripts/aut_sources.py` — one adapter per tracker: where its `usage.db` lives,
   the SQL expressions that normalise its token and project columns, and how to
   launch it. The only file that knows a schema.
2. `scripts/aut_model.py` — the cross-tool aggregation every tab draws. Pure:
   `(start_ms, end_ms) -> rows`, no Textual import, so the numbers are testable
   without a terminal.
3. `scripts/aut_chart.py` — text-only bars: `share_bar`, `pct`. Pure numbers
   in, `rich.Text` out, no Textual, so the drawing is testable glyph by glyph.
   A proportion is the easiest place here to lie by accident.
4. `scripts/aut_picker.py` — the custom date-range picker, ported verbatim from
   the tracker family (same 79x30 layout, same chips). Kept in its own file so
   the board stays about the board.
5. `scripts/aut_app.py` — the Textual board: top bar, six panes, detail screens.
6. `scripts/aut_report.py` — `aut json` and `aut sync`.

`bin/aut` is a bash dispatcher. **It is bash on purpose**: it must still run and
print a useful error when the venv is missing or broken.

This repository is public.

## Hard rules

- **Never parse a tracker's logs.** The three trackers own collection; this repo
  reads their SQLite index. A second parser is a second truth and will drift.
- **Never write.** Every connection is `file:...?mode=ro`. `r` and `enter` shell
  out to the tracker's own command; the board itself stays a reader.
- **Never invent a number.** A source that reported credits but no token shows
  `—`; a schema that moved shows `error` on the Sources tab and contributes
  nothing to the merges. `0` is a claim, and it must be true.
- **Do not show money.** Tokens are the unit. The three trackers report credits,
  credits and dollars; a single cost column would merge three units.
- **Do not merge what is not the same thing.** Tool names merge on case alone
  (`Read` / `read`). `Bash` and `shell` stay apart, and `pending` is never folded
  into `fail` — those are guesses, not facts. Models *do* merge by name across
  trackers (that is the point of the Tokens tab); provider is a column, not a
  split.
- **One number, labelled.** Every token figure the board prints is the tracker's
  own Usage Total (cbut: prompt + completion + cache hit; ocut: full prompt +
  output + the hit re-added; qcut: input + output + cache read). The providers'
  own API totals are not read anywhere. A number that says neither input, output
  nor cache is the Usage Total, and a second unlabelled total beside it is a bug.
- **One bar, one scale.** Every bar in a table shares its scale; a bar scaled to
  its own row would draw a 12M and an 81M source at the same height, which is a
  lie the eye cannot catch. The percentage beside it is its share of the window.
- **One model is one row — in the merged views only.** `canonical_model` in
  `aut_model` is the single place a spelling is folded: case, `.`/`_` → `-`,
  the free-route suffix, and `MODEL_ALIASES` for the ids no rule can infer
  (Qoder's builtin routes carry no machine-readable id — its `provider_id` is
  NULL). The Tokens by-model view and the dashboard read the folded key; Usage,
  the per-call rows and the model × tracker view keep the spelling the tracker
  wrote, and the three trackers are not touched at all. A row carries its
  `spellings` because the detail queries by them: a merged row and its
  drill-down must total the same.
- **A merged row names its sources.** A number that sums several trackers says
  which ones — `cbut+ocut`, `all` — because the total alone cannot be traced
  back to a tool. The tag sits beside the name and is paid for out of the name
  field, never out of the card: a line that wraps loses the alignment the list
  is for.
- **Cards grow, then the pane scrolls.** A list card takes the height its rows
  need — never a fixed row count that silently hides the rest — and the pane
  scrolls once the screen is full.
- **A row is sized from its card, never from a constant.** The budget is the
  card's measured content width (less one column for the scrollbar the pane may
  grow), and every field in the row is measured from the data: a nine-character
  total in a seven-cell field wrapped the percentage onto the next line. What
  gives way, in order: the bar, the origin tag, the percentage — the name
  absorbs the slack. The same rule applies to the KPI line, which drops whole
  facts rather than wrapping one.
- **Keep the three TUIs untouched.** Going deeper is `suspend()` + the tracker's
  own binary, never a re-implementation of its views.
- **Keep the keys aligned with the family.** `r` syncs, `s` sorts, `/` filters,
  `d` opens the range picker, `tab` cycles. A different meaning for a shared key
  is a bug, not a preference.
- **The total comes before its parts.** Where a row shows the usage total and
  the input / output / cache split, the total is the leading column: it is the
  number the row is ranked and sorted by, and the four parts explain it.
- **State above the table, provenance below, keys in the footer.** The caption
  names the sort and the grouping (`sort: usage total ▼ (s)`); the line under the table
  says how many indexes were read, how big they are and when they were synced.
  This is the three trackers' layout, and the reason `s` is discoverable at all.
- **The footer only lists keys that work on the tab.** `AutApp.check_action` is
  the one place a key's applicability lives: it answers for the footer and for
  dispatch at once. Do not re-add a "this tab has no sort order" notification —
  a key that cannot act must not be offered. A binding a focused widget hides
  (Textual's own `enter` on `DataTable`) is re-declared in the `Table` subclass,
  not duplicated at app level: the app-level copy never fires.
- **`suspend()` is for handing over the terminal, not for running a command.**
  `enter` on Sources suspends because the child owns the screen; `r` must not,
  because the child owns nothing the user needs to watch. Background work is
  `asyncio.create_subprocess_exec` with output captured, a hard timeout, and one
  reload at the end — the status line, not a restart, reports progress.

## Commands

```bash
./install.sh                                  # venv + ~/.local/bin/aut symlink
python3 -m unittest discover -s scripts/tests # stdlib unittest; pytest discovers them too
./bin/aut json --days 7                       # the snapshot, as JSON
./bin/aut cbut                                # jump straight into one tracker
```

## Layout

```
bin/aut                 bash dispatcher: tui | cbut/ocut/qcut | json | sync | --help
scripts/aut_sources.py  the adapters (SOURCES) and the Snapshot shape
scripts/aut_model.py    cross-tool aggregation: tokens, entities, timeline, kpis
scripts/aut_picker.py   the custom date-range picker (ported from the family)
scripts/aut_app.py      the Textual board: six panes + two detail screens
scripts/aut_chart.py    the share bar and its percentage, shared by every pane
scripts/aut_db.py       read-only connections, formatting, sparkline
scripts/aut_report.py   headless json / sync
scripts/tests/          adapters + aggregation against temp databases, board smoke tests
```

## Recording conventions

Commit subjects are English. The CHANGELOG records the non-feature commits — the
repairs, the guards, the withdrawals — and states what was true as of its commit,
not current state.

## Listed on the GitHub profile

**This repository is listed on the owner's profile front page**, and this section is the reciprocal
of `SHADE-glitch/SHADE-glitch`'s §6 index — that file is the authoritative rulebook, and
`~/.agents/standards/STANDARD.md` §8 holds the shared listing triggers. These facts must stay true
on the front page:

- **Rename / transfer / delete** — the profile link dies; fix the row.
- **Purpose drift** — the profile's one-line description must still be true. The claims it copies —
  *"one read-only board"*, *"no second parser"*, *"no writes"* — are **promises**, not slogans.
- **Source set change** — the About names `cbut`, `ocut` and `qcut`. Dropping or adding a source
  makes that sentence false; change it in the same commit.
- **LICENSE change** — the profile's license badge must equal this repo's `LICENSE`.
- **Public ↔ private** — a repo that goes private again must be **delisted**.

**The GitHub About description is under the same rule.** It must describe *this* repository: the
board that reads the three indexes and hands the terminal over — not a fourth tracker, and not a
sibling's About copied across.
