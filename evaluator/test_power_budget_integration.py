"""Every current scoring/aggregation route must retain the compile deadline."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import aggregate_with_power_budget as aggregation
import check_t09_with_power_budget as t09
import grade_t10_candidate_ppa as t10
import regrade_trial_ppa as trial_regrade
import run_t10_candidate_regrade as queue
from power_compile_budget import POLICY_ID, TIMEOUT_STATUS, apply_to_scored_record
from regrade_result_archive import regrade_record
from score_run import load_rules
from test_power_compile_budget import record


class PowerBudgetIntegrationTest(unittest.TestCase):
    def test_archive_regrading_cannot_revive_timeout_for_any_task(self):
        for i in range(1,11):
            task=f'T{i:02d}'
            original=dict(task_id=task,functional_total=50,ppa_score=40,time_score=4,
                ppa_eligible=True,display_score=89,candidate_delivery_penalty=5,
                candidate_source_sha256='source',power_compile_policy=POLICY_ID,
                power_compile_records=[record(task)])
            before=copy.deepcopy(original)
            with self.subTest(task=task):
                result=regrade_record(original,load_rules(),{'tasks':{}})
                self.assertEqual((result['ppa_score'],result['time_score'],result['display_score']),(0,0,45))
                self.assertEqual(result['ppa_status'],TIMEOUT_STATUS)
                self.assertEqual(result['power_compile_records'],original['power_compile_records'])
                self.assertEqual(original,before)

    def test_current_archive_missing_or_wrong_receipts_is_an_error_not_zero(self):
        current=dict(task_id='T01',functional_total=50,power_compile_policy=POLICY_ID,
                     candidate_source_sha256='source')
        for records in ([],[record('T02')],[record('T01')|{'candidate_source_sha256':'wrong'}]):
            with self.subTest(records=records),self.assertRaises(ValueError):
                apply_to_scored_record(dict(current,power_compile_records=records))
        old=dict(task_id='T01',ppa_score=35,scoring_policy='historical')
        self.assertEqual(apply_to_scored_record(old),old)

    def test_aggregate_binds_successful_receipts_and_rejects_swapped_seeds(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);pairs=[];rows=[]
            for seed in (11,29,47):
                power=root/f's{seed}/result.json';power.parent.mkdir()
                (power.parent/'power_compile.json').write_text(json.dumps(record('T01',seed,'completed',10)))
                pairs.append((root/f'route{seed}.json',power))
                rows.append(dict(layout_seed=seed,power_record=str(power)))
            with patch.object(aggregation,'source_hash',return_value='source'),patch.object(aggregation,'frozen_aggregate',return_value={'per_seed':rows}):
                result=aggregation.aggregate('T01',root,pairs)
                self.assertEqual(result['power_compile_policy'],POLICY_ID)
                self.assertEqual(len(result['power_compile_records']),3)
                one=pairs[0][1].parent/'power_compile.json';two=pairs[1][1].parent/'power_compile.json'
                first,second=one.read_text(),two.read_text();one.write_text(second);two.write_text(first)
                with self.assertRaises(ValueError):aggregation.aggregate('T01',root,pairs)

    def test_timeout_aggregate_needs_no_nonexistent_power_result(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'power_compile.json').write_text(json.dumps(record('T03')))
            with patch.object(aggregation,'source_hash',return_value='source'),patch.object(aggregation,'frozen_aggregate') as native:
                result=aggregation.aggregate('T03',root,[(root/'route.json',root/'result.json')])
            self.assertEqual(result['measurement_status'],TIMEOUT_STATUS)
            native.assert_not_called()

    def test_t10_current_grader_refuses_legacy_proof_by_default(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(t10,'seed_record',return_value={}):
            with self.assertRaisesRegex(ValueError,'three power compile budget records'):
                t10.grade('model',Path(temp),Path(temp),Path(temp))

    def test_t10_other_queue_recognizes_only_verified_compile_timeout(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'seed11').mkdir();(root/'activity_seed11').mkdir()
            path=root/'activity_seed11/power_compile.json';path.write_text(json.dumps(record()))
            with patch.object(queue,'source_hash',return_value='source'),patch.object(queue.subprocess,'run',return_value=subprocess.CompletedProcess(['power'],124)):
                result=queue.run_power(['power'],root,11)
                self.assertEqual((result['status'],result['ppa_score']),(TIMEOUT_STATUS,0))
            (root/'seed11/activity_queue.log').unlink()
            with patch.object(queue.subprocess,'run',return_value=subprocess.CompletedProcess(['power'],1)):
                with self.assertRaises(subprocess.CalledProcessError):queue.run_power(['power'],root,11)

    def test_t09_current_entry_uses_budget_score_and_restores_frozen_scorer(self):
        import t09_check as frozen
        rules=load_rules()
        groups={g:dict(cases_passed=item.get('required_cases_total',1),cases_total=item.get('required_cases_total',1))
                for item in rules['tasks']['T09'] for g in item['groups']}
        original=frozen.score_run
        def native(*args):
            return frozen.score_run(dict(task_id='T09',groups=groups,delivery_qualified=True,
                elapsed_seconds=1,time_limit_seconds=7200,candidate_delivery_error_count=1))
        with patch.object(t09,'source_hash',return_value='source'),patch.object(frozen,'run',side_effect=native):
            result=t09.run(Path('.'),1,1,True,power_compile_records=[record('T09')])
            self.assertEqual((result['functional_total'],result['ppa_score'],result['display_score']),(50,0,45))
            self.assertIs(frozen.score_run,original)
            with self.assertRaises(ValueError):t09.run(Path('.'),1,1,True,Path('missing'),Path('reference'))
        self.assertIs(frozen.score_run,original)

    def test_trial_regrade_retains_timeout_without_a_power_measurement(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);output=root/'regraded.json'
            prior=dict(task_id='T01',functional_total=50,ppa_score=0,time_score=0,
                candidate_source_sha256='source',power_compile_policy=POLICY_ID,
                power_compile_records=[record('T01')])
            (root/'summary.json').write_text(json.dumps({'tasks':[prior]}))
            args=['regrade',str(root),'--model','test','--output',str(output)]
            with patch.object(sys,'argv',args),patch('builtins.print'):trial_regrade.main()
            row=json.loads(output.read_text())['tasks'][0]
            self.assertEqual((row['status'],row['ppa_score'],row['time_score']),(TIMEOUT_STATUS,0,0))


if __name__=='__main__':unittest.main()
