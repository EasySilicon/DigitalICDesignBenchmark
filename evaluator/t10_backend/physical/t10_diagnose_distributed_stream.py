"""Run a diagnostic copy of the golden testbench with failure-cycle prints.

Acceptance predicates are unchanged; this is not a formal qualification receipt.
"""
import json
import os
import sys
from pathlib import Path
from t10_paths import load_qualification_module
runner = load_qualification_module('runner_t10_stream')
root = Path(os.environ['T10_DISTRIBUTED_CANDIDATE_ROOT'])
original_compile = runner.compile_hierarchical
def diagnostic_compile(command, build):
    command = command.copy(); command[command.index('-j')+1] = '2'
    command = [str(root/'diagnostic_tb.sv') if x.endswith('/hidden/tb_hidden_T10_stream.sv') else x for x in command]
    return original_compile(command, build)
runner.compile_hierarchical = diagnostic_compile
result = runner.run(root, output_dir=root/'diagnostic_reports', mixed_backpressure=True,
                    run_reset_probe=False)
(root/'diagnostic_result.json').write_text(json.dumps(result, indent=2)+'\n')
print(result.get('stream_line'), flush=True)
