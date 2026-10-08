#!/usr/bin/env bash
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)/env.sh"
set -euo pipefail
t10_init_scratch

backend_root=${T10_BACKEND_ROOT}
orfs_root=${T10_ORFS_ROOT}
seed=${T10_LAYOUT_SEED:-11}
source_version=${T10_SOURCE_VERSION:-62}
probe_version=${T10_PROBE_VERSION:-63}
source_variant=${T10_TOP_PLACEMENT_VARIANT:-ic_t10_frozen_top_v${source_version}_tilev54_gpl010_m7_wc_p1000_seed${seed}}
variant=${T10_FLOW_VARIANT:-ic_t10_frozen_top_v${probe_version}_tilev54_gpl010_resize010_m7_wc_p1000_seed${seed}}

tile_dir=$orfs_root/flow/results/asap7/t10_reference_tile_4x4/ic_t10_frozen_tile_v54_onehot_slvtclk_wideclk_grt_m7_wc_p1000_seed${seed}
tile_lef=$tile_dir/t10_reference_tile_4x4_m7.lef
tile_lib=$tile_dir/t10_reference_tile_4x4_wc.lib
cts_lef=${T10_ASAP7_PLATFORM}/lef/asap7sc7p5t_28_SL_1x_220121a.lef
source_dir=$orfs_root/flow/results/asap7/npu_systolic_matmul_16x16/$source_variant
results_dir=$orfs_root/flow/results/asap7/npu_systolic_matmul_16x16/$variant

t10_require_file "$tile_lef"
t10_require_file "$tile_lib"
t10_require_file "$cts_lef"
t10_require_file "$source_dir/3_3_place_gp.odb"
t10_require_file "$source_dir/2_floorplan.sdc"
mkdir -p "$results_dir"
if [[ ! -s $results_dir/3_3_place_gp.odb ]]; then
  cp --reflink=auto "$source_dir/3_3_place_gp.odb" "$results_dir/3_3_place_gp.odb"
fi
if [[ ! -s $results_dir/2_floorplan.sdc ]]; then
  cp "$source_dir/2_floorplan.sdc" "$results_dir/2_floorplan.sdc"
fi

T10_TILE_LEF=$tile_lef \
T10_TILE_LIB=$tile_lib \
T10_CTS_CELL_LEF=$cts_lef \
T10_FLOW_VARIANT=$variant \
  "$backend_root/physical/run_t10_frozen_top.sh" do-3_4_place_resized
