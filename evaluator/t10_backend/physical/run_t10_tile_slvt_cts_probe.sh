#!/usr/bin/env bash
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)/env.sh"
set -euo pipefail
t10_init_scratch

backend_root=${T10_BACKEND_ROOT}
orfs_root=${T10_ORFS_ROOT}
design=t10_reference_tile_4x4
seed=${T10_LAYOUT_SEED:-11}
probe_version=${T10_PROBE_VERSION:?set T10_PROBE_VERSION, for example 50}
distance=${T10_CTS_DISTANCE:-100}
tag=${T10_CTS_TAG:-d${distance}}
extra_args=${T10_CTS_EXTRA_PROBE_ARGS:-}
source_variant=${T10_SOURCE_VARIANT:-ic_t10_frozen_tile_v48_directmesh_pev16pg_slvtclk_m7_wc_p1000_seed${seed}}
variant=ic_t10_frozen_tile_v${probe_version}_directmesh_pev16pg_slvtclk_${tag}_probe_m7_wc_p1000_seed${seed}
source_dir=$orfs_root/flow/results/asap7/$design/$source_variant
result_dir=$orfs_root/flow/results/asap7/$design/$variant
cts_lef=${T10_ASAP7_PLATFORM}/lef/asap7sc7p5t_28_SL_1x_220121a.lef
cts_lib=${T10_ASAP7_PLATFORM}/lib/NLDM/asap7sc7p5t_INVBUF_SLVT_SS_nldm_220122.lib.gz

t10_require_file "$source_dir/3_place.odb"
t10_require_file "$source_dir/3_place.sdc"
t10_require_file "$cts_lef"
t10_require_file "$cts_lib"
mkdir -p "$result_dir"
cp --reflink=auto "$source_dir/3_place.odb" "$result_dir/3_place.odb"
cp "$source_dir/3_place.sdc" "$result_dir/3_place.sdc"

T10_CTS_CELL_LEF=$cts_lef \
T10_CTS_CELL_LIB=$cts_lib \
T10_SKIP_CTS_REPAIR_TIMING=1 \
T10_CTS_ARGS_OVERRIDE="-sink_clustering_enable -repair_clock_nets -apply_ndr half -distance_between_buffers $distance -macro_clustering_size 2 -macro_clustering_max_diameter 100 -library asap7sc7p5t_INVBUF_SLVT_SS_nldm_211120 -buf_list BUFx24_ASAP7_75t_SL -root_buf BUFx24_ASAP7_75t_SL -tree_buf BUFx24_ASAP7_75t_SL $extra_args" \
T10_FLOW_VARIANT=$variant \
  "$backend_root/physical/run_t10_frozen_tile.sh" cts_resume
