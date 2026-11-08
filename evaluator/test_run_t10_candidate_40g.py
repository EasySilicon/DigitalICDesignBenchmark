from pathlib import Path
import copy
import json
import sys
import tempfile
import unittest
from unittest.mock import patch,Mock

sys.path.insert(0,str(Path(__file__).parent))
import run_t10_candidate_40g as M


class Serial40Test(unittest.TestCase):
    def test_explicit_candidates_are_graded_in_order_without_a_model_allowlist(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);work=root/'work';work.mkdir()
            trials={'new-a':root/'trial-a','new-b':root/'trial-b'}
            for model in trials:
                for seed in (11,29,47):
                    directory=work/model/f'activity_seed{seed}';directory.mkdir(parents=True)
                    (directory/'power.json').write_text('{}')
            def report(model,*args,**kwargs):
                return dict(model=model,score=dict(ppa_score=35,time_score=1,display_score=86))
            with patch.object(M,'prepare',side_effect=lambda model,*args:dict(model=model)), \
                    patch.object(M,'physical_timed_out',return_value=False), \
                    patch.object(M,'completed_physical',return_value=True), \
                    patch('grade_t10_candidate_ppa.grade',side_effect=report) as grade, \
                    patch.object(M.subprocess,'Popen') as process:
                state=M.run_candidates(trials,work,root/'orfs')
            self.assertEqual(list(state['models']),list(trials))
            self.assertEqual([call.args[0] for call in grade.call_args_list],list(trials))
            self.assertEqual(state['status'],'complete')
            process.assert_not_called()

    def test_terminal_failure_and_changed_selection_cannot_automatically_resume(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);trials={'new-model':root/'trial'}
            state=dict(policy=M.POLICY,trial_selection={'new-model':str(root/'trial')},
                       status='pending_infrastructure_review',models={'new-model':{'ppa_score':None}})
            path=root/'t10_ppa_scores40.json';path.write_text(json.dumps(state))
            with patch.object(M,'prepare') as prepare:
                with self.assertRaisesRegex(ValueError,'automatic retry'):
                    M.run_candidates(trials,root,root/'orfs')
                with self.assertRaisesRegex(ValueError,'selection changed'):
                    M.run_candidates({'other-model':root/'trial'},root,root/'orfs')
            prepare.assert_not_called()

    def test_compile_timeout_stops_remaining_power_seeds(self):
        from power_compile_budget import POLICY_ID,LIMIT_SECONDS,TIMEOUT_STATUS
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);work=root/'work';work.mkdir();model='new-model'
            directory=work/model/'seed11';directory.mkdir(parents=True)
            activity=work/model/'activity_seed11';activity.mkdir()
            receipt=dict(policy_id=POLICY_ID,limit_seconds=LIMIT_SECONDS,task_id='T10',
                layout_seed=11,candidate_source_sha256='source',status='timeout',
                elapsed_seconds=LIMIT_SECONDS,process_group_terminated=True)
            (activity/'power_compile.json').write_text(json.dumps(receipt))
            runtime=dict(exit_code=124,confirmed=True,policy=M.POLICY,systemd_result='success')
            with patch.object(M,'prepare',return_value=dict(model=model,source_sha256='source')), \
                    patch.object(M,'physical_timed_out',return_value=False), \
                    patch.object(M,'completed_physical',return_value=True),patch.object(M,'assert_serial'), \
                    patch.object(M,'monitor',return_value=runtime),patch.object(M.subprocess,'Popen') as process, \
                    patch('grade_t10_candidate_ppa.grade') as grade:
                state=M.run_candidates({model:root/'trial'},work,root/'orfs')
            self.assertEqual(process.call_count,1)
            self.assertEqual(state['models'][model]['status'],TIMEOUT_STATUS)
            self.assertEqual(state['models'][model]['ppa_score'],0)
            self.assertEqual(json.loads((activity/'power_compile.json').read_text()),receipt)
            grade.assert_not_called()





    def test_scope_suffix_is_explicit_for_systemctl(self):
        with patch.object(M.subprocess,'run',return_value=Mock(returncode=0,stdout='ActiveState=active\n')) as run:
            M.properties('candidate-baseline40')
            self.assertEqual(run.call_args.args[0][3],'candidate-baseline40.scope')
            M.properties('candidate-baseline40.scope')
            self.assertEqual(run.call_args.args[0][3],'candidate-baseline40.scope')

    def test_resume_does_not_retry_terminal_failure(self):
        import json
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            self.assertFalse(M.completed_physical(root))
            (root/'baseline40.json').write_text(json.dumps({'exit_code':1}))
            with self.assertRaisesRegex(ValueError,'terminal physical failure'):
                M.completed_physical(root)

    def test_timeout_recovery_refuses_an_active_scope(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'runtime40.json').write_text(json.dumps(dict(policy=M.POLICY,confirmed=True,unit='scope')))
            with patch.object(M,'properties',return_value=dict(ActiveState='active')), \
                 self.assertRaisesRegex(ValueError,'retired'):
                M.recover_retired_timeout(root,model='m',source='s',seed=29,
                    elapsed_seconds=3600,ended_utc='now')

    def test_refuses_a_second_candidate_eda_scope(self):
        output='ic_t10_candidate_other-baseline.scope loaded active running make\n'
        with patch.object(M.subprocess,'check_output',return_value=output):
            with self.assertRaisesRegex(RuntimeError,'refusing parallel'):
                M.assert_serial()
            M.assert_serial('ic_t10_candidate_other-baseline.scope')

    def test_waits_for_finished_scope_to_retire_before_next_seed(self):
        states=[dict(ActiveState='deactivating'),dict(ActiveState='inactive')]
        with patch.object(M,'properties',side_effect=states), patch.object(M.time,'sleep') as sleep:
            M.wait_scope_inactive('candidate-baseline40')
        sleep.assert_called_once_with(.2)

    def test_nonstandard_deadline_requires_authorization(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError,'authorization'):
                M.monitor('scope',Path(temp)/'runtime.json',Mock(),physical_limit_seconds=3600)

    def test_t10_standard_deadline_is_two_hours(self):
        self.assertEqual(M.PHYSICAL_SECONDS,7200)

    def test_authorized_completion_continuation_has_no_deadline(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(M,'properties',return_value=dict(Result='success',ActiveState='inactive')), \
                 patch.object(M,'wait_scope_inactive'):
                M.monitor('scope',Path(temp)/'runtime.json',Mock(poll=lambda:0,wait=lambda:0),
                    physical_identity=('T10','source',47),physical_limit_seconds=None,
                    limit_authorization={'authority':'benchmark_owner'})
            receipt=json.loads((Path(temp)/'physical_budget.json').read_text())
            self.assertEqual(receipt['policy_id'],'physical-completion-continuation-v1')
            self.assertIsNone(receipt['limit_seconds'])
            self.assertEqual(receipt['status'],'completed')

    def test_resumed_monitor_counts_prior_active_runtime(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(M,'properties',return_value=dict(Result='success',ActiveState='inactive')), \
                 patch.object(M,'wait_scope_inactive'), patch.object(M.time,'monotonic',side_effect=[1000,1005]):
                result=M.monitor('scope',Path(temp)/'runtime.json',Mock(poll=lambda:0,wait=lambda:0),
                    physical_identity=('T10','source',29),physical_elapsed_seconds=1200)
            receipt=json.loads((Path(temp)/'physical_budget.json').read_text())
            self.assertEqual(receipt['elapsed_seconds'],1205)
            self.assertEqual(result['exit_code'],0)

    def test_monitor_retains_ram_and_swap_peaks_and_actual_policy_confirmation(self):
        values={'memory.max':str(40*1024**3),'memory.swap.max':'max','memory.current':'123',
                'memory.peak':'456','memory.swap.current':'12','memory.swap.peak':'34'}
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(M,'properties',return_value=dict(ControlGroup='/scope',Result='success',ActiveState='inactive')), \
                 patch.object(M,'sample',return_value=values):
                result=M.monitor('scope',Path(temp)/'runtime.json',Mock(poll=lambda:0,wait=lambda:0))
            self.assertTrue(result['confirmed'])
            self.assertEqual(result['peak_memory_bytes'],456)
            self.assertEqual(result['peak_swap_bytes'],34)
            self.assertEqual(result['policy']['concurrency'],1)
            self.assertEqual(result['policy']['max_address_space'],'unlimited')


if __name__=='__main__':unittest.main()
