"""Portable controls for actual measured evidence, not synthetic PPA values."""
import hashlib
import copy
import json
from pathlib import Path
import re
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
FIXTURES=ROOT/'evaluator/fixtures/t10_v1_three_seed'
sys.path.insert(0,str(ROOT/'evaluator/t10_backend/v1'))
from complete_seed import check_activity
from export_bundle import verify_bundle
sys.path.pop(0)


class V1EvidenceTest(unittest.TestCase):
    def test_three_real_seeds_and_portable_reports_match_authoritative_baseline(self):
        from jsonschema import Draft202012Validator
        import statistics
        baseline=json.loads((ROOT/'benchmark/ppa-baselines.json').read_text())['tasks']['T10']
        bundle=ROOT/baseline['report_index'];directory=bundle.parent
        self.assertEqual(hashlib.sha256(bundle.read_bytes()).hexdigest(),baseline['report_index_sha256'])
        index=verify_bundle(directory)
        portable={(row['original_path'],row['sha256']):directory/row['path'] for row in index['portable']}
        def record(artifact):
            return json.loads(portable[(artifact['path'],artifact['sha256'])].read_text())
        evidence_path=ROOT/baseline['evidence_record']
        self.assertEqual(hashlib.sha256(evidence_path.read_bytes()).hexdigest(),baseline['evidence_record_sha256'])
        evidence=json.loads(evidence_path.read_text())
        Draft202012Validator(json.loads((ROOT/'benchmark/tasks/T10/ppa-evidence.schema.json').read_text())).validate(evidence)
        self.assertEqual(evidence['measurement_scope'],'single_pe')
        self.assertEqual(evidence['measurement_status'],'three_seed_single_pe')
        self.assertEqual([row['layout_seed'] for row in evidence['per_seed']],[11,29,47])
        for row,normalized in zip(evidence['per_seed'],baseline['per_seed']):
            self.assertEqual(row['layout_seed'],normalized['layout_seed'])
            physical=record(row['physical_record']);activity=record(row['activity_manifest'])
            self.assertEqual(physical['status'],'single_seed_physical_qualified')
            self.assertFalse(physical['failures'])
            self.assertEqual(set(physical['blocks']),{'pe','fp0','fp1','fp2','int','cpa'})
            check_activity(activity,physical,next(r['sha256'] for r in activity['netlists'] if r['block']=='shell'))
            full=record(row['levels']['pe']['artifacts']['full_geometry'])
            self.assertEqual(full['status'],'single_seed_all_geometry_passed')
            self.assertEqual(set(full['blocks']),set(physical['blocks']))
            for artifact in full['blocks'].values():
                connectivity=record(artifact)
                self.assertEqual(connectivity['status'],'passed')
                self.assertEqual(connectivity['wire_iterator_policy'],'OpenDB_paths_plus_explicit_RECT_decoder')
            power=row['power']
            self.assertEqual(len(power['components']),10)
            self.assertEqual(power['matrix_blocks'],200)
            self.assertGreaterEqual(power['activity_annotation_fraction'],.95)
            self.assertAlmostEqual(sum(piece['power_w'] for piece in power['components']),power['total_power_w'])
            self.assertAlmostEqual(power['energy_j_per_block']*1e12,normalized['energy_per_op_pj'])
            self.assertEqual(normalized['drc_violations'],0)
            self.assertGreaterEqual(normalized['setup_worst_slack_ns'],0)
            self.assertGreaterEqual(normalized['hold_worst_slack_ns'],0)
        for key in ('area_um2','delay_ns','energy_per_op_pj','average_power_mw'):
            self.assertEqual(baseline[key],statistics.median(row[key] for row in baseline['per_seed']))
            self.assertEqual(baseline[key],evidence['aggregate'][key])

    def test_complete_activity_matches_actual_physical_gate_netlists(self):
        activity=json.loads((FIXTURES/'seed11_activity_manifest.json').read_text())
        physical=json.loads((FIXTURES/'seed11_physical.json').read_text())
        shell=next(row['sha256'] for row in activity['netlists'] if row['block']=='shell')
        check_activity(activity,physical,shell)
        wrong=copy.deepcopy(physical)
        wrong['blocks']['pe']['inputs']['netlist']['sha256']='a'*64
        with self.assertRaisesRegex(ValueError,'physical pe'):
            check_activity(activity,wrong,shell)
        with self.assertRaisesRegex(ValueError,'shell changed'):
            check_activity(activity,physical,'b'*64)

    def test_reused_macro_source_components_are_byte_identical(self):
        audit=json.loads((FIXTURES/'component_source_audit.json').read_text())
        old=(FIXTURES/'legacy_macro_source.sv').read_text()
        new=(ROOT/'evaluator/reference/T10_v15/rtl/npu_systolic_matmul_16x16.sv').read_text()
        self.assertEqual(hashlib.sha256(old.encode()).hexdigest(),audit['legacy_rtl_sha256'])
        self.assertEqual(hashlib.sha256(new.encode()).hexdigest(),audit['v15_rtl_sha256'])
        pattern=r'\bmodule\s+([^\s(;]+).*?\bendmodule\b'
        legacy={m[1]:m[0] for m in re.finditer(pattern,old,re.S)}
        frozen={m[1]:m[0] for m in re.finditer(pattern,new,re.S)}
        self.assertEqual(set(legacy),set(frozen))
        self.assertEqual(len(legacy),19)
        self.assertEqual({row['module'] for row in audit['components']},set(legacy))
        self.assertEqual(re.sub(pattern,'',old,flags=re.S),re.sub(pattern,'',new,flags=re.S))
        self.assertFalse(re.search(r'`(?:include|ifdef|ifndef|elsif|else|endif)\b',old+new))
        self.assertEqual({name for name in legacy if legacy[name]!=frozen[name]},{'t10_reference_pe'})
        for component in audit['components']:
            name=component['module']
            self.assertEqual(hashlib.sha256(legacy[name].encode()).hexdigest(),component['legacy_sha256'])
            self.assertEqual(hashlib.sha256(frozen[name].encode()).hexdigest(),component['v15_sha256'])

    def test_seed11_complete_physical_qualification_and_frozen_macro_libraries(self):
        record=json.loads((FIXTURES/'seed11_physical.json').read_text())
        self.assertEqual(record['status'],'single_seed_physical_qualified')
        self.assertEqual(record['measurement_scope'],'single_pe')
        self.assertEqual(record['layout_seed'],11)
        self.assertEqual(record['failures'],{})
        self.assertEqual(set(record['blocks']),{'fp0','fp1','fp2','int','cpa','pe'})
        for block in record['blocks'].values():
            self.assertEqual(block['status'],'qualified')
            self.assertEqual(block['reports']['drc']['bytes'],0)
            self.assertEqual(block['reports']['constraint_coverage']['bytes'],0)
            self.assertGreaterEqual(block['timing_ps']['internal_setup'],0)
            self.assertGreaterEqual(block['timing_ps']['internal_hold'],0)
        pe=record['blocks']['pe']
        self.assertGreaterEqual(pe['timing_ps']['setup'],0)
        self.assertGreaterEqual(pe['timing_ps']['hold'],0)
        self.assertEqual(pe['timing_ps']['setup_tns'],0)
        self.assertEqual(pe['timing_ps']['hold_tns'],0)
        probe=json.loads((ROOT/'evaluator/t10_pe_reference_probe.json').read_text())
        self.assertEqual([lib['sha256'] for lib in pe['wc_libraries'][5:]],probe['inputs']['macro_lib_sha256'])
        checker=ROOT/'evaluator/t10_backend/v1/verify_physical.py'
        self.assertEqual(record['checker_sha256'],hashlib.sha256(checker.read_bytes()).hexdigest())

    def test_complete_seed11_power_accounting_and_annotation(self):
        record=json.loads((FIXTURES/'seed11_power.json').read_text())
        self.assertEqual(record['measurement_scope'],'single_pe')
        self.assertEqual(record['layout_seed'],11)
        self.assertEqual(record['power_corner'],'TT')
        self.assertEqual(record['instance_weights'],{'pe':1})
        self.assertEqual(record['matrix_blocks'],200)
        self.assertEqual(len(record['components']),10)
        self.assertEqual(record['components'][0]['instance'],'pe_shell')
        self.assertEqual(len({row['instance'] for row in record['components']}),10)
        self.assertAlmostEqual(sum(row['power_w'] for row in record['components']),record['total_power_w'],places=12)
        self.assertAlmostEqual(sum(record['components_w'].values()),record['total_power_w'],places=12)
        self.assertAlmostEqual(record['total_power_w']*record['vcd_window_seconds']/200,record['energy_j_per_block'],places=20)
        self.assertEqual(len(record['tt_macro_abstracts']),5)
        self.assertEqual(len(record['tt_standard_libraries']),5)
        for row in record['components']:
            self.assertGreaterEqual(row['activity_annotation_fraction'],.95)
            self.assertEqual(row['sequential_activity_annotation_fraction'],1.0)
            self.assertEqual(row['activity_import']['policy'],'exact_physical_net_connected_pin_activity_v1')

    def test_whole_final_database_connectivity_is_not_only_five_edited_nets(self):
        record=json.loads((FIXTURES/'seed11_geometric_connectivity.json').read_text())
        self.assertEqual(record['status'],'passed')
        self.assertEqual(record['failures'],[])
        self.assertEqual(record['signal_nets_checked'],60649)
        self.assertEqual(record['terminals_checked'],167863)
        self.assertGreater(record['shapes_checked'],2900000)
        source=ROOT/'evaluator/t10_backend/v1/check_connectivity.py'
        self.assertEqual(record['checker_sha256'],hashlib.sha256(source.read_bytes()).hexdigest())
        closure=json.loads((ROOT/'evaluator/t10_pe_manual_closure.json').read_text())
        final=next(row for row in closure['external_artifacts'] if row['role']=='repaired_final')
        self.assertEqual(record['odb']['sha256'],final['sha256'])

    def test_actual_structure_report_binds_frozen_source(self):
        record=json.loads((FIXTURES/'v15_structure.json').read_text())
        self.assertTrue(record['passed'])
        self.assertEqual(record['pe_instances'],256)
        self.assertEqual(record['mesh_paths'],[16,16])
        self.assertLessEqual(record['top_state_bits'],306304)
        for key,path in {
            'rtl_sha256':'evaluator/reference/T10_v15/rtl/npu_systolic_matmul_16x16.sv',
            'filelist_sha256':'evaluator/reference/T10_v15/rtl/files.f',
            'checker_sha256':'evaluator/t10_structure_check.py',
        }.items():
            self.assertEqual(record[key],hashlib.sha256((ROOT/path).read_bytes()).hexdigest())
