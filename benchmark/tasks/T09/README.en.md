# T09 · RV32I five-stage pipelined CPU

[中文](README.md)

Task metadata is in `task.yaml`.

Task-level qualification was frozen on 2026-10-09: complete functionality,
22 separate cycle checks, 21 defect mutants and ASAP7 WC 1 GHz PPA seeds
11/29/47 all pass. `t09_group_cycles10_v1` assigns 40 normalized points to
legacy groups and 10/5/0 to the cycle group for 22/22, 11–21/22 or 0–10/22.
The score remains function /50 + PPA /50 + time /5. Published reference RTL
and evaluator evidence are host-only, never candidate inputs.

- [Frozen task card](task.md)
- [Acceptance plan](acceptance.md)
- Public smoke testbench: `public/tb.sv`
- [Suite-wide task rules](../../README.md#共享任务规则) and [acceptance rules](../../README.md#通用验收规则)
