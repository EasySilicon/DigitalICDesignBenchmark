# Digital IC Design Benchmark for Agents

[中文](README.md)

**Evaluate frontier models on tasks grounded in real digital IC development and delivery workflows.**

This benchmark evaluates whether widely used frontier models, working through coding agents, can handle real digital IC engineering work: delivering a **functionally correct, synthesizable digital IP with independent self-tests, PPA exploration, and reproducible execution** under a fixed specification, tool environment, resource allocation, and development budget. It also supports experiments on external harnesses such as Skills, multi-agent orchestration, and immediate quality gates, as well as regression testing across model and system versions.

The candidate develops the RTL, verification environment, fixes, and PPA optimizations. The evaluator tests the fixed DUT ports against its own behavioral models; candidate-reported PASS messages, coverage, and PPA reports do not directly determine scores. Evaluation priority is **functional correctness → PPA → completion time**.

## Navigation

- [Motivation and evaluation principles](#motivation-and-evaluation-principles)
- [Tasks and capability coverage](#tasks-and-capability-coverage)
- [Evaluated models and results](#evaluated-models-and-results)
- [Environment setup](#environment-setup)
- [Recommended testing workflows](#recommended-testing-workflows)
- [Acceptance and scoring](#acceptance-and-scoring)
- [Repository guide](#repository-guide)

## Motivation and evaluation principles

The starting point is to **build a benchmark grounded in real digital IC development and delivery workflows, and test whether widely used frontier models can handle real chip engineering work.** Writing a fragment of RTL is only part of the task. Candidates must understand requirements, organize design and verification, analyze problems with EDA tools, iterate on optimizations, and deliver artifacts that pass independent acceptance.

Tasks follow an engineering cycle: **specification comprehension → architecture and RTL → candidate verification → debugging and fixes → timing and PPA optimization → frozen handoff**. They include both greenfield design and reading, repairing, and extending existing RTL. Capabilities of interest include:

- **Long-context comprehension and requirement decomposition:** extract requirements from long specifications, interface contracts, and existing RTL while preserving consistency across files and modules.
- **Logic and microarchitecture design:** implement state machines, pipelines, storage, and protocol control with correct concurrency, backpressure, reset, and parameter boundaries.
- **Timing-window and clock-domain analysis:** understand data-valid windows, setup/hold constraints, synchronizers, and CDC behavior; distinguish logical correctness from timing safety.
- **Verification convergence:** build independent models and self-checking tests, cover corner cases, concurrency, and performance requirements, and eliminate defects through regression iterations.
- **Debugging and brownfield changes:** locate rare, cross-module defects and add features without breaking existing behavior or interface compatibility.
- **Timing closure and performance tradeoffs:** interpret timing reports, identify critical paths, and adjust logic and pipelines while meeting cycle and throughput requirements.
- **Physical implementation and PPA optimization:** use synthesis, placement and routing, and memory macros while balancing area, power, timing, and physical constraints.
- **Tool use and engineering handoff:** organize EDA runs, diagnose tool errors, manage time and compute resources, and deliver reproducible RTL, verification, and scripts.

Building on model evaluation, we will further explore **to what extent external harnesses—Skills, multi-agent orchestration, immediate quality gates, and similar mechanisms—can improve the final performance of frontier or cost-effective models on digital IC engineering tasks.** These are optional experimental variables, not prerequisites for using the benchmark. Their effects require controlled comparisons on the same tasks, without assuming that any particular architecture is better. Improvements should also be assessed against their time, inference cost, and compute requirements.

The suite follows these principles:

1. **Evaluate a complete deliverable.** Specifications constrain behavior, interfaces, resources, and handoff. Candidates deliver synthesizable RTL, their own verification, and executable reproduction, including the debugging and optimization work. Acceptance evaluates the final frozen project snapshot; claims made during development require evidence from the actual artifacts.

2. **Prioritize correctness, then physical cost, then speed.** Functional errors fail the corresponding acceptance items and prevent PPA/time ranking eligibility for that task. Excellent PPA is meaningless when the required functionality is incorrect; this gate prevents perverse incentives in PPA optimization. Partial functional scores remain useful diagnostics. Fully functional designs are compared on area, routed delay, and energy under the common flow; completion time decides within comparable PPA buckets. This follows the engineering sequence of meeting the specification before optimizing cost and efficiency.

3. **Keep acceptance independent and implementation flexible.** Fix DUT interfaces, protocols, and explicit architectural boundaries while allowing different RTL styles, legal microarchitectures, and verification frameworks. Evaluator-owned port transactions and behavioral models determine correctness; automatic netlist rules check required CDC/systolic structures. Candidate UTs assess verification handoff, while independent evaluation produces functional scores, allowing systems to use their own engineering methods.

4. **Make quality gates executable and traceable.** Requirements map to acceptance groups, and failures trace to seeds, inputs, expected values, and observations. Correct-reference regressions and known defect mutants calibrate evaluators; frozen scripts determine scores. Specification, evaluator, and tool faults receive separate attribution, followed by consistent regrading of affected frozen submissions after correction.

5. **Use consistent PPA scope and conditions.** References and candidates use the same process data, constraints, activity workloads, and measurement flows. T01–T09 measure the complete DUT. For V1.0, T10 measures one PE's area, routed delay, and energy, while the complete 256-PE DUT must still pass functional, structural, and throughput checks. Single-PE results do not represent the complete NPU's cost. Each task's PPA contract defines its scope and release requirements.

6. **Evaluate external harnesses through controlled comparisons.** Skills, orchestration strategies, and immediate quality gates are explicit experimental variables. All roles in a multi-agent system share time, monetary, and compute budgets; token usage is recorded without a cap, including reasoning, verification, and PPA iterations. The same-model control track studies harness effects; the product track measures practical model and system performance. Independent repetitions, pass rates, time, and cost provide evidence, with model settings and budget differences recorded alongside results.

7. **Build difficulty through domain coverage and engineering interactions.** Tasks cover state control, parameterization, protocols, CDC, caches, pipelines, and spatial arrays. Boundaries, concurrent state, numerical semantics, and constraints across modules create difficulty. Different task scales reveal where systems are reliable and where they fail; pilot data calibrate difficulty and budgets. A compact suite makes repeated experiments practical.

8. **Publish materials, isolate attempts, and preserve reproduction evidence.** Public specifications, evaluator sources, references, and measurement configurations support auditing. During an attempt, candidates receive only permitted task materials, with answers and previous submissions excluded. Preserve versions, tools, seeds, artifact hashes, and component results, distinguishing adjudicated failure, pending measurement, and infrastructure faults. Other teams should be able to reproduce conditions and explain the resulting scores.

9. **Task and process materials are self-contained.** This repository includes T01–T10 specifications, acceptance plans, public tests, independent evaluator code/data, evaluation configurations, and completed reference baselines. It also includes ASAP7 Liberty, LEF, GDS, gate-level simulation models, and routing/extraction rules, with provenance, licenses, and file hashes. Users do not need to download a separate ASAP7 process package or standard-cell library. Process inputs are read directly from the repository; the task preparer copies permitted public materials into independent candidate workspaces. Install and pin Verilator, Yosys, OpenROAD, ORFS, and CPU tools according to the environment guide; model API access follows the experimental track's network policy.

The intended outcome is evidence of **model capability boundaries, reliable delivery, optimization capability, and engineering cost** on real chip-development tasks, useful for model selection and external harness design. See the [full experimental methodology](benchmark/README.md#评测与评分方法).

## Current status

The main suite, `ic-delivery-rtl-v0.3`, contains **ten tasks, T01–T10**. T01–T09 have frozen task specifications, acceptance collateral, and three-seed 1 GHz PPA baselines. T10's V1.0 single-PE reference has also completed physical closure and activity-based power measurement for seeds 11/29/47. All ten reference baselines are available; the unified tool image, fairness checks across equivalent RTL implementations, and suite-wide release checks remain pending. The full suite therefore remains in the pre-release `design_only` stage.

| Scope | Available | Status |
| --- | --- | --- |
| T01–T09 | Frozen task specifications and acceptance collateral, public smoke tests, reference RTL, defect mutants, and frozen three-seed 1 GHz PPA baselines | Complete |
| T10 | Continuous-stream matrix evaluation, exact numerical oracle, reset/backpressure/throughput tests, PE mesh checks, and the single-PE three-seed 1 GHz PPA baseline with activity-based power | Complete |

The latest public T10 evaluator package replay passed **2,752 matrix blocks, a separate reset probe, 256-PE structural checks, and all 14 input phases without bubbles**. See [T10_PACKAGE_VERIFICATION.json](evaluator/T10_PACKAGE_VERIFICATION.json). See the [three-seed implementation and measurement notes](evaluator/t10_backend/v1/README.md) for timing, complete DRC/connectivity checks, and activity-based power. Each full gate-level DUT passed 200 blocks, 51,200 output checks, and protocol checks. The single-PE median reference is **60,298.3 µm², 0.944853668 ns, and 837.441929552 pJ/block**, not the cost of the full NPU.

## Tasks and capability coverage

The suite progresses from basic sequential logic through protocols, clock-domain crossing, memory hierarchy, a CPU, and an NPU. Each task specifies behavior, interfaces, resources, acceptance groups, and scoring mappings. Follow the task links for the full specifications.

| ID | Task | IC design domain | Capabilities exercised | Time limit | Suite display weight |
| --- | --- | --- | --- | ---: | ---: |
| T01 | [SerDes RX comma aligner](benchmark/tasks/T01/task.md) | Serial-link PCS and symbol synchronization | Bit windows across slices, alignment training, word assembly, lock loss/recovery | 30 min | 3% |
| T02 | [Parameterized synchronous FIFO](benchmark/tasks/T02/task.md) | Stream buffering and storage | ready/valid, simultaneous push/pop, empty/full boundaries, non-power-of-two wrap | 60 min | 3% |
| T03 | [APB4 timer peripheral](benchmark/tasks/T03/task.md) | Register peripherals and control FSMs | APB timing, byte writes, W1C, interrupts, event priorities | 90 min | 6% |
| T04 | [ready/valid round-robin arbiter](benchmark/tasks/T04/task.md) | Multiport flow control and scheduling | Fairness, sustained contention, payload retention under backpressure, parameters | 90 min | 6% |
| T05 | [Asynchronous FIFO](benchmark/tasks/T05/task.md) | CDC, dual-clock buffering and reset | Gray pointers, two-stage synchronizers, conservative flags, cross-domain recovery | 120 min | 6% |
| T06 | [AXI4-Lite to APB4 bridge](benchmark/tasks/T06/task.md) | On-chip interconnect and protocol conversion | Independent AW/W arrival, concurrent reads/writes, waits, response stalls, errors | 120 min | 10% |
| T07 | [Direct-mapped write-back cache](benchmark/tasks/T07/task.md) | Memory hierarchy | Tags/indexing, dirty replacement, write allocation, byte enables, stalls on both sides | 120 min | 10% |
| T08 | [1GbE MAC bug fix and VLAN admission](benchmark/tasks/T08/task.md) | Brownfield Ethernet MAC | Long-specification and large-codebase comprehension, corner-case repair, VLAN admission | 120 min | 11% |
| T09 | [RV32I five-stage pipelined CPU](benchmark/tasks/T09/task.md) | RTL design / verification | Five-stage pipeline, forwarding and hazard handling, variable-latency memory, precise exceptions and CSRs | 120 min | 20% |
| T10 | [Multi-precision systolic-array matrix multiplication](benchmark/tasks/T10/task.md) | RTL design / verification | Multi-format numerical accuracy, sustained-stream throughput and backpressure, 256-PE physical systolic array | 240 min | 25% |

T10 multiplies `16×64` and `64×16` matrices, accepting **1,024 bits per cycle on each of A and B**. It supports INT8, INT16, FP16, BF16, FP8 E4M3/E5M2, FP4 E2M1, MXFP8 E4M3/E5M2, and MXFP4. Continuous block throughput is required; a single high-bandwidth input burst is insufficient.



See the [full coverage mapping and scope limits](benchmark/README.md#领域与难度覆盖) in the normative specification.

## Evaluated models and results

The following values come from the [2026-10-21 per-task evaluation results](results/model-score-comparison.md). All **60 model/task results are resolved**, with no `null` functional, PPA, or time components. Models used broadly consistent time budgets and Skill settings. Column headers identify the coding framework and version used during the actual trials, checked against the original run records.

Each cell is the task's display score **out of 105, including delivery deductions**, rounded to two decimal places. Weighted totals use unrounded task scores and fixed weights, not a simple average.

Parentheses after model names indicate reasoning effort; `default` means no explicit setting was supplied. Effort levels across frameworks do not imply equal reasoning budgets.

| Task | Weight | GPT-6-Astra(high)<br><sub>Codex CLI 0.160.0</sub> | GPT-6.1-Sol(high)<br><sub>Codex CLI 0.160.0</sub> | GPT-6-Sol(high)<br><sub>Codex CLI 0.160.0</sub> | Kimi K3(max)<br><sub>Kimi CLI 2.1.1</sub> | DeepSeek V4.1 Flash(default)<br><sub>Claude Code 2.1.183</sub> | GLM-5.3-Flash(default)<br><sub>Claude Code 2.1.183</sub> |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| T01 | 3% | 88.24 | 86.33 | 86.98 | 75.49 | 82.86 | 0.00 |
| T02 | 3% | 87.88 | 87.20 | 89.70 | 89.17 | 89.07 | 81.71 |
| T03 | 6% | 91.08 | 91.18 | 89.80 | 89.96 | 90.88 | 87.04 |
| T04 | 6% | 97.27 | 86.90 | 91.12 | 68.13 | 62.63 | 64.79 |
| T05 | 6% | 89.72 | 88.93 | 90.12 | 89.18 | 90.00 | 88.22 |
| T06 | 10% | 94.78 | 93.70 | 96.22 | 25.00 | 92.93 | 87.60 |
| T07 | 10% | 93.49 | 93.12 | 88.44 | 81.88 | 92.50 | 75.57 |
| T08 | 11% | 87.89 | 87.14 | 84.21 | 84.30 | 46.83 | 44.00 |
| T09 | 20% | 60.51 | 59.20 | 56.25 | 40.00 | 44.93 | 17.00 |
| T10 | 25% | 53.83 | 53.73 | 50.00 | 41.67 | 0.00 | 0.00 |
| **Weighted total /105** | **100%** | **76.02** | **74.77** | **73.04** | **58.15** | **52.45** | **41.41** |
| **Fully functional tasks** | — | **10/10** | **10/10** | **10/10** | **7/10** | **7/10** | **6/10** |

Tasks below full functionality receive zero PPA and time points. GPT-6-Sol T10 retains 50 functional points and zero PPA/time points under its historical power-compilation termination adjudication. See the [model results](results/model-score-comparison.md) for component scores and zero-score categories.

Run conditions: Kimi T08 used a cumulative historical development budget of 150 minutes. T10 reference and candidate implementations differ in internal macros and physical flow; a same-flow comparison is not available.

Details: [per-task score-loss analysis](results/model-score-comparison.md#各模型逐题失分原因), [PPA formula audit](results/model-score-comparison.md#ppa-公式审计2026-10-21), [archive policy](results/README.md), and [result schema](results/result.schema.json).

## Environment setup

Functional and physical evaluation use open tools and **require no commercial EDA license**. The ASAP7 platform is included under [vendor/asap7/](vendor/asap7/). Custom PE/tile macro models are generated by the backend flow.

| Purpose | Main dependencies |
| --- | --- |
| Specification/report validation | Python ≥3.10, PyYAML, jsonschema |
| RTL compilation, simulation and structure | Verilator, Yosys, C++ compiler, make; some independent evaluators also use Icarus Verilog `iverilog`/`vvp` |
| PPA | Yosys with a working slang frontend, OpenROAD, OpenROAD-flow-scripts (ORFS), included ASAP7; timing/power reports come from the OpenROAD flow |
| CPU test generation/reference checking | RISC-V bare-metal tools, Sail, locked ACT4/riscv-arch-test; generated ELF artifacts are also provided |
| Candidate verification | Optional SystemVerilog/UVM, SVA, cocotb or C++; validate the syntax used against the actual installed tools |

From the repository root:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r env/requirements-spec.txt
source .venv/bin/activate
python3 env/check_env.py --profile spec
python3 benchmark/validate_spec.py
```

This installs only the Python specification-validation dependencies. See [installation and dependencies](env/README.en.md) for the full toolchain, locked sources, and ORFS compatibility patch. After installing tools, check the functional and physical environments:

```bash
python3 env/check_env.py --profile functional
python3 env/check_env.py --profile ppa \
  --orfs-root third_party/OpenROAD-flow-scripts --verify-platform-hashes
```

The default evaluation allocation is **16 vCPU, 40 GiB RAM, and 100 GiB writable disk**. Token usage is recorded without a cap and never triggers termination. Task time limits are in [manifest.yaml](benchmark/manifest.yaml). Put `TMPDIR` and the ORFS work tree on a sufficiently large data disk for large simulations/physical builds. Dependency discovery alone does not establish compatibility; run a reference smoke test too.

## Recommended testing workflows

### Workflow 1: Validate existing RTL or check the environment

Useful for IP developers, evaluator maintainers, and CI regression. A submission must contain `rtl/files.f` and the prescribed top-level interface. For example, run T03 from the evaluator repository root:

```bash
# Public DUT-port smoke test
python3 evaluator/public_check.py T03 /path/to/submission

# Independent functional evaluation and candidate self-test handoff check
python3 evaluator/t03_check.py /path/to/submission
python3 evaluator/delivery_check.py T03 /path/to/submission

# Check the environment using evaluator-owned reference RTL
python3 evaluator/t03_check.py --reference
```

Public smoke tests quickly catch interface/basic behavior issues; independent evaluation reports groups; the delivery check exercises the candidate's `run.sh`. **A successful command exit does not always mean every functional group passed.** Inspect `cases_passed/cases_total` and feed evaluator-owned results to the scorer.

T09 and T10 have dedicated entry points:

```bash
# Replace SECONDS with actual candidate time from task release to frozen submission
python3 evaluator/t09_check.py /path/to/cpu --elapsed-seconds SECONDS

# Numerical, streaming, structural, backpressure and reset checks
python3 evaluator/runner_t10_stream.py /path/to/npu \
  --output-dir work/T10-acceptance
```

The evaluator independently loads T09 ELF programs and captures instruction traces. See the [evaluator guide](evaluator/README.md) and [T10 package guide](evaluator/T10_EVALUATION.md) for detailed entry points.

### Workflow 2: Run one task with an agent

Useful for trying one model/coding agent or integrating a system. Prepare an **empty independent directory**:

```bash
python3 benchmark/prepare_trial.py T03 work/trials/my-system/run-01/T03
```

For T08, T09 and T10, also pass `--orfs-root /path/to/OpenROAD-flow-scripts` to supply the public EDA kit for synthesis, place-and-route and timing feedback during development. T09 measures the full CPU; T10 measures the candidate's own single PE. The kit includes ASAP7 views and physical constraints, without reference RTL or hidden tests. Mount the generated `public_eda/` read-only at `/opt/t08_eda` for T08 or `/opt/benchmark_eda` for T09/T10. Instructions are appended to `PROMPT.md` and, for T09/T10, `EDA_TOOLS.md`. EDA iterations count toward the original task deadline.

1. Start a fresh agent session in the generated directory and supply `PROMPT.md`. It contains only the selected public task material, smoke test, and required public assets.
2. Record task release time; run until final submission or the deadline. Preserve model settings, tokens, cost, logs, and final artifact hashes.
3. The agent develops RTL, self-tests, and PPA exploration within the budget. Reasoning, collaboration, compilation, simulation, and optimization all count toward development time.
4. Freeze the submission, then run independent acceptance, delivery checks, and available PPA evaluation in the evaluator environment. Host grading time is excluded from candidate completion time.

Use containers or equivalent access boundaries for formal comparisons so candidates cannot read host reference RTL, independent tests, or other submissions. Source may be public while excluded from candidate workspaces; creating a new directory alone does not enforce isolation.

### Workflow 3: Repeated suite comparisons or automated experiments

Useful for model comparisons, multi-agent experiments, and system version regression. Generate the task workspaces:

```bash
for task in T01 T02 T03 T04 T05 T06 T07 T08 T09 T10; do
  case "$task" in
    T08|T09|T10) python3 benchmark/prepare_trial.py "$task" "work/trials/my-system/run-01/$task/workspace" --orfs-root /path/to/OpenROAD-flow-scripts ;;
    *) python3 benchmark/prepare_trial.py "$task" "work/trials/my-system/run-01/$task/workspace" ;;
  esac
done
```

Your agent CLI/API or system runner then consumes each `PROMPT.md` in a new session with independent outputs. The repository provides preparation, acceptance, and scoring tools; the experimental runner must integrate model calls, container startup, clocks, and logging.

- **Product track:** compare native models and engineering systems with fixed monetary, time, and compute budgets.
- **Same-model control track:** use identical model snapshots, sampling settings, API, and development time limits to study orchestration/workflow effects.
- **Replicates:** the main suite specifies at least five independent attempts per task with common fixed evaluation seeds. Report per-task pass rates, medians, time, and cost rather than only the best attempt.

The current preparer generates a single-agent pilot prompt. For multi-agent experiments, evaluators must configure and freeze the corresponding collaboration, model, and Skill policy before the run. All roles share the task's aggregate time and compute budget; token usage is recorded without a cap. Keep product and control tracks separate. See the [full experimental methodology](benchmark/README.md#评测与评分方法).

## Acceptance and scoring

### Submission contract

Each task requires:

```text
submission/
├── rtl/             # Synthesizable RTL with the fixed task interface
│   └── files.f      # Source paths relative to rtl/
├── verif/           # Candidate-developed executable self-tests
├── run.sh           # Non-interactive entry point; supports BENCH_SEED
├── results.json     # Structured results generated by actual self-tests
└── README.md        # Reproduction, coverage, limitations and PPA exploration
```

`run.sh` must compare expected and observed behavior, return nonzero on failure, and reproduce outcomes for the same seed. Candidates may choose different verification frameworks and internal RTL structures while preserving the fixed acceptance interface. See the [full delivery contract](benchmark/README.md#验证与交付契约).

### Evaluator acceptance chain

| Stage | What is checked | Evidence |
| --- | --- | --- |
| Delivery | Files/interfaces, runnable reproducible self-tests, PPA exploration notes | Submission contract; candidate UT results are not the RTL correctness oracle |
| Independent functionality | Directed boundaries, seeded streams, protocol/reset/latency, CPU architectural/commit differences, exact NPU arithmetic | Evaluator-owned testbenches and behavioral models observe fixed DUT ports |
| Automatic structure | T05 synchronizer chains; T10 PE neighbors, local accumulation and resource limits | Yosys netlist rules; T09 observes pipeline timing using fetch-to-retire latency, dependencies and flushes |
| Evaluator calibration | Correct references pass; known defect mutants are detected | Reference regressions and fault injection; candidate UT mutation detection is a separate diagnostic |
| Common PPA rerun | Area, routed delay, energy per useful operation | Yosys + ASAP7 + OpenROAD with fixed process, constraints, activity workload and three layout seeds |

Per-submission functional/structural scoring is automated and requires no two-person review. Reference PPA baselines may receive engineering review before release. CPU acceptance combines ACT4/Sail with task-specific tests; ACT4 does not replace bus, exception, or pipeline checks. NPU evaluation includes every required format, including extreme MX scales, overflow, and opposite-sign cancellation.

### Scores and ordering

The current configuration is [score_rules.json](evaluator/score_rules.json). [ppa-baselines.json](benchmark/ppa-baselines.json) is the sole authoritative reference-baseline source.

| Metric | Display maximum | Conditions and interpretation |
| --- | ---: | --- |
| Functionality | 50 | Raw weights are normally F=60/P=15, but T09 uses F=48/P=27; all are scaled by `50/75`. P covers protocols, boundaries, structure, and required performance; it is part of functionality, not PPA |
| PPA | 50 | Requires full functionality and valid measurement provenance; area/delay/energy are normalized to a frozen reference scoring 35/50 |
| Completion time | 5 | Requires all 50 functional points and a strictly positive PPA score; `5 × (1 − t/T_max)`, clipped to 0–5 |

#### Functionality: score each item, not the overall test pass rate

For a typical scoring item, compute the pass rate of each acceptance group and take their unweighted mean. All groups passing earns full points; a mean of at least one half earns half points; anything lower earns zero. A safety violation or any failure in an item-designated critical group overrides this and zeros that item. Other passing tests cannot compensate. Missing required groups or malformed records are scoring-input errors, not assumed passes.

- T08 awards each item's points in proportion to passing scenarios, rather than using the half-point tier. A scenario counts as passing only if it passes all three functional seeds.
- T09 assigns 10 functional points to its separate 22-case cycle group: 22 passes earn 10 points, 11–21 earn 5, and 0–10 earn zero. All other items together contribute 40 points.
- T10 additionally requires the complete 256-PE design to pass structural and sustained-throughput acceptance. Failure zeros the corresponding systolic-array item. Single-PE PPA measurement does not relax full-design functional requirements.

**Only 50/50 counts as full functionality. Otherwise, PPA and time points are zero, while earned functional points are retained.**

#### PPA: three-seed measurements, reference normalization, and physical penalties

Common targets are **ASAP7, 1 GHz (1,000 ps)**, layout seeds `{11,29,47}`, and at least 95% valid activity annotation in every seed. T01–T09 measure the complete DUT; T10 V1.0 measures one PE, not the complete NPU's cost. Power workloads must still pass self-checks; T10 must also cover full-DUT activity and account for internal PE macros.

Take separate medians across the three seeds for area `A`, routed critical-path delay `D`, and energy per useful operation `E`. Use the worst setup and hold slacks `S` and `H`, and the largest DRC count. Do not select the best run. The reference tuple is `A_ref`, `D_ref`, `E_ref`; a task uses the same measurement scope, constraints, and workload for reference and candidate. The following matches the [current scorer](evaluator/score_run.py); all time quantities are in ns:

```text
T       = 1 ns
R(x)    = min(2, max(0, x))
D_eff   = D + max(0, -H)
D_setup = T + max(0, -S)
P_base  = min(50, 35 × R(A_ref/A)^0.35
                    × R(D_ref/D_eff)^0.35
                    × R(E_ref/E)^0.30)
PPA     = P_base × (T/D_setup)^4 × (0.5 if any DRC, otherwise 1)
```

Area, delay, and energy have weights of **35%, 35%, and 30%**. All three ratios are clipped to `[0,2]`. The reference earns 35/50; improvements can raise the score to 50. Hold violations continuously increase `D_eff`. Setup violations already affect critical-path delay and additionally incur a fourth-power penalty based on the worst seed's frequency ratio. For example, a worst setup slack of −1 ns produces an extra factor of `1/16`. Any DRC violation in any seed halves the final score once, not once per violation. **Negative timing slack does not automatically zero PPA.**

Candidate failures to complete legal routing or obtain valid activity measurements require attribution. A qualified baseline or measurement that is not yet available is recorded as `null`, not a candidate-failure zero. Tool/evaluator faults are repaired and regraded on frozen submissions without penalizing candidates. See the [measurement details](benchmark/README.md#ppa-测量与评分) for physical parameters and useful-operation definitions; this formula and the scorer define current scoring.

#### Time, delivery deductions, and ordering

Time points require 50 functional points and a strictly positive PPA score. `t` is development wall-clock time from task release to the final submitted snapshot, including inference, self-tests, PPA exploration, and retries, but excluding post-submission evaluator queues and hidden acceptance. `T_max` is the task's development limit. A zero PPA score also means zero time points.

Delivery-contract violations incur an additional deduction, **capped at 10 points per task**: deduct **5 points** for one missing deliverable or one candidate-caused execution error; deduct **10 points** for two or more missing deliverables, or two distinct delivery errors. Repeated occurrences of one root cause count once; infrastructure faults incur no deduction. Verified functional, PPA, and time components remain intact: `display = max(0, functionality + PPA + time − delivery deduction)`, with a maximum of 105. See the [delivery policy](benchmark/delivery-policy.md#delivery-contract-deductions).

Per-task ordering compares **functional score, PPA bucket, then completion time**, not the display total. The current bucket width is 1.25 points: `bucket = min(40, floor(PPA/1.25 + 0.5))`. Within a bucket, earlier completion wins only when PPA is positive. Suite ordering compares the number of fully functional tasks, then the functional score sum, then the sum of PPA buckets for fully functional tasks, then their summed `t/T_max` (lower is better). Task-weighted display scores are supplementary; missing components do not rescale the remaining weights.

#### Physical evaluation: 60 minutes per layout seed

For T01–T10, synthesis, placement, clock-tree synthesis, routing, extraction, and final reports share a **3,600-second wall-clock limit per layout seed**. The clock does not restart between stages. On timeout, terminate that seed's tool processes, retain its artifacts, and continue the other seeds. Score the valid completed seeds with measured activity-based power: take median area, delay, and energy, and retain worst-case timing slack and DRC counts. If no valid complete measurement is available, PPA and time points are zero; functional points and delivery deductions remain. Intermediate reports do not replace complete measurements. The separate 20-minute power-compilation rule below still applies. See the [physical runtime policy](benchmark/physical-runtime-policy.md).

#### Power-simulation compilation: 20 cumulative minutes per seed

New T01–T10 candidates share one **1,200-second wall-clock budget per layout seed** across the complete power-simulation build: hierarchical planning, Verilator code generation for every module, C++ compilation, linking, and SAIF runtime builds. The budget cannot restart for each module or command. **A timeout in any seed zeros the entire task's PPA and time points, retaining functional points and existing delivery deductions.** Expiry terminates the compiler process tree, retains logs and compile receipts, and stops the remaining seeds' power flow for that submission.

This is not a 20-minute limit on synthesis, place-and-route, or the entire power flow. Workload simulation, power analysis, and independent functional tests are outside this compile budget. Missing tools, ordinary build errors, missing receipts, and failed validation are not automatically classified as compile timeouts; they require separate attribution. The rule does not retroactively rewrite historical scores. See the [common compile-limit policy and current entries](benchmark/power-compile-policy.md).

Evaluation tools consume **evaluator-generated** group results and measurements, never candidate score claims. New candidates use `power_probe_with_budget.py`, `aggregate_with_power_budget.py`, and `score_with_power_budget.py`; the dedicated T10 flow enforces the same rule. Frozen entries such as `ppa_power_probe.py` and `score_run.py` remain available for historical baseline reproduction.

## Repository guide

| Location | Purpose |
| --- | --- |
| [benchmark/README.md](benchmark/README.md) | Normative shared rules, resources, full acceptance/scoring/PPA, coverage and release gates |
| [benchmark/tasks/](benchmark/tasks/) | Per-task `task.md`, `acceptance.md`, `task.yaml` and `public/` |
| [benchmark/manifest.yaml](benchmark/manifest.yaml) | Task set, time/resource limits and token-usage recording policy and score configuration |
| [evaluator/](evaluator/README.md) | Smoke tests, independent acceptance, structural/delivery checks and scoring |
| [results/](results/README.md) | Model pilot notes, per-task scores and machine-readable archives |
| [env/](env/README.en.md) | Installation, dependency discovery and compatibility patches |
| [vendor/](vendor/README.en.md) | ASAP7 platform, provenance, licenses and hashes |

Task behavior follows each `task.md`; public smoke tests are examples. See the [evaluator guide](evaluator/README.en.md) and [T10 backend guide](evaluator/t10_backend/v1/README.md) for acceptance tools and the reference physical flow.

## License and provenance

Repository-owned code/documentation use [Apache-2.0](LICENSE). ACT4, ASAP7, and experimental starter RTL retain their own licenses; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Locked revisions and sources are in [sources.lock.yaml](benchmark/sources.lock.yaml). The benchmark assesses digital RTL delivery and relative PPA on a public predictive process; it does not claim fabrication signoff or formal RISC-V/Ethernet certification.

Verify frozen materials with `python3 benchmark/freeze_tasks.py`. Inventories: [T08](benchmark/tasks/T08/FREEZE.json), [T09](benchmark/tasks/T09/FREEZE.json).
