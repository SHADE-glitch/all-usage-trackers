<p align="right"><a href="README.md"><b>English</b></a> | <a href="README.zh-CN.md">简体中文</a></p>

# 🧮 All Usage Trackers (`aut`)

![Python](https://img.shields.io/badge/python-3.11%2B-blue?logo=python&logoColor=white)
![SQLite](https://img.shields.io/badge/storage-SQLite-003B57?logo=sqlite&logoColor=white)
![Textual](https://img.shields.io/badge/TUI-Textual-ff69b4?logo=terminal&logoColor=white)
![License: MIT](https://img.shields.io/badge/license-MIT-green)
![Platform: Linux](https://img.shields.io/badge/platform-Linux-lightgrey?logo=linux&logoColor=black)
[![Repository](https://img.shields.io/badge/repository-GitHub-black?logo=github)](https://github.com/SHADE-glitch/all-usage-trackers)

**What it is** — one read-only board over the usage trackers you already run: `cbut` (CodeBuddy), `ocut` (OpenCode) and `qcut` (Qoder CN). It shows the three side by side, then hands the terminal to whichever tracker you pick and takes it back when you quit.

**What it solves** — three trackers means three TUIs and three databases, and comparing them meant opening three windows and remembering three numbers. `aut` gives one window for the comparison and a single key to go deep.

**How to run** — `./install.sh`, then `aut`.

**Where to look** — [AGENTS.md](AGENTS.md) for the invariants and the layout.

---

## The board

```text
 aut · all usage trackers     window 7d     trend 7d     refreshed 0s ago

 source     tokens   sessions  trend    last seen  state
 CodeBuddy  815.14M  399       ▅▅▅▆█▇▂  52s ago    ok
 OpenCode   205.40M  603       ▇▅▂▂▂█▂  2h ago     ok
 Qoder CN   352.17M  10        ▁▁▁▁▁█▃  43m ago    ok

╭──────────────────────────────────────────────────────────────────────────╮
│  CodeBuddy · last 7d · 815.14M tokens · 9,913 calls · 399 sessions        │
│                                                                          │
│    models    deepseek-v4.1-flash 624.35M · glm-5.3-flash 84.56M          │
│    projects  ~/work 783.81M · ~/Desktop 30.91M                           │
│    index     ~/.local/share/codebuddy-usage-tracker/usage.db  23.7 MB     │
╰──────────────────────────────────────────────────────────────────────────╯

 enter open · 1 2 3 jump · s sync · S sync all · w window · r refresh · ? help · q quit
```

**Tokens are the unit.** The board does not show credits or dollars: the three
trackers report different things (CodeBuddy and Qoder report credits, OpenCode
reports a dollar cost), so a single money column would be three units pretending
to be one. A source that reported credits but no token shows `—`, never `0`.

## Keys

| Key | What it does |
| :--- | :--- |
| `↑` `↓` / `j` `k` | move between sources |
| `enter` | open that tracker's own TUI — quit it with `q` and you are back here |
| `1` `2` `3` | open the first, second or third source directly |
| `s` | sync the selected tracker (runs its own `sync` in this terminal) |
| `S` | sync all three, one after another |
| `w` | cycle the window: `1d → 7d → 30d → all` |
| `r` | re-read the three databases |
| `?` | help |
| `q` | quit |

`aut cbut`, `aut ocut` and `aut qcut` skip the board and exec that tracker, so
the board never stands between you and a TUI you already know.

## What it does not do

- **It does not collect anything.** No log parsing, no network, no second copy of
  the truth: it reads the `usage.db` each tracker already built.
- **It does not write.** Every connection is `mode=ro`, so the board cannot
  corrupt an index and cannot take a write lock while a tracker is syncing.
  `s` and `S` write, and they do it by running that tracker's own `sync`.
- **It does not replace the trackers.** Open them directly whenever you want the
  full eight-tab view.

## Adding a fourth tracker

One entry in `SOURCES` in [scripts/aut_sources.py](scripts/aut_sources.py) — a
key, a label, the database name, the binary, and one SQL expression that
normalises its token column. The board picks it up; nothing else changes.

## Requirements

- Python 3.11+ (the board's only dependency is Textual; `aut json` and
  `aut sync` are pure standard library).
- At least one of `cbut`, `ocut`, `qcut` installed and synced. A tracker that is
  missing, unsynced or built by an older schema shows up as `missing` / `error`
  in its row — the other two keep working.
