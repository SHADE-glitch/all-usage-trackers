# CHANGELOG — all-usage-trackers

Original project, **no upstream**. This records the decisions that are not
obvious from the code — the ones a change in one of the three trackers, in
Textual, or in a schema can invalidate.

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
