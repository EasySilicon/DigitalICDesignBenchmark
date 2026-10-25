import copy
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

from power_compile_budget import CompileBudget,PowerCompileTimeout,POLICY_ID,validate_timeout
from power_probe_with_budget import run_probe
import power_probe_with_budget as probe_cli
from score_with_power_budget import score_run
from score_run import load_rules
from score_run import score_run as frozen_score_run
from run_t10_candidate_40g import compile_timeout_zero,POLICY


def record(task='T10',seed=11,status='timeout',elapsed=1200):
    return dict(policy_id=POLICY_ID,task_id=task,limit_seconds=1200,layout_seed=seed,
        candidate_source_sha256='source',elapsed_seconds=elapsed,status=status,process_group_terminated=True)


class PowerCompileBudgetTest(unittest.TestCase):
    def test_current_cli_dispatches_every_task_to_its_correct_backend(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source='a'*64
            for i in range(1,10):
                task=f'T{i:02d}'
                args=['probe','--task',task,'--candidate-source-sha256',source,'--layout-seed','29',
                    '--output-dir',str(root/'power'),'--flow-result-dir',str(root/'route')]
                with patch.object(sys,'argv',args),patch.object(probe_cli.importlib,'import_module') as imported, \
                        patch.object(probe_cli,'run_probe',return_value=0) as run:
                    self.assertEqual(probe_cli.main(),0)
                    self.assertEqual(imported.call_args.args[0],'t08_power_probe' if task=='T08' else 'ppa_power_probe')
                    forward=run.call_args.args[1]
                    self.assertEqual(forward[0],'--flow-result-dir' if task=='T08' else task)
                    self.assertNotIn('--task',forward)
            args=['probe','--task','T10','--candidate-source-sha256',source,'--layout-seed','29',
                '--model-dir',str(root/'candidate'),'--orfs',str(root/'orfs'),
                '--output-dir',str(root/'candidate/activity_seed29')]
            with patch.object(sys,'argv',args),patch('ppa_aggregate.source_hash',return_value=source), \
                    patch('t10_candidate_power.measure') as measure:
                self.assertEqual(probe_cli.main(),0)
                measure.assert_called_once_with(root/'candidate',29,root/'orfs')

    def test_success_at_exact_limit_preserves_all_ten_tasks_scoring(self):
        rules=load_rules()
        references=json.loads((Path(__file__).resolve().parents[1]/'benchmark/ppa-baselines.json').read_text())['tasks']
        for task in rules['tasks']:
            reference=references[task]
            source=reference['source_sha256']
            groups={g:dict(cases_passed=item.get('required_cases_total',1),cases_total=item.get('required_cases_total',1))
                for item in rules['tasks'][task] for g in item['groups']}
            payload=dict(task_id=task,groups=groups,delivery_qualified=True,elapsed_seconds=1,
                time_limit_seconds=14400,sustained_throughput_passed=True,candidate_source_sha256=source,
                ppa_measurement=copy.deepcopy(reference),ppa_reference=reference,
                power_compile_records=[record(task,s,'completed',1200)|{'candidate_source_sha256':source} for s in (11,29,47)])
            with self.subTest(task=task):
                self.assertEqual(score_run(payload),frozen_score_run(payload)|{
                    'delivery_penalty_policy':'delivery-contract-cap10-v1',
                    'delivery_penalty_status':'adjudicated',
                    'power_compile_policy':POLICY_ID,'candidate_source_sha256':source,
                    'power_compile_records':payload['power_compile_records']})

    def test_real_adapter_build_completes_before_longer_simulation(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'build').mkdir()
            compiler=root/'verilator';compiler.symlink_to(sys.executable)
            simulation=root/'build/Vtb';simulation.symlink_to(sys.executable)
            def main():
                compiled=subprocess.run([str(compiler),'-c','print("COMPILED")'],text=True,capture_output=True,timeout=300)
                self.assertEqual(compiled.stdout,'COMPILED\n')
                self.assertFalse((root/'power_compile.json').exists())
                subprocess.run([str(simulation),'-c','import time;time.sleep(1)'],check=True,timeout=3)
                receipt=json.loads((root/'power_compile.json').read_text())
                self.assertEqual(receipt['status'],'completed');self.assertLess(receipt['elapsed_seconds'],.8)
            module=SimpleNamespace(main=main,__file__='frozen_probe.py')
            run_probe(module,[],root,'source',11,'T03',
                budget_factory=lambda *args,**kwargs:CompileBudget(*args,**kwargs,seconds=.8))

    def test_positive_completion_after_limit_and_duplicate_seeds_are_rejected(self):
        for records in ([record('T01',status='completed',elapsed=1200.001)],
                [record('T01'),record('T01')]):
            with self.subTest(records=records),self.assertRaises(ValueError):
                score_run(dict(task_id='T01',candidate_source_sha256='source',power_compile_records=records))

    def test_commands_share_one_deadline_including_make_and_link(self):
        with tempfile.TemporaryDirectory() as temp:
            now=[0.0]
            def waited(timeout):now[0]+=500;return 0
            process=Mock(pid=999,returncode=0);process.wait.side_effect=waited
            with patch('power_compile_budget.time.monotonic',side_effect=lambda:now[0]),patch('power_compile_budget.subprocess.Popen',return_value=process):
                with CompileBudget(temp,'source',11) as budget:
                    budget.run(['verilator'],Path(temp)/'first.log',temp)
                    budget.run(['make'],Path(temp)/'second.log',temp)
            self.assertEqual([c.kwargs['timeout'] for c in process.wait.call_args_list],[1200,700])
            result=json.loads((Path(temp)/'power_compile.json').read_text())
            self.assertEqual(result['status'],'completed');self.assertEqual(result['elapsed_seconds'],1000)

    def test_expiry_before_next_command_does_not_grant_a_fresh_budget(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(PowerCompileTimeout):
                with CompileBudget(temp,'source',11,seconds=.01) as budget:
                    time.sleep(.02)
                    budget.run(['must-not-start'],Path(temp)/'none.log',temp)
            self.assertFalse((Path(temp)/'none.log').exists())

    @unittest.skipUnless(hasattr(os,'fork'),'POSIX process-group cleanup')
    def test_timeout_kills_compiler_and_term_ignoring_grandchild_and_preserves_log(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);pidfile=root/'child.pid'
            script=('import os,signal,time,pathlib\n'
                'pid=os.fork()\n'
                'if pid==0:\n signal.signal(signal.SIGTERM,signal.SIG_IGN)\n pathlib.Path("child.pid").write_text(str(os.getpid()))\n time.sleep(60)\n'
                'else:\n print("COMPILER STARTED",flush=True)\n time.sleep(60)\n')
            with self.assertRaises(PowerCompileTimeout):
                with CompileBudget(root,'source',11,seconds=.5) as budget:
                    budget.run([sys.executable,'-c',script],root/'compile.log',root)
            self.assertIn('COMPILER STARTED',(root/'compile.log').read_text())
            data=json.loads((root/'power_compile.json').read_text());self.assertEqual(data['status'],'timeout')
            self.assertTrue(data['process_group_terminated'])
            pid=int(pidfile.read_text())
            for _ in range(100):
                stat=Path(f'/proc/{pid}/stat')
                try:
                    if stat.read_text().split()[2]=='Z':break
                except (FileNotFoundError,ProcessLookupError):
                    break
                time.sleep(.01)
            else:self.fail('compiler grandchild survived the timeout')

    def test_missing_tool_is_an_error_not_a_zero(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(FileNotFoundError):
                with CompileBudget(temp,'source',11) as budget:
                    budget.run(['/definitely/missing/compiler'],Path(temp)/'compile.log',temp)
            self.assertEqual(json.loads((Path(temp)/'power_compile.json').read_text())['status'],'error')

    def test_adapter_preserves_timeout_even_when_frozen_probe_catches_oserror(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);compiler=root/'verilator';compiler.symlink_to(sys.executable)
            def main():
                try:subprocess.run([str(compiler),'-c','import time;time.sleep(5)'])
                except OSError:return 1
            module=SimpleNamespace(main=main,__file__='frozen_probe.py')
            with self.assertRaises(PowerCompileTimeout):
                run_probe(module,[],root,'source',11,'T01',
                    budget_factory=lambda *args,**kwargs:CompileBudget(*args,**kwargs,seconds=.05))
            self.assertEqual(json.loads((root/'power_compile.json').read_text())['status'],'timeout')

    def test_timeout_zero_for_all_ten_tasks_preserves_functional_and_penalties(self):
        rules=load_rules()
        for task in rules['tasks']:
            groups={g:dict(cases_passed=item.get('required_cases_total',1),cases_total=item.get('required_cases_total',1))
                for item in rules['tasks'][task] for g in item['groups']}
            payload=dict(task_id=task,groups=groups,delivery_qualified=True,elapsed_seconds=1,
                time_limit_seconds=14400,sustained_throughput_passed=True,candidate_source_sha256='source',
                candidate_delivery_error_count=1,power_compile_records=[record(task)])
            before=copy.deepcopy(payload)
            result=score_run(payload)
            with self.subTest(task=task):
                self.assertEqual(result['functional_total'],50)
                self.assertEqual(result['ppa_score'],0);self.assertEqual(result['time_score'],0)
                self.assertEqual(result['display_score'],45);self.assertIn('1200',result['ppa_zero_reason'])
                self.assertEqual(payload,before)

    def test_wrong_identity_error_nan_and_unproved_positive_are_rejected(self):
        for changed in (dict(task_id='T09'),dict(candidate_source_sha256='wrong'),dict(status='error'),
                dict(elapsed_seconds=1199),dict(elapsed_seconds=float('nan')),dict(process_group_terminated=False)):
            with self.subTest(changed=changed),self.assertRaises(ValueError):validate_timeout(record()|changed,'source',11)
        with self.assertRaisesRegex(ValueError,'three completed'):
            score_run(dict(task_id='T01',ppa_measurement={'source_sha256':'source'}))

    def test_t10_automatic_zero_requires_its_own_124_and_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);out=root/'model/activity_seed11';out.mkdir(parents=True)
            runtime=dict(exit_code=1,confirmed=True,policy=POLICY,systemd_result='success')
            self.assertIsNone(compile_timeout_zero(root,'model',11,runtime,'source'))
            runtime['exit_code']=124
            with self.assertRaises(FileNotFoundError):compile_timeout_zero(root,'model',11,runtime,'source')
            (out/'power_compile.json').write_text(json.dumps(record()))
            self.assertEqual(compile_timeout_zero(root,'model',11,runtime,'source')['ppa_score'],0)

    def test_adapter_overrides_legacy_300s_compile_and_excludes_simulation(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);native=Mock(return_value=subprocess.CompletedProcess(['sim'],0,'',''))
            budgets=[]
            class FakeBudget:
                def __init__(self,*args,**kwargs):self.record={'commands':[]};self.closed=False;budgets.append(self)
                def __enter__(self):return self
                def run(self,command,log,cwd,**kwargs):self.record['commands'].append(command);Path(log).write_text('native compile output')
                def __exit__(self,*args):self.closed=True
            def main():
                result=subprocess.run(['verilator','--binary','design.v'],text=True,capture_output=True,timeout=300)
                self.assertEqual(result.stdout,'native compile output')
                subprocess.run(['make','hier_build'],capture_output=True)
                subprocess.run([str(root/'build/Vtb')],timeout=600)
                self.assertTrue(budgets[0].closed)
            module=SimpleNamespace(main=main,__file__='frozen_probe.py')
            with patch('power_probe_with_budget.subprocess.run',native):
                run_probe(module,[],root,'source',11,'T01',budget_factory=FakeBudget)
            self.assertEqual(len(budgets),1);self.assertEqual(len(budgets[0].record['commands']),2)
            self.assertEqual(native.call_count,1);self.assertEqual(native.call_args.kwargs['timeout'],600)


if __name__=='__main__':unittest.main()
