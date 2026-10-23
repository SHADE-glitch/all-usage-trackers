<p align="right"><a href="README.md">English</a> | <a href="README.zh-CN.md"><b>简体中文</b></a></p>

# 🧮 用量追踪总览（`aut`）

![Python](https://img.shields.io/badge/python-3.11%2B-blue?logo=python&logoColor=white)
![SQLite](https://img.shields.io/badge/storage-SQLite-003B57?logo=sqlite&logoColor=white)
![Textual](https://img.shields.io/badge/TUI-Textual-ff69b4?logo=terminal&logoColor=white)
![License: MIT](https://img.shields.io/badge/license-MIT-green)
![Platform: Linux](https://img.shields.io/badge/platform-Linux-lightgrey?logo=linux&logoColor=black)
[![Repository](https://img.shields.io/badge/repository-GitHub-black?logo=github)](https://github.com/SHADE-glitch/all-usage-trackers)

**它是什么** —— 六个 tab 的总览面板，架在你已经在用的三个追踪器之上：`cbut`（CodeBuddy）、`ocut`（OpenCode）、`qcut`（Qoder CN）。它把三家的数字**跨工具合并**，同时在你想看完整视图时，仍然把终端交给那一家自己的 TUI。

**它解决什么** —— 每个追踪器回答的是"我在这一个工具里怎么用的"。没有一个回答"同一个 skill 在三家各用了多少次"、"这周哪个模型最费"、"这周比上周是涨是跌"。`aut` 就是这三个问题。

**怎么跑** —— `./install.sh`，然后 `aut`。

**看哪里** —— 不变量与目录结构见 [AGENTS.md](AGENTS.md)。

---

## 六个 tab

| Tab | 显示什么 |
| :--- | :--- |
| **Dashboard** | 当前窗口的 usage total、会话、调用，与上一个等长窗口的变化，以及模型与 skill 两张排行卡片（随内容长高，并铺满窗格剩余高度；超出后窗格滚动）。模型行还带出处：这个合并数字来自哪几家 |
| **Tools** | 一行一个工具，三家各自的调用数、ok / fail、平均耗时、最后使用 |
| **Skills** | 同样形状，一行一个 skill —— 同一个 skill 在 CodeBuddy 和 OpenCode 的使用第一次并排在一行 |
| **Tokens** | **一行一个模型**，按模型名跨三家合并，每家一列；`g` 依次切到「模型 × 来源」（usage total 在前，然后是构成它的输入 / 输出 / 缓存）和「一行一个来源」。同一个模型的两种写法（点号 / 连字符、免费通道后缀、Qoder 的内部代号）合并成一行；详情屏写明被折进来的写法，每条调用仍显示它自己那家记下的名字 |
| **Usage** | 三家最近的调用合并成一条时间线；同一分钟内完全相同的调用合并成一行（`×26`），看到的是轮次而不是刷屏 |
| **Sources** | 每家的健康度、占本窗口 token 的比例、索引大小、7 天趋势；`enter` 进入那家的 TUI |

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

## 按键

共用键沿用三家的习惯，在 `cbut` 里养成的肌肉记忆在这里一样成立。

| 按键 | 作用 |
| :--- | :--- |
| `tab` / `shift+tab` | 下一个 / 上一个 tab |
| `1`–`6` | 直接跳到某个 tab |
| `s` | 循环排序 —— 表格上方的状态行会写明（`sort: usage total ▼ (s)`） |
| `/` | 过滤行（`esc` 清除） |
| `d` | 时间范围 —— 预设或完整日历选择器 |
| `enter` | 打开选中行的详情（表格 tab；在 Sources 上把终端交给那家自己的 TUI） |
| `g` | Tokens：按模型 → 模型 × 来源 → 按来源 |
| `r` | 立即同步三家 —— 跑它们自己的 `sync`，在后台 |
| `?` `q` | 帮助 / 退出 |

底部那一行就是按键清单，而且是按 tab 变的：Sources 没有 `s`，`g` 只出现在 Tokens，`/` 只在有表格的 tab。当前 tab 上做不了事的键既不显示也不响应，所以底栏不会挂一个按下去只会说"这里没有"的键。

每个 tab 各记各的时间窗，和三家的行为一致：Dashboard / Tokens / Usage 默认今天，Tools 默认一周，Skills 默认一个月（skill 很少，一周往往只有一两次调用）。

顶栏就是 cbut 的那一对控件，分工也一样：下拉框报预设名，选 `Custom…` 打开日历；旁边的 📅 按钮报选中的区间。所以自定义窗口时下拉框显示 `Custom…`（它报不出区间），区间在按钮上（`📅 10-01 08:00 → 10-03 18:30 ▾`）。取消选择器会把顶栏退回该 tab 真正的时间窗。

屏幕布局也照三家：**状态行在表格上方**（行数、排序、分组、合计），底部一行是数据来源（读了几份索引、多大、多久前同步），最下面一行是按键提示。

`r` 在板子背后跑三家的 sync，不再把终端交出去：状态行会写正在同步哪一家（`syncing CodeBuddy 1/3`），同步期间 `r` 从底栏消失，结束后只重读当前 tab 一次。Dashboard 是只读摘要 —— 没有选中、也没有 `enter`，因为它上面每个数字在自己的 tab 里都只差一次按键。

## 怎么读这些数字

- **以 token 为单位。** 不显示 credit、不显示金额：三家分别报 credit、credit、美元，合成一列等于把三种单位假装成一种。
- **缺索引不等于零。** 没装、没同步、schema 过旧的源在合并里直接跳过，并在 Sources tab 里报出来 —— 绝不记成"用了 0"。
- **ok / fail / pending** 来自三家真实写入的状态：`completed` 是 ok；`error`、`incomplete`、`cancelled` 是失败；`running`、`backgrounded` 和没有状态都算 pending，pending 不是失败。
- **一个模型就是一行。** 同一个模型名在三家用了，就是一个总数加三列 —— "这个模型花了我多少"只有一个答案。名字按大小写不敏感合并；想看每家分开时按 `g`。
- **工具名按大小写不敏感合并**（一家叫 `Read`、一家叫 `read`，合成一行）。`Bash` 和 `shell` 保持分开：它们是不是同一个工具，这个应用不做这种猜测。
- **一个数字，有名有姓。** 板子上出现的每个 token 数字都是该家自己的 **Usage Total** —— 与各家面板同一定义（cbut：prompt + completion + 缓存命中；ocut：完整 prompt + 输出 + 再加一次命中；qcut：input + output + 缓存读）。各家上报的 API total 不再被任何地方读取；凡是没写明输入/输出/缓存的 token 数，一律是 Usage Total。
- **一根柱子一把尺。** 同一张表里的每根柱子共用一个标尺，12M 的源和 81M 的源不会画出一样高的柱子。柱子旁边的百分比是它占本窗口的比例，柱子本身按最大的那一行缩放。
- **卡片先长高，再滚动。** 列表卡片按内容的行数取高度，而不是截断到固定行数；仪表盘窗格在整屏放不下后开始滚动，没有任何内容会被悄悄裁掉。
- **同一屏上的两个数字数的是同一批调用。** Sources 的窗口取自当前 tab，而不是"最近 N×24 小时"，所以它和上方的 KPI 对得上。
- **没有 `a` 键。** 三家用它表示"装了但没用过"，这在跨工具语境里没有对应含义。

## 它不做什么

- **不采集。** 不解析日志、不联网、不造第二份真相：只读三家已经建好的 `usage.db`。
- **不写库。** 所有连接都是 `mode=ro`；`r` 和 `enter` 只通过那家自己的命令去写。
- **不替代追踪器。** 从 Sources tab 一个键就能进它们的完整八页视图。

## 加第四个追踪器

在 [scripts/aut_sources.py](scripts/aut_sources.py) 的 `SOURCES` 里加一项：key、label、数据库目录名、可执行文件名，以及把它的 token 和 project 列归一化的 SQL 表达式。所有 tab 自动认得它。

## 依赖

- Python 3.11+（面板唯一依赖是 Textual；`aut json` 和 `aut sync` 只用标准库）。
- 至少装好并同步过一个追踪器。
