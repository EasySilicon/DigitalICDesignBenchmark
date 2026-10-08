#!/usr/bin/env bash
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)/env.sh"
set -euo pipefail
t10_init_scratch
backend_root=${T10_BACKEND_ROOT}
results=${T10_ORFS_ROOT}/flow/results/asap7/npu_systolic_matmul_16x16
source_dir=$results/${T10_SPATIAL_SOURCE_VARIANT:-ic_t10_candidate_top_v97_pair_transport_synth_m7_wc_p1000_seed11}
geometry=$results/ic_t10_candidate_top_v92_clean_ports_m7_wc_p1000_seed11/4_cts_clock_repair_pending.odb
variant=${T10_FLOW_VARIANT:-ic_t10_candidate_top_v98_transport_spatial_m7_wc_p1000_seed11}
result=$results/$variant
t10_require_file "$source_dir/2_3_floorplan_tapcell.odb"
t10_require_file "$geometry"
test ! -e "$result/3_5_place_spatial_pending.odb"
source "$backend_root/physical/t10_acquire_openroad_slot.sh"
mkdir -p "$result"
cp "$source_dir/2_1_floorplan.sdc" "$result/4_cts.sdc"
cp "$source_dir/rtl_delta.json" "$result/rtl_delta.json"
for script in t10_place_transport_spatial.py t10_localize_gather_combinational.py \
  t10_place_top_port_buffers.py t10_repair_top_data_controls.py \
  t10_repair_top_clock_channels.py t10_sparse_channel_legalize.py; do
  cp "$backend_root/physical/$script" "$result/$script"
done
sha256sum "$source_dir/2_3_floorplan_tapcell.odb" "$geometry" "$result/4_cts.sdc" \
  "$result/rtl_delta.json" "$result/"*.py > "$result/spatial_provenance.sha256"
ulimit -v 50331648
options=()
if [[ ${T10_DISTRIBUTED_EGRESS:-0} == 1 ]]; then options+=(--distributed-egress); fi
/usr/bin/time -v nice -n 10 "${T10_OPENROAD_EXE}" -no_init -exit -python \
  "$result/t10_place_transport_spatial.py" "$source_dir/2_3_floorplan_tapcell.odb" \
  "$geometry" "$result/3_5_place_spatial_pending.odb" "$result/spatial_placement.json" "${options[@]}" \
  > "${T10_SCRATCH_ROOT}/t10_frozen_top/${variant}_spatial_placement.log" 2>&1
sha256sum "$result/3_5_place_spatial_pending.odb" > "$result/3_5_place_spatial_pending.odb.sha256"
printf 'T10_FULL_DUT_SPATIAL_PLACEMENT_PRODUCED\n'
