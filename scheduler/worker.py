"""Worker threads: the consumer side of the producer-consumer pattern.

The dispatcher thread in ``scheduler.py`` is the producer. It puts
``(priority, seq, task_id)`` tuples into a shared ``queue.PriorityQueue``.
Each ``Worker`` thread takes the highest-priority item from that queue and
calls the scheduler's execute callback, which runs the task and records the
outcome. Workers never touch task state directly, so all state changes stay
behind the scheduler's lock.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Callable

log = logging.getLogger("scheduler.worker")

# execute(task_id, worker_name) -> True if a task actually ran,
# False if the item was skipped (for example, cancelled while queued).
ExecuteFn = Callable[[str, str], bool]


class Worker(threading.Thread):
    """One worker thread. Subclasses ``threading.Thread`` and overrides ``run``."""

    def __init__(
        self,
        name: str,
        ready_queue: queue.PriorityQueue,
        execute: ExecuteFn,
        stop_event: threading.Event,
        poll_interval: float = 0.2,
    ) -> None:
        super().__init__(name=name, daemon=True)
        self._ready_queue = ready_queue
        self._execute = execute
        self._stop_event = stop_event
        self._poll_interval = poll_interval

        # Stats are written by this thread and read by the dashboard thread,
        # so they get their own small lock.
        self._stats_lock = threading.Lock()
        self._current_task: str | None = None
        self._busy_since: float | None = None
        self._tasks_done = 0
        self._busy_seconds = 0.0
        self._born = time.monotonic()

    def run(self) -> None:
        log.info("%s started", self.name)
        while not self._stop_event.is_set():
            try:
                _priority, _seq, task_id = self._ready_queue.get(timeout=self._poll_interval)
            except queue.Empty:
                continue  # wake up regularly so shutdown is noticed

            started = time.monotonic()
            with self._stats_lock:
                self._current_task = task_id
                self._busy_since = started
            ran = False
            try:
                ran = self._execute(task_id, self.name)
            except Exception:  # the callback should never raise; keep the thread alive if it does
                log.exception("%s: unexpected error while executing %s", self.name, task_id)
            finally:
                elapsed = time.monotonic() - started
                with self._stats_lock:
                    self._current_task = None
                    self._busy_since = None
                    if ran:
                        self._tasks_done += 1
                        self._busy_seconds += elapsed
                self._ready_queue.task_done()
        log.info("%s stopped", self.name)

    def snapshot(self) -> dict:
        """Thread-safe view of this worker for the dashboard."""
        now = time.monotonic()
        with self._stats_lock:
            busy = self._busy_seconds
            if self._busy_since is not None:
                busy += now - self._busy_since
            alive_for = max(now - self._born, 1e-9)
            return {
                "name": self.name,
                "alive": self.is_alive(),
                "state": "busy" if self._current_task else "idle",
                "current_task": self._current_task,
                "tasks_done": self._tasks_done,
                "busy_seconds": round(busy, 3),
                "utilization": round(min(busy / alive_for, 1.0), 3),
            }


class WorkerPool:
    """A fixed-size group of ``Worker`` threads sharing one ready queue."""

    def __init__(
        self,
        num_workers: int,
        ready_queue: queue.PriorityQueue,
        execute: ExecuteFn,
        name_prefix: str = "worker",
        poll_interval: float = 0.2,
    ) -> None:
        if num_workers < 1:
            raise ValueError("num_workers must be at least 1")
        self._stop_event = threading.Event()
        self._started = False
        self.workers = [
            Worker(f"{name_prefix}-{i + 1}", ready_queue, execute, self._stop_event, poll_interval)
            for i in range(num_workers)
        ]

    @property
    def size(self) -> int:
        return len(self.workers)

    def start(self) -> None:
        if self._started:
            raise RuntimeError("WorkerPool already started")
        self._started = True
        for worker in self.workers:
            worker.start()

    def stop(self, timeout: float | None = 5.0) -> None:
        """Ask workers to stop after their current task, then join them."""
        self._stop_event.set()
        for worker in self.workers:
            if worker.is_alive():
                worker.join(timeout)

    def snapshot(self) -> list[dict]:
        return [worker.snapshot() for worker in self.workers]
