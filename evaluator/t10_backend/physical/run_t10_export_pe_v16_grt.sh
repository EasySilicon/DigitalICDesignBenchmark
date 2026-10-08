#!/usr/bin/env bash
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)/env.sh"
set -euo pipefail
t10_init_scratch

backend_root=${T10_BACKEND_ROOT}
orfs_root=${T10_ORFS_ROOT}
seed=${T10_LAYOUT_SEED:-11}
variant=ic_t10_frozen_pe_exact_v16_commonvclk_m7_wc_p1000_seed${seed}
result_dir=$orfs_root/flow/results/asap7/t10_reference_pe/$variant
output_prefix=$result_dir/t10_reference_pe_m7

macro_libs=(
  "$orfs_root/flow/results/asap7/t10_reference_fp_quad_class0_exact/ic_t10_frozen_fp_class0_m7_wc_p1000_seed${seed}/t10_reference_fp_quad_class0_exact.lib"
  "$orfs_root/flow/results/asap7/t10_reference_fp_quad_class1_exact/ic_t10_frozen_fp_class1_cornerio_h50_m7_wc_p1000_seed${seed}/t10_reference_fp_quad_class1_exact.lib"
  "$orfs_root/flow/results/asap7/t10_reference_fp_quad_class2_exact/ic_t10_frozen_fp_class2_cornerio_h50_m7_wc_p1000_seed${seed}/t10_reference_fp_quad_class2_exact.lib"
  "$orfs_root/flow/results/asap7/t10_reference_int_group/ic_t10_frozen_int_group_exact_v2_m7_wc_p1000_seed${seed}/t10_reference_int_group.lib"
  "$orfs_root/flow/results/asap7/t10_reference_cpa_postprocess/ic_t10_frozen_cpa_postprocess_exact_v2_m7_wc_p1000_seed${seed}/t10_reference_cpa_postprocess.lib"
)
for path in "$result_dir/5_1_grt.odb" "$result_dir/5_1_grt.sdc" \
            "${macro_libs[@]}"; do
  t10_require_file "$path" || { echo "missing PE GRT export input: $path" >&2; exit 2; }
done

export T10_ESTIMATE_GLOBAL_ROUTE=1
export T10_MACRO_LIB_FILES="${macro_libs[*]}"
"$backend_root/physical/run_t10_finish_hier_block.sh" \
  "$result_dir/5_1_grt.odb" "$result_dir/5_1_grt.sdc" "$output_prefix"
t10_require_file "$output_prefix.lef"
t10_require_file "$output_prefix.lib"
sha256sum "$output_prefix.lef" "$output_prefix.lib"
