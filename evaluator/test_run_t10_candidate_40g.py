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
    def test_frontend_transition_preserves_build_and_never_rewrites_route_or_shell_config(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);seed=root/'seed11';seed.mkdir();activity=root/'activity_seed11';activity.mkdir()
            build=activity/'build';build.mkdir()
            args=build/'Vnpu_systolic_matmul_16x16__hierMkArgs.f';args.write_text('--cc\nactual_parent.v\n')
            (activity/'planning_only').mkdir();(activity/'actual_modules').mkdir()
            shell=root/'mapped_shell.v';shell.write_text('unchanged mapped hardware')
            config=activity/'shell_area.mk';config.write_text('unchanged configuration');mtime=config.stat().st_mtime_ns
            (activity/'shell_synth.log').write_text('completed synthesis')
            (seed/'inputs40.json').write_text(json.dumps({'source_sha256':'candidate'}))
            (seed/'baseline40.json').write_text('completed route must not change')
            (seed/'activity40.log').write_text('old native frontend log')
            (seed/'activity_runtime40.json').write_text(json.dumps(dict(exit_code=143,confirmed=True,
                policy=M.POLICY,systemd_result='signal')))
            (root/'frontend_transition_requested.json').write_text(json.dumps(dict(to='O0_unmeasured_parent',
                resource_policy=M.POLICY,source_sha256='candidate',mapped_shell=M.artifact(shell),
                parent_arguments_sha256=M.sha(args))))
            M.preserve_peripheral_frontend_attempt(root)
            archive=seed/'peripheral_frontend_O1_preserved'
            self.assertTrue((archive/'build'/args.name).exists())
            self.assertEqual((archive/'activity40.log').read_text(),'old native frontend log')
            self.assertEqual((archive/'shell_synth.log').read_text(),'completed synthesis')
            self.assertEqual(config.stat().st_mtime_ns,mtime)
            self.assertEqual((seed/'baseline40.json').read_text(),'completed route must not change')
            self.assertEqual(shell.read_text(),'unchanged mapped hardware')
            self.assertFalse((seed/'activity40.log').exists())
            self.assertIn('not a candidate failure',(archive/'transition.json').read_text())
            with self.assertRaisesRegex(ValueError,'already preserved'):
                M.preserve_peripheral_frontend_attempt(root)

    def test_frontend_retry_cannot_restart_a_scored_or_another_pending_candidate(self):
        state=dict(status='pending_infrastructure_review',models={model:dict(ppa_score=.2,status='measured_and_scored_40g')
            for model in M.TRIALS})
        state['models']['gpt-6-sol']=dict(ppa_score=None,status='pending_infrastructure_review',layout_seed=11)
        M.validate_frontend_retry(state,'gpt-6-sol')
        changed=copy.deepcopy(state);changed['models']['gpt-6-astra']['ppa_score']=None
        with self.assertRaisesRegex(ValueError,'only the canceled'):
            M.validate_frontend_retry(changed,'gpt-6-sol')
        with self.assertRaisesRegex(ValueError,'only the canceled'):
            M.validate_frontend_retry(state,'gpt-6-astra')

    def test_peripheral_policy_transition_preserves_logs_and_valid_connectivity(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);seed=root/'seed11';seed.mkdir()
            activity=root/'activity_seed11';activity.mkdir()
            (seed/'activity40.log').write_text('old mapped-shell attempt')
            (seed/'activity_runtime40.json').write_text('{"confirmed":true}')
            (seed/'baseline40.json').write_text('completed route must not change')
            (activity/'connectivity.json').write_text('passed connectivity must not change')
            (activity/'shell_synth.log').write_text('old timing-first log')
            M.preserve_peripheral_speed_attempt(root)
            archive=seed/'peripheral_speed_mapping_preserved'
            self.assertEqual((archive/'activity40.log').read_text(),'old mapped-shell attempt')
            self.assertEqual((activity/'connectivity.json').read_text(),'passed connectivity must not change')
            self.assertEqual((seed/'baseline40.json').read_text(),'completed route must not change')
            self.assertIn('not a candidate failure',(archive/'transition.json').read_text())

    def test_launcher_repair_preserves_failed_activity_and_never_touches_route(self):
        import json
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);seed=root/'seed11';seed.mkdir()
            activity=root/'activity_seed11';activity.mkdir()
            (activity/'connectivity.log').write_text("ModuleNotFoundError: No module named 'odb'\n")
            (seed/'activity_runtime40.json').write_text(json.dumps({'exit_code':1}))
            (seed/'activity40.log').write_text('old failure')
            (seed/'baseline40.json').write_text('unchanged route')
            M.preserve_python_entry_failure(root)
            archive=seed/'power_python_entry_failure_preserved'
            self.assertEqual((archive/'activity40.log').read_text(),'old failure')
            self.assertEqual((seed/'baseline40.json').read_text(),'unchanged route')
            self.assertFalse(activity.exists())
            with self.assertRaisesRegex(ValueError,'already prepared'):
                M.preserve_python_entry_failure(root)

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
