#!/usr/bin/env bash
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)/env.sh"
set -euo pipefail
t10_init_scratch
backend_root=${T10_BACKEND_ROOT}
results=${T10_ORFS_ROOT}/flow/results/asap7/npu_systolic_matmul_16x16
source_dir=$results/ic_t10_candidate_top_v99_transport_interfaces_m7_wc_p1000_seed11
variant=ic_t10_candidate_top_v102_boundary_locality_m7_wc_p1000_seed11
result=$results/$variant
t10_require_file "$source_dir/4_cts_clock_repair_pending.odb"
test ! -e "$result/3_5_place_boundary_pending.odb"
source "$backend_root/physical/t10_acquire_openroad_slot.sh"
mkdir -p "$result"
cp "$source_dir/4_cts.sdc" "$result/4_cts.sdc"
cp "$source_dir/rtl_delta.json" "$result/rtl_delta.json"
for script in t10_place_boundary_registers.py t10_place_top_port_buffers.py \
  t10_localize_gather_combinational.py t10_repair_top_data_controls.py \
  t10_repair_top_clock_channels.py t10_sparse_channel_legalize.py; do
  cp "$backend_root/physical/$script" "$result/$script"
done
sha256sum "$source_dir/4_cts_clock_repair_pending.odb" "$result/4_cts.sdc" \
  "$result/rtl_delta.json" "$result/"*.py > "$result/boundary_provenance.sha256"
ulimit -v 50331648
/usr/bin/time -v nice -n 10 "${T10_OPENROAD_EXE}" -no_init -exit -python \
  "$result/t10_place_boundary_registers.py" "$source_dir/4_cts_clock_repair_pending.odb" \
  "$result/3_5_place_boundary_pending.odb" "$result/boundary_placement.json" \
  > "${T10_SCRATCH_ROOT}/t10_frozen_top/${variant}_boundary_placement.log" 2>&1
sha256sum "$result/3_5_place_boundary_pending.odb" > "$result/3_5_place_boundary_pending.odb.sha256"
printf 'T10_FULL_DUT_BOUNDARY_LOCALITY_PRODUCED\n'
