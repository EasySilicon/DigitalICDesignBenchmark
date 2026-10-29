# Model result archive

This directory contains nine models' complete T01–T10 historical pilot scores. Each `summary.json` records component scores, fixed weights, delivery deductions, and eligibility metadata. `null` means unresolved; zero means an adjudicated zero. All 90 published results are resolved.

Scoring: functionality /50, PPA /50, time /5. Weights: T01/T02 3% each; T03–T05 6% each; T06/T07 10% each; T08 11%; T09 20%; T10 25%.

| Model | Current summary | Weighted display score /105 |
|---|---|---:|
| gpt-6-astra | [summary.json](gpt-6-astra/summary.json) | 76.023886 |
| gpt-6.1-sol | [summary.json](gpt-6.1-sol/summary.json) | 74.765969 |
| kimi-k3.1-pro | [summary.json](kimi-k3.1-pro/summary.json) | 74.576680 |
| gpt-6-sol | [summary.json](gpt-6-sol/summary.json) | 73.041966 |
| gpt-5.6-sol | [summary.json](gpt-5.6-sol/summary.json) | 72.752642 |
| glm-5.3 | [summary.json](glm-5.3/summary.json) | 66.878201 |
| kimi-k3 | [summary.json](kimi-k3/summary.json) | 55.808286 |
| deepseek-flash | [summary.json](deepseek-flash/summary.json) | 52.449760 |
| glm-5.3-flash | [summary.json](glm-5.3-flash/summary.json) | 45.554440 |

## Records and verification

- [Full scores and per-model loss analysis](model-score-comparison.md).
- [PPA formula audit](ppa-formula-audit-20261021.json): the historical audit snapshot from 2026-10-21. The GLM-5.3-Flash ZCode run is evidenced by the retained run-manifest hash and per-task report hashes in its [summary](glm-5.3-flash/summary.json). Kimi T07 is published with the corrected setup penalty in [T07.json](kimi-k3/T07.json).
- GPT-5.6-Sol was evaluated with the current scoring rules; its per-task records are bound to retained report and score-input hashes in [summary.json](gpt-5.6-sol/summary.json).
- Kimi K3.1 Pro(max) passed all ten tasks functionally. Its T10 PPA and time scores are adjudicated zeros because no layout seed completed routing and activity-based power measurement within its allowed physical-runtime limit; see its [summary](kimi-k3.1-pro/summary.json).
- The earlier [Kimi K3.1 Pro(high) trial](archive/kimi-k3.1-pro-high-20261024/summary.json) is retained separately; its T10 score reflects the current functional allocation and corrected structure check.
- Verified T10 reports: [Astra](gpt-6-astra/T10-ppa40.json), [GPT-6.1-Sol](gpt-6.1-sol/T10-ppa40.json), and [GPT-6-Sol](gpt-6-sol/T10-ppa40.json).
- Large RTL/EDA artifacts remain in the retained archives; published reports identify them by original path and hash.

## Comparability

The reference uses internal hard macros while candidates use flat PEs; a same-flow comparison remains pending. Kimi T08 used a cumulative 150-minute development budget. GPT-6-Sol T10 retains 50 functional points and zero PPA/time under its historical compilation-termination adjudication.

Task labels follow `ic-delivery-rtl-v0.3`; raw archives retain legacy labels, with `legacy_task_id` providing the mapping. Current scoring rules and measurement scope are documented in the [root README](../README.en.md#acceptance-and-scoring).
