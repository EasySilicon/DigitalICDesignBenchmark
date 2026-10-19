import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SPEC=importlib.util.spec_from_file_location('t10_bundle',Path(__file__).parent/'t10_backend/v1/export_bundle.py')
BUNDLE=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(BUNDLE)


class ReportBundleTest(unittest.TestCase):
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
