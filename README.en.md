# Digital IC Design Benchmark for Agents

[中文](README.md)

**Evaluate frontier models on tasks grounded in real digital IC development and delivery workflows.**

This benchmark evaluates whether widely used frontier models, working through coding agents, can handle real digital IC engineering work: delivering a **functionally correct, synthesizable digital IP with independent self-tests, PPA exploration, and reproducible execution** under a fixed specification, tool environment, resource allocation, and development budget. It also supports experiments on external harnesses such as Skills, multi-agent orchestration, and immediate quality gates, as well as regression testing across model and system versions.

The candidate develops the RTL, verification environment, fixes, and PPA optimizations. The evaluator tests the fixed DUT ports against its own behavioral models; candidate-reported PASS messages, coverage, and PPA reports do not directly determine scores. Evaluation priority is **functional correctness → PPA → completion time**.

## Navigation

- [Motivation and evaluation philosophy](#motivation-and-evaluation-philosophy)
- [Tasks and capability coverage](#tasks-and-capability-coverage)
- [Evaluated models and results](#evaluated-models-and-results)
- [Environment setup](#environment-setup)
- [Recommended testing workflows](#recommended-testing-workflows)
- [Acceptance and scoring](#acceptance-and-scoring)
- [Repository guide](#repository-guide)

## Motivation and evaluation philosophy

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

Building on model evaluation, we also explore **to what extent external harnesses—Skills, multi-agent orchestration, immediate quality gates, and similar mechanisms—can improve the final performance of frontier or cost-effective models on digital IC engineering tasks.** These are optional experimental variables, not prerequisites for using the benchmark. Their effects require controlled comparisons on the same tasks, without assuming that any particular architecture is better. Improvements should also be assessed against their time, inference cost, and compute requirements.

The suite follows these principles:

1. **Evaluate a complete deliverable.** Specifications constrain behavior, interfaces, resources, and handoff. Candidates deliver synthesizable RTL, their own verification, and executable reproduction, including the debugging and optimization work. Acceptance evaluates the final frozen project snapshot; claims made during development require evidence from the actual artifacts.

2. **Prioritize correctness, then physical cost, then speed.** Functional errors fail the corresponding acceptance items and prevent PPA/time ranking eligibility for that task. Excellent PPA is meaningless when the required functionality is incorrect; this gate prevents perverse incentives in PPA optimization. Partial functional scores remain useful diagnostics. Fully functional designs are compared on area, routed delay, and energy under the common flow; completion time decides within comparable PPA buckets. This follows the engineering sequence of meeting the specification before optimizing cost and efficiency.

3. **Keep acceptance independent and implementation flexible.** Fix DUT interfaces, protocols, and explicit architectural boundaries while allowing different RTL styles, legal microarchitectures, and verification frameworks. Evaluator-owned port transactions and behavioral models determine correctness; automatic netlist rules check required CDC/systolic structures. Candidate UTs assess verification handoff, while independent evaluation produces functional scores, allowing systems to use their own engineering methods.

4. **Make quality gates executable and traceable.** Requirements map to acceptance groups, and failures trace to seeds, inputs, expected values, and observations. Correct-reference regressions and known defect mutants calibrate evaluators; frozen scripts determine scores. Specification, evaluator, and tool faults receive separate attribution, followed by consistent regrading of affected frozen submissions after correction.

5. **Measure the physical cost of the complete design.** References and candidates use consistent process data, constraints, activity workloads, and measurement flows. Input transport, control, buffering, output, and actual interconnect contribute to complete-DUT cost; PE and other submodule results guide diagnosis and optimization. The goal is reproducible relative PPA, with reference-delivery scope determined by benchmark release gates.

6. **Evaluate external harnesses through controlled comparisons.** Skills, orchestration strategies, and immediate quality gates are explicit experimental variables. All roles in a multi-agent system share time, token, monetary, and compute budgets, including reasoning, verification, and PPA iterations. The same-model control track studies harness effects; the product track measures practical model and system performance. Independent repetitions, pass rates, time, and cost provide evidence, with model settings and budget differences recorded alongside results.

7. **Build difficulty through domain coverage and engineering interactions.** Tasks cover state control, parameterization, protocols, CDC, caches, pipelines, and spatial arrays. Boundaries, concurrent state, numerical semantics, and constraints across modules create difficulty. Different task scales reveal where systems are reliable and where they fail; pilot data calibrate difficulty and budgets. A compact suite makes repeated experiments practical.

8. **Publish materials, isolate attempts, and preserve reproduction evidence.** Public specifications, evaluator sources, references, and measurement configurations support auditing. During an attempt, candidates receive only permitted task materials, with answers and previous submissions excluded. Preserve versions, tools, seeds, artifact hashes, and component results, distinguishing adjudicated failure, pending measurement, and infrastructure faults. Other teams should be able to reproduce conditions and explain the resulting scores.

9. **Task and process materials are self-contained.** This repository includes T01–T10 specifications, acceptance plans, public tests, independent evaluator code/data, evaluation configurations, and completed reference baselines. It also includes ASAP7 Liberty, LEF, GDS, gate-level simulation models, and routing/extraction rules, with provenance, licenses, and file hashes. Users do not need to download a separate ASAP7 process package or standard-cell library. Process inputs are read directly from the repository; the task preparer copies permitted public materials into independent candidate workspaces. Install and pin Verilator, Yosys, OpenROAD, ORFS, and CPU tools according to the environment guide; model API access follows the experimental track's network policy.

The intended outcome is evidence of **model capability boundaries, reliable delivery, optimization capability, and engineering cost** on real chip-development tasks, useful for model selection and external harness design. See the [full experimental methodology](benchmark/README.md#评测与评分方法).

## Current status

The main suite, `ic-delivery-rtl-v0.3`, contains **ten tasks, T01–T10**, and remains in the pre-release `design_only` state.

| Scope | Available | Pending |
| --- | --- | --- |
| T01–T09 | Specifications, public smoke tests, independent evaluators, reference RTL, defect mutants, and locally calibrated three-seed 1 GHz PPA baselines | Frozen common tool image and suite-wide release evidence |
| T10 | Continuous-stream matrix evaluation, exact numerical oracle, reset/backpressure/throughput tests, and automatic PE mesh checks | Official three-seed PPA baseline for the complete DUT; currently functional pilot scoring only |

The latest public T10 evaluator package replay passed **2,752 matrix blocks, a separate reset probe, 256-PE structural checks, and all 14 input phases without bubbles**. See [T10_PACKAGE_VERIFICATION.json](evaluator/T10_PACKAGE_VERIFICATION.json). This verifies the functional package, rather than qualifying a complete physical baseline.

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
| T08 | [1GbE MAC 缺陷修复与 VLAN 准入](benchmark/tasks/T08/task.md) | Brownfield Ethernet MAC | Corner-case repair, VLAN admission, long specification | 120 min | 11% |
| T09 | [RV32I 五级流水线 CPU](benchmark/tasks/T09/task.md) | RTL design / verification | Frozen task-specific acceptance | 120 min | 20% |
| T10 | [多精度脉动阵列矩阵乘法](benchmark/tasks/T10/task.md) | RTL design / verification | Frozen task-specific acceptance | 240 min | 25% |

T10 multiplies `16×64` and `64×16` matrices, accepting **1,024 bits per cycle on each of A and B**. It supports INT8, INT16, FP16, BF16, FP8 E4M3/E5M2, FP4 E2M1, MXFP8 E4M3/E5M2, and MXFP4. Continuous block throughput is required; a single high-bandwidth input burst is insufficient.



See the [full coverage mapping and scope limits](benchmark/README.md#领域与难度覆盖) in the normative specification. The frozen [T08 MAC repair/VLAN task](benchmark/tasks/T08/README.md) is part of the ten-task suite, covering long-specification comprehension, RTL debugging, atomic frame transactions and feature regression.

## Evaluated models and results

The following values come from the [2026-10-09 per-task evaluation results](results/model-score-comparison.md). Models were evaluated with broadly consistent time budgets and Skill settings. Results use a common scoring policy to compare functional correctness, PPA and completion efficiency. Subtotals include scored components only; unmeasured components are explicitly marked.

| Model | Fully functional / evaluated tasks | Weighted display subtotal /105 | Result files |
| --- | ---: | ---: | --- |
| GPT-6-Astra | 9/9 | 65.40 | [summary.json](results/gpt-6-astra/summary.json) |
| GPT-6.1-Sol | 9/9 | 64.25 | [summary.json](results/gpt-6.1-sol/summary.json) |
| GPT-6-Sol | 9/9 | 63.78 | [summary.json](results/gpt-6-sol/summary.json) |
| Kimi K3 | 7/10 | 58.94 | [summary.json](results/kimi-k3/summary.json) |
| DeepSeek Flash | 7/9 | 47.30 | [summary.json](results/deepseek-flash/summary.json) |
| GLM-5.3-Flash | 6/10 | 41.41 | [summary.json](results/glm-5.3-flash/summary.json) |

For the three GPT models, T10 currently contributes only 50 functional points; its PPA and time components remain pending. The totals therefore include only scored components. **`null` means unavailable or unresolved; `0` means adjudicated failure.** Missing components do not rescale the remaining task weights. Reconciled reruns and penalties for GLM and other runs are explained in the snapshot.

See the [archive policy](results/README.md) and [result schema](results/result.schema.json) for result classes, fields, and ranking eligibility. Check `scoring_policy`, specification revision, actual time budget, and tools before comparing them.

## Environment setup

Functional and physical evaluation use open tools and **require no commercial EDA license**. The ASAP7 platform is included under [vendor/asap7/](vendor/asap7/). Custom PE/tile macro models are generated by the backend flow.

| Purpose | Main dependencies |
| --- | --- |
| Specification/report validation | Python ≥3.10, PyYAML, jsonschema |
| RTL compilation, simulation and structure | Verilator, Yosys, C++ compiler, make; some independent evaluators also use Icarus Verilog `iverilog`/`vvp` |
| PPA | Yosys, OpenROAD, OpenROAD-flow-scripts (ORFS), included ASAP7; timing/power reports come from the OpenROAD flow |
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

The default evaluation allocation is **16 vCPU, 32 GiB RAM, and 100 GiB writable disk**. Model token caps and time limits are in [manifest.yaml](benchmark/manifest.yaml). Put `TMPDIR` and the ORFS work tree on a sufficiently large data disk for large simulations/physical builds. Dependency discovery alone does not establish compatibility; run a reference smoke test too.

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

T09 delivery also requires `run.sh --elf`. The evaluator captures instruction traces; candidates do not need to implement a trace-file generator. See the [evaluator guide](evaluator/README.md) and [T10 package guide](evaluator/T10_EVALUATION.md) for detailed entry points.

### Workflow 2: Run one task with an agent

Useful for trying one model/coding agent or integrating a system. Prepare an **empty independent directory**:

```bash
python3 benchmark/prepare_trial.py T03 work/trials/my-system/run-01/T03
```

1. Start a fresh agent session in the generated directory and supply `PROMPT.md`. It contains only the selected public task material, smoke test, and required public assets.
2. Record task release time; run until final submission or the deadline. Preserve model settings, tokens, cost, logs, and final artifact hashes.
3. The agent develops RTL, self-tests, and PPA exploration within the budget. Reasoning, collaboration, compilation, simulation, and optimization all count toward development time.
4. Freeze the submission, then run independent acceptance, delivery checks, and available PPA evaluation in the evaluator environment. Host grading time is excluded from candidate completion time.

Use containers or equivalent access boundaries for formal comparisons so candidates cannot read host reference RTL, independent tests, or other submissions. Source may be public while excluded from candidate workspaces; creating a new directory alone does not enforce isolation.

### Workflow 3: Repeated suite comparisons or automated experiments

Useful for model comparisons, multi-agent experiments, and system version regression. Generate the task workspaces:

```bash
for task in T01 T02 T03 T04 T05 T06 T07 T08 T09 T10; do
  python3 benchmark/prepare_trial.py "$task" "work/trials/my-system/run-01/$task"
done
```

Your agent CLI/API or system runner then consumes each `PROMPT.md` in a new session with independent outputs. The repository provides preparation, acceptance, and scoring tools; the experimental runner must integrate model calls, container startup, clocks, and logging.

- **Product track:** compare native models and engineering systems with fixed monetary, time, and compute budgets.
- **Same-model control track:** use identical model snapshots, sampling settings, API, and aggregate token caps to study orchestration/workflow effects.
- **Replicates:** the main suite specifies at least five independent attempts per task with common fixed evaluation seeds. Report per-task pass rates, medians, time, and cost rather than only the best attempt.

The current preparer generates a single-agent pilot prompt. For multi-agent experiments, evaluators must configure and freeze the corresponding collaboration, model, and Skill policy before the run. All roles share the task's aggregate time, token, and compute budget. Keep product and control tracks separate. See the [full experimental methodology](benchmark/README.md#评测与评分方法).

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
| Delivery | Files/interfaces, runnable reproducible self-tests, T09 ELF loading, PPA exploration notes | Submission contract; candidate UT results are not the RTL correctness oracle |
| Independent functionality | Directed boundaries, seeded streams, protocol/reset/latency, CPU architectural/commit differences, exact NPU arithmetic | Evaluator-owned testbenches and behavioral models observe fixed DUT ports |
| Automatic structure | T05 synchronizer chains; T10 PE neighbors, local accumulation and resource limits | Yosys netlist rules; T09 observes pipeline timing using fetch-to-retire latency, dependencies and flushes |
| Evaluator calibration | Correct references pass; known defect mutants are detected | Reference regressions and fault injection; candidate UT mutation detection is a separate diagnostic |
| Common PPA rerun | Area, routed delay, energy per useful operation | Yosys + ASAP7 + OpenROAD with fixed process, constraints, activity workload and three layout seeds |

Per-submission functional/structural scoring is automated and requires no two-person review. Reference PPA baselines may receive engineering review before release. CPU acceptance combines ACT4/Sail with task-specific tests; ACT4 does not replace bus, exception, or pipeline checks. NPU evaluation includes every required format, including extreme MX scales, overflow, and opposite-sign cancellation.

### Scores and ordering

The current configuration is [score_rules.json](evaluator/score_rules.json). [ppa-baselines.json](benchmark/ppa-baselines.json) is the sole authoritative reference-baseline source.

| Metric | Display maximum | Conditions and interpretation |
| --- | ---: | --- |
| Functionality | 50 | Task-card F=60/P=15 are raw weights scaled by `50/75`; P covers boundaries, protocols, structure, and specified performance |
| PPA | 50 | Requires full functionality and valid measurement provenance; area/delay/energy are normalized to a frozen reference scoring 35/50 |
| Completion time | 5 | Requires full functionality and valid PPA; `5 × (1 − t/T_max)`, clipped to 0–5 |

Per-task ordering compares **functional score, PPA bucket, then completion time**. Suite ordering first compares the number of fully functional tasks and functional score sum, then PPA, then normalized time. The 105-point display and weighted subtotal do not replace layered ordering.

Common physical targets are **ASAP7, 1 GHz (1,000 ps)**, layout seeds `{11,29,47}`, and at least 95% activity annotation. References must meet setup/hold with zero DRC. Routed candidates receive continuous setup/hold penalties and a 0.5 multiplier if any seed has DRC violations; negative WNS does not automatically zero PPA. Candidate failures to complete legal routing or obtain valid activity measurements are adjudicated separately. See the [PPA measurement/scoring specification](benchmark/README.md#ppa-测量与评分).

`ppa_probe.py` collects physical probes, `ppa_power_probe.py` collects gate-level activity power, and `ppa_aggregate.py` combines three-seed records. `score_run.py` consumes **evaluator-generated** groups and measurements, rather than candidate score claims. Unqualified/missing baselines remain pending; tool/evaluator faults are fixed and regraded on frozen submissions; adjudicated candidate failures score zero. Fatal candidate-caused handoff errors deduct five display points per distinct root cause while retaining verified component scores.

## Repository guide

| Location | Purpose |
| --- | --- |
| [benchmark/README.md](benchmark/README.md) | Normative shared rules, resources, full acceptance/scoring/PPA, coverage and release gates |
| [benchmark/tasks/](benchmark/tasks/) | Per-task `task.md`, `acceptance.md`, `task.yaml` and `public/` |
| [benchmark/manifest.yaml](benchmark/manifest.yaml) | Task set, time/token/resource budgets and score configuration |
| [evaluator/](evaluator/README.md) | Smoke tests, independent acceptance, structural/delivery checks and scoring |
| [results/](results/README.md) | Model pilot notes, per-task scores and machine-readable archives |
| [env/](env/README.en.md) | Installation, dependency discovery and compatibility patches |
| [vendor/](vendor/README.en.md) | ASAP7 platform, provenance, licenses and hashes |

Task behavior follows each `task.md`; public smoke tests are examples. Historical pilots do not override current specifications or scoring policy. `main` holds shared specifications and evaluators. `systolic_burnish` preserves experimental T10 backend flows, reference macro builds, and physical diagnostics; see `evaluator/t10_backend/README.md` on that branch.

## License and provenance

Repository-owned code/documentation use [Apache-2.0](LICENSE). ACT4, ASAP7, and experimental starter RTL retain their own licenses; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Locked revisions and sources are in [sources.lock.yaml](benchmark/sources.lock.yaml). The benchmark assesses digital RTL delivery and relative PPA on a public predictive process; it does not claim fabrication signoff or formal RISC-V/Ethernet certification.

T08/T09 task-level freeze (2026-10-09): [T08 receipt](benchmark/tasks/T08/FREEZE.json), [T09 receipt](benchmark/tasks/T09/FREEZE.json). Run `python3 benchmark/freeze_tasks.py` from the repository root to verify specification, RTL, judge, scoring, baseline and portable evidence hashes. All six T09 archives have been regraded; untested T08 models remain null. Host-only receipts are excluded from candidate packages. T10 PPA and the suite-wide tool-image/release gates remain pending.
