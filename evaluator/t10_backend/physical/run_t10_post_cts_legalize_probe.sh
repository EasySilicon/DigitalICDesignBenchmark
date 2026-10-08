#!/usr/bin/env bash
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)/env.sh"
set -euo pipefail
t10_init_scratch
backend_root=${T10_BACKEND_ROOT}
orfs_root=${T10_ORFS_ROOT}
seed=${T10_LAYOUT_SEED:-11}
source_version=${T10_SOURCE_VERSION:-70}
version=${T10_PROBE_VERSION:-71}
source_variant=ic_t10_frozen_top_v${source_version}_tilev54_slvtclk_d200_wideclk_m7_wc_p1000_seed${seed}
variant=ic_t10_frozen_top_v${version}_tilev54_slvtclk_d200_wideclk_m7_wc_p1000_seed${seed}
source_dir=$orfs_root/flow/results/asap7/npu_systolic_matmul_16x16/$source_variant
result_dir=$orfs_root/flow/results/asap7/npu_systolic_matmul_16x16/$variant
if [[ ! -s $result_dir/4_1_cts_interval_probe.odb ]]; then
  T10_FLOW_VARIANT=$variant \
  T10_PLACEMENT_SOURCE_ODB=$source_dir/4_1_cts.odb \
  T10_PLACEMENT_SOURCE_SDC=$source_dir/4_cts.sdc \
  T10_LEGALIZED_ODB_NAME=4_1_cts_interval_probe.odb \
  T10_OUTPUT_SDC_NAME=4_cts.sdc \
  T10_ROW_STRIDE=1 \
    "$backend_root/physical/run_t10_top_sparse_legalize_probe.sh"
fi
T10_FLOW_VARIANT=$variant \
T10_PLACEMENT_INPUT_ODB=$result_dir/4_1_cts_interval_probe.odb \
T10_NATIVE_CHECKED_ODB_NAME=4_1_cts_native_checked.odb \
T10_PLACEMENT_VALIDATED_ODB_NAME=4_1_cts.odb \
  "$backend_root/physical/run_t10_validate_top_placement.sh"
