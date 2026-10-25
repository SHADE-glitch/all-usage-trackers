# MAINTENANCE.zh-CN.md — all-usage-trackers

流程文件。这是一张**路由**：长文维护资料在 [`docs/maintenance/`](docs/maintenance/tracker-contracts.md)
（已提交），本仓的工作规则在 [`AGENTS.md`](AGENTS.md)。不要把它们的表格抄到这里——抄出来的第二份
就是会腐烂的那一份。

唯一真正要紧的维护风险：**三家追踪器里有一家改了它的索引**。`aut` 自己没有 schema——它通过
`scripts/aut_sources.py` 里的六条 SQL 表达式读各家已经建好的 `usage.db`。表名或列名被改会抛错，
表现为那一家出现 `error` 徽章，是响的。安静的那种是「列还在、但不再被写入」：表达式照常工作，
数字变成 0，而面板看起来一切正常。每个适配器假定的契约——表、列、总量定义、成本单位、项目列——
写在 [`docs/maintenance/tracker-contracts.md`](docs/maintenance/tracker-contracts.md)。

## 验证层级

- **L0** — `python3 -m unittest discover -s scripts/tests`（临时 `HOME` 里现造夹具库，不碰本机状态）。
- **L1** — 一个一次性 `HOME`，里面放三家索引的副本，让真实聚合跑起来而不碰线上库。
- **L2** — 真实的 `~/.local/share/*/usage.db`；需要主人点头。

## CI

`.github/workflows/ci.yml` 在 Python 3.11 / 3.14 矩阵上跑 L0。

## 一次改动必须回答的四个问题

1. **它动的是哪一家的契约？** 一家都不动，就属于 `aut_model.py` 或界面，不属于适配器。
2. **usage total 还是那家自己的吗？** 三个总量是逐源复述的（见契约文件）；悄悄换成 provider 的
   API total，正是 0.5.0 记录过的那次失败。
3. **缺索引仍然读成「缺」而不是 0 吗？** `—` 和 `0` 是两个不同的答案。
4. **底栏变了吗？** 画出来的键必须能动作，能动作的键必须被画出来；`check_action` 是同时决定
   这两件事的唯一一处。

## 改完之后

- 不是纯 `feat` 的改动，在 [`CHANGELOG.md`](CHANGELOG.md) 里加一条 `D-###`。
- 重跑 L0。没有针对你改的那件事的夹具，全绿的 L0 什么也没证明。
