import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import t04_check


@unittest.skipUnless(shutil.which('verilator'), 'Verilator unavailable')
class T04FrontendTest(unittest.TestCase):
    def test_verilator_only_accepts_reference_and_rejects_wrong_lane(self):
        original_run = subprocess.run
        reference = (t04_check.ROOT / 'reference/T04/rtl/round_robin_stream_arbiter.sv').read_text()

        def verilator_only(command, **kwargs):
            self.assertNotIn(command[0], ('iverilog', 'vvp'))
            return original_run(command, **kwargs)

        with tempfile.TemporaryDirectory() as temp:
            submission = Path(temp)
            (submission / 'rtl').mkdir()
            (submission / 'rtl/files.f').write_text('dut.sv\n')
            for defective in (False, True):
                with self.subTest(defective=defective):
                    rtl = reference.replace('in_data[i] &', 'in_data[(i+1)%N] &') if defective else reference
                    (submission / 'rtl/dut.sv').write_text(rtl)
                    with patch.object(t04_check, 'PARAMETERS', ((4, 8),)), \
                            patch.object(t04_check.subprocess, 'run', side_effect=verilator_only):
                        result = t04_check.run(submission, 11)
                    all_passed = all(g['cases_passed'] == g['cases_total']
                                     for g in result['groups'].values())
                    self.assertEqual(all_passed, not defective)
                    self.assertEqual(result['hdl_frontends'][0]['frontend'], 'verilator')


if __name__ == '__main__':
    unittest.main()
