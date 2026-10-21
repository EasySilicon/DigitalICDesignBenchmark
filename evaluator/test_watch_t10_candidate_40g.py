import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).parent))
import watch_t10_candidate_40g as M


class WatchdogTest(unittest.TestCase):
    def test_flags_dead_controller_without_starting_work(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'t10_ppa_scores40.json').write_text(json.dumps(dict(
                status='running_serial_40g',policy=M.POLICY,models={})))
            with patch.object(M,'active_scopes',return_value=[]),patch.object(M,'service_properties',return_value={'ActiveState':'inactive'}):
                report=M.inspect(root,root,'ic-bcmk-t10-serial40-controller-test.service')
            self.assertTrue(report['alerts'])
            self.assertFalse(report['terminal'])

    def test_completed_queue_is_terminal_only_when_native_jobs_are_gone(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'t10_ppa_scores40.json').write_text(json.dumps(dict(
                status='complete',policy=M.POLICY,models={})))
            with patch.object(M,'active_scopes',return_value=[]),patch.object(M,'service_properties',return_value={'ActiveState':'inactive'}):
                report=M.inspect(root,root,'ic-bcmk-t10-serial40-controller-test.service')
            self.assertFalse(report['alerts'])
            self.assertTrue(report['terminal'])

    def test_resource_fluctuations_do_not_trigger_notifications(self):
        first=dict(queue_status='running',alerts=[],models={'candidate':dict(status='physical_running',layout_seed=11)},
            active_scopes=[{'ram_gib':10}])
        second=first|{'active_scopes':[{'ram_gib':39}]}
        self.assertEqual(M.event_key(first),M.event_key(second))


if __name__=='__main__':unittest.main()
