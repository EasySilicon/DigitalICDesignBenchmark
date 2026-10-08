#!/usr/bin/env bash
set -euo pipefail

private_root=/home/reefshark/research/agent_os/ic_bcmk_eval_private
orfs_root=${T10_ORFS_ROOT:-/mnt/ubu_3T/ic_bcmk_orfs_asap7}
rtl=$private_root/refs/T10/rtl/npu_systolic_matmul_16x16.sv
config=$private_root/physical/t10_frozen_pe/config_exact.mk
expected_rtl_sha=0c7646d7019e45477582faba0605f1c3ba557810a61cb617844aeeb24b632622
seed=${T10_LAYOUT_SEED:-11}
target=${1:-baseline}
if [[ $target == baseline ]]; then
  make_targets=(route do-finish)
else
  make_targets=("$target")
fi
variant=ic_t10_frozen_pe_exact_v16_commonvclk_m7_wc_p1000_seed${seed}
log_root=${T10_LOG_ROOT:-/mnt/ubu_3T/ic_bcmk_scratch/t10_frozen_pe_exact}
log=$log_root/${variant}_${target}.log

: "${T10_FP0_LEF:=$orfs_root/flow/results/asap7/t10_reference_fp_quad_class0_exact/ic_t10_frozen_fp_class0_m7_wc_p1000_seed${seed}/t10_reference_fp_quad_class0_exact_m7.lef}"
: "${T10_FP1_LEF:=$orfs_root/flow/results/asap7/t10_reference_fp_quad_class1_exact/ic_t10_frozen_fp_class1_cornerio_h50_m7_wc_p1000_seed${seed}/t10_reference_fp_quad_class1_exact_m7.lef}"
: "${T10_FP2_LEF:=$orfs_root/flow/results/asap7/t10_reference_fp_quad_class2_exact/ic_t10_frozen_fp_class2_cornerio_h50_m7_wc_p1000_seed${seed}/t10_reference_fp_quad_class2_exact_m7.lef}"
: "${T10_INT_LEF:=$orfs_root/flow/results/asap7/t10_reference_int_group/ic_t10_frozen_int_group_exact_v2_m7_wc_p1000_seed${seed}/t10_reference_int_group_m7.lef}"
: "${T10_CPA_LEF:=$orfs_root/flow/results/asap7/t10_reference_cpa_postprocess/ic_t10_frozen_cpa_postprocess_exact_v2_m7_wc_p1000_seed${seed}/t10_reference_cpa_postprocess_m7.lef}"
: "${T10_FP0_LIB:=$orfs_root/flow/results/asap7/t10_reference_fp_quad_class0_exact/ic_t10_frozen_fp_class0_m7_wc_p1000_seed${seed}/t10_reference_fp_quad_class0_exact.lib}"
: "${T10_FP1_LIB:=$orfs_root/flow/results/asap7/t10_reference_fp_quad_class1_exact/ic_t10_frozen_fp_class1_cornerio_h50_m7_wc_p1000_seed${seed}/t10_reference_fp_quad_class1_exact.lib}"
: "${T10_FP2_LIB:=$orfs_root/flow/results/asap7/t10_reference_fp_quad_class2_exact/ic_t10_frozen_fp_class2_cornerio_h50_m7_wc_p1000_seed${seed}/t10_reference_fp_quad_class2_exact.lib}"
: "${T10_INT_LIB:=$orfs_root/flow/results/asap7/t10_reference_int_group/ic_t10_frozen_int_group_exact_v2_m7_wc_p1000_seed${seed}/t10_reference_int_group.lib}"
: "${T10_CPA_LIB:=$orfs_root/flow/results/asap7/t10_reference_cpa_postprocess/ic_t10_frozen_cpa_postprocess_exact_v2_m7_wc_p1000_seed${seed}/t10_reference_cpa_postprocess.lib}"

macro_vars=(T10_FP0_LEF T10_FP1_LEF T10_FP2_LEF T10_INT_LEF T10_CPA_LEF
            T10_FP0_LIB T10_FP1_LIB T10_FP2_LIB T10_INT_LIB T10_CPA_LIB)
test "$(sha256sum "$rtl" | awk '{print $1}')" = "$expected_rtl_sha"
test -s "$config"
for name in "${macro_vars[@]}"; do
  path=${!name}
  test -s "$path" || { echo "missing macro input: $path" >&2; exit 2; }
  [[ "$path" == *"seed${seed}"* ]] || {
    echo "$name does not identify layout seed $seed: $path" >&2
    exit 2
  }
done
source "$private_root/physical/t10_acquire_openroad_slot.sh"
mkdir -p "$log_root"
{
  printf 'variant=%s\ntarget=%s\nlog=%s\nrtl_sha256=%s\nlayout_seed=%s\n' \
    "$variant" "$target" "$log" "$expected_rtl_sha" "$seed"
  for name in "${macro_vars[@]}"; do sha256sum "${!name}"; done
} | tee "$log_root/ACTIVE_RUN"
cd "$orfs_root/flow"
export T10_LAYOUT_SEED
export "${macro_vars[@]}"
nice -n 10 make \
  DESIGN_CONFIG="$config" \
  FLOW_VARIANT="$variant" \
  OPENROAD_EXE=/home/reefshark/.local/bin/openroad \
  YOSYS_EXE=/home/reefshark/.local/bin/yosys \
  NUM_CORES=${T10_NUM_CORES:-4} \
  "${make_targets[@]}" >"$log" 2>&1
