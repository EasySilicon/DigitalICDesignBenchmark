from pathlib import Path
import sys
import tempfile
import unittest
import hashlib
import json

sys.path.insert(0,str(Path(__file__).parent))
from grade_t10_candidate_ppa import drc_count, grade, workload_parameters, sha


class CandidateScoringTest(unittest.TestCase):
    def test_workload_contract_is_derived_from_actual_vectors_and_rejects_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);directory=root/'workload';directory.mkdir()
            files={};digest=hashlib.sha256()
            for name in ('a','b','as','bs','mode','phase'):
                payload=(name+'\n').encode();path=directory/f'{name}.mem';path.write_bytes(payload)
                files[path.name]={'bytes':len(payload),'sha256':sha(path)}
                digest.update(name.encode());digest.update(len(payload).to_bytes(8,'big'));digest.update(payload)
            manifest=directory/'manifest.json'
            manifest.write_text(json.dumps(dict(task_id='T10',seed=20260925,case_count=200,files=files)))
            expected=dict(seed=20260925,case_count=200,vectors_sha256=digest.hexdigest())
            reference={'workload_sha256':sha(manifest),'workload_parameters':expected}
            self.assertEqual(workload_parameters(root,reference),expected)
            with self.assertRaisesRegex(ValueError,'actual workload differs'):
                workload_parameters(root,reference|{'workload_parameters':expected|{'seed':1}})
            (directory/'a.mem').write_text('changed')
            with self.assertRaisesRegex(ValueError,'vector changed'):
                workload_parameters(root,reference)

    def test_native_drc_counts_are_preserved(self):
        self.assertEqual(drc_count(''),0)
        self.assertEqual(drc_count('violation type: MetalSpacing\nnet a b\nviolation type: Short\n'),2)
        with self.assertRaisesRegex(ValueError,'unrecognized'):
            drc_count('Tool failed before producing DRC results')

    def test_missing_measurements_never_become_a_zero_score(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            with self.assertRaises(FileNotFoundError):
                grade('gpt-6-sol',root,root,root)
            self.assertEqual(list(root.iterdir()),[])


if __name__=='__main__':unittest.main()
