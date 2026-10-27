# CHANGELOG — all-usage-trackers

Original project, **no upstream**. This records the decisions that are not
obvious from the code — the ones a change in one of the three trackers, in
Textual, or in a schema can invalidate.

Two kinds of entry appear below, both newest-first:

- **`D-###`** — the decision ledger, from 2026-10-25 on. Monotonic, never reused;
  `kind` ∈ `fix | perf | taste | guard | revert | chore`; an entry states what was
  true **as of its commit**.
- **`0.x.0`** — release notes written before the ledger existed, kept **verbatim**.
  They are deliberately not backfilled into `D-###`: a record invented after the
  fact is not a record.

## D-008 · 2026-10-27 · fix

**Symptom** — with **All time** (and any window containing one of them) the Tokens tab showed
`—` for CodeBuddy's usage total, input and output while `req` read 44,473, and the Dashboard's
window card showed `token usage not reported in this window`. Six rows out of 44,473 have
`usage_available = 0` because their transcript carried no usage block at all
(`missing = rawUsage`); one such row in a group was enough to make that group unknown, and
`by_source`/`model_totals` folded "unknown" into the whole row. 10.91B tokens read as `—`.

**Change** — the aggregates now follow the three trackers' own semantics: cbut, ocut and qcut each
compute their panels with a plain `SUM()`, which skips rows that reported nothing and is NULL only
when *no* row did, and each prints `missing_*` counts beside the number. `_measured_sum()` states
that rule once and the three aggregate sites (`token_rows`, `kpis`, `model_stats`) use it;
`_sum_opt()` now ignores a part that measured nothing instead of poisoning the fold. A partially
measured row keeps `tokens_real = False`, which the Tokens tab renders as a `*` on the total with
one legend line in the caption — the number is the measured sum, and it says so.

**Verified against the source of truth** — aut's all-time CodeBuddy total is now
`10,912,133,700`, byte-identical to `cbut q_usage_summary().usage_total_tokens` over the same
window (which reports `missing_prompt: 6`, `missing_completion: 6` alongside). The hard rule still
holds: a source that reports **no** tokens at all is still `—`, never `0` — the BYOK tests are
unchanged and still pass. What changed is that "some rows were unmeasured" is now disclosed rather
than used as a reason to withhold a number the tracker itself prints.

**Not changed on purpose** — the Sources tab's share column still goes `—` when any tracker's
window is wholly unmeasured: a share is a fraction of a whole, and an unknown denominator makes the
fraction unknown in a way a sum does not.

## D-007 · 2026-10-27 · fix

**Symptom** — the dashboard's window card printed a second figure beside the total
(`↑2% vs 1.95B`). That figure was the window of the same length immediately before the current one,
computed by a nested `kpis()` call. With a custom range picked from the two date fields it stopped
arriving: a three-day span already produced no base (the nested call passes `_delta=False`, so only
one level was ever computed), and the card silently lost the tail of its own line instead of saying
so. The number was also a second claim about rows the total already described.

**Change** — remove the comparison rather than repair it. `Kpis.prev_tokens` / `prev_sessions`,
the nested `kpis()` call and `aut_app._delta()` are gone; the window card now reads
`<total> usage total · N sessions · M calls · K active days`. The test that pinned the comparison
now pins the opposite: the row outside the window is counted nowhere, and the dataclass has no
field to put it in. README's Dashboard row and both mock lines lost the segment; the box keeps its
width.

**Closed by D-008 the same day** — a window of seven days or more used to fall back to "token usage
not reported in this window" because one unmeasured row set `tokens` to `None` for the whole
window. That was the same defect D-008 fixes, so the fallback now only appears when *every* row in
the window is unmeasured. The paragraph stays so the two entries read in order.

## D-006 · 2026-10-25 · chore

**Symptom** — the 2026-10-25 read-only audit of this repository existed only as a one-off session
report: P0 × 1 (BYOK/no-token sources shown as 0 in the merged views), P1 × 12, P2 × 18, plus a
14-row test-gap checklist, five next steps and the probe environment. Nothing in the repository
pointed a reader at it, and its numbers (52 tests, 24.7s) describe a tree the fixes have since
moved past.

