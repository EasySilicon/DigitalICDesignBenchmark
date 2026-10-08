#!/usr/bin/env bash
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)/env.sh"
set -euo pipefail
t10_init_scratch
backend_root=${T10_BACKEND_ROOT}
export T10_FLOW_VARIANT=${T10_CHECK_VARIANT:-ic_t10_candidate_top_v98_transport_spatial_m7_wc_p1000_seed11}
result=${T10_ORFS_ROOT}/flow/results/asap7/npu_systolic_matmul_16x16/$T10_FLOW_VARIANT
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
bash "$backend_root/physical/run_t10_validate_top_placement.sh"
if [[ ${T10_SKIP_PLACEMENT_TIMING:-0} == 1 ]]; then
  printf 'T10_FULL_DUT_SPATIAL_NATIVE_ONLY_FINISHED\n'
  exit 0
fi
export T10_MIN_AVAILABLE_GIB=50
export T10_CLOCK_ESTIMATE_ODB=$result/3_5_place_native_checked.odb
export T10_PLACEMENT_TIMING_MODE=placement_ideal_clocks
bash "$backend_root/physical/run_t10_top_clock_estimate.sh"
printf 'T10_FULL_DUT_SPATIAL_NATIVE_AND_TIMING_FINISHED\n'
