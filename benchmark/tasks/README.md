# 任务包目录

本目录属于 **Digital IC Design Benchmark for Agents**。

每道题以 `T01` 至 `T10` 为独立任务包。任务专属的公开制品应放在相应目录内，公共的运行工具、工艺库和跨题规则继续留在仓库共享位置。

每个任务包的 `task.md` 是冻结题面，`acceptance.md` 是任务专属验收计划；根级 [tasks.md](../tasks.md) 和 [acceptance.md](../acceptance.md) 仅保留共享规则和兼容索引。T01–T09 的公开 testbench 已迁入任务包，原 `evaluator/public/` 位置保留兼容入口，因此既有的 `public_check.py`、`prepare_trial.py` 和外部自动化无需改动。

T10 的题面、验收计划和公开 Python 数值 oracle 已位于任务包；正在迭代的公开 testbench 和参考 RTL 暂保留在各自现有位置，待接口冻结后再迁移。
