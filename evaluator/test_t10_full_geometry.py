from pathlib import Path
import shutil
import subprocess
import unittest


class FullGeometryRegression(unittest.TestCase):
    @unittest.skipUnless(shutil.which('openroad'),'native OpenROAD not installed')
    def test_native_attached_and_floating_rectangles(self):
        probe=Path(__file__).parent/'fixtures/t10_v1_three_seed/rect_iterator_probe.py'
        result=subprocess.run(['openroad','-exit','-no_init','-python',str(probe)],capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('RECT_PATCH_REGRESSION_PASS',result.stdout)


if __name__=='__main__':
    unittest.main()
