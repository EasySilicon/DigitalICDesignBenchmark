#!/usr/bin/env bash
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)/env.sh"
set -euo pipefail
t10_init_scratch
# Complete 16x16 top. Isolated tool variant: diagnostic evidence only.
backend_root=${T10_BACKEND_ROOT}
orfs_root=${T10_ORFS_ROOT}
seed=${T10_LAYOUT_SEED:-11}
source_variant=${T10_SOURCE_VARIANT:-ic_t10_frozen_top_v71_tilev54_slvtclk_d200_wideclk_m7_wc_p1000_seed${seed}}
variant=${T10_FLOW_VARIANT:-ic_t10_frozen_top_v72_tilev54_gcell60_m7_wc_p1000_seed${seed}}
tool_root=${T10_SCRATCH_ROOT}/t10_tools/openroad_gcell60
source_dir=$orfs_root/flow/results/asap7/npu_systolic_matmul_16x16/$source_variant
results_dir=$orfs_root/flow/results/asap7/npu_systolic_matmul_16x16/$variant
t10_require_file "$source_dir/4_cts.odb"
t10_require_file "$source_dir/4_cts.sdc"
t10_require_file "$source_dir/cell_overlap_check.json"
test -x "$tool_root/openroad"
python3 - "$source_dir/cell_overlap_check.json" "$tool_root/manifest.json" "$tool_root/openroad-gcell60" <<'PY'
import hashlib,json,sys
with open(sys.argv[1]) as f: geometry=json.load(f)
assert geometry['passed'] and geometry['cell_overlap_pairs']==0
with open(sys.argv[2]) as f: tool=json.load(f)
assert tool['diagnostic_only'] is True
with open(sys.argv[3],'rb') as f: digest=hashlib.file_digest(f,'sha256').hexdigest()
assert digest==tool['executable_sha256']
PY
mkdir -p "$results_dir"
cp --reflink=auto "$source_dir/4_cts.odb" "$results_dir/4_1_cts.odb"
cp --reflink=auto "$source_dir/4_cts.odb" "$results_dir/4_cts.odb"
cp "$source_dir/4_cts.sdc" "$results_dir/4_cts.sdc"
cp "$tool_root/manifest.json" "$results_dir/diagnostic_tool.json"
{
  printf 'diagnostic_only=1\nsource_variant=%s\ngcell_pitches=60\n' "$source_variant"
  sha256sum "$source_dir/4_cts.odb" "$source_dir/4_cts.sdc"
} > "$results_dir/input_provenance.txt"
export T10_FLOW_VARIANT=$variant
export T10_OPENROAD_EXE=$tool_root/openroad
export T10_REFERENCE_GRID_PROBE=1
export T10_EXPECT_GCELL_DBU=2280
export T10_MIN_AVAILABLE_GIB=80
export T10_NUM_CORES=2
# Bound our own process; do not consume the host's final memory reserve.
ulimit -v 73400320
set +e
"$backend_root/physical/run_t10_top_grt_probe.sh"
status=$?
set -e
printf '%s\n' "$status" > "$results_dir/grt_probe.exit"
for checkpoint in 4_cts_pin_access.odb 5_global_route_topology.odb 5_1_grt.odb; do
  if [[ -s $results_dir/$checkpoint ]]; then
    sha256sum "$results_dir/$checkpoint" > "$results_dir/${checkpoint}.sha256"
  fi
done
printf 'T10_FULL_TOP_GCELL60_EXIT=%s\n' "$status"
exit "$status"
