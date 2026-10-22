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
| **Dashboard** | tokens, sessions, calls and active days for the window, with the change against the previous window of the same length; per-source tokens per day; top models and top skills |
| **Tools** | one row per tool, with the calls each tracker made, ok / fail, average duration and last use |
| **Skills** | the same shape for skills — the one place a skill's use in CodeBuddy and OpenCode sits on one line |
| **Tokens** | one row per model with input, output, cache read, cache write, total and requests; `g` folds it to one row per source |
| **Usage** | the most recent calls from all three, in one timeline |
| **Sources** | each tracker's health, index size and 7-day trend; `enter` opens that tracker's own TUI |

```text
 aut · all usage trackers                                        📅 Custom…   7 days ▾
 Dashboard  Tools  Skills  Tokens  Usage  Sources
 96.38M tokens   ↑380%   93 sessions   3,641 calls   1 active day
 CodeBuddy 6.80M   OpenCode 8.41M   Qoder CN 81.17M

 tokens per day · 7d · context
   CodeBuddy ▅▅▅▆█▇▂  790.38M
   OpenCode  ▇▅▂▂▂█▂  184.13M
   Qoder CN  ▁▁▁▁▁█▃  357.03M
   all        ▃▃▃▃▄█▃  1331.53M

  top models                       top skills
    dfmodel            81.17M      code-review   18 calls  cbut 12 / ocut 6
    minimax-m3.1-free   8.11M      tdd            9 calls  cbut 9
```

## Keys

The shared keys are the tracker family's, so a habit learned in `cbut` works here.

| Key | What it does |
| :--- | :--- |
| `tab` / `shift+tab` | next / previous tab |
| `1`–`6` | jump to a tab directly |
| `s` | cycle the sort order |
| `/` | filter rows ( `esc` clears) |
| `d` | date range — presets or the custom calendar picker |
| `enter` | open the selected row's detail |
| `g` | Tokens: group by model ↔ by source |
| `r` | sync the three trackers now (runs their own `sync`) |
| `?` `q` | help / quit |

Every tab remembers its own window, as the trackers do: Dashboard, Tokens and Usage open on today, Tools on the week, Skills on the month (skills are rare enough that a week is often one call each).

## Reading the numbers

- **Tokens are the unit.** No credits, no dollars: the three trackers report credits, credits and dollars respectively, so one money column would present three units as one.
- **A missing index is not a zero.** A tracker that is not installed, not synced or built by an older schema is skipped in the merges and reported on the Sources tab — never counted as "used nothing".
- **ok / fail / pending** come from the status the hosts actually write: `completed` is ok; `error`, `incomplete` and `cancelled` are failures; `running`, `backgrounded` and no status at all are pending, which is not a failure.
- **Tool names merge case-insensitively** (`Read` in one tracker, `read` in another, one row). `Bash` and `shell` stay apart: whether they are the same tool is a guess this app does not make.
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
