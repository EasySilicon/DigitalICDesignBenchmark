# Environment and dependencies

[中文](README.md)

This page describes staged environment preparation. The repository provides specification validation, public port-level smoke checks, and 45 generated ACT4 RV32I/Zicsr ELF artifacts. T01–T09 evaluators, reference RTL, mutation generators, and 1 GHz PPA baselines are published and calibrated for task-level evaluation; they are not copied into contestant workspaces. A formal suite release still requires T10 qualification, the tool-image digest, and the remaining release evidence. `check_env.py` checks for dependencies; it is not a release-gate substitute.

Use Linux x86-64, Docker/OCI where possible, and at least 16 vCPU, 32 GiB RAM, and 100 GiB of disk.

Physical-design and Verilator builds can produce large temporary files. Point `TMPDIR` to a data disk with sufficient space, and keep the ORFS checkout there as well: ORFS writes its results, logs, and reports under its own `flow/` tree. Preserve active builds and the reports needed for baseline reproduction; reclaim superseded build directories only after retaining their configuration and result summaries.

| Layer | Required dependencies | Purpose |
| --- | --- | --- |
| Specification checks | Python 3.10+, PyYAML, jsonschema | Schema and source-lock validation |
| RTL preflight | Verilator, Yosys, C++ compiler, Python/cocotb | Compilation, simulation, and synthesis checks |
| ASAP7 PPA | Yosys, OpenROAD, GNU make, ORFS, vendored ASAP7 | Mapping, place/route, RC, timing, and power reports |
| CPU evaluation | RV32 bare-metal GCC/objdump, Sail 0.14.1, ACT4, uv, Ruby, Bundler | ELF generation and architectural reference traces |

From the repository root:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r env/requirements-spec.txt
.venv/bin/python env/check_env.py --profile spec
```


```bash
.venv/bin/python env/check_env.py --profile all \
  --orfs-root /path/to/OpenROAD-flow-scripts --act4-root /path/to/riscv-arch-test \
  --verify-platform-hashes
```

Clone the ORFS and ACT4 revisions in `benchmark/sources.lock.yaml`; point ORFS's `PLATFORM_DIR` to this repository's `vendor/asap7`. A production evaluation image must pin every tool/package revision, the ASAP7 hashes, and its OCI digest. See the Chinese document for detailed Ubuntu installation notes and the ORFS compatibility patch used for local exploration.

T08/T09 task-level freeze (2026-10-09): [T08 receipt](../benchmark/tasks/T08/FREEZE.json), [T09 receipt](../benchmark/tasks/T09/FREEZE.json). Run `python3 benchmark/freeze_tasks.py` from the repository root to verify specification, RTL, judge, scoring, baseline and portable evidence hashes. All six T09 archives have been regraded; untested T08 models remain null. Host-only receipts are excluded from candidate packages. T10 PPA and the suite-wide tool-image/release gates remain pending.
