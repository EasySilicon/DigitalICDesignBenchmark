"""Independent candidate-development and serial grading queues."""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable, Iterable
from typing import Any


class PipelineError(RuntimeError):
    pass


class DevelopmentGradingPipeline:
    """Run candidates sequentially while grading completed submissions separately.

    There is exactly one development worker and one grading worker.  The grader may
    block on the machine-wide physical-flow lock without delaying the next candidate
    task.  No candidate task is ever run concurrently with another candidate task.
    """

    def __init__(self, tasks: Iterable[Any], develop: Callable[[Any], Any],
                 grade: Callable[[Any, Any], Any], *,
                 stopped: Callable[[], bool] = lambda: False,
                 event: Callable[..., None] = lambda *args, **kwargs: None):
        self.tasks = tuple(tasks)
        self.develop = develop
        self.grade = grade
        self.stopped = stopped
        self.event = event
        self.pending: queue.Queue[tuple[Any, Any] | None] = queue.Queue()
        self.errors: queue.Queue[tuple[str, BaseException]] = queue.Queue()

    def _development(self) -> None:
        try:
            for task in self.tasks:
                if self.stopped():
                    break
                artifact = self.develop(task)
                self.pending.put((task, artifact))
        except BaseException as error:
            self.errors.put(("development", error))
            self.event("DEVELOPMENT_ERROR", error=str(error), error_type=type(error).__name__)
        finally:
            self.event("DEVELOPMENT_STOPPED" if self.stopped() else "DEVELOPMENT_COMPLETE")
            self.pending.put(None)

    def _grading(self) -> None:
        try:
            while True:
                item = self.pending.get()
                try:
                    if item is None:
                        return
                    task, artifact = item
                    self.grade(task, artifact)
                finally:
                    self.pending.task_done()
        except BaseException as error:
            self.errors.put(("grading", error))
            self.event("GRADING_ERROR", error=str(error), error_type=type(error).__name__)

    def run(self) -> None:
        workers = [threading.Thread(target=self._development, name="candidate-development"),
                   threading.Thread(target=self._grading, name="serial-grading")]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()
        if not self.errors.empty():
            stage, error = self.errors.get()
            raise PipelineError(f"{stage} failed: {error}") from error
