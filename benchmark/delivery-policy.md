# 交付契约扣分规则

本规则适用于 T01–T10。交付物不符合任务规定时，在功能、PPA 和时间分之和上额外扣分，**每题最多扣 10 分**，扣后总分最低为 0。

| 交付情况 | 额外扣分 |
| --- | ---: |
| 交付符合契约 | 0 分 |
| 单项交付物缺失，或一处由候选自身造成的运行错误 | 5 分 |
| 缺少两项及以上交付物 | 10 分 |
| 两个不同的交付错误，包括缺件与另一处独立错误同时存在 | 10 分 |

交付检查须列出全部缺件，并记录不同错误的根因和归因依据。同一根因导致的重复失败及其连带现象只计一次；缺少整个目录时，不把其下随之缺失的文件重复计为缺件。工具缺失、评测器缺陷等基础设施故障不扣分；归因不明时保留独立验收分量，交付扣分和总分暂不定案。

交付清单为任务约定的 RTL 与 `rtl/files.f`、`verif/`、可执行 `run.sh`、真实生成的 `results.json` 和 `README.md`。清单是否齐全以最终提交为准；自检复跑仍须清除旧构建产物和旧结果，验证提交能够重新生成有效结果。无论候选是否主动宣布完成，都检查最终提交。

T09 同样使用通用自检交付契约。ELF 装载、执行状态判定及逐指令记录由评测方独立完成。

功能、PPA、时间仍独立计算；交付扣分不抹掉这些分量。单纯的 RTL 功能不通过或物理实现失败按对应分量的规则计分，不额外算作交付错误。交付错误已扣满 10 分后不再叠加。

`显示总分 = max(0, 功能分 + PPA分 + 时间分 − 交付扣分)`。

现行评分入口为 `evaluator/score_with_power_budget.py`，交付检查报告通过 `delivery_assessment` 输入评分器；`evaluator/score_run.py` 保留历史计算规则，用于复现旧结果。采用新规则须在报告中记录 `delivery_penalty_policy=delivery-contract-cap10-v1`，不自动改写历史成绩。

# Delivery-contract deductions

This policy applies to T01–T10. Deduct **5 points** for one missing deliverable or one candidate-caused execution error; deduct **10 points** for two or more missing deliverables, or two distinct delivery errors, including a missing item plus an independent error. Deductions are capped at **10 points per task**. The display total is `max(0, functionality + PPA + time − delivery deduction)`; earned component scores remain unchanged.

Inventory all required deliverables in the final submission, whether or not the candidate declared completion. Count repeated failures and downstream symptoms of one root cause once. An absent directory and its absent children do not count separately. Infrastructure faults incur no deduction; unresolved attribution leaves the deduction and display total pending. Functional or physical failures alone affect their own components and do not automatically count as delivery errors. Clean replay must regenerate valid results rather than reuse existing build products or results.

T09 uses the same generic self-test contract. The evaluator independently loads ELF programs, determines execution status and captures instruction traces.

Use `evaluator/score_with_power_budget.py` with the checker's `delivery_assessment`, and record `delivery_penalty_policy=delivery-contract-cap10-v1`. Historical scores are preserved; `evaluator/score_run.py` retains their original calculation.