**Change** — file the report as `docs/audit/2026-10-25.md`, English, matching this
repository's dimension-A English-first convention. The banner marks it a 2026-10-25 snapshot and
names the suites as the source of current state. Each finding that a post-audit commit repaired
carries that commit on its heading — verified against the commits' own diffs, not assumed:
`68b2a9c` covers P0-1, P1-1..P1-6, P1-11, P1-12, P2-1, P2-3..P2-6; `9570347` covers P1-7..P1-10
and P2-11; `7e5d8c0` covers P2-2, P2-7..P2-9, P2-12, P2-13, P2-15, P2-16, P2-18; `444098b`
covers P2-14 and part of P2-10. Still open: P2-10's `timeline` and P2-17. Every finding keeps
its severity, `file:line` evidence, impact and fix direction; the prose is compressed but nothing
is dropped and no number is changed. Both READMEs gain the `docs/audit/` row in their layout
block, so the tree on disk and the tree the docs draw stay identical.

**Evidence** — `python3 -m unittest discover -s scripts/tests`: 72 tests, OK on the final tree.
The new document is a pure addition under `docs/audit/` — no script, test or root file touched —
so the suite and `.github/workflows/ci.yml` are unaffected.

**Cost** — records only; no behaviour change. The audit's line numbers describe the 2026-10-25
tree (suite at 52 tests), not HEAD; the document says so in its banner.


## D-005 · 2026-10-25 · chore

**Symptom** — `aut_model` carried two functions with no caller and no test
(`_classify`, `daily_tokens`), and both the report's docstring and the READMEs
called `aut json` "the same snapshot the board draws". With D-003 the board
reads each source inside one read transaction, so "the same snapshot" was now a
stronger claim than either path makes: the JSON report reads each source
separately, and no claim is made across the three.

**Change** — the two dead functions are gone; `OK_STATUSES` / `FAIL_STATUSES`
stay because the entity rows still classify by them. The wording now says what
is true and checkable — the same numbers, through the same adapters, each
source read inside one transaction.

**Evidence** — `python3 -m unittest discover -s scripts/tests`: 72 tests, OK;
`grep` for both deleted names returns nothing outside this entry.

**Cost** — none to behaviour; nothing called either function.

## D-004 · 2026-10-25 · fix

**Symptom** — six more places where the board said something it could not
support. `tokens_real` treated "no usage flag anywhere in the index" as "every
call carried usage", so a tracker that never wrote the flag got the same vouch
as one that did. A value that is text where a number belongs escaped as an
uncaught `ValueError` out of a source read instead of becoming that source's
`error` row. `aut sync` had no ceiling while the board's `r` waited 300s.
`--days 14` became 7 without a word. The status line printed "synced 0s ago"
at boot, before anything had been synced, and counted indexes that exist on
disk as if they had been read. Usage hid that its list is capped at 300 rows,
and offered "Open" in the footer with nothing to open.

