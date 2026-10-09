# T09 · RV32I 五级流水线 CPU

[English](README.en.md)

任务元数据见 `task.yaml`。

本题已于 2026-10-09 完成任务级冻结：完整功能、独立 22 项周期检查、
21 个缺陷变异体及 11/29/47 三种子 ASAP7 WC 1 GHz PPA 均通过。
采用 `t09_group_cycles10_v1`：原有功能组总计 40 分，周期组 22/22、
11–21/22、0–10/22 分别得 10、5、0 分；总计功能 /50 + PPA /50 + 时间 /5。
参考 RTL 与原始资格证据可公开审计，但不提供给做题 Agent。

- [冻结任务卡](task.md)
- [CPU 验收计划](acceptance.md)
- 公开接口 testbench：`public/tb.sv`
- 公开 ELF 总线平台：`public/tb_cpu_elf.sv`
- [跨题共享规则](../../README.md#共享任务规则)与[通用验收规则](../../README.md#通用验收规则)
