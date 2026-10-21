import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).parent))
from publish_t10_candidate_ppa import task_record,summary_record,POLICY
import publish_t10_candidate_ppa as M


def measured():
    return dict(model='gpt-6-sol',elapsed_seconds=1000,measurement={'source_sha256':'unchanged'},
        score=dict(functional_total=50,full_functional_pass=True,delivery_qualified=True,ppa_eligible=True,ppa_score=40,
            ppa_rank_bucket=32,time_score=4,display_score=94,candidate_delivery_error_count=0,
            candidate_delivery_penalty=0,display_score_before_candidate_penalty=94))


class PublishTest(unittest.TestCase):
    def test_automatic_compile_timeout_has_its_own_policy_not_manual_or_oom(self):
        report=measured();report.pop('measurement')
        report.update(candidate_source_sha256='unchanged',queue_status=M.TIMEOUT_STATUS,
            adjudication='power compilation exceeded 1200 seconds',measurement_completed=False,
            failing_seed=11,power_compile_timeout_record=dict(policy_id='power-compile-wall-1200s-v1',
                status='timeout',task_id='T10',layout_seed=11,candidate_source_sha256='unchanged',
                limit_seconds=1200,elapsed_seconds=1201,process_group_terminated=True))
        report['score'].update(ppa_score=0,time_score=0,display_score=50,display_score_before_candidate_penalty=50)
        task=task_record(dict(candidate_sha256='unchanged',functional_total=50),report,{},'date')
        self.assertEqual(task['functional_total'],50)
        self.assertEqual(task['ppa_score'],0);self.assertEqual(task['time_score'],0)
        self.assertIn('power-compile-wall-1200s-v1',task['scoring_policy'])
        self.assertNotIn('resource_failure_adjudication',task)
        self.assertNotIn('explicit-user',task['scoring_policy'])

    def test_user_compile_stop_is_explicit_and_not_mislabeled_as_oom(self):
        report=measured();report.pop('measurement')
        report.update(candidate_source_sha256='unchanged',queue_status=M.COMPILE_STOP_ZERO,
            adjudication='explicit user stop, not OOM',measurement_completed=False)
        report['score'].update(ppa_score=0,time_score=0,display_score=50,
            display_score_before_candidate_penalty=50,ppa_rank_bucket=0)
        task=task_record(dict(candidate_sha256='unchanged',functional_total=50),report,{},'date')
        self.assertEqual(task['functional_total'],50)
        self.assertEqual(task['ppa_score'],0)
        self.assertEqual(task['time_score'],0)
        self.assertNotIn('resource_failure_adjudication',task)
        self.assertNotIn('ppa_measurement',task)
        self.assertEqual(task['ppa_adjudication'],report['adjudication'])
        self.assertIn('explicit-user-compile-stop-zero',task['scoring_policy'])

    def test_partial_publication_requires_opt_in_and_cached_native_rescoring(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);model='gpt-6-sol';directory=root/model;directory.mkdir()
            report=measured();(directory/'scored40.json').write_text(json.dumps(report))
            state={'models':{model:{'ppa_score':None,'status':'pending_infrastructure_review'}}}
            original=copy.deepcopy(state)
            with self.assertRaisesRegex(ValueError,'incomplete'):
                M.verified_report(model,state,root,root,root)
            with patch.object(M,'prepare'),patch.object(M,'grade',return_value=report) as scorer:
                self.assertEqual(M.verified_report(model,state,root,root,root,allow_cached=True),report)
                scorer.assert_called_once_with(model,root,root,root,cached_only=True)
            changed=copy.deepcopy(report);changed['score']['ppa_score']=41
            with patch.object(M,'prepare'),patch.object(M,'grade',return_value=changed):
                with self.assertRaisesRegex(ValueError,'disagrees'):
                    M.verified_report(model,state,root,root,root,allow_cached=True)
            self.assertEqual(state,original)

    def test_partial_publication_cannot_manufacture_a_missing_report(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);state={'models':{'gpt-6-sol':{'ppa_score':None}}}
            with self.assertRaises(FileNotFoundError):
                M.verified_report('gpt-6-sol',state,root,root,root,allow_cached=True)
            self.assertEqual(list(root.iterdir()),[])

    def test_summary_only_historical_record_needs_verified_trial_identity(self):
        old=dict(functional_total=50,delivery_qualified=None)
        with self.assertRaisesRegex(ValueError,'identity or functional'):
            task_record(old,measured(),{},'date')
        updated=task_record(old,measured(),{},'date',verified_source='unchanged')
        self.assertEqual(updated['candidate_sha256'],'unchanged')
        self.assertTrue(updated['delivery_qualified'])
        self.assertEqual(updated['elapsed_seconds'],1000)
        self.assertIsNone(old['delivery_qualified'])

    def test_retains_original_functional_evidence_and_candidate_identity(self):
        old=dict(candidate_sha256='unchanged',functional_total=50,
            functional_groups={'MM-INT':{'cases_passed':128}},trial='original')
        before=copy.deepcopy(old)
        updated=task_record(old,measured(),{'path':'receipt'},'2026-10-20')
        self.assertEqual(old,before)
        self.assertEqual(updated['functional_groups'],old['functional_groups'])
        self.assertEqual(updated['candidate_sha256'],'unchanged')
        self.assertEqual(updated['ppa_score'],40)
        self.assertEqual(updated['t10_ppa_remeasurement']['resource_policy'],POLICY)
        self.assertFalse(updated['ranking_eligible'])

    def test_refuses_changed_candidate_or_functional_score(self):
        with self.assertRaisesRegex(ValueError,'identity or functional'):
            task_record({'candidate_sha256':'other','functional_total':50},measured(),{},'date')
        report=measured();report['score']['functional_total']=49
        with self.assertRaisesRegex(ValueError,'identity or functional'):
            task_record({'candidate_sha256':'unchanged','functional_total':50},report,{},'date')

    def test_summary_only_changes_t10_and_recomputes_totals(self):
        old=dict(tasks=[dict(task_id='T09',functional_total=50,ppa_score=20,time_score=3,display_score=73,
            preserved={'evidence':'do not overwrite'}),dict(task_id='T10',functional_total=50,
            ppa_score=None,time_score=None,display_score=50)],pending_components={'T10':['ppa_score','time_score']},
            task_scoring_policies={'T09':'preserve original task policy'})
        before=copy.deepcopy(old)
        task=task_record({'candidate_sha256':'unchanged','functional_total':50},measured(),{},'date')
        updated=summary_record(old,task,'date')
        self.assertEqual(old,before)
        self.assertEqual(updated['tasks'][0],old['tasks'][0])
        self.assertEqual(updated['display_score_sum'],167)
        self.assertAlmostEqual(updated['weighted_display_score'],73*.20+94*.25)
        self.assertTrue(updated['totals_complete'])
        self.assertEqual(updated['pending_components'],{})
        self.assertEqual(updated['task_scoring_policies']['T09'],'preserve original task policy')
        self.assertEqual(updated['task_scoring_policies']['T10'],task['scoring_policy'])
        self.assertTrue(any('40 GiB' in reason for reason in updated['ranking_ineligible_reasons']))
        self.assertTrue(any('hard macros' in reason for reason in updated['ranking_ineligible_reasons']))


if __name__=='__main__':unittest.main()