**Change** — `Snapshot` requires `real_avg is not None` before it vouches for
a total, and says so in a third note ("the index does not record whether calls
carried usage"). `snapshot()` and `_per_source()` catch
`(sqlite3.Error, ValueError, TypeError)`, so a bad conversion is that
source's error. `SYNC_TIMEOUT_S` moved into `aut_sources` and `aut sync`
applies it. `--days` takes `choices` from `WINDOWS`, so an unknown window is
refused with usage instead of being rounded. The status line reads "indexes on
disk" and prints "synced" only after this session has synced. Usage names its
300-row cap in the note, and `check_action` answers "Open" only for the tabs
that implement `open_selected`.

**Evidence** — `python3 -m unittest discover -s scripts/tests`: 72 tests, OK.
The new cases cover an index whose usage flag is all NULL reading as a floor
with its own note, a `_read` that raises `ValueError` becoming an `error` row,
`aut json --days 14` exiting 2, and the Usage tab offering no "Open" while
Tokens' does.

**Cost** — a JSON consumer that passed an arbitrary `--days` (14, 3, 0.5) now
gets exit 2 instead of a silent 7-day report. `tokens_real: false` for an index
without the flag is a downgrade of a claim, not of a number: the tokens are
still summed, and only the vouch is withdrawn.

## D-003 · 2026-10-25 · fix

**Symptom** — four places where the board's promises outran its code. `aut json`
imported the date picker at module level, so the "pure standard library" report
needed Textual to start. A model name containing `[` reached a `DataTable` as a
plain `str`, which Textual parses as Rich markup — `bad[/red]` raised
`MarkupError` inside the renderer and took the screen with it — and an ESC in a
name was handed to the terminal untouched. A tracker that dropped a column only
the merges read (`provider`, `status`, `duration_ms`) still showed `ok` on
Sources while Tokens or Tools came back empty with no explanation. And each
tab's reload opened a fresh connection per question, so a tracker syncing in
between could answer the KPIs from before its commit and the model rows from
after — one screen, two moments.

**Change** — the window arithmetic (presets, `CustomWindow`, the date/time
parsers, `bounds_of`) moved to `aut_windows.py`, which imports no Textual;
`aut_picker` is the modal only and `aut_report` reads `aut_windows`. Every
tracker string that becomes a cell goes through `_cell`, which replaces C0
control characters and builds a `Text` — a `Text` is never parsed as markup.
The Sources note is a `Text` too, and the sync notification sets
`markup=False` because its tail is the child's own output. `Source._read`
prepares one SELECT naming the columns the merges need (its own expressions
plus `model`, `provider`, `session_id`, `ts`) and reports `error` when that
fails; `aut_model` records a failed merge query per (source, query) in
`source_errors()` and Sources shows `error` for it, clearing when the same
query succeeds again. `aut_model.read_session()` opens one connection per
source inside one read transaction; every pane's reload and both detail
screens run inside it, and `Snapshot` starts its own read transaction.

**Evidence** — `python3 -m unittest discover -s scripts/tests`: 68 tests, OK.
The new cases run the JSON report in a child process with `textual` blocked,
check `_cell` on `bad[/red]` and on an ESC payload, render a `bad[/red]` model
through the board, read a source without `provider` as `error`, surface a
missing entity `status` column through `source_errors()`, and count
connections: one reload now opens one per source instead of one per query.

**Cost** — a reload holds a read transaction per source for its duration, so a
tracker syncing at that moment waits (the connection is `mode=ro` with a 2s
busy timeout) rather than interleaving. Cross-source consistency is still not
claimed: the three indexes commit independently, and only each source's own
numbers come from one moment. A new module is one more import for anything
that needs a window.

## D-001 · 2026-10-25 · guard

**Symptom** — this repo's `AGENTS.md` declared dimension A, but the repo was not in
`STANDARD.md` §0, so no audit ever looked at it. It carried none of the A-tier
shape: no CI, no `docs/`, no `MAINTENANCE` pair, a `.gitignore` without the runtime
entries, and a CHANGELOG with no `D-###` entry. A declaration nothing checks is a
claim, not a state.

**Change** — registered as the 18th governed repository (A, 11 of 11) and given the
shape it claimed: `.github/workflows/ci.yml` (unittest on 3.11 / 3.14),
`docs/maintenance/tracker-contracts.md` (what each adapter assumes about a tracker's
index), the `MAINTENANCE` bilingual pair, the §4 runtime ignore entries, and the
missing README sections — Install, Usage, Troubleshooting, Testing, Repository
layout, Contributing, License — in both languages, plus the four-label block the
Chinese page lacked.

**Evidence** — `audit-layout.sh`: 18/18 repos match their dimension's shape;
`python3 -m unittest discover -s scripts/tests`: 52 tests, OK.

**Cost** — one more document can now drift from `scripts/aut_sources.py`. The
contracts file states the tie-break: if the two disagree, the code is right and the
document is a bug. The 0.1.0–0.5.0 notes below stay in their own format; the ledger
starts here rather than pretending to cover them.

## D-002 · 2026-10-25 · fix

**Symptom** — a source that reports credits but no tokens (qcut's BYOK routes)
reached the board as `0`: `aut_sources` already knew the difference, but
`aut_model` ran every token column through `COALESCE(..., 0)`, and the dashboard
turned the result into "nothing recorded". The same audit found three more
places where the numbers did not mean what they said: `active_days` took the
busiest tracker's count instead of the union of days, an entity's average
duration divided by calls that had no duration, and an entity's drill-down
queried only the spelling shown on the merged row. A NULL model was labelled
`(unknown)` but the detail queried the literal string, so its calls vanished.
Sources also applied only a start bound, so a custom historical window counted
calls that happened after its end.

**Change** — the three adapters now use the same `CASE` expressions as their
own trackers' Usage Total: a row with missing API parts is NULL, not zero, and
a missing cache column still contributes 0. `aut_model` keeps NULL through
`TokenRow`, `ModelTotal`, `CallRow` and `Kpis`; a merged row with any
unreported call is unknown, not a sum of the known rows. `Kpis.active_days` is
the union of per-source dates; entity averages divide by `measured_calls`; an
`EntityRow` carries every spelling and the detail queries all of them;
`(unknown)` maps to `model IS NULL` / `name IS NULL`. The entity detail screen
shows status and duration in their own columns instead of borrowing the model
and token columns. The dashboard, Tokens and Sources show `—` for unknown, and
the JSON report no longer exposes `cost` / `cost_unit` (the board does not show
money). `Source.snapshot` now takes an `end_ms`: totals, buckets, top rows and
the last-event clock are bounded by the window's end, so a historical window
cannot see later calls. `SourcesPane` and `aut json` pass that end through, and
the JSON report names it as `window_end_ms`. README/README.zh-CN, the help
screen and `install.sh`'s source check were corrected to match.

**Evidence** — `python3 -m unittest discover -s scripts/tests`: 62 tests, OK.
The new cases cover BYOK NULLs, a mixed known/unknown model, missing cbut
parts, active-day union, NULL-duration averages, `(unknown)` drill-down,
entity spelling merge, entity status/duration, a custom end that excludes later
calls, and an empty window that still reads `idle` from older history.

**Cost** — `aut json` consumers that read `cost` or `cost_unit` must read the
tracker's own index instead; those fields were the one place money still
crossed the board's boundary. A partly reported window on Sources is still a
floor (with `tokens_real: false` and a note), while the merged Tokens and
Dashboard views show `—` rather than an unlabelled floor.

## 0.5.0

One token number everywhere, and a dashboard that fits its content.

### Changed

- **Every token figure is the tracker's Usage Total.** The three adapters each
  restate the definition their own tracker's panels use (cbut: prompt +
  completion + cache hit; ocut: full prompt + output + the hit re-added; qcut:
  input + output + cache read), and `snapshot` / `daily` / `by_day` all read
  that one expression. The separate `token_expr` field — the API-side provider
  total, which had drifted from the Usage Total the panels print — is deleted:
  two totals in one adapter meant the KPI strip, the per-day buckets and the
  top-model ranking could each answer a different question.
- **Token columns are named for what they are.** `total` reads `usage total`
  on Tokens, Usage, Sources and the dashboard KPI strip, so a number that says
  neither input, output nor cache is always the Usage Total.
- **One model is one row, however it is spelled.** The by-model view folded
  case only, so `deepseek-v4.1-flash` (cbut's builtin route),
  `deepseek-v4-1-flash` (the same model through Volcano ARK) and
  `deepseek-v4.1-flash-free` (ocut's free route) were three rows for one model,
  and Qoder's `dfmodel` was a fourth. `canonical_model` folds punctuation and
  the free-route suffix, and `MODEL_ALIASES` names the ids no rule can infer —
  Qoder's builtin routes report `provider_id` NULL, so its model picker is the
  only source for those two. The Tokens by-model view and the dashboard read
  the folded key; Usage, the per-call rows and the model × tracker view keep
  each tracker's own spelling. A row carries the spellings it folded, and the
  detail screen queries all of them — otherwise the row said 910M and the
  drill-down 638M.
- **The usage total leads the split on Tokens.** In the model × tracker view it
  used to sit after input / output / cache r / cache w, which read as a sum
  arriving after its parts. It is the column the table is sorted by, so it now
  comes first; the four parts follow it.

### Removed

- **The dashboard's stacked chart and the tokens-per-day strip.** The chart
  duplicated what the Tokens tab's per-day buckets draw with real sorting and
  real filters; the strip read the retired API total, so its caption said
  "tokens" while every other number on the screen said something else.
- **Recent calls** from the dashboard. It repeated the Usage tab's newest rows
  in a narrower box with no way to open them.
- **The tokens-per-call block under the dashboard's model list.** It answered a
  per-tracker question inside a card ranked by model, and the two numbers it
  printed are already on the Sources tab (share, trend) and in the KPI strip
  (per-tracker totals). The card is now only the ranked list its title
  promises; `Kpis.per_source_calls` went with it, since nothing read it.

### Layout

- The dashboard's bottom half is two cards — top models and top skills — that
  grow with their rows and fill the pane: each card's `min-height` is the
  height the pane has left after the state line and the KPI card, so a short
  window ends at the status line instead of a dozen rows above it. It is a
  floor, not a fixed height — a list taller than the pane still grows to its
  own height and the pane scrolls (`overflow-y: auto`), so nothing is clipped
  either way.
- **A top-model row names its origin.** A model's total is a sum over the
  trackers that used it, and on a merged board that is exactly what the number
  cannot tell you, so each row carries a tag beside the name (`cbut`, `ocut`,
  `qcut`, `cbut+ocut`, `all`). The tag is nine columns and the model name gives
  them up, with an ellipsis once the name no longer fits — the row still fits
  the card at every width the two-column layout is used at.
- **Rows are sized from the card, and the numbers stop growing.** At All time a
  model total is ten digits — nine characters as "10151.90M" — while the row
  was laid out for seven, so the percentage wrapped onto the next line and read
  as an entry of its own. Token counts now scale to B and T ("21.21B"), and the
  name field is whatever the card's *measured* width leaves after the origin,
  the number, the bar and the percentage. When the card is too narrow for all
  four, the bar goes first (the percentage carries the same fact), then the
  origin tag, then the percentage; the name absorbs the slack, so a row cannot
  wrap at any width. The same measurement replaces the pane-width formula, which
  was one column wide whenever the pane scrolled.
- **The KPI line drops whole facts instead of wrapping them,** and the Tokens
  caption uses the short grouping label below 100 columns. Both were 2-20 cells
  too wide at 80.
- **The screen keeps the theme's default background.** A whole-screen
  `background: $surface` painted aut with `rgb(30,30,30)` while the three
  trackers render on the `textual-dark` default `rgb(18,18,18)` — the family's
  one app that looked lighter. The override is gone; the top bar, cards, filter
  and help box keep the same `$panel` / `$boost` / `$accent` tokens the trackers
  use, so the palettes now match to the cell.
- **The two range controls are cbut's, including "Custom…".** The top bar's
  Select listed the seven presets only, so a custom span had nowhere to show:
  the Select kept naming whatever preset was last chosen while the 📅 button
  beside it showed a week, and the only way to a span was the 📅 button. The
  Select now carries `Custom…` as its last entry and opens the picker, a window
  picked in the calendar reads `Custom…` in the Select (it has no preset to
  name) with the span on the 📅 control, and cancelling puts the bar back.
  A programmatic `Select.value` write is told from a user choice by comparing
  against the tab's own window, so switching tabs no longer re-opens the picker.
  The Select is 30 cells wide, as in cbut, so `30 days` and `Custom…` are not
  clipped. Windows remain per tab and the defaults are unchanged.

### Tests

- **The qcut fixture declared a `model_calls` without `provider`,** and
  `token_rows` selects `COALESCE(provider, '')` for every source: the query
  failed and `_per_source` swallowed it, so every qcut token row was silently
  absent from the aggregation tests. The real index has the column; the fixture
  now does too.

## 0.4.0

The board is driven from its footer now: every tab lists exactly the keys it
answers, and `r` no longer leaves the screen.

### Changed

- **The footer is per-tab.** `AutApp.check_action` decides both whether a binding
  is drawn and whether the key fires, so `s` is gone from Sources, `g` from every
  tab but Tokens, and `/` from every tab without a table. The "this tab has no
  sort order" notifications went with them: a key that cannot act is not offered.
- **`⏎ Open` is in the footer on every table tab.** Textual binds enter on
  `DataTable` with `show=False`, so the one key that opens a row was the one key
  missing from the list; a two-line `Table(DataTable)` subclass re-declares the
  same `select_cursor` action under a visible name.
- **`r` syncs in the background.** It used to call `app.suspend()` once per
  tracker, so one key press read as three restarts. The syncs now run as captured
  subprocesses (`asyncio.create_subprocess_exec`, `SYNC_TIMEOUT_S = 300`): the
  status line names the tracker and step (`syncing CodeBuddy 1/3`), `r` leaves the
  footer while it runs, and the active tab is re-read once at the end.
- **The Dashboard has no selection.** `↑`/`↓` and `enter` are gone, along with the
  reverse-video row and `open_tokens_for`; its caption names the window instead
  (`6 models · 0 skills in this window · last call 18s ago`).

### Removed

- The app-level `enter` → `open_row` binding. It never fired — a focused
  `DataTable`'s own enter binding shadows the app's — which is why the footer
  entry had to come from the table in the first place.

### Decisions worth remembering

- **`check_action` is the single place a key's applicability lives.** It answers
  for the footer and for dispatch at once, so a tab-specific key costs one branch
  there instead of a "not on this tab" notification inside the action.
- **Suspend is for handing over the terminal, not for running a command.**
  `enter` on Sources still suspends (the child owns the screen); `r` does not
  (the child owns nothing the user needs to watch), and it gets a timeout because
  a sync that never returns must not wedge the board.

## 0.3.2

### Added

- **Rounded cards on the Dashboard**, the way the three trackers draw their
  summary panels: `╭─╮` around the window, the chart, and each ranked list,
  title on the first row inside the border.

### Changed

- The chart card spends four columns on chrome (border + padding), so the chart
  is drawn `width - 4` wide and the ranked lists take their name width from the
  card, not from the pane.
- The chart height is now chosen so the list cards keep at least five rows:
  `max(4, min(8, height - 18))`.

### Decisions worth remembering

- **Cards cost rows, and the chart is the flexible one.** A card is two rows of
  border; at 26 rows the dashboard shows a four-row chart and three list rows,
  at 38 rows a full chart plus the tokens-per-call block. Nothing is dropped —
  the chart shrinks first.
- **The two bottom cards differ by one column on an odd width.** That is the
  terminal, not a bug: `1fr` cannot split 129 columns evenly. The trackers'
  own dashboards show the same difference.

## 0.3.1

The screen now has the three trackers' chrome: state above the table, keys in the
footer.

### Changed

- **The per-tab state line moved above its table** and names both keys:
  `5 rows · sort: total ▼ (s) · grouping: by model (g) · total 144.19M`. It used to
  sit under the table, where it read as a footnote to a reorder nobody could see.
- **The bottom is the family's**: a provenance line (`3 of 3 indexes · 87.2 MB ·
  synced 0s ago`) and Textual's `Footer` with the key list, replacing the
  hand-written hint string.
- **Bindings are described in Title Case** (`Sync now`, `Sort`, `Filter`) and
  `ENABLE_COMMAND_PALETTE = False`, both matching the three trackers.

### Fixed

- **The hidden-columns note never appeared on Tokens.** It compared against
  `COLUMNS`, which that pane no longer defines — its column set depends on `g`.
  The full set now comes from `columns_for()`, so the second line reads
  `7 of 10 columns · hidden: provider, cache r, cache w · widen to see them`.
- **The help box was narrower than its own text**, so every line wrapped.

### Decisions worth remembering

- **State above, provenance below.** The caption answers "what am I looking at
  and how is it ordered"; the bottom line answers "what was read and when". The
  two were one line before, which is why the sort was invisible.
- **The caption is per pane, not per app.** It lives in the pane that owns the
  state, so a tab switch cannot show another tab's sort.
- **The footer is Textual's, not a string.** It follows `BINDINGS`, so a new key
  appears without a second edit — and it can hide what does not apply.

## 0.3.0

The dashboard was rebuilt, the Tokens tab learned what a model is, and the
hand-off to a tracker's own TUI stopped repainting the board.

### Added

- **A real dashboard**: one KPI strip (tokens, change against the previous
  window, sessions, calls, active days), one stacked chart with a y axis, an x
  axis and **one shared scale per chart**, then ranked lists that carry a
  proportion bar, the tokens-per-call of each tracker, and the last calls.
- **`up`/`down` on the dashboard** picks a model; `enter` opens Tokens filtered by
  it. The dashboard previously had no action at all.
- **Sort marker**: the sorted column's header carries a `▼` and the status line
  names it, so `s` never has to be pressed to find out what it did. Panes without
  a sort order say so instead of swallowing the key.
- **`g` has three states on Tokens**: by model (default), model × tracker, tracker.
- **`model_totals()`** and **`timeline()`** in the model layer, and a new
  `aut_chart.py` with `stacked_chart`, `share_bar`, `pct`.
- **Tests**: the chart's glyphs, the shared scale, label anchoring, the collapse
  rule, and the sort marker.

### Changed

- **Tokens merges by model name by default.** The same model through three
  trackers is one total with three columns; the per-source rows are one `g` away.
- **Usage collapses identical calls within a minute** into one row (`×26`). 300
  rows of one model became 52 rows that can be read. Only in time order: sorted by
  tokens, one row is still one call.
- **Skills and Tools open sorted by last use**, not by call count, and their bars
  scale to the busiest row.
- **Sources counts the tab's window**, not "the last N×24 hours". It used to
  disagree with the KPI strip above it (357M against 127M on the same screen).
- **Sources gained a share column**, and the note line now carries the reason a
  row is not simply "ok".
- **Narrow terminals**: Tokens drops `provider` below 128 columns and the cache
  split below 108; Sources drops its index size below 108. Rows are never dropped.
- **The status line was invisible.** `#status` and `#hint` both docked to the
  bottom edge and were laid out on the same row; they now share a two-row footer.

### Fixed

- **`_share_cell` was referenced but never written** — the Sources tab raised
  `NameError` on mount. Caught by opening the tab, not by the tests; the tests now
  cover the cell helper.
- **The x axis drew one label.** The density was computed from the number of
  buckets instead of the plot's width, and the clamp pushed every label onto the
  same column.
- **The y axis never showed 0**, the one label a reader uses to judge a bar.

### Decisions worth remembering

- **The window is the chart.** A one-day window draws hours; it does not borrow a
  week of context. The previous version drew 7 bars under a "Today" KPI, which is
  why the screen read as decoration.
- **Bars are a magnitude chart, percentages are shares.** A bar is scaled to the
  largest row (so the ranking is visible); the number beside it is the share of
  the window (so the sum is visible). Both are labelled, neither is implied.
- **Model merging folds case, not provider.** `Claude` and `claude` are one
  model; two providers serving the same model name are still one model, because
  the question is about the model. The provider column survives in the
  model × tracker view.
- **A cell is padded in the string, not with `Text(justify=...)`.** A DataTable
  renders each cell on its own, so justify pads against the wrong width and the
  column stops lining up.
- **`on_resize` repaints columns only when the visible set changes.** Dragging a
  window edge must not re-query three databases per pixel.
- **Returning from a tracker's TUI reloads one row.** `SourcesPane.reload(only=)`
  updates cells by row key instead of clearing the table, so the cursor, the
  scroll position and the other two rows survive the round trip.

## 0.2.0

### Added

- **Six tabs**: Dashboard, Tools, Skills, Tokens, Usage, Sources. The board is no
  longer a launcher with three rows; it answers questions no single tracker can.
- **Cross-tool skills and tools**: one row per name, one column per tracker. This
  is the only view where a skill's use in CodeBuddy and OpenCode sits on one line.
- **Tokens with a group toggle** (`g`): per model, or folded to one row per
  source, with input / output / cache read / cache write / total / requests.
- **Dashboard with a delta**: the window's tokens, sessions, calls and active days
  against the previous window of the same length, plus per-source daily bars.
- **Detail screens**: `enter` on a token row shows that model's daily series and
  every call; `enter` on a skill or tool shows its calls.
- **The family's date-range picker**, ported rather than re-invented: same chips,
  same 79x30 calendar, same typed `MM/DD/YYYY` + `HH:MM`.
- **Per-tab windows**, as the trackers have.

### Changed

- **Keys now match the family**: `r` syncs (it used to refresh), `s` sorts,
  `/` filters, `d` opens the range picker, `tab` cycles. The old board had `r` and
  `s` swapped against every tracker the user already knows.
- **The old three-row board became the Sources tab**, which is what it always was:
  health, plus the way into each tracker.

### Decisions worth remembering

- **Skills open on 30 days, not 7.** A week of skills is often one call each; the
  month is the smallest window where the tab says anything. The one deliberate
  deviation from the family's 7-day default, and it is about the data.
- **No `a` key.** The trackers use it for "installed but never used", which has no
  cross-tool meaning. A key that does nothing is worse than an absent key, and the
  help says why.
- **Tool names merge on case only.** `Read` and `read` are one row; `Bash` and
  `shell` are not, because whether they are the same tool is a guess.
- **`pending` is its own column.** `running`, `backgrounded` and a missing status
  are not failures; folding them into `fail` would report errors that never
  happened.
- **The delta shifts by whole days.** Comparing "today so far" with "the previous
  equal span" compares it with yesterday evening; shifting by calendar days
  compares the same time of day.
- **The dashboard chart keeps a week of context.** A one-day window draws one bar,
  which is not a trend; the title says `context` when the chart is wider than the
  window.
- **OpenCode stores a hashed project id beside the directory.** The adapter reads
  `directory`; reading `project` showed a 40-character hash in the timeline.
- **`DataTable` claims `enter`, and `name` is a DOMNode property.** Row selection
  is handled on `RowSelected`, and screen attributes are `model_name` /
  `entity_name` — both were runtime failures, not style choices.

## 0.1.0

### Added

- **The board.** Three sources, one row each: tokens, sessions, a 30-day-at-most
  sparkline, the age of the newest record, and a state badge. `enter` suspends
  the app and runs that tracker's own TUI; its `q` returns to a refreshed board.
- **`w` window cycling** (1d / 7d / 30d / all) applied to all three sources at
  once — the comparison the board exists for.
- **`s` / `S` sync** through each tracker's own command, run in the real terminal
  so its output stays visible.
- **`aut json`** — the same snapshot the board draws, from one code path.
- **`aut cbut|ocut|qcut`** — skip the board and exec the tracker.

### Fixed

- **`aut sync` reports a missing tracker instead of raising.** On a machine that
  has only one of the three installed, `aut sync` used to end in a
  `FileNotFoundError` traceback; it now names the missing binary, moves on to the
  next source, and exits 1.
- **`install.sh` refuses before it builds anything.** The symlink guard used to run
  after the venv step, so a refused install still left a venv behind and read like
  a half-success. The guard now runs first, and the symlink step is a single
  `rm -f` + `ln -s`.

### Decisions worth remembering

- **Read-only connections, always** (`mode=ro`). The board must not corrupt an
  index, and must not take a write lock while a tracker is syncing.
- **No cost column.** The three trackers report credits, credits and dollars.
  Merging them into one money column would present three units as one, so the
  board shows tokens only.
- **`—` is not `0`.** Qoder's BYOK routes report credits without tokens; that row
  shows an em dash and the detail pane says "no token reported".
- **Adapters normalise in SQL, not in Python.** The three schemas differ by table
  name (`model_responses` vs `model_calls`) and column names
  (`prompt/completion_tokens`, `input/output_tokens`, `total_tokens`); keeping one
  expression per source is what makes adding a fourth tracker a one-entry change.
