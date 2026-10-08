#!/usr/bin/env bash
set -euo pipefail

private_root=/home/reefshark/research/agent_os/ic_bcmk_eval_private
orfs_root=${T10_ORFS_ROOT:-/mnt/ubu_3T/ic_bcmk_orfs_asap7}
seed=${T10_LAYOUT_SEED:-11}
probe_version=${T10_PROBE_VERSION:-64}
source_variant=${T10_TOP_PLACEMENT_VARIANT:-ic_t10_frozen_top_v63_tilev54_gpl010_resize010_m7_wc_p1000_seed${seed}}
variant=${T10_FLOW_VARIANT:-ic_t10_frozen_top_v${probe_version}_tilev54_legal_m7_wc_p1000_seed${seed}}
tile_dir=$orfs_root/flow/results/asap7/t10_reference_tile_4x4/ic_t10_frozen_tile_v54_onehot_slvtclk_wideclk_grt_m7_wc_p1000_seed${seed}
source_dir=$orfs_root/flow/results/asap7/npu_systolic_matmul_16x16/$source_variant
results_dir=$orfs_root/flow/results/asap7/npu_systolic_matmul_16x16/$variant
test -s "$source_dir/3_4_place_resized.odb"
test -s "$source_dir/2_floorplan.sdc"
mkdir -p "$results_dir"
cp --reflink=auto "$source_dir/3_4_place_resized.odb" "$results_dir/3_4_place_resized.odb"
cp "$source_dir/2_floorplan.sdc" "$results_dir/2_floorplan.sdc"
T10_TILE_LEF=$tile_dir/t10_reference_tile_4x4_m7.lef \
T10_TILE_LIB=$tile_dir/t10_reference_tile_4x4_wc.lib \
T10_CTS_CELL_LEF=$orfs_root/flow/platforms/asap7/lef/asap7sc7p5t_28_SL_1x_220121a.lef \
T10_FLOW_VARIANT=$variant \
  "$private_root/physical/run_t10_frozen_top.sh" do-3_5_place_dp
