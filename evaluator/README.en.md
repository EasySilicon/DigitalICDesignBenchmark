# Public executable examples for independent port-level checking

[中文](README.md)

## T08 SRAM physical qualification

Run `PYTHONPATH=evaluator python3 evaluator/run_t08_sram_ppa.py /path/to/reference --orfs-root /path/to/ORFS --output-dir /path/to/fresh-evidence`
in a memory-bounded process group. Stages are model self-test, automatic memory
mapping, 111 functional and 270 concurrency runs, then seed11 layout and checked
gate-level power including macro Liberty. Optimization defaults to one seed.
Only after setup/hold/DRC pass, use `--qualify-from /path/to/seed11/aggregate.json`
to reuse seed11 and add 29/47. The original RTL and FIFO
capacities are unchanged. All three clocks remain independent at 1 GHz.
WC standard-cell timing and TT SRAM timing are explicitly mixed-corner research
models, not silicon signoff. Full macro area, per-instance active power and placed
input connectivity are audited. DRC covers routing/pin access, not macro internal
DRC/LVS. Freeze requires three passing setup/hold/DRC seeds and fresh replay.
Each physical seed waits for at least 50 GiB available host memory. `state.json`
records progress/errors without changing historical scores. See the
[author guide](../benchmark/tasks/T08/AUTHOR_GUIDE.md) for policy and limitations.

## T08 checker qualification

Run `python3 -m evaluator.t08_check /path/to/submission --output /tmp/t08.json`
for 37 case entries at three seeds, with functional maximum 50. The three-seed
1 GHz SRAM physical reference is frozen. Judge revision `3.1-boundary-crosses` separately edits VID values,
valid bits, untagged and priority flags after the inherited raw-decoder first byte
but before header classification, in both directions, then checks the next frame.
The four snapshot points remain equally divided across six case entries.

```sh
python3 -m evaluator.t08_mutation_check --baseline /path/to/correct/submission --output-dir /tmp/t08-qualification --jobs 3
python3 -m unittest evaluator.test_t08_mutation_check benchmark.test_t08_spec benchmark.test_prepare_trial
```

Qualification first requires a fully passing baseline, then checks fourteen
temporary fault variants. Compilation failure, a missing mutation anchor or a
missed designated witness seed is not successful detection. No corrected RTL is
bundled; anchors target the qualified pilot streaming parser and must be explicitly
adapted for another structure. These host-side files are not candidate inputs.
Finite mutations are not proof against every possible RTL error. Existing frozen
trials retain their original judges and reports.

`public_check.py` reads only a submission's `rtl/files.f` and RTL sources, then compiles the fixed task-specific testbench. It does not run the submission's `run.sh`, `verif/`, or `results.json`.

```bash

python3 evaluator/public_check.py T01 /path/to/submission --seed 1234
python3 evaluator/public_check.py T02 /path/to/submission --width 32 --depth 16
python3 evaluator/public_check.py T03 /path/to/submission
python3 evaluator/public_check.py T04 /path/to/submission --n-inputs 8 --width 32
python3 evaluator/public_check.py T05 /path/to/submission --depth 16 --width 32
python3 evaluator/public_check.py T06 /path/to/submission
python3 evaluator/public_check.py T07 /path/to/submission
python3 evaluator/public_check.py T09 /path/to/submission
```

Compilation and simulation run in an isolated temporary directory. Failures return a nonzero status and a JSON summary. These public tests are smoke examples, not the formal scoring suite. T10's public material includes the task-local numerical oracle at `benchmark/tasks/T10/public/matmul_oracle.py`; it specifies numeric decoding, MX scales, and output tolerance without supplying RTL or hidden vectors.

`cpu_elf_check.py` loads an RV32 ELF under the task-card memory map and checks the fixed CPU interface. The 45 public ACT4 ELF artifacts under `act4_elfs/` can be checked with `verify_act4_artifacts.py` and run with `check_act4_sail.py` using a locked Sail setup.

`delivery_check.py` validates the submission layout and self-checking entry point. A passing submission test is evidence of delivery quality only: independent evaluator tests decide DUT correctness.

The default raw `F=60` and `P=15` acceptance weights preserve the
relative importance of functional groups and are normalized by `50/75` to a
50-point functional score. PPA contributes 50 points and completion time 5,
for a maximum display score of 105. The suite display score uses fixed,

T02--T04, 0.10 each for T05/T06, 0.11 for T07, 0.20 for T09, and 0.25 for T10.
Missing components are omitted without rescaling the remaining weights. A task must earn the full 50 functional
points and pass the PPA provenance gates before PPA or time can score. Each
distinct candidate-caused fatal handoff error deducts 5 display points; repeated
runs exposing the same root cause count once, and evaluator/tool infrastructure
failures do not count. This fixed deduction does not erase otherwise valid PPA
or time points.

