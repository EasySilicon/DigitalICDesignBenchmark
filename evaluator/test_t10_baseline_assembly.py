from pathlib import Path
import hashlib
import subprocess
import sys
import tempfile
import unittest


class BaselineAssemblyTest(unittest.TestCase):
    def test_historical_before_image_requires_exact_archived_original(self):
        sys.path.insert(0,str(Path(__file__).parent/'t10_backend/v1'))
        try:
            from assemble_baseline import check_archived_invariant
        finally:
            sys.path.pop(0)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);canonical=root/'final.odb';original=root/'original.odb'
            canonical.write_bytes(b'repaired');original.write_bytes(b'original')
            archived=dict(path=str(original),bytes=8,sha256=hashlib.sha256(b'original').hexdigest())
            invariant=dict(before=dict(archived,path=str(canonical)))
            manual=dict(original_artifacts={'6_final.odb':archived})
            check_archived_invariant(invariant,manual)
            self.assertEqual(invariant['before']['path'],str(canonical))
            original.write_bytes(b'tampered')
            with self.assertRaisesRegex(ValueError,'changed artifact'):
                check_archived_invariant(invariant,manual)
            original.write_bytes(b'original')
            invariant['before']['sha256']='f'*64
            with self.assertRaisesRegex(ValueError,'differs from archived'):
                check_archived_invariant(invariant,manual)

    def test_incomplete_seeds_cannot_create_any_baseline_output(self):
        script=Path(__file__).parent/'t10_backend/v1/assemble_baseline.py'
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            output=root/'must_not_be_created/evidence.json'
            result=subprocess.run([sys.executable,str(script),'--work',str(root),'--orfs',str(root),'--output',str(output)],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('three-seed evidence incomplete',result.stderr)
            self.assertFalse(output.parent.exists())
