#!/usr/bin/env bash
set -euo pipefail
private_root=/home/reefshark/research/agent_os/ic_bcmk_eval_private
result_root=/mnt/ubu_3T/ic_bcmk_orfs_asap7/flow/results/asap7/npu_systolic_matmul_16x16
source_variant=${T10_SOURCE_VARIANT:-ic_t10_candidate_top_v81_popcount_spread_m7_wc_p1000_seed11}
variant=${T10_FLOW_VARIANT:-ic_t10_candidate_top_v83_controlio_m7_wc_p1000_seed11}
source_dir=$result_root/$source_variant
result_dir=$result_root/$variant
input=${T10_REPAIR_SOURCE_ODB:-$source_dir/4_cts_clock_repair_pending.odb}
test -s "$input"
test ! -e "$result_dir/4_cts_clock_repair_pending.odb"
source "$private_root/physical/t10_acquire_openroad_slot.sh"
mkdir -p "$result_dir"
cp "$source_dir/4_cts.sdc" "$result_dir/4_cts.sdc"
if [[ -s $source_dir/rtl_delta.json ]]; then cp "$source_dir/rtl_delta.json" "$result_dir/rtl_delta.json"; fi
for script in t10_repair_top_data_controls.py t10_repair_top_clock_channels.py t10_sparse_channel_legalize.py; do
  cp "$private_root/physical/$script" "$result_dir/$script"
done
sha256sum "$input" "$result_dir/4_cts.sdc" \
  "$result_dir/"*.py > "$result_dir/data_control_repair_provenance.sha256"
ulimit -v 50331648
options=()
if [[ ${T10_REPAIR_ALL_CONTROLS:-0} == 1 ]]; then options+=(--control-scope all); fi
if [[ ${T10_REPAIR_RAW_CONTROLS:-0} == 1 ]]; then options+=(--control-scope raw); fi
if [[ ${T10_REPAIR_ALL_SIGNALS:-0} == 1 ]]; then options+=(--control-scope signals); fi
if [[ ${T10_REPAIR_OUTPUT_DATA:-0} == 1 ]]; then options+=(--output-data); fi
if [[ ${T10_REPAIR_CONTROLLER_MIN_FANOUT:-0} != 0 ]]; then options+=(--minimum-controller-fanout "$T10_REPAIR_CONTROLLER_MIN_FANOUT"); fi
if [[ ${T10_REPAIR_ROOT_BUFFER:-0} == 1 ]]; then options+=(--root-buffer); fi
if [[ ${T10_REPAIR_PLAN_ONLY:-0} == 1 ]]; then options+=(--plan-only); fi
options+=(--spacing-um "${T10_REPAIR_SPACING_UM:-200}" --threshold-um "${T10_REPAIR_THRESHOLD_UM:-300}")
/usr/bin/time -v nice -n 10 /home/reefshark/.local/bin/openroad -no_init -exit -python \
  "$result_dir/t10_repair_top_data_controls.py" \
  "$input" "$result_dir/4_cts_clock_repair_pending.odb" \
  "$result_dir/data_control_repair.json" "${options[@]}" \
  > "/mnt/ubu_3T/ic_bcmk_scratch/t10_frozen_top/${variant}_data_control_repair.log" 2>&1
