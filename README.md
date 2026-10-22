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

**Where to look** — [AGENTS.md](AGENTS.md) for the invariants and the layout.

---

## Tabs

| Tab | What it shows |
| :--- | :--- |
| **Dashboard** | the window's tokens, sessions and calls, the change against the previous window of the same length, a stacked chart of the window itself (hourly for a day, daily beyond), top models, top skills, tokens per call per tracker, and the last calls |
| **Tools** | one row per tool, with the calls each tracker made, ok / fail, average duration and last use |
| **Skills** | the same shape for skills — the one place a skill's use in CodeBuddy and OpenCode sits on one line |
| **Tokens** | **one row per model**, merged across trackers by name, with a column per tracker; `g` cycles to model × tracker, then one row per tracker |
| **Usage** | the most recent calls from all three in one timeline; identical calls within a minute share a row (`×26`), so the list shows turns rather than rows |
| **Sources** | each tracker's health, share of the window's tokens, index size and 7-day trend; `enter` opens that tracker's own TUI |

```text
 aut · all usage trackers                                       📅 Custom…   Today ▾
 Dashboard  Tools  Skills  Tokens  Usage  Sources
 5 models · 0 skills in this window · last call 8m ago
 ╭────────────────────────────────────────────────────────────────────────────────────────────────╮
 │ Window                                                                                         │
 │ 144.19M tokens   ↑330% vs 33.51M   ·   122 sessions · 5,377 calls · 1 active day               │
 │ CodeBuddy 50.73M 35%   OpenCode 12.29M  9%   Qoder CN 81.17M 56%                               │
 ╰────────────────────────────────────────────────────────────────────────────────────────────────╯
 ╭────────────────────────────────────────────────────────────────────────────────────────────────╮
 │ tokens per hour  ·  Today  ·  peak 50.46M at 11                                                │
 │ 50.5M ┤           █                                                                            │
 │       │           █ █                                                                          │
 │ 25.2M ┤           █ █                                                                          │
 │       │          ████                                                                          │
 │     0 ┤█         █████                                                                         │
 │       └───────────────                                                                         │
 │          02 05 08 11 14                                                                        │
 ╰────────────────────────────────────────────────────────────────────────────────────────────────╯
 ╭──────────────────────────────────────────────╮ ╭───────────────────────────────────────────────╮
 │ top models · 144.19M                         │ │ top skills · 0 calls                          │
 │  dfmodel                 81.17M ██████ 56%   │ │   none in this window · d widens it           │
 │  deepseek-v4.1-flash     50.70M ████░░ 35%   │ │                                               │
 │  minimax-m3.1-flash-fre  11.99M █░░░░░  8%   │ │ recent calls                                  │
 │  deepseek-v4.1-flash-fr    301K █░░░░░  0%   │ │    8m ago  CodeBuddy  deepseek-v    198K      │
 ╰──────────────────────────────────────────────╯ ╰───────────────────────────────────────────────╯
 3 of 3 indexes · 87.2 MB · synced 0s ago
 tab Next tab  shift+tab Prev tab  q Quit  r Sync now  d Date  ? Help
```

## Keys

The shared keys are the tracker family's, so a habit learned in `cbut` works here.

| Key | What it does |
| :--- | :--- |
| `tab` / `shift+tab` | next / previous tab |
| `1`–`6` | jump to a tab directly |
| `s` | cycle the sort order — the caption above the table names it (`sort: total ▼ (s)`) |
| `/` | filter rows ( `esc` clears) |
| `d` | date range — presets or the custom calendar picker |
| `enter` | open the selected row's detail (the table tabs; on Sources it hands the terminal to that tracker) |
| `g` | Tokens: by model → model × tracker → tracker |
| `r` | sync the three trackers now — their own `sync`, in the background |
| `?` `q` | help / quit |

The footer is the key list, and it is per-tab: `s` is absent on Sources, `g` appears only on Tokens, `/` only where there is a table. A key that cannot do anything on the current tab is neither shown nor listened for, so the footer never advertises a key that would answer "nothing here".

Every tab remembers its own window, as the trackers do: Dashboard, Tokens and Usage open on today, Tools on the week, Skills on the month (skills are rare enough that a week is often one call each).

The screen is laid out like the three trackers: the state line (rows, sort, grouping, totals) sits **above** the table, the bottom line is provenance — how many indexes were read, how big they are, when they were last synced — and the footer lists the keys.

`r` runs the three syncs behind the board instead of handing the terminal over: the status line names the tracker being synced (`syncing CodeBuddy 1/3`), `r` leaves the footer while it runs, and the tab is re-read once at the end. The Dashboard is a read-only summary — it has no selection and no `enter`, because every number on it is one keystroke away on its own tab.

## Reading the numbers

- **Tokens are the unit.** No credits, no dollars: the three trackers report credits, credits and dollars respectively, so one money column would present three units as one.
- **A missing index is not a zero.** A tracker that is not installed, not synced or built by an older schema is skipped in the merges and reported on the Sources tab — never counted as "used nothing".
- **ok / fail / pending** come from the status the hosts actually write: `completed` is ok; `error`, `incomplete` and `cancelled` are failures; `running`, `backgrounded` and no status at all are pending, which is not a failure.
- **One model is one row.** The same model name through three trackers is one total with three columns, because "what did this model cost me" has one answer. Names merge case-insensitively; `g` still shows the per-tracker rows when that is what you want.
- **Tool names merge case-insensitively** (`Read` in one tracker, `read` in another, one row). `Bash` and `shell` stay apart: whether they are the same tool is a guess this app does not make.
- **One chart, one scale.** Every series in a chart shares a y-axis, so a 12M tracker and an 81M tracker do not draw the same bar. The percentage beside a bar is its share of the window; the bar itself is scaled to the largest row.
- **The window is the chart.** `Today` draws today's hours, `7d` draws seven days — never a week hidden inside a day.
- **Two numbers on one screen count the same calls.** The Sources tab takes its window from the tab, not from "the last N×24 hours", so it agrees with the KPI strip above it.
- **There is no `a` key.** The trackers use it for "installed but never used", which has no cross-tool meaning here.

## What it does not do

- **It does not collect anything.** No log parsing, no network, no second copy of the truth: it reads the `usage.db` each tracker already built.
- **It does not write.** Every connection is `mode=ro`; `r` and `enter` write only through the tracker's own commands.
- **It does not replace the trackers.** The Sources tab is one key from their full eight-tab view.

## Adding a fourth tracker

One entry in `SOURCES` in [scripts/aut_sources.py](scripts/aut_sources.py): a key, a label, the database name, the binary, and the SQL expressions that normalise its token and project columns. Every tab picks it up.

## Requirements

- Python 3.11+ (the board's only dependency is Textual; `aut json` and `aut sync` are pure standard library).
- At least one of `cbut`, `ocut`, `qcut` installed and synced.
