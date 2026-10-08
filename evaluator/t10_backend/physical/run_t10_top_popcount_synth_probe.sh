#!/usr/bin/env bash
set -euo pipefail
# Synthesis only: the complete parent still contains sixteen 4x4 tile macros.
# Keep the frozen reference untouched until candidate physical qualification.
private_root=/home/reefshark/research/agent_os/ic_bcmk_eval_private
orfs_root=/mnt/ubu_3T/ic_bcmk_orfs_asap7
qualification=/mnt/ubu_3T/ic_bcmk_scratch/t10_qualification/v65_popcount
candidate=$qualification/rtl/npu_systolic_matmul_16x16.sv
variant=ic_t10_frozen_top_v75_popcount_synth_m7_wc_p1000_seed11
result_dir=$orfs_root/flow/results/asap7/npu_systolic_matmul_16x16/$variant
log=/mnt/ubu_3T/ic_bcmk_scratch/t10_frozen_top/${variant}_synthesis.log
mkdir -p "$result_dir"
python3 - "$private_root/refs/T10/rtl/npu_systolic_matmul_16x16.sv" "$qualification" "$result_dir" <<'PY'
import hashlib,json,sys
from pathlib import Path
reference,q,result=map(Path,sys.argv[1:])
candidate=q/'rtl/npu_systolic_matmul_16x16.sv'
old,new=reference.read_bytes(),candidate.read_bytes()
assert hashlib.sha256(old).hexdigest()=='0c7646d7019e45477582faba0605f1c3ba557810a61cb617844aeeb24b632622'
sha=hashlib.sha256(new).hexdigest()
assert sha=='68da56e51120c4dd6b34cfd7100409c47b13d661cb97845acd8a2566c2805531'
before=b'assign final_pop = (|out_valid) && out_ready;'
after=b'assign final_pop = (output_queue_count != 0) && out_ready;'
comments=(b'    // Each enqueued entry has nonzero valid because final_push requires\n'
          b'    // |output_stage_valid. Queue occupancy therefore gives the same pop\n'
          b'    // condition locally, without reducing the four distant output-valid bits.\n')
assert old.count(before)==1 and old.replace(b'    '+before,comments+b'    '+after)==new
assert old.split(b'endmodule',1)[1]==new.split(b'endmodule',1)[1]
qualification=json.loads((q/'qualification.json').read_text())
assert qualification['rtl_sha256']==sha and qualification['qualification_passed']
assert qualification['cases']==2752 and qualification['structure']['pe_instances']==256
assert qualification['reset_probe_passed'] and not qualification['failures']
evidence={'candidate_only':True,'reference_sha256':hashlib.sha256(old).hexdigest(),
          'candidate_sha256':sha,'only_top_module_changed':True,
          'all_submodule_definitions_byte_identical':True,
          'submodule_source_sha256':hashlib.sha256(old.split(b'endmodule',1)[1]).hexdigest(),
          'functional_qualification':str(q/'qualification.json'),
          'qualification_sha256':hashlib.sha256((q/'qualification.json').read_bytes()).hexdigest(),
          'functional_cases_passed':2752,'pe_instances':256,
          'physical_macro_instances':16,'physical_qualification_passed':False}
(result/'rtl_delta.json').write_text(json.dumps(evidence,indent=2)+'\n')
PY
export T10_LAYOUT_SEED=11
tile_dir=$orfs_root/flow/results/asap7/t10_reference_tile_4x4/ic_t10_frozen_tile_v54_onehot_slvtclk_wideclk_grt_m7_wc_p1000_seed11
export T10_TILE_LEF=$tile_dir/t10_reference_tile_4x4_m7.lef
export T10_TILE_LIB=$tile_dir/t10_reference_tile_4x4_wc.lib
test -s "$T10_TILE_LEF"
test -s "$T10_TILE_LIB"
ulimit -v 8388608
cd "$orfs_root/flow"
# Both targets below run synth.sh/Yosys, without synth_odb or any physical step.
nice -n 10 make DESIGN_CONFIG="$private_root/physical/t10_frozen_top/config.mk" \
  FLOW_VARIANT="$variant" VERILOG_FILES="$candidate" \
  YOSYS_EXE=/home/reefshark/.local/bin/yosys \
  OPENROAD_EXE=/home/reefshark/.local/bin/openroad NUM_CORES=2 \
  do-yosys-canonicalize do-yosys > "$log" 2>&1
sha256sum "$result_dir/1_2_yosys.v" > "$result_dir/1_2_yosys.v.sha256"
printf 'T10_FULL_TOP_POPCOUNT_SYNTH_PASS %s\n' "$result_dir/1_2_yosys.v"
