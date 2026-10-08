#!/usr/bin/env bash
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)/env.sh"
set -euo pipefail
t10_init_scratch
backend_root=${T10_BACKEND_ROOT}
export T10_SPATIAL_SOURCE_VARIANT=ic_t10_candidate_top_v108_distributed_synth_m7_wc_p1000_seed11
export T10_FLOW_VARIANT=ic_t10_candidate_top_v115_distributed_control_local_m7_wc_p1000_seed11
export T10_DISTRIBUTED_EGRESS=1
bash "$backend_root/physical/run_t10_transport_spatial_probe.sh"
export T10_CHECK_VARIANT=$T10_FLOW_VARIANT
bash "$backend_root/physical/run_t10_transport_spatial_checks.sh"
export T10_INTERFACE_SOURCE_VARIANT=$T10_FLOW_VARIANT
export T10_FLOW_VARIANT=ic_t10_candidate_top_v116_distributed_local_interfaces_m7_wc_p1000_seed11
bash "$backend_root/physical/run_t10_transport_interface_probe.sh"
export T10_SOURCE_VARIANT=$T10_FLOW_VARIANT
export T10_FLOW_VARIANT=ic_t10_candidate_top_v117_distributed_local_signals_m7_wc_p1000_seed11
export T10_REPAIR_ALL_SIGNALS=1
export T10_REPAIR_ROOT_BUFFER=1
export T10_REPAIR_SPACING_UM=150
export T10_REPAIR_THRESHOLD_UM=200
bash "$backend_root/physical/run_t10_top_data_control_repair.sh"
export T10_CHECK_VARIANT=$T10_FLOW_VARIANT
export T10_CHECK_INPUT_ODB=${T10_ORFS_ROOT}/flow/results/asap7/npu_systolic_matmul_16x16/$T10_FLOW_VARIANT/4_cts_clock_repair_pending.odb
bash "$backend_root/physical/run_t10_transport_spatial_checks.sh"
