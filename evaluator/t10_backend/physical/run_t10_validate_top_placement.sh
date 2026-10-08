#!/usr/bin/env bash
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)/env.sh"
set -euo pipefail
t10_init_scratch
backend_root=${T10_BACKEND_ROOT}
orfs_root=${T10_ORFS_ROOT}
seed=${T10_LAYOUT_SEED:-11}
version=${T10_PROBE_VERSION:-68}
variant=${T10_FLOW_VARIANT:-ic_t10_frozen_top_v${version}_tilev54_interval_legal_m7_wc_p1000_seed${seed}}
result_dir=$orfs_root/flow/results/asap7/npu_systolic_matmul_16x16/$variant
log_root=${T10_SCRATCH_ROOT}/t10_frozen_top
input_odb=${T10_PLACEMENT_INPUT_ODB:-$result_dir/3_5_place_interval_probe.odb}
t10_require_file "$input_odb"
source "$backend_root/physical/t10_acquire_openroad_slot.sh"
export T10_AUDIT_ODB=$input_odb
export T10_AUDIT_CELL_BOXES=$log_root/${variant}_cell_boxes.tsv
export T10_PLACEMENT_CHECK_REPORT=$result_dir/placement_check.json
export T10_VALIDATED_ODB=$result_dir/${T10_NATIVE_CHECKED_ODB_NAME:-3_5_place_native_checked.odb}
/usr/bin/time -v nice -n 10 "${T10_OPENROAD_EXE}" \
  -no_init -exit "$backend_root/physical/t10_validate_top_placement.tcl" \
  > "$log_root/${variant}_placement_validation.log" 2>&1
python3 "$backend_root/physical/t10_check_top_cell_overlaps.py" \
  "$T10_AUDIT_CELL_BOXES" --report "$result_dir/cell_overlap_check.json"
cp --reflink=auto "$T10_VALIDATED_ODB" \
  "$result_dir/${T10_PLACEMENT_VALIDATED_ODB_NAME:-3_5_place_dp.odb}"
