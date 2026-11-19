import json
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from pathlib import Path

from benchmark.runner.grade_job import run


class RunnerGradeJobTest(unittest.TestCase):
    def test_old_final_report_without_requested_resources_is_not_reused(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root/'grading/T07'
            output.mkdir(parents=True)
            report = output/'report.json'
            original = '{"status":"scored","display_score":50}'
            report.write_text(original)
            request = output/'grade_job.json'
            request.write_text(json.dumps({'command':['grader'], 'cwd':str(root),
                'driver_log':str(output/'driver.log'),'lock':str(root/'grade.lock'),
                'report':str(report),'status':str(output/'job_status.json'),
                'pythonpath':str(root),'cpu_weight':10000}))
            with patch('benchmark.runner.grade_job.subprocess.run',
                       return_value=subprocess.CompletedProcess([],17)) as execute:
                self.assertEqual(run(request),17)
            execute.assert_called_once()
            archives = list((root/'grading/_attempts').iterdir())
            self.assertEqual(len(archives),1)
            self.assertEqual((archives[0]/'report.json').read_text(),original)
            self.assertFalse(report.exists())

    def test_weighted_grader_cannot_publish_without_resource_attestation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = root/'report.json'
            request = root/'request.json'
            request.write_text(json.dumps({'command':['grader'], 'cwd':str(root),
                'driver_log':str(root/'driver.log'),'lock':str(root/'grade.lock'),
                'report':str(report),'status':str(root/'job_status.json'),
                'pythonpath':str(root),'cpu_weight':10000}))
            def fake_success(*args, **kwargs):
                report.write_text('{"status":"scored"}')
                return subprocess.CompletedProcess([],0)
            with patch('benchmark.runner.grade_job.subprocess.run', side_effect=fake_success):
                self.assertEqual(run(request),76)
            self.assertFalse(report.exists())
            self.assertEqual(len(list(root.glob('unqualified_report-*.json'))),1)

    def test_cpu_weight_uses_owned_scope_without_fallback(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request = root / 'request.json'
            report = root / 'report.json'
            value = {'command': ['grader', 'T07'], 'cwd': str(root),
                'driver_log': str(root/'driver.log'), 'lock': str(root/'grade.lock'),
                'report': str(report), 'status': str(root/'job_status.json'),
                'pythonpath': str(root), 'cpu_weight': 10000}
            request.write_text(json.dumps(value))
            with patch('benchmark.runner.grade_job.subprocess.run',
                       return_value=subprocess.CompletedProcess([], 17)) as execute:
                self.assertEqual(run(request), 17)
            command = execute.call_args.args[0]
            self.assertEqual(command[:4], ['systemd-run','--user','--scope','--quiet'])
            self.assertIn('--property=CPUWeight=10000', command)
            self.assertTrue(any(item.startswith('--unit=ic-bcmk-grade-') for item in command))
            self.assertIn('grade_resources.py', ' '.join(command))
            self.assertEqual(execute.call_count, 1)
            self.assertFalse(report.exists())
            self.assertEqual(json.loads((root/'job_status.json').read_text())['phase'], 'grader_failed')

    def test_duplicate_jobs_execute_grader_exactly_once(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = root / "report.json"
            count = root / "count.txt"
            grader = root / "grader.py"
            grader.write_text(
                "import json,time\n"
                "from pathlib import Path\n"
                f"count=Path({str(count)!r}); report=Path({str(report)!r})\n"
                "n=int(count.read_text())+1 if count.exists() else 1\n"
                "count.write_text(str(n)); time.sleep(.1)\n"
                "report.write_text(json.dumps({'status':'scored'}))\n")
            request = root / "request.json"
            request.write_text(json.dumps({
                "command": [sys.executable, str(grader)], "cwd": str(root),
                "driver_log": str(root / "driver.log"), "lock": str(root / "grade.lock"),
                "report": str(report), "status": str(root / "job_status.json"),
                "pythonpath": str(root),
            }))
            results = []
            workers = [threading.Thread(target=lambda: results.append(run(request))) for _ in range(2)]
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join()
            self.assertEqual(sorted(results), [0, 0])
            self.assertEqual(count.read_text(), "1")
            self.assertIn(json.loads((root / "job_status.json").read_text())["phase"],
                          {"complete", "skipped_existing_report"})

    def test_success_without_report_is_infrastructure_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request = root / "request.json"
            request.write_text(json.dumps({
                "command": [sys.executable, "-c", "pass"], "cwd": str(root),
                "driver_log": str(root / "driver.log"), "lock": str(root / "grade.lock"),
                "report": str(root / "missing.json"),
                "status": str(root / "job_status.json"), "pythonpath": str(root),
            }))
            self.assertEqual(run(request), 74)
            self.assertEqual(json.loads((root / "job_status.json").read_text())["phase"],
                             "missing_report")

    def test_retry_archives_interrupted_attempt_before_clean_run(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "grading" / "T08"
            output.mkdir(parents=True)
            (output / "delivery_sandbox").mkdir()
            (output / "report.json").write_text(json.dumps({
                "status": "infrastructure_or_candidate_attribution_pending",
            }))
            grader = root / "grader.py"
            grader.write_text(
                "import json\n"
                "from pathlib import Path\n"
                f"output=Path({str(output)!r})\n"
                "assert not (output/'delivery_sandbox').exists()\n"
                "(output/'report.json').write_text(json.dumps({'status':'scored'}))\n")
            request = output / "grade_job.json"
            request.write_text(json.dumps({
                "command": [sys.executable, str(grader)], "cwd": str(root),
                "driver_log": str(output / "driver.log"),
                "lock": str(root / "grade.lock"),
                "report": str(output / "report.json"),
                "status": str(output / "job_status.json"), "pythonpath": str(root),
            }))
            self.assertEqual(run(request), 0)
            self.assertEqual(json.loads((output / "report.json").read_text())["status"],
                             "scored")
            attempts = list((root / "grading" / "_attempts").iterdir())
            self.assertEqual(len(attempts), 1)
            self.assertTrue((attempts[0] / "delivery_sandbox").is_dir())

    def test_retryable_report_is_not_treated_as_complete(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = root / "report.json"
            grader = root / "grader.py"
            grader.write_text(
                "import json\n"
                "from pathlib import Path\n"
                f"Path({str(report)!r}).write_text(json.dumps({{'status':'infrastructure_pending'}}))\n")
            request = root / "grade_job.json"
            request.write_text(json.dumps({
                "command": [sys.executable, str(grader)], "cwd": str(root),
                "driver_log": str(root / "driver.log"), "lock": str(root / "grade.lock"),
                "report": str(report), "status": str(root / "job_status.json"),
                "pythonpath": str(root),
            }))
            self.assertEqual(run(request), 75)
            self.assertEqual(json.loads((root / "job_status.json").read_text())["phase"],
                             "retryable_report")


if __name__ == "__main__":
    unittest.main()
