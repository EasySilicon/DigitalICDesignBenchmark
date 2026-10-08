#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 3 ]]; then
  echo "usage: $0 INPUT.odb INPUT.sdc OUTPUT_PREFIX" >&2
  exit 2
fi

input_odb=$1
input_sdc=$2
output_prefix=$3
repo=/home/reefshark/research/agent_os/ic_bcmk_eval_private
platform=${T10_ASAP7_PLATFORM:-/mnt/ubu_3T/ic_bcmk_orfs_asap7/flow/platforms/asap7}
openroad=${T10_OPENROAD:-/home/reefshark/.local/bin/openroad}

source "$repo/physical/t10_acquire_openroad_slot.sh"
for path in "$input_odb" "$input_sdc" "$platform/rcx_patterns.rules" \
            "$platform/setRC.tcl"; do
  test -s "$path" || { echo "missing input: $path" >&2; exit 2; }
done

standard_libs=(
  "$platform/lib/NLDM/asap7sc7p5t_AO_RVT_SS_nldm_211120.lib.gz"
  "$platform/lib/NLDM/asap7sc7p5t_INVBUF_RVT_SS_nldm_220122.lib.gz"
  "$platform/lib/NLDM/asap7sc7p5t_OA_RVT_SS_nldm_211120.lib.gz"
  "$platform/lib/NLDM/asap7sc7p5t_SEQ_RVT_SS_nldm_220123.lib"
  "$platform/lib/NLDM/asap7sc7p5t_SIMPLE_RVT_SS_nldm_211120.lib.gz"
)
for path in "${standard_libs[@]}"; do test -s "$path"; done

mkdir -p "$(dirname "$output_prefix")"
log="${output_prefix}_finish.log"
test ! -e "$log" || { echo "refusing stale output: $log" >&2; exit 4; }

export T10_LIB_FILES="${standard_libs[*]} ${T10_MACRO_LIB_FILES:-}"
export T10_INPUT_ODB="$input_odb"
export T10_INPUT_SDC="$input_sdc"
export T10_RCX_RULES="$platform/rcx_patterns.rules"
export T10_SETRC_TCL="$platform/setRC.tcl"
export T10_OUTPUT_PREFIX="$output_prefix"
export T10_THREADS=${T10_THREADS:-4}

ulimit -v 31457280
set +e
/usr/bin/time -v "$openroad" -no_init -exit \
  "$repo/physical/t10_finish_hier_block.tcl" >"$log" 2>&1
status=$?
set -e
printf '%s\n' "$status" >"$log.exit"
exit "$status"
