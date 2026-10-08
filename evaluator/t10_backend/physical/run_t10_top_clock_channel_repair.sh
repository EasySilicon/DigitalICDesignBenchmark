#!/usr/bin/env bash
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)/env.sh"
set -euo pipefail
t10_init_scratch
backend_root=${T10_BACKEND_ROOT}
orfs_root=${T10_ORFS_ROOT}
seed=${T10_LAYOUT_SEED:-11}
source_variant=ic_t10_frozen_top_v72_tilev54_gcell60_m7_wc_p1000_seed${seed}
variant=${T10_FLOW_VARIANT:-ic_t10_frozen_top_v76_tilev54_clockchannels_m7_wc_p1000_seed${seed}}
source_dir=$orfs_root/flow/results/asap7/npu_systolic_matmul_16x16/$source_variant
result_dir=$orfs_root/flow/results/asap7/npu_systolic_matmul_16x16/$variant
log_root=${T10_SCRATCH_ROOT}/t10_frozen_top
t10_require_file "$source_dir/4_cts_pin_access.odb"
t10_require_file "$source_dir/4_cts_pin_access.sdc"
sha256sum --check "$source_dir/4_cts_pin_access.odb.sha256"
source "$backend_root/physical/t10_acquire_openroad_slot.sh"
mkdir -p "$result_dir"
cp "$source_dir/4_cts_pin_access.sdc" "$result_dir/4_cts.sdc"
cp "$backend_root/physical/t10_repair_top_clock_channels.py" "$result_dir/clock_repair_producer.py"
cp "$backend_root/physical/t10_sparse_channel_legalize.py" "$result_dir/t10_sparse_channel_legalize.py"
cp "${BASH_SOURCE[0]}" "$result_dir/clock_repair_runner.sh"
sha256sum "$source_dir/4_cts_pin_access.odb" "$source_dir/4_cts_pin_access.sdc" \
  "$result_dir/clock_repair_producer.py" "$result_dir/t10_sparse_channel_legalize.py" \
  "$result_dir/clock_repair_runner.sh" > "$result_dir/clock_repair_provenance.sha256"
ulimit -v 50331648
set +e
/usr/bin/time -v nice -n 10 "${T10_OPENROAD_EXE}" -no_init -exit -python \
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
