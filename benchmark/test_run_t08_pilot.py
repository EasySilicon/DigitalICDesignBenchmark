from __future__ import annotations
import inspect
import unittest
from pathlib import Path
from benchmark.run_t08_pilot import command, run

class T08PilotResumeTest(unittest.TestCase):
    def test_resume_keeps_workspace_and_explicit_session(self):
        cmd=command(Path("/trial"),session_id="01a1124b-d87a-7c80-b837-729336114a70",
                    seconds=6740,container_name="trial-resume-1",gate="resume_gate")
        self.assertIn("/trial/workspace:/workspace",cmd)
        self.assertIn("/trial/codex_home:/home/reefshark/.codex",cmd)
        self.assertIn("/trial/empty_skills:/home/reefshark/.codex/skills:ro",cmd)
        shell=cmd[-1]
        self.assertIn("6740s",shell)
        self.assertIn("resume 01a1124b-d87a-7c80-b837-729336114a70 -",shell)
        self.assertIn("/workspace/RESUME_PROMPT.md",shell)
        self.assertIn("/tmp/resume_gate",shell)
        self.assertNotIn("--ephemeral",shell)
        self.assertIn('web_search="disabled"',shell)

    def test_initial_run_is_not_resume(self):
        shell=command(Path("/trial"))[-1]
        self.assertIn("7200s",shell)
        self.assertIn("/workspace/PROMPT.md",shell)
        self.assertNotIn("resume ",shell)

    def test_token_tracking_never_stops_container(self):
        source=inspect.getsource(run)
        watcher=source.split("def usage_watch():",1)[1].split("threading.Thread",1)[0]
        self.assertNotIn("docker",watcher)
        self.assertNotIn("1200000",source)
        self.assertIn('"cap":None',watcher)
        self.assertIn('"stop_enabled":False',watcher)

if __name__=="__main__": unittest.main()
