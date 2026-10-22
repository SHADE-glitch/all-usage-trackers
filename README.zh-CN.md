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
| **Dashboard** | 当前窗口的 token、会话、调用、活跃天数，以及与上一个等长窗口的变化；按源的每日 token；模型与 skill 排行 |
| **Tools** | 一行一个工具，三家各自的调用数、ok / fail、平均耗时、最后使用 |
| **Skills** | 同样形状，一行一个 skill —— 同一个 skill 在 CodeBuddy 和 OpenCode 的使用第一次并排在一行 |
| **Tokens** | 一行一个模型：input、output、cache read、cache write、total、请求数；`g` 折成一行一个来源 |
| **Usage** | 三家最近的调用合并成一条时间线 |
| **Sources** | 每家的健康度、索引大小、7 天趋势；`enter` 进入那家的 TUI |

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

## 按键

共用键沿用三家的习惯，在 `cbut` 里养成的肌肉记忆在这里一样成立。

| 按键 | 作用 |
| :--- | :--- |
| `tab` / `shift+tab` | 下一个 / 上一个 tab |
| `1`–`6` | 直接跳到某个 tab |
| `s` | 循环排序 |
| `/` | 过滤行（`esc` 清除） |
| `d` | 时间范围 —— 预设或完整日历选择器 |
| `enter` | 打开选中行的详情 |
| `g` | Tokens：按模型 ↔ 按来源 切换分组 |
| `r` | 立即同步三家（跑它们自己的 `sync`） |
| `?` `q` | 帮助 / 退出 |

每个 tab 各记各的时间窗，和三家的行为一致：Dashboard / Tokens / Usage 默认今天，Tools 默认一周，Skills 默认一个月（skill 很少，一周往往只有一两次调用）。

## 怎么读这些数字

- **以 token 为单位。** 不显示 credit、不显示金额：三家分别报 credit、credit、美元，合成一列等于把三种单位假装成一种。
- **缺索引不等于零。** 没装、没同步、schema 过旧的源在合并里直接跳过，并在 Sources tab 里报出来 —— 绝不记成"用了 0"。
- **ok / fail / pending** 来自三家真实写入的状态：`completed` 是 ok；`error`、`incomplete`、`cancelled` 是失败；`running`、`backgrounded` 和没有状态都算 pending，pending 不是失败。
- **工具名按大小写不敏感合并**（一家叫 `Read`、一家叫 `read`，合成一行）。`Bash` 和 `shell` 保持分开：它们是不是同一个工具，这个应用不做这种猜测。
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
