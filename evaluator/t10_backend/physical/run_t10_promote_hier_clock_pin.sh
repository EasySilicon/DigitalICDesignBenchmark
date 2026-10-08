#!/usr/bin/env bash
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)/env.sh"
set -euo pipefail
t10_init_scratch

if [[ $# -ne 8 ]]; then
  echo "usage: $0 INPUT.odb OUTPUT.odb OUTPUT.lef LAYER X_MIN_DBU Y_MIN_DBU X_MAX_DBU Y_MAX_DBU" >&2
  exit 2
fi

input_odb=$1
output_odb=$2
output_lef=$3
layer=$4
x_min=$5
y_min=$6
x_max=$7
y_max=$8
repo=${T10_BACKEND_ROOT}
openroad=${T10_OPENROAD:-"${T10_OPENROAD_EXE}"}

t10_require_file "$input_odb"
test ! -e "$output_odb"
test ! -e "$output_lef"
source "$repo/physical/t10_acquire_openroad_slot.sh"

export T10_INPUT_ODB=$input_odb
export T10_OUTPUT_ODB=$output_odb
export T10_OUTPUT_LEF=$output_lef
export T10_CLOCK_PIN_LAYER=$layer
export T10_CLOCK_PIN_X_MIN_DBU=$x_min
export T10_CLOCK_PIN_Y_MIN_DBU=$y_min
export T10_CLOCK_PIN_X_MAX_DBU=$x_max
export T10_CLOCK_PIN_Y_MAX_DBU=$y_max

log="${output_odb%.odb}_clock_pin.log"
"$openroad" -no_init -exit "$repo/physical/t10_promote_hier_clock_pin.tcl" >"$log" 2>&1
{
  sha256sum "$input_odb" "$output_odb" "$output_lef"
  printf 'layer=%s\nrect_dbu=%s,%s,%s,%s\n' "$layer" "$x_min" "$y_min" "$x_max" "$y_max"
} >"${output_odb%.odb}_clock_pin.audit"
