#!/usr/bin/env bash
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)/env.sh"
# Validate one functionally accepted RTL change against full-DUT path reports.
set -euo pipefail
t10_init_scratch
backend_root=${T10_BACKEND_ROOT}
export T10_DISTRIBUTED_CANDIDATE_ROOT=${T10_PATH_CANDIDATE_ROOT:-${T10_SCRATCH_ROOT}/t10_qualification/v118_local_accept}
export T10_DISTRIBUTED_SYNTH_VARIANT=${T10_PATH_SYNTH_VARIANT:-ic_t10_candidate_top_v119_local_accept_synth_m7_wc_p1000_seed11}
export T10_DISTRIBUTED_PLACE_VARIANT=${T10_PATH_PLACE_VARIANT:-ic_t10_candidate_top_v120_local_accept_spatial_m7_wc_p1000_seed11}
export T10_SKIP_PLACEMENT_TIMING=1
synth_result=${T10_ORFS_ROOT}/flow/results/asap7/npu_systolic_matmul_16x16/$T10_DISTRIBUTED_SYNTH_VARIANT
if [[ -s $synth_result/2_3_floorplan_tapcell.odb ]]; then
    sha256sum --quiet -c "$synth_result/floorplan_inputs.sha256"
    sha256sum --quiet -c "$synth_result/2_3_floorplan_tapcell.odb.sha256"
    export T10_SPATIAL_SOURCE_VARIANT=$T10_DISTRIBUTED_SYNTH_VARIANT
    export T10_FLOW_VARIANT=$T10_DISTRIBUTED_PLACE_VARIANT
    export T10_DISTRIBUTED_EGRESS=1
    bash "$backend_root/physical/run_t10_transport_spatial_probe.sh"
    export T10_CHECK_VARIANT=$T10_FLOW_VARIANT
    bash "$backend_root/physical/run_t10_transport_spatial_checks.sh"
else
    bash "$backend_root/physical/run_t10_distributed_physical_candidate.sh"
fi
export T10_INTERFACE_SOURCE_VARIANT=$T10_DISTRIBUTED_PLACE_VARIANT
export T10_FLOW_VARIANT=${T10_PATH_INTERFACE_VARIANT:-ic_t10_candidate_top_v121_local_accept_interfaces_m7_wc_p1000_seed11}
bash "$backend_root/physical/run_t10_transport_interface_probe.sh"
export T10_SOURCE_VARIANT=$T10_FLOW_VARIANT
export T10_FLOW_VARIANT=${T10_PATH_REPAIR_VARIANT:-ic_t10_candidate_top_v122_local_accept_signals_m7_wc_p1000_seed11}
export T10_REPAIR_ALL_SIGNALS=1 T10_REPAIR_ROOT_BUFFER=1
export T10_REPAIR_SPACING_UM=150 T10_REPAIR_THRESHOLD_UM=200
bash "$backend_root/physical/run_t10_top_data_control_repair.sh"
unset T10_SKIP_PLACEMENT_TIMING
export T10_CHECK_VARIANT=$T10_FLOW_VARIANT
export T10_CHECK_INPUT_ODB=${T10_ORFS_ROOT}/flow/results/asap7/npu_systolic_matmul_16x16/$T10_FLOW_VARIANT/4_cts_clock_repair_pending.odb
bash "$backend_root/physical/run_t10_transport_spatial_checks.sh"
bash "$backend_root/physical/run_t10_full_dut_path_audit.sh"
python3 "$backend_root/physical/t10_summarize_top_paths.py" \
    ${T10_ORFS_ROOT}/flow/results/asap7/npu_systolic_matmul_16x16/$T10_FLOW_VARIANT/top_path_audit
