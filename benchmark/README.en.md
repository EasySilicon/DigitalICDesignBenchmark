# Digital IC Design Benchmark for Agents

Evaluator physical runs for T01–T10 have a **60-minute limit per layout seed**, from synthesis through final reports. On timeout, retain artifacts and score the valid completed seeds with measured power; with no valid measurements, PPA and time points are zero. See the [physical runtime policy](physical-runtime-policy.md).

[中文](README.md)

This benchmark evaluates whether widely used frontier models, working through coding agents, can handle real digital IC development and delivery tasks. Capabilities include long-context comprehension, logic and microarchitecture design, timing-window and CDC analysis, verification convergence, debugging and feature integration, timing closure, physical implementation and PPA optimization, and reproducible engineering handoff.

It also supports controlled experiments on whether external harnesses such as Skills, multi-agent orchestration, and immediate quality gates improve the final performance of frontier or cost-effective models. These mechanisms are optional experimental variables, not entry requirements or presumed advantages. See the [motivation and evaluation philosophy](../README.en.md#motivation-and-evaluation-philosophy) and [experimental methodology](README.md#评测与评分方法).

| ID | Task | Time limit |
| --- | --- | ---: |

| T01 | SerDes RX comma aligner | 30 min |
| T02 | Parameterized synchronous FIFO | 1 h |
| T03 | APB4 timer peripheral | 90 min |
| T04 | ready/valid round-robin arbiter | 90 min |
| T05 | Asynchronous FIFO | 2 h |
| T06 | AXI4-Lite to APB4 bridge | 2 h |
| T07 | Direct-mapped write-back cache | 2 h |
| T08 | 1GbE MAC bug repair and VLAN admission | 2 h |
| T09 | RV32I five-stage pipelined CPU | 2 h |
| T10 | 16×16 streaming multi-precision systolic-array matrix multiplication | 4 h |

The suite allocation is **16 vCPU, 40 GiB RAM and 100 GiB writable disk**.
The RAM ceiling limits actual memory, not virtual address space.
Token usage is recorded only: there is no token budget or token-triggered termination.

## Entry points

- [Task packages](tasks/): frozen task cards, task-specific acceptance plans, public artifacts, and machine-readable metadata.
- [Shared task rules](README.md#共享任务规则) and [shared acceptance rules](README.md#通用验收规则).
- [Verification and delivery contract](README.md#验证与交付契约): submission layout, fixed DUT interfaces, and independent evaluation.
- [Public executable checks](../evaluator/README.en.md): task-specific port-level smoke checks.
- [Evaluation methodology](README.md#评测与评分方法) and [PPA methodology](README.md#ppa-测量与评分).
- [Environment setup](../env/README.en.md) and the vendored [ASAP7 platform](../vendor/README.en.md).

Run `python3 benchmark/validate_spec.py` for a local consistency check. Create a task-only public workspace with `python3 benchmark/prepare_trial.py T03 /path/to/empty/T03`. Each evaluation run starts in a new conversation and an empty workspace with the same task material, model configuration, tool environment, and timing boundary.

T09 follows the same self-test delivery contract as the other tasks. The evaluator independently loads ELF programs, drives the CPU bus and captures execution traces for ACT4 and differential checks.



## Unexpected failures and scoring

T09 retains the full/half/zero rubric, with 40 functional points distributed proportionally across its legacy groups and 10 reserved for the 22 cycle checks. The cycle group earns 10 points for 22/22, 5 for 11–21/22, and 0 for 0–10/22; failures are not deducted once per case or merged into legacy hazard/latency groups again. Functional correctness remains out of 50, PPA out of 50, and time out of 5. Historical scores require explicit regrading under the new policy.

Preserve the frozen submission, command, tool version, stage logs, exit status/signal, time and memory limits, and available resource peaks before attributing a failure. A timeout or kill signal alone does not establish candidate fault.

- Functional errors, deadlocks, and functional-test timeouts affect the corresponding functional items, not every independent item. Incomplete functional correctness makes PPA/time zero.
- A reviewed candidate-caused resource-limit failure during Yosys frontend processing, synthesis, or structural netlist generation, or failure to complete the common physical flow, receives PPA=0 and time=0. Preserve verified functional points; this does not itself prove incorrect functionality or semantic unsynthesizability.
- Evaluator defects, missing tools/dependencies, host reboots, unrelated process kills, and unexplained timeouts/OOM leave affected components `null`/pending. Correct the infrastructure and re-evaluate the unchanged submission without candidate penalties.
- An unavailable or unqualified PPA baseline leaves PPA/time pending, except that an independently adjudicated candidate PPA failure is explicitly zero.
- Delivery-contract deductions are capped at 10 points per task: one missing deliverable or one candidate-caused execution error costs 5 points; two or more missing deliverables, or two distinct delivery errors, cost 10. Repeated failures of one root cause count once. Infrastructure faults incur no deduction, and earned component scores remain intact. A synthesis resource-limit failure alone incurs no additional delivery deduction. See the [delivery policy](delivery-policy.md#delivery-contract-deductions).

Keep functional and synthesis/structural results separately. An incomplete structural check must not be treated as a pass; unmeasured functional components remain pending. Zero means an adjudicated failure, whereas `null` means no conclusion. Freeze and calibrate per-task/per-stage tool budgets and resource-failure rules before official evaluation, using the reference and alternative equivalent RTL styles. Diagnostic budget extensions are not changes to official budgets. Do not rewrite or optimize candidate RTL. Version scoring-relevant evaluator corrections and regrade all affected frozen submissions.

Pre-release example (2026-10-05, Kimi K3-256k / T10): the delivery self-check passed, but full-design Yosys structural elaboration timed out even with a diagnostic 900-second budget. Its result store uses a 196,608-bit packed vector with dynamic partial writes from 192 sequential processes; a separate memory-limited probe also hit a frontend resource limit. The evaluator adjudicated PPA=0, leaving official functional grading pending, with no RTL edits or extra handoff penalty. This neither bans dynamic indexing nor establishes a universal 900-second budget. The evaluator exception that interrupted subsequent functional grading is a separate issue to fix. See the [full failure policy](README.md#异常归因与分项判分).

T08/T09 task-level freeze (2026-10-09): [T08 receipt](../benchmark/tasks/T08/FREEZE.json), [T09 receipt](../benchmark/tasks/T09/FREEZE.json). Run `python3 benchmark/freeze_tasks.py` from the repository root to verify specification, RTL, judge, scoring, baseline and portable evidence hashes. All six T09 archives have been regraded, and all six T08 answers have been scored. Host-only receipts are excluded from candidate packages. T10 V1.0 measures single-PE PPA; full-DUT functional, structural, and throughput requirements remain unchanged. The v15 single-PE reference has passed timing, complete DRC/connectivity, and activity-based power checks for seeds 11/29/47; archived candidates still need individual PPA/time measurements. See the [PPA contract](tasks/T10/ppa.md) and [manual-repair record](../evaluator/t10_pe_manual_closure.json). Suite-wide tool-image, fairness, and release checks remain pending. See the [three-seed measurement notes](../evaluator/t10_backend/v1/README.md).
