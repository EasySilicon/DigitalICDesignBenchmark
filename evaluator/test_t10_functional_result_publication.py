"""Keep the functional correction source-bound and preserve historical PPA."""
import hashlib
import json
import math
from pathlib import Path
import unittest

import jsonschema
from evaluator.score_run import load_rules,score_functional,weighted_suite_score

ROOT=Path(__file__).resolve().parents[1]
RESULTS=ROOT/'results'
BACKUP=RESULTS/'archive/t10-before-cancel-range-20261105'
REVISION_20261105=RESULTS/'archive/t10-before-range-expansion-20261106'


def read(path):return json.loads(path.read_text())


class T10FunctionalPublicationTest(unittest.TestCase):
    def test_current_records_replay_functionality_and_keep_ppa_and_other_tasks(self):
        replay=read(RESULTS/'t10-functional-retest-20261105.json')
        rules=load_rules();schema=read(RESULTS/'result.schema.json')
        changed=[]
        for result in replay['models']:
            name=result['model'];folder=REVISION_20261105/name
            old=read(BACKUP/name/'summary.json');summary=read(folder/'summary.json')
            # Current contract references may advance without changing an
            # earlier task's actual score or qualification evidence.
            without_binding=lambda rows:[{k:v for k,v in row.items() if k!='benchmark_freeze'} for row in rows]
            self.assertEqual(without_binding(old['tasks'][:9]),without_binding(summary['tasks'][:9]))
            row=summary['tasks'][9];task=read(folder/'T10.json')
            evidence=row['functional_retest']['functional_report']
            raw=(ROOT/evidence['path']).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(),evidence['sha256'])
            report=json.loads(raw)
            basic,edge,items=score_functional('T10',report['groups'],rules)
            self.assertEqual(report['seed'],11)
            self.assertEqual(report['candidate_source_sha256'],result['candidate_source_sha256'])
            self.assertEqual(row['functional_total'],basic+edge)
            self.assertEqual(row['functional_total'],result['functional_total'])
            self.assertEqual(row['score_items'],items)
            self.assertEqual(row['full_functional_pass'],result['full_functional_pass'])
            for key in ['functional_total','ppa_score','time_score','display_score']:
                self.assertEqual(row[key],task[key])
            for before,after in zip(old['tasks'],summary['tasks']):
                for key in ['ppa_score','time_score','candidate_delivery_penalty']:
                    self.assertEqual(before.get(key,0),after.get(key,0),(name,key))
            if not row['full_functional_pass']:
                self.assertEqual((row['ppa_score'],row['time_score']),(0,0))
            self.assertEqual(row['display_score'],max(0,row['functional_total']+row['ppa_score']+row['time_score']-row.get('candidate_delivery_penalty',0)))
            weighted=weighted_suite_score({t['task_id']:t['display_score'] for t in summary['tasks']},rules)
            for key in ['weighted_display_score','weighted_display_score_with_unscored_components_omitted']:
                if key in summary:self.assertAlmostEqual(summary[key],weighted['weighted_display_score'],places=12)
            self.assertEqual(summary['full_functional_task_count'],sum(t.get('full_functional_pass',t['functional_total']==50) is True for t in summary['tasks']))
            for component,aliases in {
                'functional_total':['functional_total_sum','functional_score_sum'],
                'ppa_score':['ppa_score_sum','ppa_score_sum_for_available_tasks'],
                'time_score':['time_score_sum','time_score_sum_for_available_tasks'],
                'display_score':['display_score_sum','display_score_subtotal_with_unscored_components_omitted']}.items():
                for key in aliases:
                    if key in summary:self.assertAlmostEqual(summary[key],math.fsum(t[component] for t in summary['tasks']),places=12)
            jsonschema.validate(task,schema)
            if old['weighted_display_score']!=summary['weighted_display_score']:changed.append(name)
        self.assertEqual(set(changed),{'claude-sonnet-5.5','gpt-5.6-sol','glm-5.3'})

    def test_current_and_historical_manifests_and_ppa_reports_stay_valid(self):
        receipt=read(RESULTS/'t10-functional-results-update-20261105.json')
        backup=read(BACKUP/'backup_manifest.json')
        for entry in backup['files']:
            path=BACKUP/entry['path']
            self.assertEqual(path.stat().st_size,entry['bytes'])
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),entry['sha256'])
        for model in receipt['models']:
            name=model['model'];folder=RESULTS/name
            for entry in read(folder/'archive_manifest.json')['files']:
                path=folder/entry['path']
                self.assertEqual(path.stat().st_size,entry['bytes'])
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),entry['sha256'])
            old_manifest=BACKUP/name/'archive_manifest.json'
            if old_manifest.exists():
                for entry in read(old_manifest)['files']:
                    path=old_manifest.parent/entry['path']
                    self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),entry['sha256'])
            for old in (BACKUP/name).glob('T10-ppa*.json'):
                self.assertEqual(old.read_bytes(),(folder/old.name).read_bytes())


if __name__=='__main__':unittest.main()
