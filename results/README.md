# Model result archive

This directory contains eleven models' T01–T10 historical pilot records. Benchmark v1 retains strict `exact-dot-v1` precision. The MMA-inspired relaxed envelope is diagnostic only; relaxed official precision is reserved for benchmark v2.

The [2026-11-06 strict replay](t10-strict-functional-retest-20261106.json) applies the 2,898-case strict corpus, including 64 cancellation cases and 82 additional range probes, with seed 11 and unchanged group weights. Retained 3,154-command traces also contain 256 auxiliary normal cases. Input vectors and pre-existing output-log attestations are verified; no model or PPA rerun was launched. Functional, display and weighted scores are updated; prior PPA/time decisions are retained. Previous records are preserved in the [pre-range snapshot](archive/t10-before-range-expansion-20261106/), and the earlier [64-case correction](t10-functional-results-update-20261105.json) remains historical evidence.

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

The archive manifests are file/hash indices for integrity verification. Updating a summary's current freeze-reference metadata also requires refreshing its current index; historical snapshots and their original hashes are retained.

See [score comparisons](model-score-comparison.md) and [token usage](token-usage.md). The Kimi K3.1 Pro token row uses the max trial, including its T03 rerun, rather than the historical high trial. Opus has all ten task records and retained source evidence. Both Claude T10 unlimited PPA diagnostics were stopped and do not change published PPA/time decisions. Large RTL and physical artifacts remain at their recorded external paths and hashes.

All scores are historical pilot results, not a production signoff or official suite ranking. Earlier timing limits and scoring decisions are not retroactively relabeled.
