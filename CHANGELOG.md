# CHANGELOG — all-usage-trackers

Original project, **no upstream**. This records the decisions that are not
obvious from the code — the ones a change in one of the three trackers, in
Textual, or in a schema can invalidate.

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
- **`enter` is handled on `DataTable.RowSelected`, not as an app binding.**
  DataTable claims `enter` for its own `select_cursor`, so an app-level binding
  never fires while the board has focus. The footer was replaced with an explicit
  hint line for the same reason: the footer only listed the bindings Textual did
  not swallow, which silently hid `enter`.
- **Adapters normalise in SQL, not in Python.** The three schemas differ by table
  name (`model_responses` vs `model_calls`) and column names
  (`prompt/completion_tokens`, `input/output_tokens`, `total_tokens`); keeping one
  expression per source is what makes adding a fourth tracker a one-entry change.
