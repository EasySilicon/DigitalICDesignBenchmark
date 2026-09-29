# 任务包目录

[English](README.en.md)

本目录属于 **Digital IC Design Benchmark for Agents**。

每道题以 `T01` 至 `T10` 为独立任务包。任务专属的公开制品应放在相应目录内，公共的运行工具、工艺库和跨题规则继续留在仓库共享位置。

每个任务包的 `task.md` 是冻结题面，`acceptance.md` 是任务专属验收计划；跨题[任务规则](../README.md#共享任务规则)和[通用验收规则](../README.md#通用验收规则)统一写在 benchmark README 中。公开 testbench 和其他公开制品均从各任务包的 `public/` 目录读取；使用 `public_check.py` 或 `prepare_trial.py` 即可取得相同的任务材料。

T10 的公开 Python 数值 oracle 位于 `T10/public/matmul_oracle.py`；它定义数值规范，不是 RTL 实现。
