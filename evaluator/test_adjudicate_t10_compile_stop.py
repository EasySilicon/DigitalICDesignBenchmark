import copy
import unittest

from adjudicate_t10_compile_stop import DECISION, POLICY, STATUS, validate_decision


class CompileStopDecisionTest(unittest.TestCase):
    def setUp(self):
        self.receipt=dict(kind=STATUS,user_decision=DECISION,model='gpt-6-sol',
            candidate_source_sha256='source',resource_policy=POLICY,ppa_score=0,
            time_score=0,measurement_completed=False,unit='exact.scope')
        self.runtime=dict(policy=POLICY,confirmed=True,ended_utc='date',exit_code=-15,
            systemd_result='success',unit='exact')

    def test_explicit_stop_is_not_an_oom_or_a_measurement(self):
        validate_decision(self.receipt,self.runtime,'gpt-6-sol','source')

    def test_missing_or_changed_user_decision_is_rejected(self):
        for key,value in [('user_decision',''),('candidate_source_sha256','other'),
                ('model','gpt-6-astra'),('measurement_completed',True),('ppa_score',1)]:
            receipt=copy.deepcopy(self.receipt);receipt[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):
                validate_decision(receipt,self.runtime,'gpt-6-sol','source')

    def test_live_successful_oom_or_wrong_scope_runtime_is_rejected(self):
        for key,value in [('ended_utc',None),('exit_code',None),('exit_code',0),
                ('systemd_result','oom-kill'),('confirmed',False),('unit','other.scope')]:
            runtime=copy.deepcopy(self.runtime);runtime[key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):
                validate_decision(self.receipt,runtime,'gpt-6-sol','source')


if __name__=='__main__':unittest.main()
