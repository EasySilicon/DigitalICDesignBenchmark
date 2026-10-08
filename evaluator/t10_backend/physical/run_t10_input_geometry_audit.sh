#!/usr/bin/env bash
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)/env.sh"
set -euo pipefail
t10_init_scratch
backend_root=${T10_BACKEND_ROOT}
root=${T10_ORFS_ROOT}/flow/results/asap7/npu_systolic_matmul_16x16
source_dir=$root/ic_t10_candidate_top_v93_clean_controls_m7_wc_p1000_seed11
audit=${T10_SCRATCH_ROOT}/t10_frozen_top/v93_input_configuration_audit
source "$backend_root/physical/t10_acquire_openroad_slot.sh"
mkdir -p "$audit"
for script in t10_audit_full_dut_input_geometry.py t10_place_top_port_buffers.py \
  t10_localize_gather_combinational.py t10_repair_top_clock_channels.py \
  t10_repair_top_data_controls.py t10_sparse_channel_legalize.py; do
  cp "$backend_root/physical/$script" "$audit/$script"
done
sha256sum "$source_dir/4_cts_native_checked.odb" "$audit/"*.py > "$audit/inputs.sha256"
ulimit -v 4194304
/usr/bin/time -v nice -n 10 "${T10_OPENROAD_EXE}" -no_init -exit -python \
  "$audit/t10_audit_full_dut_input_geometry.py" "$source_dir/4_cts_native_checked.odb" \
  "$audit/geometry.json" > "$audit/run.log" 2>&1
printf 'T10_FULL_DUT_INPUT_GEOMETRY_AUDIT_FINISHED\n'
