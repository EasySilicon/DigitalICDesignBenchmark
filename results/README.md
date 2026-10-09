# Model result archive

Current task labels follow `ic-delivery-rtl-v0.3`: old T02–T08 become T01–T07, old T11 becomes T08, and T09/T10 are unchanged. The CVDP task is no longer part of this suite. Raw evidence and RTL were not renamed; each result carries `legacy_task_id`.

Each model publishes only its final `summary.json`, including per-task scores, totals, weights, penalties and pending status. Models were evaluated with broadly consistent time budgets and Skill settings, and results are summarized under a common scoring policy. Untested components are `null`, never silently zero.

Scoring is function /50 + PPA /50 + time /5 with the existing per-slot weights: T01/T02 0.03; T03–T05 0.06; T06/T07 0.10; T08 0.11; T09 0.20; T10 0.25. Missing scores are omitted, without renormalization.

| Model | Current summary | Available weighted subtotal /105 |
|---|---|---:|
| gpt-6-astra | [summary.json](gpt-6-astra/summary.json) | 65.397494 |
| gpt-6.1-sol | [summary.json](gpt-6.1-sol/summary.json) | 64.249046 |
| gpt-6-sol | [summary.json](gpt-6-sol/summary.json) | 63.779280 |
| kimi-k3 | [summary.json](kimi-k3/summary.json) | 58.935377 |
| deepseek-flash | [summary.json](deepseek-flash/summary.json) | 47.298094 |
| glm-5.3-flash | [summary.json](glm-5.3-flash/summary.json) | 41.410337 |

On 2026-10-09, all six frozen T09 answers were replayed under `t09_group_cycles10_v1`: 40 normalized points across the legacy groups and 10/5/0 for the separate 22-case cycle group. Kimi passed 10/22 (confirmed by an independent repeat); all others passed 22/22. Functional scores are 50 for all three GPTs, 40 for Kimi, 44.933333 for DeepSeek and 22 for GLM; GLM's preserved 5-point delivery penalty makes its display score 17. Compatible GPT PPA evidence was rescored against the new reference without rerunning physical EDA. Elapsed times and delivery deductions were unchanged. Final published scores are in `summary.json`. Other tasks were not regraded.

T08 is complete for Kimi: function 50, PPA 33.787798, time 0.508893, display 84.296691. GLM retains the independent 44/50 boundary replay; its PPA/time are 0 under the full-functional gate, with no PPA EDA run. Other models have no current frozen-MAC result. The three GPT models retain pending T10 PPA/time; candidate functional failures and adjudicated tool/resource failures remain actual zeros.

Full comparison: [model-score-comparison.md](model-score-comparison.md).

T08/T09 task-level freeze (2026-10-09): [T08 receipt](../benchmark/tasks/T08/FREEZE.json), [T09 receipt](../benchmark/tasks/T09/FREEZE.json). Run `python3 benchmark/freeze_tasks.py` from the repository root to verify specification, RTL, judge, scoring, baseline and portable evidence hashes. All six T09 archives have been regraded; untested T08 models remain null. Host-only receipts are excluded from candidate packages. T10 PPA and the suite-wide tool-image/release gates remain pending.
