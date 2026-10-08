#!/usr/bin/env bash
set -euo pipefail
private_root=/home/reefshark/research/agent_os/ic_bcmk_eval_private
result_root=/mnt/ubu_3T/ic_bcmk_orfs_asap7/flow/results/asap7/npu_systolic_matmul_16x16
source_variant=ic_t10_candidate_top_v80_popcount_eco_m7_wc_p1000_seed11
variant=ic_t10_candidate_top_v81_popcount_spread_m7_wc_p1000_seed11
source_dir=$result_root/$source_variant
result_dir=$result_root/$variant
test -s "$source_dir/4_cts_clock_repair_pending.odb"
source "$private_root/physical/t10_acquire_openroad_slot.sh"
mkdir -p "$result_dir"
cp "$source_dir/4_cts.sdc" "$result_dir/4_cts.sdc"
for script in t10_spread_output_repeaters.py t10_repair_top_clock_channels.py t10_sparse_channel_legalize.py; do
  cp "$private_root/physical/$script" "$result_dir/$script"
done
sha256sum "$source_dir/4_cts_clock_repair_pending.odb" "$result_dir/4_cts.sdc" \
  "$result_dir/"*.py > "$result_dir/repeater_spread_provenance.sha256"
ulimit -v 50331648
/usr/bin/time -v nice -n 10 /home/reefshark/.local/bin/openroad -no_init -exit -python \
  "$result_dir/t10_spread_output_repeaters.py" \
  "$source_dir/4_cts_clock_repair_pending.odb" "$result_dir/4_cts_clock_repair_pending.odb" \
  "$result_dir/output_repeater_spread.json" \
  > "/mnt/ubu_3T/ic_bcmk_scratch/t10_frozen_top/${variant}_repeater_spread.log" 2>&1
