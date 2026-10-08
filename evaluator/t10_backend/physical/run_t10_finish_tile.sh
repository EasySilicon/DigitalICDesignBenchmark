#!/usr/bin/env bash
set -euo pipefail

private_root=/home/reefshark/research/agent_os/ic_bcmk_eval_private
orfs_root=${T10_ORFS_ROOT:-/mnt/ubu_3T/ic_bcmk_orfs_asap7}
seed=${T10_LAYOUT_SEED:-11}
variant=${T10_TILE_VARIANT:-ic_t10_frozen_tile_v33_directmesh_pev16pg_m7_wc_p1000_seed${seed}}
result_dir=$orfs_root/flow/results/asap7/t10_reference_tile_4x4/$variant
log_root=${T10_LOG_ROOT:-/mnt/ubu_3T/ic_bcmk_scratch/t10_frozen_tile}
pe_lib=$orfs_root/flow/results/asap7/t10_reference_pe/ic_t10_frozen_pe_exact_v16_commonvclk_m7_wc_p1000_seed${seed}/t10_reference_pe_m7.lib
slvt_clock_lib=$orfs_root/flow/platforms/asap7/lib/NLDM/asap7sc7p5t_INVBUF_SLVT_SS_nldm_220122.lib.gz
output_prefix=$result_dir/t10_reference_tile_4x4_m7
wc_lib=$result_dir/t10_reference_tile_4x4_wc.lib
log=$log_root/${variant}_finish_hier_block.log

finish_stage=${T10_FINISH_STAGE:-final}
case "$finish_stage" in
  final)
    input_odb=$result_dir/6_final.odb
    input_sdc=$result_dir/6_final.sdc
    input_spef=$result_dir/6_final.spef
    ;;
  grt)
    input_odb=$result_dir/5_1_grt.odb
    input_sdc=$result_dir/5_1_grt.sdc
    input_spef=
    ;;
  *)
    echo "ERROR: T10_FINISH_STAGE must be final or grt" >&2
    exit 2
    ;;
esac
test -s "$input_odb"
test -s "$input_sdc"
if [[ -n "$input_spef" ]]; then test -s "$input_spef"; fi
test -s "$pe_lib"
test -s "$slvt_clock_lib"
source "$private_root/physical/t10_acquire_openroad_slot.sh"

platform=$orfs_root/flow/platforms/asap7
standard_libs=(
  "$platform/lib/NLDM/asap7sc7p5t_AO_RVT_SS_nldm_211120.lib.gz"
  "$platform/lib/NLDM/asap7sc7p5t_INVBUF_RVT_SS_nldm_220122.lib.gz"
  "$platform/lib/NLDM/asap7sc7p5t_OA_RVT_SS_nldm_211120.lib.gz"
  "$platform/lib/NLDM/asap7sc7p5t_SEQ_RVT_SS_nldm_220123.lib"
  "$platform/lib/NLDM/asap7sc7p5t_SIMPLE_RVT_SS_nldm_211120.lib.gz"
)
for path in "${standard_libs[@]}"; do test -s "$path"; done

export T10_LIB_FILES="${standard_libs[*]} $pe_lib $slvt_clock_lib"
export T10_INPUT_ODB=$input_odb
export T10_INPUT_SDC=$input_sdc
if [[ -n "$input_spef" ]]; then
  export T10_INPUT_SPEF=$input_spef
  unset T10_ESTIMATE_GLOBAL_ROUTE || true
else
  unset T10_INPUT_SPEF || true
  export T10_ESTIMATE_GLOBAL_ROUTE=1
fi
export T10_RCX_RULES=$platform/rcx_patterns.rules
export T10_SETRC_TCL=$platform/setRC.tcl
export T10_OUTPUT_PREFIX=$output_prefix
export T10_THREADS=${T10_NUM_CORES:-4}

mkdir -p "$log_root"
nice -n 10 /home/reefshark/.local/bin/openroad -no_init -exit \
  "$private_root/physical/t10_finish_hier_block.tcl" >"$log" 2>&1
cp "$output_prefix.lib" "$wc_lib"
test -s "$output_prefix.lef"
test -s "$wc_lib"
sha256sum "$output_prefix.lef" "$wc_lib" | tee "$log_root/${variant}_tile_abstract.sha256"
printf 'finish_stage=%s\ninput_odb=%s\ninput_sdc=%s\ninput_spef=%s\n' \
  "$finish_stage" "$input_odb" "$input_sdc" "$input_spef" \
  >"$result_dir/t10_reference_tile_4x4_abstract_source.txt"
