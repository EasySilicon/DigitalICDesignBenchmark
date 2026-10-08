#!/usr/bin/env bash
set -euo pipefail
private_root=/home/reefshark/research/agent_os/ic_bcmk_eval_private
export T10_FLOW_VARIANT=${T10_CHECK_VARIANT:-ic_t10_candidate_top_v98_transport_spatial_m7_wc_p1000_seed11}
result=/mnt/ubu_3T/ic_bcmk_orfs_asap7/flow/results/asap7/npu_systolic_matmul_16x16/$T10_FLOW_VARIANT
input=${T10_CHECK_INPUT_ODB:-$result/3_5_place_spatial_pending.odb}
python3 - "$result" "$input" <<'PY'
import json,sys
from pathlib import Path
p=Path(sys.argv[1]); input=Path(sys.argv[2])
if (p/'spatial_placement.json').exists():
    d=json.loads((p/'spatial_placement.json').read_text())
    assert d['netlist_and_macro_geometry_unchanged']
else:
    d=json.loads((p/'data_control_repair.json').read_text())
    assert d['original_geometry_and_clock_unchanged'] and d['independent_positive_chain_equivalence_passed']
assert d['tile_macros']==16 and input.is_file()
PY
export T10_MIN_AVAILABLE_GIB=80
export T10_PLACEMENT_INPUT_ODB=$input
export T10_NATIVE_CHECKED_ODB_NAME=3_5_place_native_checked.odb
export T10_PLACEMENT_VALIDATED_ODB_NAME=3_5_place_validated.odb
ulimit -v 73400320
bash "$private_root/physical/run_t10_validate_top_placement.sh"
if [[ ${T10_SKIP_PLACEMENT_TIMING:-0} == 1 ]]; then
  printf 'T10_FULL_DUT_SPATIAL_NATIVE_ONLY_FINISHED\n'
  exit 0
fi
export T10_MIN_AVAILABLE_GIB=50
export T10_CLOCK_ESTIMATE_ODB=$result/3_5_place_native_checked.odb
export T10_PLACEMENT_TIMING_MODE=placement_ideal_clocks
bash "$private_root/physical/run_t10_top_clock_estimate.sh"
printf 'T10_FULL_DUT_SPATIAL_NATIVE_AND_TIMING_FINISHED\n'
