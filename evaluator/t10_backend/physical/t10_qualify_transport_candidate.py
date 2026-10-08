"""Run unchanged independent full-DUT streaming/reset/structure acceptance."""
import hashlib
import json
import os
import sys
from pathlib import Path

from t10_paths import load_qualification_module
runner = load_qualification_module('runner_t10_stream')

root=Path(os.environ['T10_TRANSPORT_CANDIDATE_ROOT'])
original_compile=runner.compile_hierarchical
def limited_compile(command,build):
    command=command.copy();command[command.index('-j')+1]='2'
    return original_compile(command,build)
runner.compile_hierarchical=limited_compile
result=runner.run(root,output_dir=root/'reports',mixed_backpressure=True)
result['rtl_sha256']=hashlib.sha256((root/'rtl/npu_systolic_matmul_16x16.sv').read_bytes()).hexdigest()
passed=result.get('phase')=='run' and not result.get('failures') and result.get('reset_probe_passed') \
       and result.get('structure',{}).get('passed') \
       and all(g['cases_passed']==g['cases_total'] for g in result.get('groups',{}).values())
result['qualification_passed']=bool(passed)
(root/'qualification.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:result.get(k) for k in ('phase','cases','groups','reset_probe_passed',
                                         'structure','qualification_passed','rtl_sha256')},indent=2),flush=True)
raise SystemExit(0 if passed else 1)
