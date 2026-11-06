import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest

from power_compile_budget import CompileBudget, LIMIT_SECONDS
from power_compile_continuation import ContinuedCompileBudget


class ContinuationTest(unittest.TestCase):
    def prepare(self,root,source='candidate',status='error',elapsed=5):
        archive=root/'archive';archive.mkdir();log=archive/'prior.log';log.write_text('original command')
        prior=CompileBudget(root,source,11).record
        prior.update(status=status,elapsed_seconds=elapsed,started_utc='2026-11-04T00:00:00+00:00',
                     commands=[dict(command=['compiler'],log='/old/prior.log')])
        receipt=archive/'power_compile.json';receipt.write_text(json.dumps(prior))
        (root/'compile_continuation.json').write_text(json.dumps(dict(
            reason='evaluator_unmeasured_parent_frontend',prior_receipt=dict(
                path=str(receipt),sha256=hashlib.sha256(receipt.read_bytes()).hexdigest()))))

    def test_prior_time_and_immutable_command_logs_are_carried_forward(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);self.prepare(root)
            with ContinuedCompileBudget(root,'candidate',11) as budget:
                self.assertGreaterEqual(time.monotonic()-budget.started,5)
                self.assertLess(time.monotonic()-budget.started,6)
                self.assertEqual(budget.seconds,LIMIT_SECONDS)
            record=json.loads((root/'power_compile.json').read_text())
            self.assertEqual(record['status'],'completed')
            self.assertGreaterEqual(record['elapsed_seconds'],5)
            self.assertEqual(record['commands'][0]['log'],str(root/'archive/prior.log'))

    def test_other_sources_and_exhausted_budgets_cannot_be_restarted(self):
        for source,status,elapsed in [('other','error',5),('candidate','timeout',LIMIT_SECONDS),
                                      ('candidate','error',LIMIT_SECONDS)]:
            with self.subTest(source=source,status=status),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);self.prepare(root,source,status,elapsed)
                with self.assertRaisesRegex(ValueError,'source-bound'):
                    with ContinuedCompileBudget(root,'candidate',11):pass
                self.assertFalse((root/'power_compile.json').exists())


if __name__=='__main__':unittest.main()
