#!/usr/bin/env bash
set -euo pipefail
private_root=/home/reefshark/research/agent_os/ic_bcmk_eval_private
orfs_root=${T10_ORFS_ROOT:-/mnt/ubu_3T/ic_bcmk_orfs_asap7}
seed=${T10_LAYOUT_SEED:-11}
version=${T10_PROBE_VERSION:-68}
variant=${T10_FLOW_VARIANT:-ic_t10_frozen_top_v${version}_tilev54_interval_legal_m7_wc_p1000_seed${seed}}
result_dir=$orfs_root/flow/results/asap7/npu_systolic_matmul_16x16/$variant
log_root=/mnt/ubu_3T/ic_bcmk_scratch/t10_frozen_top
input_odb=${T10_PLACEMENT_INPUT_ODB:-$result_dir/3_5_place_interval_probe.odb}
test -s "$input_odb"
source "$private_root/physical/t10_acquire_openroad_slot.sh"
export T10_AUDIT_ODB=$input_odb
export T10_AUDIT_CELL_BOXES=$log_root/${variant}_cell_boxes.tsv
export T10_PLACEMENT_CHECK_REPORT=$result_dir/placement_check.json
export T10_VALIDATED_ODB=$result_dir/${T10_NATIVE_CHECKED_ODB_NAME:-3_5_place_native_checked.odb}
/usr/bin/time -v nice -n 10 /home/reefshark/.local/bin/openroad \
  -no_init -exit "$private_root/physical/t10_validate_top_placement.tcl" \
  > "$log_root/${variant}_placement_validation.log" 2>&1
python3 "$private_root/physical/t10_check_top_cell_overlaps.py" \
  "$T10_AUDIT_CELL_BOXES" --report "$result_dir/cell_overlap_check.json"
cp --reflink=auto "$T10_VALIDATED_ODB" \
  "$result_dir/${T10_PLACEMENT_VALIDATED_ODB_NAME:-3_5_place_dp.odb}"
