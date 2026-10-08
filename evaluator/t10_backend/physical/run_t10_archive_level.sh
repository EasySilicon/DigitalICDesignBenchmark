#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 6 ]]; then
  echo "usage: $0 LEVEL(pe|tile|top) SEED INPUT.odb INPUT.sdc DRC.rpt OUTPUT_PREFIX" >&2
  exit 2
fi
level=$1
seed=$2
input_odb=$3
input_sdc=$4
drc_report=$5
output_prefix=$6
repo=/home/reefshark/research/agent_os/ic_bcmk_eval_private

[[ "$level" =~ ^(pe|tile|top)$ ]]
[[ "$seed" =~ ^(11|29|47)$ ]]
for path in "$input_odb" "$input_sdc" "$drc_report"; do
  test -e "$path" || { echo "missing input: $path" >&2; exit 2; }
done
[[ "$input_odb" == *"seed${seed}"* ]] || {
  echo "ODB does not identify layout seed $seed: $input_odb" >&2
  exit 2
}
test ! -e "${output_prefix}.odb" || {
  echo "refusing stale evidence prefix: $output_prefix" >&2
  exit 4
}
mkdir -p "$(dirname "$output_prefix")"

T10_MACRO_LIB_FILES=${T10_MACRO_LIB_FILES:-} \
  "$repo/physical/run_t10_finish_hier_block.sh" \
  "$input_odb" "$input_sdc" "$output_prefix"
"$repo/physical/t10_make_level_evidence.py" \
  "$level" "$seed" "$output_prefix" "$drc_report" \
  "${output_prefix}_evidence.json"
