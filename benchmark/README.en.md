# Digital IC Design Benchmark for Agents

[中文](README.md)

Digital IC Design Benchmark for Agents evaluates end-to-end RTL delivery by multi-agent systems and general coding agents. The suite has ten tasks spanning combinational logic, sequential control, on-chip buses, CDC, cache design, a five-stage CPU, and multi-precision NPU matrix multiplication. Agents deliver RTL, a runnable verification environment, and PPA exploration records. The common physical target is 1000 ps / 1 GHz. PPA baselines become active task by task after their release gates pass; T01 through T09 are qualified, while the tool image and suite-wide release evidence are still being frozen.

| ID | Task | Time limit |
| --- | --- | ---: |
| T01 | 8-bit serial-in/parallel-out shift register | 45 min |
| T02 | SerDes RX comma aligner | 90 min |
| T03 | Parameterized synchronous FIFO | 2 h |
| T04 | APB4 timer peripheral | 3 h |
| T05 | ready/valid round-robin arbiter | 4 h |
| T06 | Asynchronous FIFO | 6 h |
| T07 | AXI4-Lite to APB4 bridge | 8 h |
| T08 | Direct-mapped write-back cache | 12 h |
| T09 | RV32I five-stage pipelined CPU | 24 h |
| T10 | 16×16 streaming multi-precision systolic-array matrix multiplication | 48 h |

## Entry points

- [Task packages](tasks/): frozen task cards, task-specific acceptance plans, public artifacts, and machine-readable metadata.
- [Shared task rules](README.md#共享任务规则) and [shared acceptance rules](README.md#通用验收规则).
- [Verification and delivery contract](README.md#验证与交付契约): submission layout, fixed DUT interfaces, and independent evaluation.
- [Public executable checks](../evaluator/README.en.md): task-specific port-level smoke checks.
- [Evaluation methodology](README.md#评测与评分方法) and [PPA methodology](README.md#ppa-测量与评分).
- [Environment setup](../env/README.en.md) and the vendored [ASAP7 platform](../vendor/README.en.md).

Run `python3 benchmark/validate_spec.py` for a local consistency check. Create a task-only public workspace with `python3 benchmark/prepare_trial.py T04 /path/to/empty/T04`. Each evaluation run starts in a new conversation and an empty workspace with the same task material, model configuration, tool environment, and timing boundary.

The repository evaluates functional correctness, open-flow PPA estimates, completion time, and verification-delivery quality. It does not claim tapeout signoff, analog validation, or RISC-V certification. T01 is a modified derivative of NVIDIA CVDP material; its attribution and license are listed in [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).
