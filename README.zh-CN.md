<p align="right"><a href="README.md">English</a> | <a href="README.zh-CN.md"><b>简体中文</b></a></p>

# 🧮 用量总览（`aut`）

![Python](https://img.shields.io/badge/python-3.11%2B-blue?logo=python&logoColor=white)
![SQLite](https://img.shields.io/badge/storage-SQLite-003B57?logo=sqlite&logoColor=white)
![Textual](https://img.shields.io/badge/TUI-Textual-ff69b4?logo=terminal&logoColor=white)
![License: MIT](https://img.shields.io/badge/license-MIT-green)
![Platform: Linux](https://img.shields.io/badge/platform-Linux-lightgrey?logo=linux&logoColor=black)
[![Repository](https://img.shields.io/badge/repository-GitHub-black?logo=github)](https://github.com/SHADE-glitch/all-usage-trackers)

**是什么** — 一块盖在你已经在跑的三家追踪器之上的六页看板：`cbut`（CodeBuddy）、`ocut`（OpenCode）、`qcut`（Qoder CN）。它把三家的数字跨工具合起来看，想看某一家完整视图时又把终端交还给它。

**解决什么** — 每家追踪器回答的都是「我**这一个**工具用得怎么样」。没有一家回答「我到底在三个工具里都用了哪些 skill」「这周哪个模型最费」「这周比上周是升是降」。`aut` 就是这三个问题。

**怎么跑** — `./install.sh`，然后 `aut`。

**去哪看** — 不变量与目录结构在 [AGENTS.md](AGENTS.md)；每个适配器对三家索引假定了什么，在 [docs/maintenance/tracker-contracts.md](docs/maintenance/tracker-contracts.md)。

---

## ✨ 功能

- **一块看板，三家追踪器。** 六个 tab——Dashboard、Tools、Skills、Tokens、Usage、Sources——读的都是各家已经建好的 SQLite 索引。不解析第二遍，也不写入。
- **跨工具的答案。** 同一个 skill 在 CodeBuddy 与 OpenCode 的用量落在同一行；同一个模型穿过三家是一条总量、每家一列。
- **「token」只有一个定义。** 每个数字都是那家自己的 **Usage Total**，逐源复述，永远不是 provider 的 API total。
- **底栏按页给键。** 只画当前页真能动作的键，也只监听这些键。
- **是交接，不是替代。** 在 Sources 上按 `enter` 会挂起看板、打开那家自己的八页 TUI；在那边按 `q` 回到重新读过数据的看板。

## 📊 六个 tab

| Tab | 显示什么 |
| :--- | :--- |
| **Dashboard** | 本窗口的 usage total、会话数与调用数、与上一个等长窗口的对比、top models 与 top skills 两张随行数增长并撑满面板的卡片（行数放不下时面板滚动），以及窗口说明。模型行带来源标记——这个合并后的数字来自哪家（哪几家） |
| **Tools** | 每个工具一行：各家调用次数、ok / fail、平均耗时、最后使用时间 |
| **Skills** | 与 Tools 同形——这里是唯一能把一个 skill 在 CodeBuddy 与 OpenCode 的用量摆在同一行的地方 |
| **Tokens** | **每个模型一行**，按名字跨家合并，每家一列；`g` 切到 模型 × 追踪器（先 usage total，再它由之构成的 input / output / cache 拆分），再切到每家一行。同一个模型被记成两种拼写——这里带点、那里带连字符、一条免费路由、Qoder 的内部 id——仍然是一行；详情会列出它合并掉的拼写，并把每次调用列在写下它的那家下面 |
| **Usage** | 三家最近的调用合成一条时间线；一分钟内完全相同的调用共用一行（`×26`），所以列表显示的是「轮」而不是「行」 |
| **Sources** | 各家的健康状态、占本窗口 token 的份额、索引大小、7 天趋势；`enter` 打开那家自己的 TUI |

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

## ⌨️ 按键

共用的键就是这套追踪器家族的键，在 `cbut` 里养成的习惯在这里照样能用。

| 键 | 做什么 |
| :--- | :--- |
| `tab` / `shift+tab` | 下一个 / 上一个 tab |
| `1`–`6` | 直接跳到某个 tab |
| `s` | 循环排序——表格上方的说明会写出当前排序（`sort: usage total ▼ (s)`） |
| `/` | 过滤行（`esc` 清除） |
| `d` | 时间范围——预设或自定义日历选择器 |
| `enter` | 打开所选行的详情（表格页；在 Sources 上则是把终端交给那家追踪器） |
| `g` | Tokens：按模型 → 模型 × 追踪器 → 追踪器 |
| `r` | 立刻同步三家——跑的是各家自己的 `sync`，在后台 |
| `?` `q` | 帮助 / 退出 |

底栏就是键表，而且是**按页**的：Sources 上没有 `s`，`g` 只出现在 Tokens，`/` 只出现在有表格的页。当前页上做不了事的键既不画也不监听，所以底栏永远不会给一个按下去只答「这里没有」的键。

每个 tab 记住自己的窗口，与追踪器一致：Dashboard、Tokens、Usage 开在今天，Tools 开在最近一周，Skills 开在最近一月（skill 很稀疏，一周往往一个一次）。

顶栏是 cbut 的那一对，两件事也一样：Select 写着一个预设、在 `Custom…` 上打开日历，旁边的 📅 按钮写着实际选中的区间。所以自定义窗口在 Select 里读作 `Custom…`——它没有预设可写——区间由按钮承担（`📅 10-01 08:00 → 10-03 18:30 ▾`）。取消选择器会把顶栏还原成该 tab 的真实窗口。

屏幕布局与三家追踪器一致：状态行（行数、排序、分组、合计）在表格**上方**，底部一行是出处——读了几份索引、多大、上次同步是什么时候——再下面是键表。

`r` 是在看板背后跑三家同步，而不是把终端交出去：状态行写出正在同步哪一家（`syncing CodeBuddy 1/3`），运行期间 `r` 从底栏消失，结束后整页重读一次。Dashboard 是只读摘要——它没有选中行也没有 `enter`，因为它上面每个数字都在自己那一页上只差一次按键。

## 🔢 怎么读这些数字

- **单位是 token。** 没有 credit，没有美元：三家分别报 credit、credit 和美元，合成一列钱就是把三个单位当成一个。
- **缺索引不是 0。** 没装、没同步、或由旧 schema 建出来的那一家会在合并里被跳过，并在 Sources 上说明——绝不算作「用了零」。
- **缺 token 数字也不是 0。** 只报 credit、不报 token 的来源（qcut 的 BYOK 路由）在 Sources 上显示 `—`。Tokens 与 Dashboard 的合并里，只要一个模型有未上报 token 的调用，它也显示 `—`；看板不会只把已知行加起来，再把结果叫作总量。
- **ok / fail / pending** 来自宿主真实写下的状态：`completed` 是 ok；`error`、`incomplete`、`cancelled` 是失败；`running`、`backgrounded` 以及完全没有状态是 pending，pending 不是失败。
- **一个模型就是一行。** 同一个模型名穿过三家是一条总量加三列，因为「这个模型花了我多少」只有一个答案。名字按大小写不敏感合并；想看逐家行时 `g` 仍然给你。
- **工具名按大小写不敏感合并**（一家写 `Read`、另一家写 `read`，合成一行）。`Bash` 与 `shell` 保持分开：它们是不是同一个工具，这个程序不去猜。
- **一个数，带标签。** 看板打印的每个 token 数字都是那家的 **Usage Total**——各家面板自己用的定义（cbut：prompt + completion + cache hit；ocut：完整 prompt + output + 再加一次命中；qcut：input + output + cache read）。provider 自己的 API total 已经不再读；一个既不说 input、也不说 output 或 cache 的数字，永远是 Usage Total。
- **一根条，一个刻度。** 一张表里所有条共用刻度，所以 12M 的一家与 81M 的一家不会画出同样长的条。条旁边的百分比是它在本窗口的份额。排行表里的条按最大的那一行缩放；Sources 用窗口总量作分母，和它旁边印的百分比是同一个分母。
- **卡片先长，然后面板滚动。** 列表卡片取它行数需要的高度，而不是截断到固定行数；屏幕满了之后是面板滚动，所以没有任何东西被悄悄裁掉。
- **同一屏上的两个数字数的是同一批调用。** Sources 的窗口取自该 tab，而不是「最近 N×24 小时」，所以它与上方的 KPI 条一致。
- **没有 `a` 键。** 追踪器用它表示「装了但没用过」，这件事在跨工具这里没有意义。

## 🚫 它不做什么

- **它不采集任何东西。** 不解析日志、不联网、不存第二份真相：它读的是每家追踪器已经建好的 `usage.db`。
- **它不写入。** 每个连接都是 `mode=ro`；`r` 与 `enter` 只通过那家自己的命令去写。
- **它不替代追踪器。** 从 Sources 到各家完整的八页视图只差一个键。

## 📋 依赖

- Python 3.11+（看板唯一的依赖是 Textual；`aut json` 与 `aut sync` 是纯标准库）。
- `cbut`、`ocut`、`qcut` 里至少装好并同步过一家。

| 组件 | 版本 | 说明 |
| :--- | :--- | :--- |
| Python | 3.11+ | 下限是 `pyproject.toml` 里的 `requires-python`；CI 覆盖 3.11 与 3.14 |
| Textual | 见 `requirements.txt` | 只有看板需要；`json` / `sync` 不需要任何第三方包 |
| Linux | 任意 | 读 `~/.local/share/*/usage.db` |

## 📥 安装

```bash
git clone https://github.com/SHADE-glitch/all-usage-trackers.git
cd all-usage-trackers
./install.sh
```

`install.sh` 可重复执行。它在仓里建 `.venv` 并把 `requirements.txt` 装进去，然后把 `bin/aut` 软链到 `~/.local/bin`，所以在仓里 `git pull` 就等于更新已安装的那份。目标位置是真实文件时它会拒绝覆盖；确实要覆盖就加 `--force`。`AUT_BIN_DIR` 可以换软链目录。最后一步会跑 `aut json --days 7`，并报告是否有来源报错。

如果之后 `aut` 找不到，那是 `~/.local/bin` 不在 `PATH` 里。

## 🧭 使用

```bash
aut                  # 看板
aut cbut             # 直接进某家追踪器自己的 TUI
aut sync             # 跑三家自己的同步命令
aut sync cbut ocut   # ……或者只同步其中几家
aut json --days 7    # 与看板同源的数字，输出 JSON
aut --help
```

`aut json` 的 `--days` 接受 `1` / `7` / `30` / `0`（= 全部），其它值会被拒绝而不是被悄悄改成 7；它是纯标准库，不需要 venv——这正是它能被脚本直接调用的原因。

## 🧯 故障排查

| 症状 | 原因 | 怎么办 |
| :--- | :--- | :--- |
| 某家显示 `no db` | 那家没装，或索引从未建过 | 装上并跑它自己的 `sync`；`aut sync` 会替你跑 |
| 某家显示 `error` | 它的 `usage.db` 与 `aut` 读的列对不上了 | 见[契约文件](docs/maintenance/tracker-contracts.md)；适配器就是 `scripts/aut_sources.py` 里的一条 |
| 某家显示 `idle` | 最近一周没有调用——不是故障 | 不用管 |
| 某个模型显示 `—` | 那家报了调用，但没报 token（例如只记 credit 的 BYOK 路由） | 先去那家自己的面板核对；看板不会把未知写成 0 |
| 某家的备注说索引不记录 usage | 那家写了调用却没写 usage 标记，于是没有任何东西为这个总量背书 | 总量是下限；去那家自己的面板核对 |
| 状态栏没有 `synced` 这一项 | 本次会话还没同步过——看板只是在启动时读了索引 | 按 `r`，或把数字理解为 app 启动那一刻 |
| `aut: command not found` | `~/.local/bin` 不在 `PATH` 里 | 加进 `PATH`，或用 `AUT_BIN_DIR` 重跑 `install.sh` |
| 看板起不来，但 `aut json` 正常 | venv 没了或 Textual 缺失 | 重跑 `./install.sh` |

## 🧪 测试

```bash
python3 -m unittest discover -s scripts/tests
```

套件是纯标准库，在临时 `HOME` 里现造 SQLite 夹具，所以从不打开真实索引。CI 在 Python 3.11 与 3.14 上跑它。没有针对你改的那件事的夹具，全绿什么也证明不了——三级验证见 [MAINTENANCE.zh-CN.md](MAINTENANCE.zh-CN.md)。

## 📁 仓库结构

```text
bin/aut                     入口（bash：venv 没了也能给出有用的错误）
install.sh                  幂等安装：.venv + 软链到 ~/.local/bin
scripts/aut_sources.py      每家一个适配器——唯一知道 schema 的文件
scripts/aut_db.py           只读连接、窗口、格式化
scripts/aut_model.py        每个 tab 都在画的跨工具聚合（纯函数，不 import Textual）
scripts/aut_chart.py        文本条与百分比
scripts/aut_app.py          Textual 看板：tab、绑定、底栏
scripts/aut_picker.py       家族的时间范围选择器
scripts/aut_report.py       JSON 视图
scripts/tests/test_aut.py   套件（临时 HOME 里的夹具库）
docs/maintenance/           三家契约——每个适配器假定了什么
docs/audit/                 按日期归档的只读审计报告（是快照，不是当前状态）
```

## 🧩 加第四个追踪器

在 [scripts/aut_sources.py](scripts/aut_sources.py) 的 `SOURCES` 里加一条：key、label、数据库名、可执行文件名，以及把它的 token 与项目列归一化的 SQL 表达式。每个 tab 都会自动认到它。先要弄清新家的哪些事，契约文件里列了清单。

## 🤝 参与贡献

这是个人工具，但规则是写下来的：不变量（只读连接、每源一个 usage-total 定义、底栏由 `check_action` 决定）在 [AGENTS.md](AGENTS.md)；改前改后都跑套件；凡不是纯功能的改动，在 [CHANGELOG.md](CHANGELOG.md) 里加一条 `D-###`。

## 📄 许可证

MIT —— 见 [LICENSE](LICENSE)。
