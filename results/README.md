# Published model results

This directory contains eleven models' T01–T10 historical pilot records. Benchmark v1 retains strict `exact-dot-v1` precision. The MMA-inspired relaxed envelope is diagnostic only; relaxed official precision is reserved for benchmark v2.

The [current T10 acceptance inventory](t10-strict-functional-retest-20261106.json) describes the strict 2,898-case stream plus a reset probe. Scores use the strict numerical profile. Raw grading evidence stays outside this directory.

Scoring: functionality /50, PPA /50, time /5. Weights: T01/T02 3% each; T03–T05 6% each; T06/T07 10% each; T08 11%; T09 20%; T10 25%.

| Model | Current summary | Weighted display score /105 |
|---|---|---:|
| claude-sonnet-5.5 | [summary.json](claude-sonnet-5.5/summary.json) | 80.622595 |
| claude-opus-5.5 | [summary.json](claude-opus-5.5/summary.json) | 78.547838 |
| gpt-6-astra | [summary.json](gpt-6-astra/summary.json) | 76.023886 |
| gpt-6.1-sol | [summary.json](gpt-6.1-sol/summary.json) | 74.765969 |
| kimi-k3.1-pro | [summary.json](kimi-k3.1-pro/summary.json) | 74.576680 |
| gpt-6-sol | [summary.json](gpt-6-sol/summary.json) | 73.041966 |
| gpt-5.6-sol | [summary.json](gpt-5.6-sol/summary.json) | 72.531456 |
| glm-5.3 | [summary.json](glm-5.3/summary.json) | 66.712109 |
| kimi-k3 | [summary.json](kimi-k3/summary.json) | 55.618503 |
| deepseek-flash | [summary.json](deepseek-flash/summary.json) | 52.449760 |
| glm-5.3-flash | [summary.json](glm-5.3-flash/summary.json) | 45.554440 |

Each model directory publishes exactly one `summary.json`, validated by [result.schema.json](result.schema.json). It contains ten task results, optional final group counts and physical metrics, score totals, weights and experiment settings. Missing historical details are represented by `null`. There are no separate `Txx.json` copies.

Final summaries exclude replay history, evaluator repair notes, old scores, original report paths/hashes and archive pointers. Raw grading reports, per-case diagnostics, snapshots and measurement evidence stay outside version control. The explicit allowlist in `.gitignore` controls publication.

See [score comparisons](model-score-comparison.md) and [token usage](token-usage.md). The Kimi K3.1 Pro token row uses the max trial, including its T03 rerun. Earlier result versions are available in Git history.

All scores are historical pilot results, not a production signoff or official suite ranking. Earlier timing limits and scoring decisions are not retroactively relabeled.
