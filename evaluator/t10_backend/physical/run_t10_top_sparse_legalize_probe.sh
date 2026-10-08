#!/usr/bin/env bash
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)/env.sh"
set -euo pipefail
t10_init_scratch
backend_root=${T10_BACKEND_ROOT}
orfs_root=${T10_ORFS_ROOT}
seed=${T10_LAYOUT_SEED:-11}
version=${T10_PROBE_VERSION:-68}
source_variant=${T10_TOP_PLACEMENT_VARIANT:-ic_t10_frozen_top_v63_tilev54_gpl010_resize010_m7_wc_p1000_seed${seed}}
variant=${T10_FLOW_VARIANT:-ic_t10_frozen_top_v${version}_tilev54_interval_legal_m7_wc_p1000_seed${seed}}
source_dir=$orfs_root/flow/results/asap7/npu_systolic_matmul_16x16/$source_variant
result_dir=$orfs_root/flow/results/asap7/npu_systolic_matmul_16x16/$variant
log_root=${T10_SCRATCH_ROOT}/t10_frozen_top
input_odb=${T10_PLACEMENT_SOURCE_ODB:-$source_dir/3_4_place_resized.odb}
input_sdc=${T10_PLACEMENT_SOURCE_SDC:-$source_dir/2_floorplan.sdc}
output_odb_name=${T10_LEGALIZED_ODB_NAME:-3_5_place_interval_probe.odb}
output_sdc_name=${T10_OUTPUT_SDC_NAME:-2_floorplan.sdc}
t10_require_file "$input_odb"
t10_require_file "$input_sdc"
source "$backend_root/physical/t10_acquire_openroad_slot.sh"
mkdir -p "$result_dir" "$log_root"
cp "$input_sdc" "$result_dir/$output_sdc_name"
printf 'variant=%s\ntarget=sparse_legalize\nsource=%s\n' \
  "$variant" "$input_odb" | tee "$log_root/ACTIVE_RUN"
(
  ulimit -v 16777216
  /usr/bin/time -v nice -n 10 "${T10_OPENROAD_EXE}" \
    -no_init -exit -python "$backend_root/physical/t10_sparse_channel_legalize.py" \
    "$input_odb" \
    "$result_dir/$output_odb_name" \
    "$result_dir/interval_placement.json" \
    --row-stride "${T10_ROW_STRIDE:-16}"
) > "$log_root/${variant}_sparse_legalize.log" 2>&1
