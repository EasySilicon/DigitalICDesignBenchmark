# Published model results

This directory contains fourteen models' T01–T10 historical pilot records. Benchmark v1 retains strict `exact-dot-v1` precision. The MMA-inspired relaxed envelope is diagnostic only; relaxed official precision is reserved for benchmark v2.

The [current T10 acceptance inventory](t10-strict-functional-retest-20261106.json) describes the strict 2,898-case stream plus a reset probe. Scores use the strict numerical profile. The T10 v16 reference measures whole-design area and energy and PE-internal timing, with mapped zero-wire peripheral power. Raw grading evidence stays outside this directory.

Scoring: functionality /50, PPA /50, time /5. Weights: T01/T02 3% each; T03–T05 6% each; T06/T07 10% each; T08 11%; T09 20%; T10 25%.

| Model | Current summary | Weighted display score /105 |
|---|---|---:|
| claude-fable-5.2 | [summary.json](claude-fable-5.2/summary.json) | 88.994861 |
| gpt-6.2-astra | [summary.json](gpt-6.2-astra/summary.json) | 88.808383 |
| gpt-6.2-sol | [summary.json](gpt-6.2-sol/summary.json) | 87.624441 |
| claude-sonnet-5.5 | [summary.json](claude-sonnet-5.5/summary.json) | 80.622595 |
| claude-opus-5.5 | [summary.json](claude-opus-5.5/summary.json) | 78.547838 |
| gpt-6-astra | [summary.json](gpt-6-astra/summary.json) | 75.966070 |
| gpt-6.1-sol | [summary.json](gpt-6.1-sol/summary.json) | 74.723226 |
| kimi-k3.1-pro | [summary.json](kimi-k3.1-pro/summary.json) | 74.576680 |
| gpt-6-sol | [summary.json](gpt-6-sol/summary.json) | 73.041966 |
| gpt-5.6-sol | [summary.json](gpt-5.6-sol/summary.json) | 72.531456 |
| glm-5.3 | [summary.json](glm-5.3/summary.json) | 66.712109 |
| kimi-k3 | [summary.json](kimi-k3/summary.json) | 55.618503 |
| deepseek-flash | [summary.json](deepseek-flash/summary.json) | 52.449760 |
| glm-5.3-flash | [summary.json](glm-5.3-flash/summary.json) | 45.554440 |

Each model directory publishes exactly one `summary.json`, validated by [result.schema.json](result.schema.json). It contains ten final task results, score totals, weights and experiment settings. It also records final group counts, physical metrics and T10 scoring policy and reference IDs where available. Missing historical details are represented by `null`. There are no separate `Txx.json` copies.

Final summaries exclude replay history, evaluator repair notes, old scores, original report paths/hashes and archive pointers. Raw grading reports, per-case diagnostics, snapshots and measurement evidence stay outside version control. The explicit allowlist in `.gitignore` controls publication.

See [score comparisons](model-score-comparison.md) and [token usage](token-usage.md).

## Development time

Each task's development duration is recorded in `tasks[].elapsed_seconds` in its model summary. The totals below sum T01–T10 for the submissions represented by the published scores; they include the agent's own tests and EDA work, and exclude post-submission grading, between-task waits and discarded attempts. A missing duration remains `null`, rather than being treated as zero.

| Model | T01–T10 total | T10 |
|---|---:|---:|
| gpt-6.2-astra | 13 h 44 min 29 s | 3 h 59 min 55 s |
| gpt-6.2-sol | 11 h 13 min 10 s | 3 h 23 min 22 s |
| claude-fable-5.2 | 10 h 55 min 3 s | 2 h 56 min 49 s |
| gpt-6-astra | 5 h 23 min 12 s | 1 h 16 min 12 s |
| gpt-6.1-sol | 5 h 42 min 52 s | 1 h 14 min 31 s |
| gpt-6-sol | 6 h 1 min 23 s | 1 h 14 min 1 s |
| gpt-5.6-sol | 5 h 13 min 3 s | 2 h 5 min 2 s |
| glm-5.3-flash | 14 h 5 min 54 s | 4 h 0 min 0 s |

Fable 5.2 durations include active work across quota resumes and exclude quota waits and the manually requested native compaction.

Totals are calculated from the unrounded per-task seconds, then rounded to the nearest second. Historical budgets and settings differ across trials, so these durations are descriptive rather than a controlled speed comparison.

These historical pilot results are not production signoff or an official suite ranking. T10 v16 uses strict V1 precision.
