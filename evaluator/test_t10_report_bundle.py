import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC=importlib.util.spec_from_file_location('t10_bundle',Path(__file__).parent/'t10_backend/v1/export_bundle.py')
BUNDLE=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(BUNDLE)


class ReportBundleTest(unittest.TestCase):
    def test_export_uses_actual_dependencies_without_inventory_or_duplicate_reference(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);repo=root/'repo';work=root/'work';work.mkdir()
            for name,text in [('benchmark/tasks/T10/ppa.md','# contract\n'),
                              ('benchmark/tasks/T10/ppa-evidence.schema.json','{}'),
                              ('evaluator/t10_structure_check.py','# checker\n'),
                              ('evaluator/t10_backend/v1/debug_only.tcl','# unrelated\n'),
                              ('measured_checker.py','# actual measured input\n')]:
                path=repo/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
            checker=repo/'measured_checker.py'
            native=work/'native.cpp';native.write_text('native runtime\n')
            for seed in (11,29,47):
                directory=work/f'seed{seed}_activity_directnets'
                (directory/'saif_window').mkdir(parents=True);(directory/'build').mkdir()
                corrected=directory/'saif_window/t10_saif_window.cpp';corrected.write_text('corrected runtime\n')
                executable=directory/'build/Vtb_hidden_T10_stream_windowed';executable.write_text('test binary\n')
                (directory/'activity.saif').write_text('activity\n')
                average=directory/'average.saif';average.write_text('average\n')
                (directory/'activity_manifest.json').write_text(json.dumps(dict(
                    activity_sha256=BUNDLE.sha(directory/'activity.saif'),saif_writer=dict(
                    native_source=str(native),native_sha256=BUNDLE.sha(native),
                    corrected_sha256=BUNDLE.sha(corrected),executable_sha256=BUNDLE.sha(executable)))))
                (directory/'merge_audit.json').write_text(json.dumps(dict(output_sha256=BUNDLE.sha(average))))
                (directory/'staged_build_manifest.json').write_text('{}')
                (directory/'simulation.log').write_text('checked simulation\n')
            evidence=work/'evidence.json'
            evidence.write_text(json.dumps(dict(measurement_status='three_seed_single_pe',measurement_scope='single_pe',
                per_seed=[dict(layout_seed=seed,levels={'pe':{'artifacts':{}}}) for seed in (11,29,47)],
                actual_input=dict(path=str(checker),bytes=checker.stat().st_size,sha256=BUNDLE.sha(checker)))))
            # Obsolete sidecars cannot add dependencies, even if present beside the evidence.
            (work/'evaluator_inventory.json').write_text('not a required input')
            (work/'scoring_reference.json').write_text('not a required input')
            bundle=root/'bundle'
            with patch.object(BUNDLE,'REPO',repo):
                BUNDLE.export(evidence,work,bundle)
                index=BUNDLE.verify_bundle(bundle)
                self.assertEqual({row['path'] for row in index['repository']},
                    {'measured_checker.py','benchmark/tasks/T10/ppa.md',
                     'benchmark/tasks/T10/ppa-evidence.schema.json','evaluator/t10_structure_check.py'})
                self.assertFalse(any('evaluator_inventory' in row['path'] or 'scoring_reference' in row['path']
                                     for row in index['portable']))
                checker.write_text('changed measured input\n')
                with self.assertRaisesRegex(ValueError,'dependency missing/changed'):
                    BUNDLE.verify_bundle(bundle)

    def test_historical_dependency_requires_exact_live_or_archived_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo, bundle = root / 'repo', root / 'bundle'
            repo.mkdir(); bundle.mkdir()
            source = repo / 'checker.py'
            source.write_text('historical checker\n')
            expected = BUNDLE.sha(source)
            size = source.stat().st_size
            row = dict(path='checker.py', bytes=size, sha256=expected)
            (bundle / 'index.json').write_text(json.dumps(dict(portable=[], repository=[row])))
            with patch.object(BUNDLE, 'REPO', repo):
                BUNDLE.verify_bundle(bundle)
                original = source.read_bytes()
                source.write_text('updated checker\n')
                with self.assertRaisesRegex(ValueError, 'dependency missing/changed'):
                    BUNDLE.verify_bundle(bundle)
                snapshots = bundle / 'repository_snapshots'
                snapshots.mkdir()
                archived = snapshots / (expected + '_checker.py')
                archived.write_bytes(original)
                BUNDLE.verify_bundle(bundle)
                self.assertEqual(BUNDLE.repository_artifact(bundle, 'checker.py', expected, size), archived)
                archived.write_text('tampered historical checker\n')
                with self.assertRaisesRegex(ValueError, 'dependency missing/changed'):
                    BUNDLE.verify_bundle(bundle)

    def test_raw_report_export_cannot_write_into_repository(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            with patch.object(BUNDLE,'REPO',root),self.assertRaisesRegex(ValueError,'outside the repository'):
                BUNDLE.export(root/'unused.json',root,root/'evaluator/fixtures/reports')
            self.assertFalse((root/'evaluator').exists())

    def test_incomplete_assembly_cannot_create_bundle(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);evidence=root/'evidence.json';output=root/'output'
            evidence.write_text(json.dumps(dict(measurement_status='pending',per_seed=[])))
            with self.assertRaisesRegex(ValueError,'completed three-seed'):
                BUNDLE.export(evidence,root,output)
            self.assertFalse(output.exists())

    def test_portable_verification_does_not_require_external_mount(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);report=root/'timing.rpt';report.write_text('worst slack max 1.0\n')
            index=dict(portable=[dict(path=report.name,bytes=report.stat().st_size,sha256=BUNDLE.sha(report))],
                       repository=[],external=[dict(original_path='/unavailable/final.odb',sha256='f'*64)])
            (root/'index.json').write_text(json.dumps(index))
            BUNDLE.verify_bundle(root)
            report.write_text('altered\n')
            with self.assertRaisesRegex(ValueError,'missing/changed'):BUNDLE.verify_bundle(root)

    def test_portable_path_cannot_escape_bundle(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);index=dict(portable=[dict(path='../escape',bytes=0,sha256='a'*64)],repository=[])
            (root/'index.json').write_text(json.dumps(index))
            with self.assertRaisesRegex(ValueError,'missing/changed'):BUNDLE.verify_bundle(root)
