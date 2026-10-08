# Historical T10 physical experiments

Source `../env.sh` (relative to this directory) before running the examples.
Their artifact names and original hash guards are preserved; use the backend
[configuration guide](../README.md) for current path defaults and prerequisites.

# T10 sparse legalization experiment

OpenROAD's standard detailed placement and `check_placement` both exceed the
32 GiB task limit on the 75%-utilization 16×16 T10 floorplan, including an
unresized no-tap global-placement database. The two Python scripts here use
OpenROAD's `-python` ODB API to place 270-DBU-high ASAP7 standard cells on
macro-cut, 54-DBU-pitch row segments and to check the output independently.

Run with the same OpenROAD build used for the physical flow:

```sh
openroad -python -exit -no_init -no_splash \
  physical/t10_sparse_legalize.py input.odb output.odb legalize.json
openroad -python -exit -no_init -no_splash \
  physical/t10_sparse_check.py output.odb check.json
```

For the valid-only-reset T10 placement-repair ODB, the legalizer placed
577,345 movable cells across 391,383 row segments in 154 seconds. The
separate checker found zero cell overlaps, macro overlaps, or site/orientation
errors. Evidence: `../qualification/T10_SPARSE_LEGALIZE.json` and
`../qualification/T10_SPARSE_LEGALIZE_CHECK.json`.

This is an experimental geometry step. It has not passed tap/endcap insertion,
power connectivity, routing DRC, extracted setup/hold, or multiple seeds.
Neither this ODB nor its timing is a released T10 PPA result.

With the same estimated-placement RC, the legalized ODB's worst synchronous
slack was -10580.10 ps, versus -6818.33 ps on the unlegalized repaired ODB.
The larger cell displacement damaged critical paths, so this algorithm needs
timing-aware refinement before even placement-only use. Evidence:
`../qualification/T10_SPARSE_LEGALIZED_PLACEMENT_STA.log`.

## T10 routed macro LEF with M8 power access

The routed PE and result-bank macro views used by the 4×4 tile need the M8
special-wire power shapes as supply pins. An ordinary bloated abstract blocks
all of M9, while a detailed abstract contains millions of lower-layer OBS
rectangles. Generate the hybrid view from the **final routed ODB**:

```sh
ODB_INPUT=/path/to/6_final.odb LEF_OUTPUT=/path/to/detailed.lef \
  openroad -exit -no_init physical/t10_export_detailed_lef.tcl
ODB_INPUT=/path/to/6_final.odb PG_OUTPUT=/path/to/m8_pg.txt \
  openroad -exit -no_init physical/t10_extract_macro_pg.tcl
python3 physical/t10_build_macro_lef.py \
  /path/to/detailed.lef /path/to/m8_pg.txt /path/to/macro_hybrid.lef
```

The Python step fills RVTN/RVTP/M1–M7 OBS over the whole macro and retains
the routed M8/M9 geometry, subtracting only actual VDD/VSS pin regions from
their OBS. It rejects missing or out-of-bounds supply shapes. The three steps
reproduced the earlier PG-connected PE macro's detailed LEF, M8 PG rectangle
file, and hybrid LEF byte-for-byte; hashes are in
`../qualification/T10_PE_MACRO_LEF_REPRODUCTION.json`. Each new macro still
requires a fresh tile floorplan and independent VDD/VSS
`check_power_grid` checks before placement or routing.

## Frozen PE checkpointed detailed routing

The exact frozen PE is large enough that a normal OpenROAD detailed-routing
invocation can lose a long search-and-repair run when the process must yield
the machine. Use the bounded checkpoint driver instead:

```sh
# Inspect the last completed stage without starting OpenROAD.
physical/run_t10_frozen_pe_checkpoint_route.sh status

# Route from the frozen seed's 5_1_grt.odb and save the first bounded stage.
T10_LAYOUT_SEED=11 \
  physical/run_t10_frozen_pe_checkpoint_route.sh initial

# Continue from the last committed ODB. Each successful call creates a new
# ODB, DRC report, maze log, OpenROAD log, and hash-bound state.json.
T10_LAYOUT_SEED=11 T10_DRT_ITERATIONS=1 \
  physical/run_t10_frozen_pe_checkpoint_route.sh repair

# An ODB does not contain TritonRoute's optimization-iteration state. If a
# repair reproduces the same DRC count, restart at GRT and keep the requested
# iterations in one OpenROAD process. Earlier checkpoints remain untouched.
T10_LAYOUT_SEED=11 T10_DRT_ITERATIONS=20 \
  physical/run_t10_frozen_pe_checkpoint_route.sh restart

# This refuses unless the latest completed stage reports zero DRC markers.
T10_LAYOUT_SEED=11 \
  physical/run_t10_frozen_pe_checkpoint_route.sh promote
```

The runner checks Linux `MemAvailable` immediately before every OpenROAD
stage and returns status 75 when less than 50 GiB is available. Override the
threshold only for a controlled experiment with `T10_MIN_AVAILABLE_GIB`.
OpenROAD runs at nice level 10, defaults to four threads, and has a 30 GiB
virtual-memory limit. An interrupted or failed stage never replaces
`state.json`; rerunning `repair` therefore starts from the last complete ODB.
A private `flock` prevents two instances of this T10 route from sharing the
same checkpoint directory. The driver does not stop or signal other jobs.

After all three seeds have complete PE, tile, top, and power evidence, build
the hash-bound release record with:

```sh
python3 physical/t10_make_asap7_manifest.py \
  ${T10_ASAP7_PLATFORM} \
  qualification/T10_ASAP7_PLATFORM_MANIFEST.json

python3 physical/t10_assemble_ppa_evidence.py \
  --evidence-root ${T10_SCRATCH_ROOT}/t10_baseline \
  --workload-manifest qualification/T10_POWER_WORKLOAD_SEED20260925/manifest.json \
  --hierarchy-report qualification/T10_PPA_HIERARCHY_20261003.json \
  --rtl refs/T10/rtl/npu_systolic_matmul_16x16.sv \
  --filelist refs/T10/rtl/files.f \
  --asap7-manifest qualification/T10_ASAP7_PLATFORM_MANIFEST.json \
  --orfs-root ${T10_ORFS_ROOT} \
  --yosys ${T10_YOSYS_EXE} \
  --openroad ${T10_OPENROAD_EXE} \
  --output qualification/T10_PPA_BASELINE.json \
  --qualification-output qualification/T10_PPA_BASELINE_GATE.json
```

The evidence root must contain `seed11`, `seed29`, and `seed47`; each seed
directory must contain `pe.json`, `tile.json`, `top.json`, and `power.json`.
The assembler calculates the hierarchical delay and three-seed medians, then
runs `t10_ppa_qualify.py`. It writes the release record atomically only after
every artifact hash and all timing, DRC, activity, hierarchy, and arithmetic
gates pass.
