# T10 backend development

This directory contains the PE, 4x4-tile and complete 16x16-DUT backend sources
imported from `ic_bcmk_eval_private` commit `e9da70a`. Runtime paths now follow
this checkout and explicit environment overrides. Reference sources are in
[../reference/T10/](../reference/T10/README.md); the latest distributed-egress
candidate is in `../reference/T10_candidates/v123/rtl/`.

## Configure and check

From the repository root:

```bash
source evaluator/t10_backend/env.sh
python3 evaluator/t10_backend/doctor.py --profile paths
python3 evaluator/t10_backend/doctor.py --profile ppa
python3 evaluator/t10_backend/test_portability.py -v
```

Python tools and shell runners can also be invoked by absolute path from any
working directory. Shell runners source `env.sh` automatically. Source it
manually before invoking a Tcl driver directly in OpenROAD. Make configs load
`config.mk` and derive the backend location when invoked directly; runners
export that location so copied floorplan configs resolve it correctly.

| Variable | Default | Purpose |
| --- | --- | --- |
| `T10_BACKEND_ROOT` | This directory | Backend drivers/configuration |
| `T10_REPO_ROOT` | Detected checkout root | Public benchmark checkout |
| `T10_EVALUATOR_ROOT` | `$T10_REPO_ROOT/evaluator` | Evaluator assets |
| `T10_REFERENCE_RTL` | `evaluator/reference/T10/rtl/npu_systolic_matmul_16x16.sv` | Selected, hash-checked source |
| `T10_ORFS_ROOT` | `$T10_REPO_ROOT/third_party/OpenROAD-flow-scripts` | ORFS checkout |
| `T10_ASAP7_PLATFORM` | `$T10_REPO_ROOT/vendor/asap7` | Shared, checked-in process platform |
| `T10_SCRATCH_ROOT` | `$T10_REPO_ROOT/work/t10_backend` | Logs, temporary files and experiment artifacts |
| `T10_OPENROAD_EXE` | `openroad` found on PATH | OpenROAD executable; `T10_OPENROAD` is a legacy alias |
| `T10_YOSYS_EXE` | `yosys` found on PATH | Yosys executable |
| `T10_QUALIFICATION_ROOT` | `$T10_EVALUATOR_ROOT` | Independent streaming acceptance package |
| `T10_OPENROAD_LOCK` | `$T10_SCRATCH_ROOT/t10_openroad.lock` | One-process admission lock |

Set overrides **before** sourcing the environment or invoking a runner. For
example, set `T10_ORFS_ROOT` to your installed ORFS checkout and
`T10_SCRATCH_ROOT` to a disk with sufficient space. `PLATFORM_DIR` is exported
from `T10_ASAP7_PLATFORM` so ORFS and the standalone drivers use the same PDK.
Keep ORFS/build/platform paths free of whitespace: several upstream Make and
Liberty-list interfaces use whitespace-separated file lists. Shell executable
and single input/output arguments are quoted.

See [the environment guide](../../env/README.md) for tool installation, locked
ORFS revision and the OpenROAD 26Q2 compatibility patch. Python needs standard
library support; the functional evaluator additionally uses the dependencies
listed in that guide. OpenROAD must provide its Python ODB bindings for Python
geometry/ECO tools. Bash, GNU make/time, `flock`, and standard Linux process and
memory utilities are used by the runners.

## Inputs required by individual experiments

Path portability does not recreate generated models or qualify old experiments.
The historical runners select named PE/tile checkpoints and enforce their
original source/receipt hashes. Provide the matching ODB, SDC, macro LEF/Liberty
and qualification receipts for that experiment. If selecting another stored
reference version, set `T10_REFERENCE_RTL` to the matching source; hash guards
are retained. Per-run overrides such as `T10_PE_LEF`, `T10_PE_LIB`,
`T10_TILE_LEF`, `T10_TILE_LIB` and `T10_CHECK_INPUT_ODB` remain available.

`doctor.py --input path/to/model.lef` checks additional generated inputs without
launching EDA. `--profile ppa` checks tools, ORFS and the platform; it does not
claim all experiment artifacts are present. Missing required shell inputs
report their resolved paths.

The two full-stream qualification helpers require `runner_t10_stream.py` and
its independent evaluator package. Configure its directory explicitly with
`T10_QUALIFICATION_ROOT`; use `doctor.py --profile qualification` to check the
package files. No sibling private checkout is searched or assumed. The PPA
record validator `physical/t10_ppa_qualify.py` is included locally, so evidence
assembly has no external private-module dependency.

The historical diagnostic GCell tool generator requires an explicitly selected,
hash-matching installation: `physical/openroad_grid_probe/make_probe.py OUTPUT
--openroad-prefix PREFIX`. It never patches the installed executable. Its
output remains diagnostic-only and cannot establish a released baseline.

## Publication and PPA status

Reference implementations and evaluators may be public under this benchmark's
policy. Keep them and these backend sources outside candidate containers and
accessible mounts; `prepare_trial.py` does not copy them to task workspaces.
Full filesystem access defeats directory-only isolation. Public source exposure
also needs to be considered when interpreting model comparisons.

The complete-DUT 1 GHz PPA baseline remains unqualified. Latest v127 placement
parasitics with ideal parent clocks report setup WNS -14106.48 ps and hold WNS
-363.59 ps; these are not CTS/post-route signoff measurements. See
[the path analysis](physical/T10_TOP_TIMING_CLOSURE_20261006.md). Exploratory
alternative cells, timing budgets and sparse placements are historical probes;
this path cleanup changes no timing, clock-layer, functional or grading rule.

`SNAPSHOT.json` preserves original imported SHA-256 values in `sha256`, records
current relocated versions in `current_sha256`, and lists added support files.
RTL bytes are unchanged. No physical baseline is promoted by this cleanup.
