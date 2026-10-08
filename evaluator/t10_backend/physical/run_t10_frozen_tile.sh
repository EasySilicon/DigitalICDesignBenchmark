#!/usr/bin/env bash
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)/env.sh"
set -euo pipefail
t10_init_scratch

backend_root=${T10_BACKEND_ROOT}
orfs_root=${T10_ORFS_ROOT}
rtl=${T10_REFERENCE_RTL}
config=$backend_root/physical/t10_frozen_tile/config.mk
expected_rtl_sha=0c7646d7019e45477582faba0605f1c3ba557810a61cb617844aeeb24b632622
seed=${T10_LAYOUT_SEED:-11}
target=${1:-baseline}
if [[ $target == baseline ]]; then
  make_targets=(route do-finish)
elif [[ $target == cts_resume ]]; then
  # Re-run only CTS from a preserved 3_place checkpoint.  This keeps clock
  # experiments independent from synthesis and placement and avoids spending
  # more than an hour regenerating an identical placed tile.
  make_targets=(do-4_1_cts)
elif [[ $target == grt_resume ]]; then
  # Resume from the already qualified 4_cts.odb without re-evaluating older
  # stage timestamps.  This is used only after an interrupted downstream run.
  make_targets=(do-5_1_grt)
else
  make_targets=("$target")
fi
variant=${T10_FLOW_VARIANT:-ic_t10_frozen_tile_v33_directmesh_pev16pg_m7_wc_p1000_seed${seed}}
log_root=${T10_LOG_ROOT:-${T10_SCRATCH_ROOT}/t10_frozen_tile}
log=$log_root/${variant}_${target}.log

: "${T10_PE_LEF:=$orfs_root/flow/results/asap7/t10_reference_pe/ic_t10_frozen_pe_exact_v16_commonvclk_m7_wc_p1000_seed${seed}/t10_reference_pe_m7_pgfix.lef}"
: "${T10_PE_LIB:=$orfs_root/flow/results/asap7/t10_reference_pe/ic_t10_frozen_pe_exact_v16_commonvclk_m7_wc_p1000_seed${seed}/t10_reference_pe_m7.lib}"
test "$(sha256sum "$rtl" | awk '{print $1}')" = "$expected_rtl_sha"
t10_require_file "$config"
t10_require_file "$T10_PE_LEF"
t10_require_file "$T10_PE_LIB"
[[ "$T10_PE_LEF" == *"seed${seed}"* ]]
[[ "$T10_PE_LIB" == *"seed${seed}"* ]]
source "$backend_root/physical/t10_acquire_openroad_slot.sh"
mkdir -p "$log_root"
{
  printf 'variant=%s\ntarget=%s\nlog=%s\nrtl_sha256=%s\nlayout_seed=%s\n' \
    "$variant" "$target" "$log" "$expected_rtl_sha" "$seed"
  sha256sum "$T10_PE_LEF" "$T10_PE_LIB"
} | tee "$log_root/ACTIVE_RUN"
cd "$orfs_root/flow"
export T10_LAYOUT_SEED T10_PE_LEF T10_PE_LIB
nice -n 10 make \
  DESIGN_CONFIG="$config" \
  FLOW_VARIANT="$variant" \
  OPENROAD_EXE="${T10_OPENROAD_EXE}" \
  YOSYS_EXE="${T10_YOSYS_EXE}" \
  NUM_CORES=${T10_NUM_CORES:-4} \
  "${make_targets[@]}" >"$log" 2>&1
