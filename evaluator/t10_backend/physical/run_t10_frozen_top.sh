#!/usr/bin/env bash
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)/env.sh"
set -euo pipefail
t10_init_scratch

backend_root=${T10_BACKEND_ROOT}
orfs_root=${T10_ORFS_ROOT}
rtl=${T10_REFERENCE_RTL}
config=$backend_root/physical/t10_frozen_top/config.mk
expected_rtl_sha=0c7646d7019e45477582faba0605f1c3ba557810a61cb617844aeeb24b632622
seed=${T10_LAYOUT_SEED:-11}
target=${1:-baseline}
if [[ $target == baseline ]]; then
  make_targets=(route do-finish)
elif [[ $target == hier_probe ]]; then
  make_targets=(do-4_1_cts do-4_cts do-5_1_grt)
elif [[ $target == place_probe ]]; then
  make_targets=(3_4_place_resized)
elif [[ $target == cts_resume ]]; then
  make_targets=(do-4_1_cts)
elif [[ $target == grt_resume ]]; then
  make_targets=(do-5_1_grt)
else
  make_targets=("$target")
fi
variant=${T10_FLOW_VARIANT:-ic_t10_frozen_top_v46_directmesh_tilev33_m7_wc_p1000_seed${seed}}
log_root=${T10_LOG_ROOT:-${T10_SCRATCH_ROOT}/t10_frozen_top}
log=$log_root/${variant}_${target}.log

: "${T10_TILE_LEF:=$orfs_root/flow/results/asap7/t10_reference_tile_4x4/ic_t10_frozen_tile_v33_directmesh_pev16pg_m7_wc_p1000_seed${seed}/t10_reference_tile_4x4_m7.lef}"
: "${T10_TILE_LIB:=$orfs_root/flow/results/asap7/t10_reference_tile_4x4/ic_t10_frozen_tile_v33_directmesh_pev16pg_m7_wc_p1000_seed${seed}/t10_reference_tile_4x4_m7.lib}"
test "$(sha256sum "$rtl" | awk '{print $1}')" = "$expected_rtl_sha"
t10_require_file "$config"
t10_require_file "$T10_TILE_LEF"
t10_require_file "$T10_TILE_LIB"
[[ "$T10_TILE_LEF" == *"seed${seed}"* ]]
[[ "$T10_TILE_LIB" == *"seed${seed}"* ]]
source "$backend_root/physical/t10_acquire_openroad_slot.sh"
mkdir -p "$log_root"
{
  printf 'variant=%s\ntarget=%s\nlog=%s\nrtl_sha256=%s\nlayout_seed=%s\n' \
    "$variant" "$target" "$log" "$expected_rtl_sha" "$seed"
  sha256sum "$T10_TILE_LEF" "$T10_TILE_LIB"
} | tee "$log_root/ACTIVE_RUN"
cd "$orfs_root/flow"
export T10_LAYOUT_SEED T10_TILE_LEF T10_TILE_LIB
if [[ $target == hier_probe || $target == cts_resume ]]; then
  results_dir=$orfs_root/flow/results/asap7/npu_systolic_matmul_16x16/$variant
  if [[ ! -s $results_dir/3_4_place_resized.odb ]]; then
    seed_variant=${T10_TOP_PLACEMENT_VARIANT:-ic_t10_frozen_top_v46_directmesh_tilev33_m7_wc_p1000_seed${seed}}
    seed_results=$orfs_root/flow/results/asap7/npu_systolic_matmul_16x16/$seed_variant
    placement_odb=$seed_results/3_4_place_resized.odb
    if [[ -s $seed_results/3_5_place_dp.odb ]]; then
      placement_odb=$seed_results/3_5_place_dp.odb
    fi
    if [[ ${T10_REQUIRE_LEGAL_PLACEMENT:-0} == 1 ]]; then
      t10_require_file "$seed_results/3_5_place_dp.odb"
    fi
    t10_require_file "$placement_odb"
    t10_require_file "$seed_results/2_floorplan.sdc"
    mkdir -p "$results_dir"
    cp --reflink=auto "$placement_odb" "$results_dir/3_4_place_resized.odb"
    cp "$seed_results/2_floorplan.sdc" "$results_dir/2_floorplan.sdc"
  fi
  t10_require_file "$results_dir/3_4_place_resized.odb"
  t10_require_file "$results_dir/2_floorplan.sdc"
  cp --reflink=auto "$results_dir/3_4_place_resized.odb" "$results_dir/3_place.odb"
  cp "$results_dir/2_floorplan.sdc" "$results_dir/3_place.sdc"
fi
nice -n 10 make \
  DESIGN_CONFIG="$config" \
  FLOW_VARIANT="$variant" \
  OPENROAD_EXE="${T10_OPENROAD_EXE:-"${T10_OPENROAD_EXE}"}" \
  YOSYS_EXE="${T10_YOSYS_EXE}" \
  NUM_CORES=${T10_NUM_CORES:-4} \
  "${make_targets[@]}" >"$log" 2>&1
