from pathlib import Path
import sys
import tempfile
import unittest
import hashlib
import json
import shutil
import grade_t10_candidate_ppa as M

sys.path.insert(0,str(Path(__file__).parent))
from grade_t10_candidate_ppa import drc_count, grade, workload_parameters, sha, functional_score
from unittest.mock import patch


class CandidateScoringTest(unittest.TestCase):
    def test_new_candidate_grades_without_published_history_and_legacy_failure_stays_ineligible(self):
        from physical_budget import receipt
        from delivery_policy import assessment
        from score_run import load_rules
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);trial=root/'trial';workspace=trial/'workspaces/T10'
            (workspace/'rtl').mkdir(parents=True)
            (workspace/'rtl/files.f').write_text('dut.sv\n')
            (workspace/'rtl/dut.sv').write_text('module pe; endmodule\n')
            (workspace/'trial_started_epoch.txt').write_text('0')
            (workspace/'trial_finished_epoch.txt').write_text('10')
            model='new-model';model_dir=root/'work'/model;model_dir.mkdir(parents=True)
            shutil.copytree(workspace/'rtl',model_dir/'submission/rtl')
            source=M.source_hash(workspace)
            (model_dir/'structure.json').write_text(json.dumps(dict(passed=True,candidate_source_sha256=source)))
            for seed in (11,29,47):
                directory=model_dir/f'seed{seed}';directory.mkdir()
                (directory/'physical_budget.json').write_text(json.dumps(
                    receipt('T10',source,seed,7200,'timeout',process_group_terminated=True)))
            groups={group:dict(cases_passed=1,cases_total=1)
                    for item in load_rules()['tasks']['T10'] for group in item['groups']}
            functional=dict(groups=groups,phase='run',cases=9,structure={'passed':True},
                reset_probe_passed=True,failures=[],stream_line='MM_STREAM input_bubble_phases=00000000000000 finished=9')
            grading=trial/'grading/T10';grading.mkdir(parents=True)
            (grading/'functional.json').write_text(json.dumps(functional))
            (grading/'delivery.json').write_text(json.dumps(dict(delivery_qualified=True,delivery_assessment=assessment())))
            with patch.object(M,'load_task') as published:
                report=M.grade(model,root/'work',{model:trial},root/'orfs')
                published.assert_not_called()
            self.assertEqual(report['score']['functional_total'],50)
            self.assertEqual(report['score']['ppa_status'],'physical_timeout_no_results')
            self.assertEqual(report['candidate_source_sha256'],source)
            with patch.object(M,'load_task',return_value=dict(functional_total=49,functional_groups=groups)), \
                    self.assertRaisesRegex(ValueError,'not functionally qualified'):
                M.grade(model,root/'work',{model:trial},root/'orfs',legacy_replay=True)

    def test_functional_full_score_gate_tolerates_only_rounding_noise(self):
        for edges,expected in ((9.999999999999993,50.0),(9.5,49.5)):
            with self.subTest(edges=edges), \
                    patch('grade_t10_candidate_ppa.load_rules',return_value={'functional_total':50}), \
                    patch('grade_t10_candidate_ppa.score_functional',return_value=(40.0,edges,[])):
                self.assertEqual(functional_score({'groups':{}}),expected)

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
