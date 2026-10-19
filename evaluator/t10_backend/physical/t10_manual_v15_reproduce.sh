#!/usr/bin/env bash
set -euo pipefail

# Dependencies must belong to the pinned OpenROAD build, not another ABI.
for name in T10_ORFS_FLOW T10_OPENROAD_SRC T10_WORK_DIR T10_THIRDPARTY_INCLUDE T10_BOOST_INCLUDE T10_ORTOOLS_INCLUDE; do
  if [[ -z ${!name:-} ]]; then printf '%s is required\n' "$name" >&2; exit 2; fi
done
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
work=$T10_WORK_DIR
mkdir -p "$work/plugins" "$work/final"
openroad_bin=${OPENROAD:-openroad}
if [[ $("$openroad_bin" -version) != *08f67ee5ec* ]]; then
  printf '%s\n' 'This patch requires OpenROAD 26Q2-1164-g08f67ee5ec.' >&2
  exit 2
fi
includes=(
  "-I$T10_OPENROAD_SRC/include"
  "-I$T10_OPENROAD_SRC/src/odb/include"
  "-I$T10_OPENROAD_SRC/src/odb/src/db"
  "-I$T10_OPENROAD_SRC/src/utl/include"
  "-I$T10_THIRDPARTY_INCLUDE" "-I$T10_BOOST_INCLUDE" "-I$T10_ORTOOLS_INCLUDE"
)
build() {
  "${CXX:-g++}" -std=c++20 -O2 -fPIC -shared -DFMT_HEADER_ONLY -DSPDLOG_HEADER_ONLY \
    "${includes[@]}" "$script_dir/$1" -o "$work/plugins/$2" > "$work/$2.build.log" 2>&1
}
build t10_manual_v15_patch.cc t10_manual_v15_case5.so
build t10_manual_v15_enclosure.cc t10_manual_v15_compact_v2.so
build t10_manual_v15_local.cc t10_manual_v15_local_v2.so
includes+=("-I$T10_OPENROAD_SRC/src/drt/include" "-I$T10_OPENROAD_SRC/src/drt/src" -fopenmp)
build t10_manual_v15_gc_diag.cc t10_manual_v15_gc_full.so
variant=ic_t10_frozen_pe_exact_v15_margin_escape_m7_wc_p1000_seed11
original=$T10_ORFS_FLOW/results/asap7/t10_reference_pe/$variant/5_2_route.odb
expected=76cb0aafa5ef8f94bbe7551314a90ab43426b1a8323a236023967c0481a7158b
actual=$(sha256sum "$original")
if [[ ${actual%% *} != "$expected" ]]; then
  printf '%s\n' 'Original v15 route ODB hash does not match.' >&2; exit 2
fi
T10_INPUT_ODB="$original" T10_OUTPUT_ODB="$work/route.odb" T10_PLUGIN_DIR="$work/plugins" \
  "$openroad_bin" -exit "$script_dir/t10_manual_v15_apply.tcl" > "$work/apply.log" 2>&1
"$openroad_bin" -python "$script_dir/t10_manual_v15_audit.py" "$original" "$work/route.odb" \
  > "$work/audit.log" 2>&1
"$openroad_bin" -python "$script_dir/t10_manual_v15_connectivity.py" "$work/route.odb" \
  > "$work/connectivity.log" 2>&1
# Run sequentially to bound memory. Each run checks the entire PE, not a local
# repair window; .raw preserves the unfiltered native-worker markers.
for label in original repaired; do
  input=$original
  if [[ $label == repaired ]]; then input=$work/route.odb; fi
  T10_INPUT_ODB="$input" T10_DRC_REPORT="$work/$label.drc.rpt" \
  T10_PATCH_SO="$work/plugins/t10_manual_v15_gc_full.so" \
    "$openroad_bin" -exit "$script_dir/t10_manual_v15_gc_full.tcl" > "$work/$label.drc.log" 2>&1
done
fixtures=$script_dir/../../fixtures/t10_v15_manual
python3 "$script_dir/t10_manual_v15_compare_drc.py" \
  "$fixtures/historical.drc.rpt" "$fixtures/original_full.drc.rpt" "$fixtures/repaired_full.drc.rpt" \
  "$work/original.drc.rpt" "$work/repaired.drc.rpt" > "$work/drc_verification.json"
T10_WORK_DIR="$work/final" T10_PATCH_SO="$work/plugins/t10_manual_v15_case5.so" \
T10_ENCLOSURE_SO="$work/plugins/t10_manual_v15_compact_v2.so" \
T10_LOCAL_SO="$work/plugins/t10_manual_v15_local_v2.so" \
  "$openroad_bin" -exit "$script_dir/t10_manual_v15_verify.tcl" > "$work/final/verify.log" 2>&1
# Return failure if either extracted timing margin is negative or unconstrained.
awk '$1=="worst" && $2=="slack" {if ($4<0) bad=1; count++} END {exit bad || count!=2}' \
  "$work/final/setup.rpt" "$work/final/hold.rpt"
test ! -s "$work/final/constraint_coverage.rpt"
test ! -s "$work/final/antenna.rpt"
printf '%s\n' 'Whole-PE scoped DRC, connectivity, invariants, extracted timing and antenna checks passed.'
printf '%s\n' 'Electrical-rule violations and incomplete vectorless power remain diagnostic, not signoff or official PPA.'
