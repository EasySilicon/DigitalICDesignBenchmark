#!/usr/bin/env bash
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)/env.sh"
set -euo pipefail
t10_init_scratch
backend_root=${T10_BACKEND_ROOT}
orfs_root=${T10_ORFS_ROOT}
qualification=${T10_TRANSPORT_QUALIFICATION_ROOT:-${T10_SCRATCH_ROOT}/t10_qualification/v96_pair_transport}
candidate=$qualification/rtl/npu_systolic_matmul_16x16.sv
variant=${T10_FLOW_VARIANT:-ic_t10_candidate_top_v97_pair_transport_synth_m7_wc_p1000_seed11}
result_dir=$orfs_root/flow/results/asap7/npu_systolic_matmul_16x16/$variant
log=${T10_SCRATCH_ROOT}/t10_frozen_top/${variant}_synthesis.log
mkdir -p "$result_dir"
python3 - "${T10_REFERENCE_RTL}" "$qualification" "$result_dir" <<'PY'
import hashlib,json,sys
from pathlib import Path
reference,q,result=map(Path,sys.argv[1:])
candidate=q/'rtl/npu_systolic_matmul_16x16.sv'
old,new=reference.read_bytes(),candidate.read_bytes()
assert hashlib.sha256(old).hexdigest()=='0c7646d7019e45477582faba0605f1c3ba557810a61cb617844aeeb24b632622'
sha=hashlib.sha256(new).hexdigest()
old_modules=old.split(b'\nendmodule\n',1)[1]
new_modules=new.split(b'\nendmodule\n',1)[1]
d=json.loads((q/'rtl_delta.json').read_text())
if d.get('existing_submodule_definitions_byte_identical'):
    # A new shell helper may follow the exact original PE/tile/math bodies.
    assert new_modules.startswith(old_modules)
    assert d['existing_submodule_definitions_sha256']==hashlib.sha256(old_modules).hexdigest()
else:
    assert old_modules==new_modules and d['all_submodule_definitions_byte_identical']
assert d['rtl_sha256']==sha
qualification=json.loads((q/'qualification.json').read_text())
assert qualification['rtl_sha256']==sha and qualification['qualification_passed']
assert qualification['cases']==2752 and qualification['structure']['pe_instances']==256
assert qualification['structure']['top_state_bits']<=306304
assert qualification['reset_probe_passed'] and not qualification['failures']
evidence={'candidate_only':True,'diagnostic_only':True,'reference_sha256':hashlib.sha256(old).hexdigest(),
          'candidate_sha256':sha,'existing_submodule_definitions_byte_identical':True,
          'all_submodule_definitions_byte_identical':old_modules==new_modules,
          'submodule_source_sha256':hashlib.sha256(new.split(b'\nendmodule\n',1)[1]).hexdigest(),
          'functional_qualification':str(q/'qualification.json'),
          'qualification_sha256':hashlib.sha256((q/'qualification.json').read_bytes()).hexdigest(),
          'functional_cases_passed':2752,'pe_instances':256,
          'top_state_bits':qualification['structure']['top_state_bits'],
          'physical_macro_instances':16,'physical_qualification_passed':False,
          'macro_view_note':'Reuse byte-identical submodules only for diagnosis; not release-qualified views.'}
(result/'rtl_delta.json').write_text(json.dumps(evidence,indent=2)+'\n')
PY
export T10_LAYOUT_SEED=11
tile_dir=$orfs_root/flow/results/asap7/t10_reference_tile_4x4/ic_t10_frozen_tile_v54_onehot_slvtclk_wideclk_grt_m7_wc_p1000_seed11
export T10_TILE_LEF=$tile_dir/t10_reference_tile_4x4_m7.lef
export T10_TILE_LIB=$tile_dir/t10_reference_tile_4x4_wc.lib
t10_require_file "$T10_TILE_LEF"
t10_require_file "$T10_TILE_LIB"
sha256sum "$candidate" "$backend_root/physical/t10_frozen_top/config.mk" \
  "$T10_TILE_LEF" "$T10_TILE_LIB" "$qualification/qualification.json" \
  > "$result_dir/synthesis_inputs.sha256"
ulimit -v 8388608
cd "$orfs_root/flow"
nice -n 10 make DESIGN_CONFIG="$backend_root/physical/t10_frozen_top/config.mk" \
  FLOW_VARIANT="$variant" VERILOG_FILES="$candidate" \
  YOSYS_EXE="${T10_YOSYS_EXE}" \
  OPENROAD_EXE="${T10_OPENROAD_EXE}" NUM_CORES=2 \
  do-yosys-canonicalize do-yosys > "$log" 2>&1
sha256sum "$result_dir/1_2_yosys.v" > "$result_dir/1_2_yosys.v.sha256"
printf 'T10_FULL_TOP_TRANSPORT_SYNTH_PASS %s\n' "$result_dir/1_2_yosys.v"
