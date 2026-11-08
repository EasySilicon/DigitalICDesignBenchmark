"""Final publication strips workflow state while preserving score facts."""
import copy
import unittest

from result_publication import final_summary, final_task, task_record


def sample_summary():
    return dict(suite_id='test-suite',model='test-model',ranking_eligible=False,
                tasks=[dict(task_id=f'T{i:02}',functional_total=50,full_functional_pass=True,
                            ppa_score=30,time_score=2,display_score=82) for i in range(1,11)])


class ResultPublicationTest(unittest.TestCase):
    def test_projection_is_pure_idempotent_and_excludes_source_and_replay_state(self):
        source=sample_summary()
        source['source_trial']='/private/trial'
        source['tasks'][0].update(candidate_source_sha256='a'*64,
            functional_retest={'previous_summary':'private'},archive_evidence={'report':'private'})
        before=copy.deepcopy(source)
        result=final_summary(source)
        self.assertEqual(source,before)
        self.assertEqual(final_summary(result),result)
        self.assertNotIn('source_trial',result)
        self.assertNotIn('functional_retest',result['tasks'][0])
        self.assertNotIn('candidate_source_sha256',result['tasks'][0])
        self.assertEqual(result['display_score_sum'],820)
        self.assertEqual(result['full_functional_task_count'],10)

    def test_override_changes_only_one_task_and_retains_delivery_penalty(self):
        old=final_summary(sample_summary())
        changed=final_summary(old,{'T10':dict(functional_total=40,full_functional_pass=False,
            ppa_eligible=False,ppa_score=0,time_score=0,candidate_delivery_penalty=10,display_score=30)})
        self.assertEqual(old['tasks'][:9],changed['tasks'][:9])
        self.assertEqual(changed['tasks'][-1]['candidate_delivery_penalty'],10)
        self.assertEqual(changed['functional_total_sum'],490)
        self.assertEqual(changed['display_score_sum'],768)
        self.assertAlmostEqual(changed['weighted_display_score'],69)

    def test_missing_duplicate_or_mismatched_task_ids_and_invalid_scores_fail(self):
        for mode in ['missing','duplicate','wrong-override','bad-score','bad-display']:
            source=sample_summary();overrides={}
            if mode=='missing':source['tasks'].pop()
            if mode=='duplicate':source['tasks'][-1]['task_id']='T01'
            if mode=='wrong-override':overrides={'T10':dict(task_id='T09')}
            if mode=='bad-score':source['tasks'][0]['ppa_score']=float('nan')
            if mode=='bad-display':source['tasks'][0]['display_score']=99
            with self.subTest(mode=mode),self.assertRaises(ValueError):final_summary(source,overrides)

    def test_nested_measurements_publish_final_metrics_only_and_use_the_new_measurement(self):
        task=sample_summary()['tasks'][0]
        task.update(ppa_metrics={'area_um2':999},ppa_measurement=dict(area_um2=42,delay_ns=.5,
            energy_per_op_pj=7,per_seed=[{'path':'/private/route'}],source_sha256='private'))
        result=final_task(task)
        self.assertEqual(result['ppa_metrics']['area_um2'],42)
        self.assertNotIn('per_seed',result['ppa_metrics'])
        self.assertNotIn('source_sha256',result['ppa_metrics'])

    def test_pending_scores_and_explicit_unknowns_are_preserved(self):
        task=dict(task_id='T01',functional_total=None,full_functional_pass=None,ppa_score=None,time_score=None,display_score=None)
        result=final_task(task)
        self.assertEqual(result['score_status'],'pending')
        self.assertIsNone(result['candidate_delivery_penalty'])
        self.assertIsNone(result['elapsed_seconds'])
        self.assertIsNone(result['full_functional_pass'])
        self.assertNotIn('path',result)
