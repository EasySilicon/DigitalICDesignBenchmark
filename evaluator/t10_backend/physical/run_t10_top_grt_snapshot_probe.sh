#!/usr/bin/env bash
set -euo pipefail
private_root=/home/reefshark/research/agent_os/ic_bcmk_eval_private
orfs_root=${T10_ORFS_ROOT:-/mnt/ubu_3T/ic_bcmk_orfs_asap7}
seed=${T10_LAYOUT_SEED:-11}
source_variant=${T10_SOURCE_VARIANT:-ic_t10_frozen_top_v72_tilev54_gcell60_m7_wc_p1000_seed${seed}}
variant=${T10_FLOW_VARIANT:-ic_t10_frozen_top_v73_tilev54_gcell60_diagnostic_m7_wc_p1000_seed${seed}}
source_dir=$orfs_root/flow/results/asap7/npu_systolic_matmul_16x16/$source_variant
result_dir=$orfs_root/flow/results/asap7/npu_systolic_matmul_16x16/$variant
log_root=/mnt/ubu_3T/ic_bcmk_scratch/t10_frozen_top
tool_root=/mnt/ubu_3T/ic_bcmk_scratch/t10_tools/openroad_gcell60
test -s "$source_dir/4_cts_pin_access.odb.sha256"
test -s "$source_dir/4_cts_pin_access.receipt"
test -s "$source_dir/4_cts_pin_access.sdc"
mkdir -p "$result_dir"
python3 - "$source_dir" "$log_root/${source_variant}_grt_resume.log" "$result_dir" "$tool_root" "${T10_EXPECT_INSTANCE_COUNT:-191281}" <<'PY'
import hashlib,json,re,sys
from pathlib import Path
source,log,result,tool=map(Path,sys.argv[1:5])
expected_count=int(sys.argv[5])
odb=source/'4_cts_pin_access.odb'
actual=hashlib.file_digest(odb.open('rb'),'sha256').hexdigest()
assert actual==(source/'4_cts_pin_access.odb.sha256').read_text().split()[0]
receipt=dict(line.split('=',1) for line in (source/'4_cts_pin_access.receipt').read_text().splitlines())
assert receipt=={'native_pin_access_completed':'1','gcell_dbu':'2280','instance_count':str(expected_count)}
if expected_count != 191281:
    repair=json.loads((source/'clock_channel_repair.json').read_text())
    assert repair['instance_count']==expected_count and repair['old_instances_unchanged']
    assert repair['original_clock_loads_preserved'] and repair['tile_macro_count']==16
    assert json.loads((source/'cell_overlap_check.json').read_text())['passed']
native_log=log.read_text()
assert re.search(r'#stdCellPinNoAp\s*=\s*0\s*\n',native_log)
assert re.search(r'#macroNoAp\s*=\s*0\s*\n',native_log)
assert 'Complete pin access.' in native_log and 'T10_PIN_ACCESS_CHECKPOINT' in native_log
manifest=json.loads((tool/'manifest.json').read_text())
assert manifest==json.loads((source/'diagnostic_tool.json').read_text())
assert hashlib.file_digest((tool/'openroad-gcell60').open('rb'),'sha256').hexdigest()==manifest['executable_sha256']
evidence={'diagnostic_only':True,'checkpoint':str(odb),'checkpoint_sha256':actual,
          'source_log':str(log),'source_log_sha256':hashlib.sha256(native_log.encode()).hexdigest(),
          'native_pin_access_completed':True,'standard_cell_pins_without_access':0,
          'macro_pins_without_access':0,'gcell_dbu':2280,'instance_count':expected_count,
          'tool_sha256':manifest['executable_sha256']}
(result/'verified_pin_access_resume.json').write_text(json.dumps(evidence,indent=2)+'\n')
PY
cp --reflink=auto "$source_dir/4_cts_pin_access.odb" "$result_dir/4_1_cts.odb"
cp --reflink=auto "$source_dir/4_cts_pin_access.odb" "$result_dir/4_cts.odb"
cp "$source_dir/4_cts_pin_access.sdc" "$result_dir/4_cts.sdc"
cp "$source_dir/diagnostic_tool.json" "$result_dir/diagnostic_tool.json"
export T10_FLOW_VARIANT=$variant
export T10_OPENROAD_EXE=$tool_root/openroad
export T10_REFERENCE_GRID_PROBE=1
export T10_EXPECT_GCELL_DBU=2280
export T10_RESUME_VERIFIED_PIN_ACCESS=1
export T10_PROBE_CONGESTION_ITERATIONS=${T10_PROBE_CONGESTION_ITERATIONS:-3}
export T10_MIN_AVAILABLE_GIB=80
export T10_NUM_CORES=2
ulimit -v 73400320
set +e
"$private_root/physical/run_t10_top_grt_probe.sh"
status=$?
set -e
printf '%s\n' "$status" > "$result_dir/grt_probe.exit"
for checkpoint in 5_global_route_topology.odb 5_1_grt.odb; do
  if [[ -s $result_dir/$checkpoint ]]; then
    sha256sum "$result_dir/$checkpoint" > "$result_dir/${checkpoint}.sha256"
  fi
done
printf 'T10_FULL_TOP_DIAGNOSTIC_EXIT=%s\n' "$status"
exit "$status"
