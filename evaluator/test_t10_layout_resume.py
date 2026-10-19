import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SPEC=importlib.util.spec_from_file_location('t10_layout',Path(__file__).parent/'t10_backend/v1/run_layout.py')
MODULE=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class LayoutResumeTest(unittest.TestCase):
    def test_verified_completion_skips_tools_but_changed_outputs_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp)/'work'; result=Path(temp)/'results'
            output.mkdir(); result.mkdir()
            inputs={'block':'fp0','seed':47}
            (output/'inputs.json').write_text(json.dumps(inputs))
            self.assertFalse(MODULE.completed_baseline(output,result,inputs))
            artifacts={}
            for name in MODULE.baseline_files('fp0',MODULE.BLOCKS['fp0'][0]):
                path=result/name; path.write_text('synthetic unit-test artifact')
                artifacts[name]={'bytes':path.stat().st_size,'sha256':MODULE.sha(path)}
            (output/'baseline.completed.json').write_text(json.dumps(dict(status='flow_completed_not_yet_qualified',inputs_sha256=MODULE.sha(output/'inputs.json'),result_dir=str(result),artifacts=artifacts)))
            self.assertTrue(MODULE.completed_baseline(output,result,inputs))
            with self.assertRaisesRegex(RuntimeError,'input provenance'):
                MODULE.completed_baseline(output,result,dict(inputs,seed=29))
            (result/'6_final.v').write_text('changed')
            with self.assertRaisesRegex(RuntimeError,'output changed'):
                MODULE.completed_baseline(output,result,inputs)
