"""Deadline cleanup and retained physical results through the actual scorer."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch, Mock

import physical_budget as policy
from score_run import load_rules
from score_with_power_budget import score_run
from power_compile_budget import POLICY_ID as POWER_POLICY


class PhysicalBudgetTest(unittest.TestCase):
    def payload(self, task='T01', completed=(11,29)):
        rules=load_rules()
        baseline=json.loads((Path(__file__).resolve().parents[1]/'benchmark/ppa-baselines.json').read_text())['tasks'][task]
        source='a'*64
        physical=[policy.receipt(task,source,s,100 if s in completed else policy.limit_seconds(task),
                    'completed' if s in completed else 'timeout',process_group_terminated=s not in completed)
                  for s in policy.SEEDS]
        power=[dict(policy_id=POWER_POLICY,limit_seconds=1200,task_id=task,
                    candidate_source_sha256=source,layout_seed=s,status='completed',elapsed_seconds=10)
               for s in completed]
        payload=dict(task_id=task,groups={g:dict(cases_passed=item.get('required_cases_total',1),
                         cases_total=item.get('required_cases_total',1))
                         for item in rules['tasks'][task] for g in item['groups']},
                     elapsed_seconds=10,time_limit_seconds=1800,delivery_qualified=True,
                     candidate_source_sha256=source,physical_records=physical,power_compile_records=power,
                     sustained_throughput_passed=True)
        if completed:
            m=copy.deepcopy(baseline)
            m.update(source_sha256=source,routed=True)
            m['per_seed']=[r for r in m['per_seed'] if r['layout_seed'] in completed]
            import statistics
            for k in ('area_um2','delay_ns','energy_per_op_pj'):
                m[k]=statistics.median(r[k] for r in m['per_seed'])
            for k,fn in [('setup_worst_slack_ns',min),('hold_worst_slack_ns',min),
                         ('drc_violations',max),('annotation_fraction',min)]:
                m[k]=fn(r[k] for r in m['per_seed'])
            payload.update(ppa_measurement=policy.attach(m,physical),ppa_reference=baseline)
        return payload

    def test_retained_one_or_two_seeds_score_for_all_tasks(self):
        for task in [f'T{i:02d}' for i in range(1,11)]:
            for completed in [(11,),(29,),(47,),(11,29),(29,47)]:
                with self.subTest(task=task,completed=completed):
                    result=score_run(self.payload(task,completed))
                    self.assertTrue(result['ppa_eligible'])
                    self.assertGreater(result['ppa_score'],0)
                    self.assertGreater(result['time_score'],0)
                    self.assertEqual(result['functional_total'],50)

    def test_t10_alone_has_a_two_hour_physical_deadline(self):
        t01=policy.receipt('T01','source',11,3600,'timeout',process_group_terminated=True)
        t10=policy.receipt('T10','source',11,7200,'timeout',process_group_terminated=True)
        self.assertEqual((t01['policy_id'],t01['limit_seconds']),
                         ('physical-wall-3600s-retain-results-v1',3600))
        self.assertEqual((t10['policy_id'],t10['limit_seconds']),
                         ('physical-wall-7200s-retain-results-v1',7200))
        policy.validate_records([t01],'source','T01',complete=False)
        policy.validate_records([t10],'source','T10',complete=False)
        with self.assertRaisesRegex(ValueError,'invalid physical deadline receipt'):
            policy.validate_records([t10],'source','T01',complete=False)

    def test_t10_completion_between_one_and_two_hours_is_valid(self):
        row=policy.receipt('T10','source',47,5400,'completed')
        self.assertEqual(policy.validate_records([row],'source','T10',complete=False),set())
        row['elapsed_seconds']=7201
        with self.assertRaisesRegex(ValueError,'completed after its deadline'):
            policy.validate_records([row],'source','T10',complete=False)

    def test_no_results_is_zero_without_erasing_function_or_delivery(self):
        p=self.payload(completed=());p['candidate_delivery_error_count']=1
        r=score_run(p)
        self.assertEqual((r['ppa_score'],r['time_score'],r['display_score']),(0,0,45))

    def test_aggregate_no_results_marker_scores_zero(self):
        from aggregate_with_power_budget import aggregate
        p=self.payload(completed=())
        with patch('aggregate_with_power_budget.source_hash',return_value=p['candidate_source_sha256']):
            p['ppa_measurement']=aggregate('T01',Path('.'),[],physical_records=p['physical_records'])
        r=score_run(p)
        self.assertEqual((r['ppa_score'],r['time_score'],r['functional_total']),(0,0,50))

    def test_missing_seed_requires_real_timeout_and_matching_power(self):
        for mutate in [lambda p:p['physical_records'][2].update(process_group_terminated=False),
                       lambda p:p['physical_records'][2].update(candidate_source_sha256='wrong'),
                       lambda p:p['physical_records'].pop(),
                       lambda p:p['power_compile_records'].pop(),
                       lambda p:p['ppa_measurement'].update(area_um2=1)]:
            p=self.payload();mutate(p)
            with self.assertRaises(ValueError):score_run(p)

    def test_power_compile_timeout_still_overrides_retained_results(self):
        p=self.payload();p['power_compile_records'][0].update(status='timeout',elapsed_seconds=1200,process_group_terminated=True)
        r=score_run(p)
        self.assertEqual((r['ppa_score'],r['time_score']),(0,0))
        self.assertEqual(r['ppa_status'],'power_compile_timeout_zero')

    def test_first_seed_power_timeout_does_not_require_remaining_physical_runs(self):
        p=self.payload(completed=(11,))
        p.pop('ppa_measurement');p.pop('ppa_reference')
        p['physical_records']=p['physical_records'][:1]
        p['power_compile_records'][0].update(status='timeout',elapsed_seconds=1200,process_group_terminated=True)
        r=score_run(p)
        self.assertEqual((r['ppa_score'],r['time_score']),(0,0))

    def test_deadline_kills_grandchildren_and_keeps_receipt(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d);marker=path/'escaped';rec=path/'physical_budget.json'
            child='import time,pathlib;time.sleep(.6);pathlib.Path('+repr(str(marker))+').touch()'
            parent='import subprocess,sys,time;subprocess.Popen([sys.executable,"-c",'+repr(child)+']);time.sleep(10)'
            result=policy.run([sys.executable,'-c',parent],task='T01',source='s',seed=11,
                              record_path=rec,seconds=.15)
            time.sleep(.65)
            self.assertEqual(result.returncode,124)
            self.assertFalse(marker.exists())
            self.assertEqual(json.loads(rec.read_text())['status'],'timeout')

    def test_success_and_tool_errors_are_distinct_from_timeout(self):
        with tempfile.TemporaryDirectory() as d:
            for code in [0,7]:
                p=Path(d)/str(code)
                r=policy.run([sys.executable,'-c',f'raise SystemExit({code})'],
                             task='T10',source='s',seed=11,record_path=p)
                self.assertEqual(r.returncode,code)
                self.assertEqual(json.loads(p.read_text())['status'],'completed' if code==0 else 'error')

    def test_actual_aggregate_scores_one_retained_seed(self):
        from ppa_aggregate import source_hash
        from aggregate_with_power_budget import aggregate
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'rtl').mkdir()
            (root/'rtl/files.f').write_text('dut.sv\n')
            (root/'rtl/dut.sv').write_text('module dut; endmodule\n')
            source=source_hash(root);p=self.payload(completed=(11,))
            for rows in [p['physical_records'],p['power_compile_records']]:
                for r in rows:r['candidate_source_sha256']=source
            p['candidate_source_sha256']=source
            report=root/'reports/asap7/dut/seed11/6_finish.rpt'
            route=dict(task='T01',exit_code=0,corner='WC',period_ps=1000,utilization=10,density=.6,
                       seed=11,report=str(report),cell_area_um2=100,critical_path_delay_ps=1100,
                       worst_slack_ps=-100,hold_worst_slack_ps=50,drc_violations=1)
            ref=p['ppa_reference']
            power=dict(task='T01',flow_result_dir=str(root/'results/asap7/dut/seed11'),
                       activity_annotation=.99,ops=10,seed=20260927,workload_sha256=ref['workload_sha256'],
                       workload_id=ref['workload_id'],workload_parameters=ref['workload_parameters'],
                       energy_j_per_op=1e-10,power_w={'total':.01})
            rp=root/'route.json';rp.write_text(json.dumps(route))
            pp=root/'power/result.json';pp.parent.mkdir();pp.write_text(json.dumps(power))
            (pp.parent/'power_compile.json').write_text(json.dumps(p['power_compile_records'][0]))
            measurement=aggregate('T01',root,[(rp,pp)],physical_records=p['physical_records'])
            p['ppa_measurement']=measurement;r=score_run(p)
            self.assertTrue(r['ppa_eligible'])
            self.assertEqual(measurement['drc_violations'],1)
            self.assertEqual([r['layout_seed'] for r in measurement['per_seed']],[11])

    def test_t10_scope_deadline_produces_timeout_receipt(self):
        import run_t10_candidate_40g as native
        with tempfile.TemporaryDirectory() as d:
            process=Mock();process.poll.return_value=None;process.wait.return_value=-9
            with patch.object(native,'PHYSICAL_SECONDS',.01), \
                 patch.object(native,'properties',return_value={'ActiveState':'active'}), \
                 patch.object(native,'stop_scope') as kill, \
                 patch.object(native,'wait_scope_inactive'):
                result=native.monitor('test.scope',Path(d)/'runtime.json',process,
                                      physical_identity=('T10','source',11))
            kill.assert_called_once_with('test.scope')
            self.assertEqual(result['exit_code'],124)
            self.assertEqual(json.loads((Path(d)/'physical_budget.json').read_text())['status'],'timeout')

    def test_route_entry_preserves_timeout_exit_code(self):
        import ppa_probe
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);flow=root/'flow';flow.mkdir();(flow/'Makefile').touch()
            rtl=root/'rtl';rtl.mkdir();(rtl/'files.f').write_text('dut.sv\n')
            (rtl/'dut.sv').write_text('module serdes_rx_comma_aligner; endmodule\n')
            args=['probe','T01',str(root),'--orfs-root',str(root),'--output-dir',str(root/'out')]
            with patch.object(sys,'argv',args),patch.object(ppa_probe.shutil,'which',return_value='/bin/true'),patch.object(ppa_probe,'physical_run',return_value=subprocess.CompletedProcess([],124)),patch('builtins.print'):
                self.assertEqual(ppa_probe.main(),124)
            self.assertEqual(json.loads((root/'out/result.json').read_text())['exit_code'],124)


if __name__=='__main__':unittest.main()
