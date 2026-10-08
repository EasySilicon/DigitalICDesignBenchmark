#!/usr/bin/env bash
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)/env.sh"
set -euo pipefail
t10_init_scratch

backend_root=${T10_BACKEND_ROOT}
orfs_root=${T10_ORFS_ROOT}
seed=${T10_LAYOUT_SEED:-11}
probe_version=${T10_PROBE_VERSION:-61}
distance=${T10_CTS_DISTANCE:-200}
variant=${T10_FLOW_VARIANT:-ic_t10_frozen_top_v${probe_version}_tilev54_slvtclk_d${distance}_wideclk_m7_wc_p1000_seed${seed}}

tile_dir=$orfs_root/flow/results/asap7/t10_reference_tile_4x4/ic_t10_frozen_tile_v54_onehot_slvtclk_wideclk_grt_m7_wc_p1000_seed${seed}
tile_lef=$tile_dir/t10_reference_tile_4x4_m7.lef
tile_lib=$tile_dir/t10_reference_tile_4x4_wc.lib
cts_lef=${T10_ASAP7_PLATFORM}/lef/asap7sc7p5t_28_SL_1x_220121a.lef
cts_lib=${T10_ASAP7_PLATFORM}/lib/NLDM/asap7sc7p5t_INVBUF_SLVT_SS_nldm_220122.lib.gz
cts_odb=$orfs_root/flow/results/asap7/npu_systolic_matmul_16x16/$variant/4_1_cts.odb
grt_input_odb=$orfs_root/flow/results/asap7/npu_systolic_matmul_16x16/$variant/4_cts.odb

t10_require_file "$tile_lef"
t10_require_file "$tile_lib"
t10_require_file "$cts_lef"
t10_require_file "$cts_lib"
t10_require_file "$cts_odb"
if [[ ! -s $grt_input_odb ]]; then
  cp --reflink=auto "$cts_odb" "$grt_input_odb"
fi
t10_require_file "$grt_input_odb"

T10_TILE_LEF=$tile_lef \
T10_TILE_LIB=$tile_lib \
T10_CTS_CELL_LEF=$cts_lef \
T10_POST_CTS_CELL_LIB=$cts_lib \
T10_WIDE_CLOCK_NDR=1 \
T10_FLOW_VARIANT=$variant \
  "$backend_root/physical/run_t10_frozen_top.sh" grt_resume