After routing, a setup miss is represented by the measured critical-path delay and additionally multiplies the score by `(T_target/D_worst)^4`, where `D_worst=T_target+max(0,-setup_slack)` uses the worst routed seed. Lower achieved frequency therefore produces a stronger but continuous penalty. Negative hold slack remains added to the effective delay. DRC is a separate physical-validity penalty: any routed seed with a DRC violation halves the final PPA score. A reference baseline must still pass setup, hold, and DRC; PPA is zero only when legal routing, a constrained timing path, or valid activity-based power is unavailable.

`ppa_aggregate.py` is the public three-seed PPA-record aggregator. It verifies that route and power records describe the same routed result, fixed flow parameters, activity annotation, workload identity and hash, and layout seeds `{11,29,47}`. It preserves setup, hold, and DRC measurements for continuous scoring by `score_run.py`. [`benchmark/ppa-baselines.json`](../benchmark/ppa-baselines.json) is the repository's sole authoritative reference baseline; evaluator scripts must not keep duplicate baseline copies.

`t10_structure_check.py` is the public T10 structural acceptance entry point. On a Yosys-elaborated netlist it checks the fixed stream interface, 256 PEs, the 16-by-16 horizontal and vertical registered chains, and accumulator feedback. It accepts both explicit hierarchy and recursive instances produced when Yosys preserves hierarchy; it does not require all 256 PEs to be direct top-level instances. Run its regressions together with the PPA aggregator tests using:

```bash
PYTHONPATH=evaluator python3 -m unittest \
  evaluator.test_ppa_aggregate evaluator.test_t10_structure_check -v
```

Dated `t*_pilot_*.json` files are historical run evidence. Their original time
limits and score units remain unchanged and are not the active configuration.
Only [`benchmark/manifest.yaml`](../benchmark/manifest.yaml) and each task's
`task.yaml` define current time limits.



T01's independent functional entry point is `python3 evaluator/t01_check.py /path/to/submission`. It generates cycle-accurate vectors with an independent Python bit-stream oracle and checks groups `AC-05` through `AC-08B`; `--reference` runs the evaluator-owned reference RTL. `python3 evaluator/t01_mutation_check.py` qualifies ten synthesizable fault variants. `make_t01_power_vectors.py` generates the frozen self-checking power workload, while `ppa_probe.py` and `ppa_power_probe.py` collect routed area/timing and 1 GHz gate-level activity power for each layout seed. Frozen hashes and reference qualification results are recorded in `t01_qualification.json`. These evaluator artifacts are public in the repository but are not copied into contestant workspaces by `prepare_trial.py`.

T02's independent functional entry point is `python3 evaluator/t02_check.py /path/to/submission`. It aggregates groups `AC-09` through `AC-15` over the six combinations `WIDTH={8,32}` and `DEPTH={3,8,16}`; `--reference` runs the evaluator-owned reference RTL. `python3 evaluator/t02_mutation_check.py` deterministically builds and qualifies nine synthesizable fault variants. The three-seed 1 GHz baseline, frozen hashes, and qualification results are in `t02_qualification.json`.

T03's independent functional entry point is `python3 evaluator/t03_check.py /path/to/submission`. Its cycle-accurate APB4/timer model checks groups `AC-16` through `AC-20`; `--reference` runs the evaluator-owned reference RTL. `python3 evaluator/t03_mutation_check.py` deterministically builds and qualifies ten synthesizable fault variants. The power testbench runs the same self-checking workload at a 1000 ps clock period and counts completed APB accesses. The three-seed 1 GHz baseline, frozen hashes, and qualification results are in `t03_qualification.json`.

T04's independent functional entry point is `python3 evaluator/t04_check.py /path/to/submission`. It aggregates groups `AC-21` through `AC-25` over the four combinations `N={4,8}` and `WIDTH={8,32}`; `--reference` runs the evaluator-owned reference RTL. `python3 evaluator/t04_mutation_check.py` deterministically builds and qualifies nine synthesizable fault variants. The power testbench runs the same self-checking arbitration workload at a 1000 ps clock period and counts completed stream transfers. The three-seed 1 GHz baseline, frozen hashes, and qualification results are in `t04_qualification.json`.

T05's independent functional entry point is `python3 evaluator/t05_check.py /path/to/submission`. It aggregates groups `AC-26` through `AC-31` over the four combinations `WIDTH={8,32}` and `DEPTH={8,16}` and several non-phase-locked write/read clock ratios; `--reference` runs the evaluator-owned reference RTL. Alongside its cycle-accurate external scoreboard, AC-31 runs the Yosys-netlist bidirectional 2FF/local-reset structural check for every parameter combination. `python3 evaluator/t05_mutation_check.py` deterministically builds and qualifies thirteen synthesizable fault variants, including binary-pointer crossing and incorrect full-flag Gray-code polarity. The PPA flow constrains both `wr_clk` and `rd_clk` to 1000 ps while declaring them asynchronous clock groups, and the power workload counts successful reads. The three-seed 1 GHz baseline, frozen hashes, and qualification results are in `t05_qualification.json`.

