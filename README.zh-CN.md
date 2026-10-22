<p align="right"><a href="README.md">English</a> | <a href="README.zh-CN.md"><b>简体中文</b></a></p>

# 🧮 用量追踪总览（`aut`）

![Python](https://img.shields.io/badge/python-3.11%2B-blue?logo=python&logoColor=white)
![SQLite](https://img.shields.io/badge/storage-SQLite-003B57?logo=sqlite&logoColor=white)
![Textual](https://img.shields.io/badge/TUI-Textual-ff69b4?logo=terminal&logoColor=white)
![License: MIT](https://img.shields.io/badge/license-MIT-green)
![Platform: Linux](https://img.shields.io/badge/platform-Linux-lightgrey?logo=linux&logoColor=black)
[![Repository](https://img.shields.io/badge/repository-GitHub-black?logo=github)](https://github.com/SHADE-glitch/all-usage-trackers)

**它是什么** —— 一个只读的总览面板，把你在用的三个追踪器并排放在一起：`cbut`（CodeBuddy）、`ocut`（OpenCode）、`qcut`（Qoder CN）。选中哪一个，它就把终端交给那一个自己的 TUI；你按 `q` 退出，就回到总览。

**它解决什么** —— 三个追踪器就是三个 TUI、三个数据库，想比较就得开三个窗口、记三个数字。`aut` 给一个窗口做比较，一个按键进细节。

**怎么跑** —— `./install.sh`，然后 `aut`。

**看哪里** —— 不变量与目录结构见 [AGENTS.md](AGENTS.md)。

---

## 面板

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

**以 token 为单位。** 面板不显示积分或金额：三家报的东西本来就不一样（CodeBuddy
和 Qoder 报 credit，OpenCode 报美元成本），合成一列等于把三种单位假装成一种。
只报了 credit、没报 token 的源显示 `—`，绝不显示 `0`。

## 按键

| 按键 | 作用 |
| :--- | :--- |
| `↑` `↓` / `j` `k` | 在三个源之间移动 |
| `enter` | 打开那家的 TUI —— 在里面按 `q` 就回到这里 |
| `1` `2` `3` | 直接打开第一 / 第二 / 第三个源 |
| `s` | 同步选中的追踪器（在终端里跑它自己的 `sync`） |
| `S` | 依次同步全部三个 |
| `w` | 切换时间窗：`1d → 7d → 30d → all` |
| `r` | 重新读取三个数据库 |
| `?` | 帮助 |
| `q` | 退出 |

`aut cbut`、`aut ocut`、`aut qcut` 跳过面板直接进入对应追踪器，总览不会挡在你和
已经用惯的 TUI 之间。

## 它不做什么

- **不采集。** 不解析日志、不联网、不造第二份真相：只读三家已经建好的 `usage.db`。
- **不写库。** 所有连接都是 `mode=ro`，所以它既弄不坏索引，也不会在某家 sync 时
  抢写锁。写操作只有 `s` / `S`，而且是交给那家自己的 `sync` 去写。
- **不替代追踪器。** 想看完整的八页视图，直接开那一家。

## 加第四个追踪器

在 [scripts/aut_sources.py](scripts/aut_sources.py) 的 `SOURCES` 里加一项：key、
label、数据库目录名、可执行文件名，以及一条把它的 token 列归一化的 SQL 表达式。
面板自动认得它，别处不用改。

## 依赖

- Python 3.11+（面板唯一依赖是 Textual；`aut json` 和 `aut sync` 只用标准库）。
- 至少装好并同步过一个追踪器。缺失、没同步或 schema 过旧的源会在自己那一行显示
  `missing` / `error`，另外两家照常工作。
