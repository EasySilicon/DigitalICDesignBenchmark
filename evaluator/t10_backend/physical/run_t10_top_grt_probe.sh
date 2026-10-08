#!/usr/bin/env bash
set -euo pipefail

private_root=/home/reefshark/research/agent_os/ic_bcmk_eval_private
orfs_root=${T10_ORFS_ROOT:-/mnt/ubu_3T/ic_bcmk_orfs_asap7}
seed=${T10_LAYOUT_SEED:-11}
probe_version=${T10_PROBE_VERSION:-61}
distance=${T10_CTS_DISTANCE:-200}
variant=${T10_FLOW_VARIANT:-ic_t10_frozen_top_v${probe_version}_tilev54_slvtclk_d${distance}_wideclk_m7_wc_p1000_seed${seed}}

tile_dir=$orfs_root/flow/results/asap7/t10_reference_tile_4x4/ic_t10_frozen_tile_v54_onehot_slvtclk_wideclk_grt_m7_wc_p1000_seed${seed}
tile_lef=$tile_dir/t10_reference_tile_4x4_m7.lef
tile_lib=$tile_dir/t10_reference_tile_4x4_wc.lib
cts_lef=$orfs_root/flow/platforms/asap7/lef/asap7sc7p5t_28_SL_1x_220121a.lef
cts_lib=$orfs_root/flow/platforms/asap7/lib/NLDM/asap7sc7p5t_INVBUF_SLVT_SS_nldm_220122.lib.gz
cts_odb=$orfs_root/flow/results/asap7/npu_systolic_matmul_16x16/$variant/4_1_cts.odb
grt_input_odb=$orfs_root/flow/results/asap7/npu_systolic_matmul_16x16/$variant/4_cts.odb

test -s "$tile_lef"
test -s "$tile_lib"
test -s "$cts_lef"
test -s "$cts_lib"
test -s "$cts_odb"
if [[ ! -s $grt_input_odb ]]; then
  cp --reflink=auto "$cts_odb" "$grt_input_odb"
fi
test -s "$grt_input_odb"

T10_TILE_LEF=$tile_lef \
T10_TILE_LIB=$tile_lib \
T10_CTS_CELL_LEF=$cts_lef \
T10_POST_CTS_CELL_LIB=$cts_lib \
T10_WIDE_CLOCK_NDR=1 \
T10_FLOW_VARIANT=$variant \
  "$private_root/physical/run_t10_frozen_top.sh" grt_resume
