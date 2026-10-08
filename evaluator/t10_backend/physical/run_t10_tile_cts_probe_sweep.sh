#!/usr/bin/env bash
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)/env.sh"
set -euo pipefail
t10_init_scratch

backend_root=${T10_BACKEND_ROOT}
orfs_root=${T10_ORFS_ROOT}
design=t10_reference_tile_4x4
seed=${T10_LAYOUT_SEED:-11}
source_variant=ic_t10_frozen_tile_v33_directmesh_pev16pg_m7_wc_p1000_seed${seed}
source_dir=$orfs_root/flow/results/asap7/$design/$source_variant

run_probe() {
  local variant=$1
  local args=$2
  local result_dir=$orfs_root/flow/results/asap7/$design/$variant
  mkdir -p "$result_dir"
  cp --reflink=auto "$source_dir/3_place.odb" "$result_dir/3_place.odb"
  cp "$source_dir/3_place.sdc" "$result_dir/3_place.sdc"
  T10_SKIP_CTS_REPAIR_TIMING=1 \
  T10_CTS_ARGS_OVERRIDE="$args" \
  T10_FLOW_VARIANT="$variant" \
    "$backend_root/physical/run_t10_frozen_tile.sh" cts_resume
}

base='-sink_clustering_enable -repair_clock_nets -apply_ndr half'
run_probe "ic_t10_frozen_tile_v36_cts_d50_m2d100_probe_m7_wc_p1000_seed${seed}" \
  "$base -distance_between_buffers 50 -macro_clustering_size 2 -macro_clustering_max_diameter 100"
run_probe "ic_t10_frozen_tile_v37_cts_d200_m2d100_probe_m7_wc_p1000_seed${seed}" \
  "$base -distance_between_buffers 200 -macro_clustering_size 2 -macro_clustering_max_diameter 100"
run_probe "ic_t10_frozen_tile_v38_cts_d100_macroauto_probe_m7_wc_p1000_seed${seed}" \
  "$base -distance_between_buffers 100"
run_probe "ic_t10_frozen_tile_v39_cts_d100_m4d800_probe_m7_wc_p1000_seed${seed}" \
  "$base -distance_between_buffers 100 -macro_clustering_size 4 -macro_clustering_max_diameter 800"
run_probe "ic_t10_frozen_tile_v40_cts_d100_m1d1_probe_m7_wc_p1000_seed${seed}" \
  "$base -distance_between_buffers 100 -macro_clustering_size 1 -macro_clustering_max_diameter 1"
run_probe "ic_t10_frozen_tile_v41_cts_d100_m2d100_derate50_probe_m7_wc_p1000_seed${seed}" \
  "$base -distance_between_buffers 100 -macro_clustering_size 2 -macro_clustering_max_diameter 100 -delay_buffer_derate 0.5"

python3 - "$orfs_root/flow/logs/asap7/$design" <<'PY'
import glob
import json
import os
import sys

root = sys.argv[1]
for path in sorted(glob.glob(os.path.join(root, "ic_t10_frozen_tile_v*_probe_m7_wc_p1000_seed*", "4_1_cts.json"))):
    with open(path, encoding="utf-8") as stream:
        data = json.load(stream)
    print("T10_CTS_PROBE", os.path.basename(os.path.dirname(path)),
          data.get("cts__timing__setup__ws"),
          data.get("cts__timing__setup__tns"),
          data.get("cts__timing__hold__ws"),
          data.get("cts__clock__skew__setup"),
          data.get("cts__timing__fmax"))
PY
