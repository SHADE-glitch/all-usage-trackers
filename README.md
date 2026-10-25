<p align="right"><a href="README.md"><b>English</b></a> | <a href="README.zh-CN.md">简体中文</a></p>

# 🧮 All Usage Trackers (`aut`)

![Python](https://img.shields.io/badge/python-3.11%2B-blue?logo=python&logoColor=white)
![SQLite](https://img.shields.io/badge/storage-SQLite-003B57?logo=sqlite&logoColor=white)
![Textual](https://img.shields.io/badge/TUI-Textual-ff69b4?logo=terminal&logoColor=white)
![License: MIT](https://img.shields.io/badge/license-MIT-green)
![Platform: Linux](https://img.shields.io/badge/platform-Linux-lightgrey?logo=linux&logoColor=black)
[![Repository](https://img.shields.io/badge/repository-GitHub-black?logo=github)](https://github.com/SHADE-glitch/all-usage-trackers)

**What it is** — a six-tab board over the usage trackers you already run: `cbut` (CodeBuddy), `ocut` (OpenCode) and `qcut` (Qoder CN). It merges their numbers across tools, and still hands the terminal to whichever tracker you pick when you want its full view.

**What it solves** — each tracker answers "how did I use *this* tool". None of them answers "which skill do I actually use across all three", "which model costs me the most this week", or "is this week up or down". `aut` is those three questions.

**How to run** — `./install.sh`, then `aut`.

**Where to look** — [AGENTS.md](AGENTS.md) for the invariants and the layout; [docs/maintenance/tracker-contracts.md](docs/maintenance/tracker-contracts.md) for what each adapter assumes about the three indexes.

---

## ✨ Features

- **One board, three trackers.** Six tabs — Dashboard, Tools, Skills, Tokens, Usage, Sources — over the SQLite index each tracker already built. Nothing is parsed twice and nothing is written.
- **Cross-tool answers.** A skill's use in CodeBuddy and OpenCode sits on one line; one model through three trackers is one total with a column per tracker.
- **One definition of "tokens".** Every figure is the tracker's own *Usage Total*, stated per source, never the provider's API total.
- **A per-tab footer.** Only the keys that can act on the current tab are drawn and listened for.
- **A hand-off, not a replacement.** `enter` on Sources suspends the board and opens that tracker's own eight-tab TUI; its `q` returns to a re-read board.

## 📊 The six tabs

| Tab | What it shows |
| :--- | :--- |
| **Dashboard** | the window's usage total, sessions and calls, the change against the previous window of the same length, top models and top skills as two cards that grow with their rows and fill the pane (the pane scrolls once the lists no longer fit), and the window caption. A model row carries its origin — which tracker(s) the merged number came from |
| **Tools** | one row per tool, with the calls each tracker made, ok / fail, average duration and last use |
| **Skills** | the same shape for skills — the one place a skill's use in CodeBuddy and OpenCode sits on one line |
| **Tokens** | **one row per model**, merged across trackers by name, with a column per tracker; `g` cycles to model × tracker (the usage total first, then the input / output / cache split it is made of), then one row per tracker. One model recorded under two spellings — dots here, hyphens there, a free route, Qoder's internal ids — is one row; the detail names the spellings it folded and lists each call under the one its tracker wrote |
| **Usage** | the most recent calls from all three in one timeline; identical calls within a minute share a row (`×26`), so the list shows turns rather than rows |
| **Sources** | each tracker's health, share of the window's tokens, index size and 7-day trend; `enter` opens that tracker's own TUI |

```text
 aut · all usage trackers                                                           📅 Custom…   Today                ▼
 Dashboard  Tools  Skills  Tokens  Usage  Sources
╸━━━━━━━━━╺━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 5 models · 1 skills in this window · last call 6m ago
 ╭────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
 │ Window                                                                                                             │
 │ 3.13B usage total   ↑49% vs 2.10B   ·   271 sessions · 19,894 calls · 1 active day                                 │
 │ CodeBuddy █░░░░░░░ 403.75M 13%   OpenCode ████░░░░   1.60B 51%   Qoder CN ███░░░░░   1.12B 36%                     │
 ╰────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
 ╭────────────────────────────────────────────────────────╮ ╭─────────────────────────────────────────────────────────╮
 │ top models · 3.13B                                     │ │ top skills · 1 calls                                    │
 │  minimax-m3.1-flash-fr… ocut        1.59B ██████  51%  │ │  chinese-to-English-camp…      1 ██████ 100%  47m ago   │
 │  deepseek-v4.1-flash    all         1.00B ████░░  32%  │ │                                                         │
 │  qwen3.8-flash          qcut      484.65M ██░░░░  16%  │ ╰─────────────────────────────────────────────────────────╯
 │  glm-5.3-flash          cbut       46.33M █░░░░░   1%  │
 │  flint-40b-free         ocut        4.96M █░░░░░   0%  │
 │                                                        │
 ╰────────────────────────────────────────────────────────╯
 3 of 3 indexes · 97.3 MB · synced 0s ago
 tab Next tab  shift+tab Prev tab  q Quit  r Sync now  d Date  ? Help
```

## ⌨️ Keys

The shared keys are the tracker family's, so a habit learned in `cbut` works here.

| Key | What it does |
| :--- | :--- |
| `tab` / `shift+tab` | next / previous tab |
| `1`–`6` | jump to a tab directly |
| `s` | cycle the sort order — the caption above the table names it (`sort: usage total ▼ (s)`) |
| `/` | filter rows ( `esc` clears) |
| `d` | date range — presets or the custom calendar picker |
| `enter` | open the selected row's detail (the table tabs; on Sources it hands the terminal to that tracker) |
| `g` | Tokens: by model → model × tracker → tracker |
| `r` | sync the three trackers now — their own `sync`, in the background |
| `?` `q` | help / quit |

The footer is the key list, and it is per-tab: `s` is absent on Sources, `g` appears only on Tokens, `/` only where there is a table. A key that cannot do anything on the current tab is neither shown nor listened for, so the footer never advertises a key that would answer "nothing here".

Every tab remembers its own window, as the trackers do: Dashboard, Tokens and Usage open on today, Tools on the week, Skills on the month (skills are rare enough that a week is often one call each).

The top bar is cbut's pair, with the same two jobs: the Select names a preset and opens the calendar on `Custom…`, and the 📅 button beside it names the picked span. A custom window therefore reads `Custom…` in the Select — it has no preset to name — while the button carries the range (`📅 10-01 08:00 → 10-03 18:30 ▾`). Cancelling the picker puts the bar back on the tab's real window.

The screen is laid out like the three trackers: the state line (rows, sort, grouping, totals) sits **above** the table, the bottom line is provenance — how many indexes were read, how big they are, when they were last synced — and the footer lists the keys.

`r` runs the three syncs behind the board instead of handing the terminal over: the status line names the tracker being synced (`syncing CodeBuddy 1/3`), `r` leaves the footer while it runs, and the tab is re-read once at the end. The Dashboard is a read-only summary — it has no selection and no `enter`, because every number on it is one keystroke away on its own tab.

## 🔢 Reading the numbers

- **Tokens are the unit.** No credits, no dollars: the three trackers report credits, credits and dollars respectively, so one money column would present three units as one.
- **A missing index is not a zero.** A tracker that is not installed, not synced or built by an older schema is skipped in the merges and reported on the Sources tab — never counted as "used nothing".
- **A missing token figure is not a zero either.** A source that reports credits but no tokens (qcut's BYOK routes) shows `—` on Sources. In the Tokens and Dashboard merges, a model with any unreported call is `—` too; the board never sums only the known rows and calls the result a total.
- **ok / fail / pending** come from the status the hosts actually write: `completed` is ok; `error`, `incomplete` and `cancelled` are failures; `running`, `backgrounded` and no status at all are pending, which is not a failure.
- **One model is one row.** The same model name through three trackers is one total with three columns, because "what did this model cost me" has one answer. Names merge case-insensitively; `g` still shows the per-tracker rows when that is what you want.
- **Tool names merge case-insensitively** (`Read` in one tracker, `read` in another, one row). `Bash` and `shell` stay apart: whether they are the same tool is a guess this app does not make.
- **One number, labelled.** Every token figure the board prints is the tracker's own **Usage Total** — the definition each tracker's panels use (cbut: prompt + completion + cache hit; ocut: full prompt + output + the hit re-added; qcut: input + output + cache read). The providers' own API totals are no longer read anywhere; a number that says neither input, output nor cache is always the Usage Total.
- **One bar, one scale.** Every bar in a table shares its scale, so a 12M tracker and an 81M tracker do not draw the same bar. The percentage beside a bar is its share of the window. In the ranked tables the bar is scaled to the largest row; Sources uses the window total, which is the same denominator as the percentage it prints.
- **Cards grow, then the pane scrolls.** A list card takes the height its rows need instead of truncating to a fixed row count; the dashboard pane scrolls once the screen is full, so nothing is silently cut.
- **Two numbers on one screen count the same calls.** The Sources tab takes its window from the tab, not from "the last N×24 hours", so it agrees with the KPI strip above it.
- **There is no `a` key.** The trackers use it for "installed but never used", which has no cross-tool meaning here.

## 🚫 What it does not do

- **It does not collect anything.** No log parsing, no network, no second copy of the truth: it reads the `usage.db` each tracker already built.
- **It does not write.** Every connection is `mode=ro`; `r` and `enter` write only through the tracker's own commands.
- **It does not replace the trackers.** The Sources tab is one key from their full eight-tab view.

## 📋 Requirements

- Python 3.11+ (the board's only dependency is Textual; `aut json` and `aut sync` are pure standard library).
- At least one of `cbut`, `ocut`, `qcut` installed and synced.

| Component | Version | Notes |
| :--- | :--- | :--- |
| Python | 3.11+ | the floor is `requires-python` in `pyproject.toml`; CI covers 3.11 and 3.14 |
| Textual | see `requirements.txt` | board only — `json` / `sync` need no third-party package |
| Linux | any | reads `~/.local/share/*/usage.db` |

## 📥 Install

```bash
git clone https://github.com/SHADE-glitch/all-usage-trackers.git
cd all-usage-trackers
./install.sh
```

`install.sh` is idempotent. It creates `.venv` in the repo and installs `requirements.txt` into it, then symlinks `bin/aut` into `~/.local/bin`, so `git pull` here updates the running install. It refuses to replace a real file at the target; pass `--force` if you really mean it. `AUT_BIN_DIR` moves the symlink target. The last step runs `aut json --days 7` and reports whether any source errored.

If `aut` is not found afterwards, `~/.local/bin` is not on your `PATH`.

## 🧭 Usage

```bash
aut                  # the board
aut cbut             # jump straight into one tracker's own TUI
aut sync             # run the three trackers' own sync commands
aut sync cbut ocut   # …or only some of them
aut json --days 7    # the numbers the board draws, as JSON
aut --help
```

`aut json` takes `1` / `7` / `30` / `0` (= all time) for `--days` — anything else is refused, not silently rounded to 7 — and is stdlib-only, so it works without the venv, which is what makes it usable from a script.

## 🧯 Troubleshooting

| Symptom | Cause | What to do |
| :--- | :--- | :--- |
| a source shows `no db` | that tracker is not installed, or its index was never built | install it and run its `sync`; `aut sync` does that for you |
| a source shows `error` | its `usage.db` no longer matches the columns `aut` reads | see [the contracts file](docs/maintenance/tracker-contracts.md); the adapter is one entry in `scripts/aut_sources.py` |
| a source shows `idle` | no calls in the last week — not a fault | nothing |
| a model shows `—` | that source reported calls but no token figure (for example a BYOK route that only records credits) | check that tracker's own panel; the board will not turn unknown into 0 |
| a source's note says the index does not record usage | the tracker wrote the calls but not the usage flag, so nothing vouches for the total | the total is a floor; compare against that tracker's own panel |
| a line says `synced` is missing | this session has not run a sync — the board read the indexes at start | press `r`, or read the numbers as of the app start |
| `aut: command not found` | `~/.local/bin` not on `PATH` | add it, or re-run `install.sh` with `AUT_BIN_DIR` |
| the board will not start, `aut json` works | the venv is gone or Textual is missing | re-run `./install.sh` |

## 🧪 Testing

```bash
python3 -m unittest discover -s scripts/tests
```

The suite is stdlib-only and builds its own SQLite fixtures in a temporary `HOME`, so it never opens a real tracker index. CI runs it on Python 3.11 and 3.14. A green run with no fixture for the thing you changed proves nothing — see [MAINTENANCE.md](MAINTENANCE.md) for the three verification tiers.

## 📁 Repository layout

```text
bin/aut                      the entry point (bash: still useful when the venv is gone)
install.sh                   idempotent install: .venv + symlink into ~/.local/bin
scripts/aut_sources.py       one adapter per tracker — the only file that knows a schema
scripts/aut_db.py            read-only connections, windows, formatting
scripts/aut_model.py         the cross-tool aggregation every tab draws (pure, no Textual)
scripts/aut_chart.py         text bars and percentages
scripts/aut_app.py           the Textual board: tabs, bindings, footer
scripts/aut_picker.py        the family's date-range picker
scripts/aut_report.py        the JSON view
scripts/tests/test_aut.py    the suite (fixture databases in a temp HOME)
docs/maintenance/            the tracker contracts — what each adapter assumes
docs/audit/                  dated read-only audit reports (a snapshot, not current state)
```

## 🧩 Adding a fourth tracker

One entry in `SOURCES` in [scripts/aut_sources.py](scripts/aut_sources.py): a key, a label, the database name, the binary, and the SQL expressions that normalise its token and project columns. Every tab picks it up. The contracts file lists what you have to find out about the new tracker first.

## 🤝 Contributing

This is a personal tool, but the rules are written down: read [AGENTS.md](AGENTS.md) for the invariants (read-only connections, one usage-total definition per source, the footer drawn from `check_action`), run the suite before and after, and add a `D-###` entry to [CHANGELOG.md](CHANGELOG.md) for anything that is not a plain feature.

## 📄 License

MIT — see [LICENSE](LICENSE).
