#!/usr/bin/env bash
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)/env.sh"
set -euo pipefail
t10_init_scratch

if [[ $# -ne 5 ]]; then
  echo "usage: $0 KLAYOUT_BIN INPUT_GDS DRC_DECK REPORT_RDB LOG" >&2
  exit 2
fi

klayout_bin=$1
input_gds=$2
drc_deck=$3
report_rdb=$4
log=$5
: "${T10_KLAYOUT_VMEM_KIB:=31457280}"

for input in "$klayout_bin" "$input_gds" "$drc_deck"; do
  if [[ ! -e "$input" ]]; then
    echo "missing input: $input" >&2
    exit 2
  fi
done

mkdir -p "$(dirname "$report_rdb")" "$(dirname "$log")"
ulimit -v "$T10_KLAYOUT_VMEM_KIB"
# Mark the sidecar as nonterminal before launching so a monitor cannot mistake
# an exit code left by an earlier run for the status of the active process.
printf 'RUNNING\n' > "${log}.exit"
set +e
/usr/bin/time -v "$klayout_bin" -b \
  -rd in_gds="$input_gds" \
  -rd report_file="$report_rdb" \
  -r "$drc_deck" 2>&1 | tee "$log"
status=${PIPESTATUS[0]}
set -e
printf '%s\n' "$status" > "${log}.exit"
printf 'T10_KLAYOUT_DRC_EXIT=%s\n' "$status"
exit "$status"