T06's independent functional entry point is `python3 evaluator/t06_check.py /path/to/submission`. It aggregates groups `AC-32` through `AC-37`, covering either AXI write-channel arrival order, APB SETUP/ACCESS, read/write responses, concurrent arbitration, wait/output backpressure, and reset; `--reference` runs the evaluator-owned reference RTL. `python3 evaluator/t06_mutation_check.py` deterministically builds and qualifies fifteen synthesizable fault variants. The three-seed 1 GHz baseline, frozen hashes, and qualification results are in `t06_qualification.json`.

T07's independent functional entry point is `python3 evaluator/t07_check.py /path/to/submission`. It aggregates groups `AC-38` through `AC-43`, covering read/write hits, clean and dirty replacement, write allocation, every byte strobe, backpressure on both interfaces, reset, and hit latency; `--reference` runs the evaluator-owned reference RTL. `python3 evaluator/t07_mutation_check.py` deterministically builds and qualifies sixteen synthesizable fault variants. The three-seed 1 GHz reference baseline, frozen hashes, and qualification results are in `t07_qualification.json`.

T09's independent functional entry point is `python3 evaluator/t09_check.py /path/to/submission --elapsed-seconds SECONDS`. It runs 45 ACT4 programs, 108 directed programs, 100 differential-random programs, 80 memory-wait runs, four live-reset cases, four task-specific exception cases, and the 64-instruction fetch-to-retire latency check before invoking the common scorer. Frozen ELF files, assembly sources, and compressed commit oracles are under `t09_data/`; `python3 evaluator/verify_t09_artifacts.py` checks their manifests, SHA-256 digests, compressed JSONL, and event counts. `programs/random/diff_mem_seed035_v0.elf` and `programs/delivery_bad_tohost.elf` are the public positive and negative probes for `delivery_check.py T09`. `python3 evaluator/t09_mutation_check.py` builds and checks twenty-one synthesizable fault variants in a temporary directory. The current reference RTL scores 50/50 normalized functional points and passes all 22 cycle checks; its 2026-10-09 requalification hashes and evidence are in `t09_qualification.json`. The three-seed ASAP7 WC 1 GHz T09 reference baseline is complete, with setup, hold, and DRC passing in all seeds; the smallest setup margin is +9.008 ps in seed 47. See `benchmark/ppa-baselines.json`.

On 2026-10-09, `port_timing_v1` added 22 fixed-port cycle checks: `python3 evaluator/t09_timing_check.py --submission /path/to/submission --output timing.json`. Under `t09_group_cycles10_v1`, they form the separate `CPU-PIPE-CYCLES` group: 22/22 earns 10 normalized points, 11–21/22 earns 5, and 0–10/22 earns 0. Legacy groups retain their relative weights but total 40 normalized points (raw F=48/P=27 overall); cycle failures are no longer merged into LAT/HAZ. The functional maximum remains 50. The checker requires four-cycle latency AND IPC=1 for independent ADDIs, zero extra ALU-forwarding bubbles, at most one extra load-use bubble, and a fixed retirement-span budget for straight-line probes so common avoidable stalls cannot cancel in paired comparisons. Three external ready/response profiles are fixed. Branch/JAL/JALR cycle penalties are diagnostic only. See `benchmark/tasks/T09/acceptance.md` for the precise budget. The legacy reference initially passed 6/22. After forwarding, memory/fetch recovery and combinational-adder optimization, the current reference passes 22/22, and its RTL and three-seed 1 GHz PPA baseline have been requalified and frozen. Evidence is in `t09_timing_qualification.json` and `fixtures/t09_cpu_20261009_cycles10/`. Historical contestant scores have not been automatically regraded. The newly quantified throughput budgets are a policy supplement, not a retroactive claim about the old specification.

Re-freeze with `python3 evaluator/t09_reference_freeze.py --measurement /path/to/three_seed_measurement.json --evidence-dir evaluator/fixtures/NEW_T09_EVIDENCE`. It reaggregates all three seeds, verifies the actual RTL, unchanged 1 GHz SDC, finish reports and frozen power workload, then reruns full functional, 22 cycle and 21 mutation checks. Every reference seed must pass setup, hold and DRC. A new evidence directory is required; the authoritative baseline is published last with an atomic replacement. Historical contestant scores are not automatically regraded.

T08/T09 task-level freeze (2026-10-09): [T08 receipt](../benchmark/tasks/T08/FREEZE.json), [T09 receipt](../benchmark/tasks/T09/FREEZE.json). Run `python3 benchmark/freeze_tasks.py` from the repository root to verify specification, RTL, judge, scoring, baseline and portable evidence hashes. All six T09 archives have been regraded; untested T08 models remain null. Host-only receipts are excluded from candidate packages. T10 PPA and the suite-wide tool-image/release gates remain pending.
