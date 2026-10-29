import json
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from benchmark.runner.grade_job import run


class RunnerGradeJobTest(unittest.TestCase):
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
