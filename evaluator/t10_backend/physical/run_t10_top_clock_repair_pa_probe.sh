#!/usr/bin/env bash
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)/env.sh"
set -euo pipefail
t10_init_scratch
# New buffers require fresh native PA. End at its atomic checkpoint, then
# release the process's PA allocations before routing in a separate stage.
backend_root=${T10_BACKEND_ROOT}
orfs_root=${T10_ORFS_ROOT}
variant=${T10_FLOW_VARIANT:-ic_t10_frozen_top_v76_tilev54_clockchannels_m7_wc_p1000_seed11}
result_dir=$orfs_root/flow/results/asap7/npu_systolic_matmul_16x16/$variant
tool_root=${T10_SCRATCH_ROOT}/t10_tools/openroad_gcell60
t10_require_file "$result_dir/4_cts.odb"
python3 - "$result_dir" "$tool_root" <<'PY'
import hashlib,json,sys
from pathlib import Path
r,t=map(Path,sys.argv[1:])
assert json.loads((r/'cell_overlap_check.json').read_text())['passed']
repair=json.loads((r/'clock_channel_repair.json').read_text())
assert repair['old_instances_unchanged'] and repair['original_clock_loads_preserved']
assert repair['tile_macro_count']==16 and repair['max_clock_branch_manhattan_um']<355
m=json.loads((t/'manifest.json').read_text())
assert m['diagnostic_only'] and hashlib.file_digest((t/'openroad-gcell60').open('rb'),'sha256').hexdigest()==m['executable_sha256']
PY
cp --reflink=auto "$result_dir/4_cts.odb" "$result_dir/4_1_cts.odb"
cp "$tool_root/manifest.json" "$result_dir/diagnostic_tool.json"
export T10_FLOW_VARIANT=$variant
export T10_OPENROAD_EXE=$tool_root/openroad
export T10_REFERENCE_GRID_PROBE=1
export T10_EXPECT_GCELL_DBU=2280
export T10_PROBE_STOP_AFTER_PIN_ACCESS=1
export T10_CLOCK_NDR_POLICY=backbone_only
export T10_MIN_AVAILABLE_GIB=80
export T10_NUM_CORES=2
ulimit -v 73400320
set +e
"$backend_root/physical/run_t10_top_grt_probe.sh"
status=$?
set -e
printf '%s\n' "$status" > "$result_dir/pa_probe.exit"
if [[ -s $result_dir/4_cts_pin_access.odb ]]; then
  sha256sum "$result_dir/4_cts_pin_access.odb" > "$result_dir/4_cts_pin_access.odb.sha256"
fi
exit "$status"
