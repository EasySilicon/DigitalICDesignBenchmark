#!/usr/bin/env bash
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)/env.sh"
set -euo pipefail
t10_init_scratch
backend_root=${T10_BACKEND_ROOT}
result_root=${T10_ORFS_ROOT}/flow/results/asap7/npu_systolic_matmul_16x16
source_variant=ic_t10_candidate_top_v80_popcount_eco_m7_wc_p1000_seed11
variant=ic_t10_candidate_top_v81_popcount_spread_m7_wc_p1000_seed11
source_dir=$result_root/$source_variant
result_dir=$result_root/$variant
t10_require_file "$source_dir/4_cts_clock_repair_pending.odb"
source "$backend_root/physical/t10_acquire_openroad_slot.sh"
mkdir -p "$result_dir"
cp "$source_dir/4_cts.sdc" "$result_dir/4_cts.sdc"
for script in t10_spread_output_repeaters.py t10_repair_top_clock_channels.py t10_sparse_channel_legalize.py; do
  cp "$backend_root/physical/$script" "$result_dir/$script"
done
sha256sum "$source_dir/4_cts_clock_repair_pending.odb" "$result_dir/4_cts.sdc" \
  "$result_dir/"*.py > "$result_dir/repeater_spread_provenance.sha256"
ulimit -v 50331648
/usr/bin/time -v nice -n 10 "${T10_OPENROAD_EXE}" -no_init -exit -python \
  "$result_dir/t10_spread_output_repeaters.py" \
  "$source_dir/4_cts_clock_repair_pending.odb" "$result_dir/4_cts_clock_repair_pending.odb" \
  "$result_dir/output_repeater_spread.json" \
  > "${T10_SCRATCH_ROOT}/t10_frozen_top/${variant}_repeater_spread.log" 2>&1
