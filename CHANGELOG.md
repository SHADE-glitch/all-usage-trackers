# CHANGELOG — all-usage-trackers

Original project, **no upstream**. This records the decisions that are not
obvious from the code — the ones a change in one of the three trackers, in
Textual, or in a schema can invalidate.

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
