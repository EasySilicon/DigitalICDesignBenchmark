import threading
import time
import unittest

from benchmark.runner.pipeline import DevelopmentGradingPipeline


class RunnerPipelineTest(unittest.TestCase):
    def test_slow_grading_never_blocks_next_candidate_task(self):
        grade_started = threading.Event()
        release_grade = threading.Event()
        second_developed = threading.Event()
        timeline = []

        def develop(task):
            timeline.append(("develop", task))
            if task == "T02":
                second_developed.set()
            return task + "-submission"

        def grade(task, submission):
            timeline.append(("grade", task))
            if task == "T01":
                grade_started.set()
                self.assertTrue(release_grade.wait(2))

        pipeline = DevelopmentGradingPipeline(("T01", "T02"), develop, grade)
        worker = threading.Thread(target=pipeline.run)
        worker.start()
        self.assertTrue(grade_started.wait(1))
        self.assertTrue(second_developed.wait(1), "T02 was blocked by T01 grading")
        release_grade.set()
        worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertLess(timeline.index(("develop", "T02")), timeline.index(("grade", "T02")))

    def test_grading_is_single_file_even_when_development_runs_ahead(self):
        active = 0
        peak = 0
        lock = threading.Lock()

        def develop(task):
            return task

        def grade(task, submission):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.01)
            with lock:
                active -= 1

        DevelopmentGradingPipeline(range(6), develop, grade).run()
        self.assertEqual(peak, 1)


if __name__ == "__main__":
    unittest.main()
