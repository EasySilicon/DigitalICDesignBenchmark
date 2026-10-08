#!/usr/bin/env bash
set -euo pipefail
private_root=/home/reefshark/research/agent_os/ic_bcmk_eval_private
orfs_root=${T10_ORFS_ROOT:-/mnt/ubu_3T/ic_bcmk_orfs_asap7}
seed=${T10_LAYOUT_SEED:-11}
source_variant=ic_t10_frozen_top_v72_tilev54_gcell60_m7_wc_p1000_seed${seed}
variant=${T10_FLOW_VARIANT:-ic_t10_frozen_top_v76_tilev54_clockchannels_m7_wc_p1000_seed${seed}}
source_dir=$orfs_root/flow/results/asap7/npu_systolic_matmul_16x16/$source_variant
result_dir=$orfs_root/flow/results/asap7/npu_systolic_matmul_16x16/$variant
log_root=/mnt/ubu_3T/ic_bcmk_scratch/t10_frozen_top
test -s "$source_dir/4_cts_pin_access.odb"
test -s "$source_dir/4_cts_pin_access.sdc"
sha256sum --check "$source_dir/4_cts_pin_access.odb.sha256"
source "$private_root/physical/t10_acquire_openroad_slot.sh"
mkdir -p "$result_dir"
cp "$source_dir/4_cts_pin_access.sdc" "$result_dir/4_cts.sdc"
cp "$private_root/physical/t10_repair_top_clock_channels.py" "$result_dir/clock_repair_producer.py"
cp "$private_root/physical/t10_sparse_channel_legalize.py" "$result_dir/t10_sparse_channel_legalize.py"
cp "${BASH_SOURCE[0]}" "$result_dir/clock_repair_runner.sh"
sha256sum "$source_dir/4_cts_pin_access.odb" "$source_dir/4_cts_pin_access.sdc" \
  "$result_dir/clock_repair_producer.py" "$result_dir/t10_sparse_channel_legalize.py" \
  "$result_dir/clock_repair_runner.sh" > "$result_dir/clock_repair_provenance.sha256"
ulimit -v 50331648
set +e
/usr/bin/time -v nice -n 10 /home/reefshark/.local/bin/openroad -no_init -exit -python \
  "$result_dir/clock_repair_producer.py" \
  "$source_dir/4_cts_pin_access.odb" "$result_dir/4_cts_clock_repair_pending.odb" \
  "$result_dir/clock_channel_repair.json" \
  --spacing-um "${T10_CLOCK_CHANNEL_SPACING_UM:-200}" \
  --threshold-um "${T10_CLOCK_CHANNEL_THRESHOLD_UM:-300}" \
  > "$log_root/${variant}_clock_repair.log" 2>&1
status=$?
set -e
printf '%s\n' "$status" > "$result_dir/clock_repair.exit"
exit "$status"
