# Environment and dependencies

[中文](README.md)

This page describes staged environment preparation. The repository provides specification validation, public port-level smoke checks, and 45 generated ACT4 RV32I/Zicsr ELF artifacts. A formal benchmark release additionally freezes all task evaluators, reference implementations, PPA parameters, and a single tool-image digest. `check_env.py` checks for dependencies; it is not a release-gate substitute.

Use Linux x86-64, Docker/OCI where possible, and at least 16 vCPU, 32 GiB RAM, and 100 GiB of disk.

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
.venv/bin/python benchmark/validate_spec.py --verify-source
```

Without network access, omit `--verify-source`. For a full local report after installing tools:

```bash
.venv/bin/python env/check_env.py --profile all \
  --orfs-root /path/to/OpenROAD-flow-scripts --act4-root /path/to/riscv-arch-test \
  --verify-platform-hashes
```

Clone the ORFS and ACT4 revisions in `benchmark/sources.lock.yaml`; point ORFS's `PLATFORM_DIR` to this repository's `vendor/asap7`. A production evaluation image must pin every tool/package revision, the ASAP7 hashes, and its OCI digest. See the Chinese document for detailed Ubuntu installation notes and the ORFS compatibility patch used for local exploration.
