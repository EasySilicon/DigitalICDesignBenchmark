#!/usr/bin/env bash
set -euo pipefail
private_root=/home/reefshark/research/agent_os/ic_bcmk_eval_private
orfs_root=/mnt/ubu_3T/ic_bcmk_orfs_asap7
variant=${T10_FLOW_VARIANT:-ic_t10_frozen_top_v74_tilev54_gcell60_backbone_m7_wc_p1000_seed11}
result_dir=$orfs_root/flow/results/asap7/npu_systolic_matmul_16x16/$variant
platform=$orfs_root/flow/platforms/asap7
tool_root=/mnt/ubu_3T/ic_bcmk_scratch/t10_tools/openroad_gcell60
log=/mnt/ubu_3T/ic_bcmk_scratch/t10_frozen_top/${variant}_retime_saved_route.log
test -s "$result_dir/5_1_grt.odb.sha256"
python3 - "$result_dir" "$tool_root" <<'PY'
import hashlib,json,sys
from pathlib import Path
result,tool=map(Path,sys.argv[1:])
odb=result/'5_1_grt.odb'
assert hashlib.file_digest(odb.open('rb'),'sha256').hexdigest()==(result/'5_1_grt.odb.sha256').read_text().split()[0]
manifest=json.loads((result/'diagnostic_tool.json').read_text())
assert hashlib.file_digest((tool/'openroad-gcell60').open('rb'),'sha256').hexdigest()==manifest['executable_sha256']
PY
libs=()
for pattern in '*_AO_RVT_SS*' '*_INVBUF_RVT_SS*' '*_OA_RVT_SS*' '*_SEQ_RVT_SS*' '*_SIMPLE_RVT_SS*' '*_INVBUF_SLVT_SS*'; do
  while IFS= read -r path; do libs+=("$path"); done < <(find "$platform/lib/NLDM" -maxdepth 1 -name "$pattern" -type f)
done
[[ ${#libs[@]} == 6 ]]
libs+=("$orfs_root/flow/results/asap7/t10_reference_tile_4x4/ic_t10_frozen_tile_v54_onehot_slvtclk_wideclk_grt_m7_wc_p1000_seed11/t10_reference_tile_4x4_wc.lib")
export T10_RETIME_LIBS="${libs[*]}"
export T10_RETIME_ODB=$result_dir/5_1_grt.odb
export T10_RETIME_SDC=$result_dir/5_1_grt.sdc
export T10_RETIME_SEGMENTS=$result_dir/route_topology.segments
export T10_RETIME_SETRC=$platform/setRC.tcl
# Keep the original diagnostic intact; write the corrected macro-inclusive
# audit to a separate subdirectory until comparison proves faithful replay.
export RESULTS_DIR=$result_dir/saved_route_retime
export REPORTS_DIR=$orfs_root/flow/reports/asap7/npu_systolic_matmul_16x16/$variant/saved_route_retime
export T10_REFERENCE_GRID_PROBE=1
mkdir -p "$RESULTS_DIR" "$REPORTS_DIR"
source "$private_root/physical/t10_acquire_openroad_slot.sh"
ulimit -v 50331648
/usr/bin/time -v nice -n 10 "$tool_root/openroad" -no_init -exit -threads 2 \
  "$private_root/physical/t10_frozen_top/retime_route_checkpoint.tcl" \
  > "$log" 2>&1
printf 'T10_FULL_TOP_SAVED_ROUTE_RETIME_PASS %s\n' "$REPORTS_DIR"
