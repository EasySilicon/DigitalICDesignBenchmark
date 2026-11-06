"""Explicit infrastructure continuation without restarting a seed's budget."""
import hashlib
import json
import time
from pathlib import Path

from power_compile_budget import CompileBudget


class ContinuedCompileBudget(CompileBudget):
    def __enter__(self):
        authorization=self.output/'compile_continuation.json'
        prior=None
        if authorization.exists():
            decision=json.loads(authorization.read_text())
            receipt=Path(decision['prior_receipt']['path'])
            if hashlib.sha256(receipt.read_bytes()).hexdigest()!=decision['prior_receipt']['sha256']:
                raise ValueError('prior compilation receipt changed')
            prior=json.loads(receipt.read_text())
            if (decision.get('reason')!='evaluator_unmeasured_parent_frontend'
                    or prior.get('status')!='error'
                    or not 0<=prior.get('elapsed_seconds',-1)<self.seconds
                    or any(prior.get(key)!=self.record[key] for key in
                           ('policy_id','limit_seconds','task_id','candidate_source_sha256','layout_seed'))):
                raise ValueError('invalid source-bound compilation continuation')
        result=super().__enter__()
        if prior is not None:
            self.started-=prior['elapsed_seconds']
            self.record.update(prior_elapsed_seconds=prior['elapsed_seconds'],
                               prior_compile_receipt=decision['prior_receipt'],
                               original_started_utc=prior['started_utc'])
            for entry in prior['commands']:
                entry=dict(entry)
                log=receipt.parent/Path(entry['log']).name
                if not log.is_file():raise ValueError('prior compilation log is missing')
                entry['log']=str(log)
                self.record['commands'].append(entry)
        return result
