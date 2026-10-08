#!/usr/bin/env bash
set -euo pipefail
private_root=/home/reefshark/research/agent_os/ic_bcmk_eval_private
results=/mnt/ubu_3T/ic_bcmk_orfs_asap7/flow/results/asap7/npu_systolic_matmul_16x16
source_dir=$results/${T10_INTERFACE_SOURCE_VARIANT:-ic_t10_candidate_top_v98_transport_spatial_m7_wc_p1000_seed11}
variant=${T10_FLOW_VARIANT:-ic_t10_candidate_top_v99_transport_interfaces_m7_wc_p1000_seed11}
result=$results/$variant
test -s "$source_dir/3_5_place_native_checked.odb"
test ! -e "$result/4_cts_clock_repair_pending.odb"
source "$private_root/physical/t10_acquire_openroad_slot.sh"
mkdir -p "$result"
cp "$source_dir/4_cts.sdc" "$result/4_cts.sdc"
cp "$source_dir/rtl_delta.json" "$result/rtl_delta.json"
for script in t10_add_interface_buffers.py t10_place_top_port_buffers.py \
  t10_localize_gather_combinational.py t10_repair_top_data_controls.py \
  t10_repair_top_clock_channels.py t10_sparse_channel_legalize.py; do
  cp "$private_root/physical/$script" "$result/$script"
done
sha256sum "$source_dir/3_5_place_native_checked.odb" "$result/4_cts.sdc" \
  "$result/rtl_delta.json" "$result/"*.py > "$result/interface_provenance.sha256"
ulimit -v 50331648
/usr/bin/time -v nice -n 10 /home/reefshark/.local/bin/openroad -no_init -exit -python \
  "$result/t10_add_interface_buffers.py" "$source_dir/3_5_place_native_checked.odb" \
  "$result/4_cts_clock_repair_pending.odb" "$result/interface_buffers.json" \
  > /mnt/ubu_3T/ic_bcmk_scratch/t10_frozen_top/${variant}_interface_buffers.log 2>&1
sha256sum "$result/4_cts_clock_repair_pending.odb" > "$result/4_cts_clock_repair_pending.odb.sha256"
printf 'T10_FULL_DUT_INTERFACE_BUFFERS_PRODUCED\n'
