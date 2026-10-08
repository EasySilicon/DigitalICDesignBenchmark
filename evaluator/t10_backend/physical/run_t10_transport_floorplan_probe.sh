#!/usr/bin/env bash
set -euo pipefail
private_root=/home/reefshark/research/agent_os/ic_bcmk_eval_private
flow=/mnt/ubu_3T/ic_bcmk_orfs_asap7/flow
variant=${T10_FLOW_VARIANT:-ic_t10_candidate_top_v97_pair_transport_synth_m7_wc_p1000_seed11}
result=$flow/results/asap7/npu_systolic_matmul_16x16/$variant
qualification=${T10_TRANSPORT_QUALIFICATION_ROOT:-/mnt/ubu_3T/ic_bcmk_scratch/t10_qualification/v96_pair_transport}
candidate=$qualification/rtl/npu_systolic_matmul_16x16.sv
test ! -e "$result/2_3_floorplan_tapcell.odb"
python3 - "$qualification" "$result" <<'PY'
import hashlib,json,sys
from pathlib import Path
q,result=map(Path,sys.argv[1:])
receipt=json.loads((q/'qualification.json').read_text())
proof=json.loads((result/'rtl_delta.json').read_text())
sha=hashlib.sha256((q/'rtl/npu_systolic_matmul_16x16.sv').read_bytes()).hexdigest()
assert receipt['qualification_passed'] and receipt['rtl_sha256']==sha==proof['candidate_sha256']
assert receipt['cases']==2752 and receipt['structure']['pe_instances']==256
assert proof['qualification_sha256']==hashlib.sha256((q/'qualification.json').read_bytes()).hexdigest()
PY
export T10_LAYOUT_SEED=11
tile=$flow/results/asap7/t10_reference_tile_4x4/ic_t10_frozen_tile_v54_onehot_slvtclk_wideclk_grt_m7_wc_p1000_seed11
export T10_TILE_LEF=$tile/t10_reference_tile_4x4_m7.lef
export T10_TILE_LIB=$tile/t10_reference_tile_4x4_wc.lib
source "$private_root/physical/t10_acquire_openroad_slot.sh"
mkdir -p "$result/floorplan_snapshot"
cp "$private_root/physical/t10_frozen_top/"{config.mk,macro_place.tcl,skip_floorplan_timing_reference.tcl,tapcell_reference.tcl} "$result/floorplan_snapshot/"
cp "$private_root/physical/t10_frozen_top/constraint.sdc" "$result/1_2_yosys.sdc"
sha256sum "$candidate" "$result/1_2_yosys.v" "$qualification/qualification.json" \
  "$result/1_2_yosys.sdc" "$T10_TILE_LEF" "$T10_TILE_LIB" "$result/floorplan_snapshot/"* > "$result/floorplan_inputs.sha256"
ulimit -v 50331648
cd "$flow"
nice -n 10 make DESIGN_CONFIG="$result/floorplan_snapshot/config.mk" \
  FLOW_VARIANT="$variant" VERILOG_FILES="$candidate" \
  MACRO_PLACEMENT_TCL="$result/floorplan_snapshot/macro_place.tcl" \
  PRE_FLOORPLAN_TCL="$result/floorplan_snapshot/skip_floorplan_timing_reference.tcl" \
  TAPCELL_TCL="$result/floorplan_snapshot/tapcell_reference.tcl" \
  YOSYS_EXE=/home/reefshark/.local/bin/yosys \
  OPENROAD_EXE=/home/reefshark/.local/bin/openroad NUM_CORES=2 \
  do-1_synth do-2_1_floorplan do-2_2_floorplan_macro do-2_3_floorplan_tapcell \
  > /mnt/ubu_3T/ic_bcmk_scratch/t10_frozen_top/${variant}_floorplan.log 2>&1
sha256sum "$result/2_3_floorplan_tapcell.odb" > "$result/2_3_floorplan_tapcell.odb.sha256"
printf 'T10_TRANSPORT_FLOORPLAN_FINISHED\n'
