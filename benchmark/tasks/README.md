# Task packages / 任务包目录

## English

The active v0.3 suite contains T01 through T10. Task-specific public artifacts belong in their respective packages; shared tools, technology files, and suite-wide rules stay in shared locations.

`task.md` is the frozen task specification and `acceptance.md` is the task-specific acceptance plan. The [suite-wide task rules](../README.en.md#tasks) and [acceptance rules](../README.en.md#acceptance) are in the benchmark README. Public testbenches and other public artifacts are read from each package's `public/` directory; `public_check.py` and `prepare_trial.py` expose the same material.

T10's public numerical oracle is `T10/public/matmul_oracle.py`. It defines the numerical contract and is not an RTL implementation.

## 中文

本目录属于 **Digital IC Design Benchmark for Agents**。

正式套件由 T01 至 T10 组成。任务专属的公开制品应放在相应目录内，公共的运行工具、工艺库和跨题规则继续留在仓库共享位置。

每个任务包的 `task.md` 是冻结题面，`acceptance.md` 是任务专属验收计划；跨题[任务规则](../README.md#共享任务规则)和[通用验收规则](../README.md#通用验收规则)统一写在 benchmark README 中。公开 testbench 和其他公开制品均从各任务包的 `public/` 目录读取；使用 `public_check.py` 或 `prepare_trial.py` 即可取得相同的任务材料。

T10 的公开 Python 数值 oracle 位于 `T10/public/matmul_oracle.py`；它定义数值规范，不是 RTL 实现。
