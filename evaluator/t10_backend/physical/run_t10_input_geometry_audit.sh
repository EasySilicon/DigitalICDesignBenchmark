#!/usr/bin/env bash
set -euo pipefail
private_root=/home/reefshark/research/agent_os/ic_bcmk_eval_private
root=/mnt/ubu_3T/ic_bcmk_orfs_asap7/flow/results/asap7/npu_systolic_matmul_16x16
source_dir=$root/ic_t10_candidate_top_v93_clean_controls_m7_wc_p1000_seed11
audit=/mnt/ubu_3T/ic_bcmk_scratch/t10_frozen_top/v93_input_configuration_audit
source "$private_root/physical/t10_acquire_openroad_slot.sh"
mkdir -p "$audit"
for script in t10_audit_full_dut_input_geometry.py t10_place_top_port_buffers.py \
  t10_localize_gather_combinational.py t10_repair_top_clock_channels.py \
  t10_repair_top_data_controls.py t10_sparse_channel_legalize.py; do
  cp "$private_root/physical/$script" "$audit/$script"
done
sha256sum "$source_dir/4_cts_native_checked.odb" "$audit/"*.py > "$audit/inputs.sha256"
ulimit -v 4194304
/usr/bin/time -v nice -n 10 /home/reefshark/.local/bin/openroad -no_init -exit -python \
  "$audit/t10_audit_full_dut_input_geometry.py" "$source_dir/4_cts_native_checked.odb" \
  "$audit/geometry.json" > "$audit/run.log" 2>&1
printf 'T10_FULL_DUT_INPUT_GEOMETRY_AUDIT_FINISHED\n'
