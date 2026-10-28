"""
worker.py
Worker thread = CONSUMER in the producer-consumer model.
Topics: threading.Thread subclass, queue.get/task_done, Event, Semaphore, try/except/finally

The Scheduler (producer) puts (priority, seq, task) tuples into a shared
queue.PriorityQueue. Each Worker takes the highest-priority item, runs it and
reports the result. Failures are sent back to the scheduler for a retry.
"""
import queue
import threading
import time
from datetime import datetime, timedelta

import config
from .task import TaskStatus
from .exceptions import TaskExecutionError, MaxRetriesExceeded
from .logger import get_logger

logger = get_logger(__name__)


class Worker(threading.Thread):
    """
    Constructor args (passed in by Scheduler):
        worker_id      -> int
        task_queue     -> queue.PriorityQueue  (shared, thread-safe)
        stop_event     -> threading.Event      (set() = please stop)
        io_semaphore   -> threading.Semaphore(config.MAX_CONCURRENT_IO)
        stats_lock     -> threading.Lock       (protects the shared stats dict)
        stats          -> dict {"completed": 0, "failed": 0, "retried": 0, ...}
        db             -> TaskDatabase instance
        retry_callback -> function(task) that sends a task back to the scheduler
        retry_delay    -> base seconds before a retry (doubles each attempt)
    """

    def __init__(self, worker_id, task_queue, stop_event, io_semaphore,
                 stats_lock, stats, db, retry_callback,
                 retry_delay=config.RETRY_DELAY):
        super().__init__(name=f"Worker-{worker_id}", daemon=True)
        self.worker_id = worker_id
        self.task_queue = task_queue
        self.stop_event = stop_event
        self.io_semaphore = io_semaphore
        self.stats_lock = stats_lock
        self.stats = stats
        self.db = db
        self.retry_callback = retry_callback
        self.retry_delay = retry_delay
        self.current_task = None
        self.tasks_done = 0

    def run(self):
        """Main loop. Thread.start() calls this automatically."""
        logger.info("%s started", self.name)
        while not self.stop_event.is_set():
            try:
                _priority, _seq, task = self.task_queue.get(timeout=config.POLL_INTERVAL)
            except queue.Empty:
                continue                          # wake up regularly to check stop_event
            try:
                if task.status == TaskStatus.CANCELLED:
                    logger.info("%s skipped cancelled task %s", self.name, task.name)
                else:
                    self._process(task)
            finally:
                self.task_queue.task_done()       # ALWAYS, or queue.join() hangs
        logger.info("%s stopped", self.name)

    def _process(self, task):
        self.current_task = task
        start = time.perf_counter()
        try:
            if getattr(task, "is_io", False):
                with self.io_semaphore:           # at most MAX_CONCURRENT_IO IO tasks at once
                    task.execute()
            else:
                task.execute()
        except Exception as exc:                  # task failed -> retry or give up
            self._on_failure(task, exc, time.perf_counter() - start)
        else:
            self._on_success(task, time.perf_counter() - start)
        finally:
            self.current_task = None
            self.tasks_done += 1

    def _on_success(self, task, duration):
        with self.stats_lock:
            self.stats["completed"] += 1
        self._save(task, duration)
        logger.info("%s finished %s in %.3fs", self.name, task.name, duration)
        if task.is_recurring() and not self.stop_event.is_set():
            task.reschedule()
            self.retry_callback(task)

    def _on_failure(self, task, exc, duration):
        task.error = f"{type(exc).__name__}: {exc}"
        task.finished_at = task.finished_at or datetime.now()
        if task.can_retry():
            task.retries += 1
            task.status = TaskStatus.RETRYING
            # Exponential backoff: delay, 2*delay, 4*delay, ...
            # Never time.sleep() here - that would block this worker.
            wait = self.retry_delay * 2 ** (task.retries - 1)
            task.run_at = datetime.now() + timedelta(seconds=wait)
            with self.stats_lock:
                self.stats["retried"] += 1
            logger.warning("%s: %s - retry %d/%d in %.1fs", self.name,
                           TaskExecutionError(task.task_id, exc), task.retries,
                           task.max_retries, wait)
            self._save(task, duration)
            self.retry_callback(task)
        else:
            task.status = TaskStatus.FAILED
            with self.stats_lock:
                self.stats["failed"] += 1
            logger.error("%s: %s (%s)", self.name,
                         MaxRetriesExceeded(task.task_id, task.retries), task.error)
            self._save(task, duration)

    def _save(self, task, duration):
        try:
            self.db.update_status(task)
            self.db.log_run(task, self.name, round(duration, 4))
        except Exception:                         # a DB problem must not kill the worker
            logger.exception("%s could not save %s", self.name, task.task_id)

    def snapshot(self):
        """Small dict for the dashboard / summary."""
        task = self.current_task
        return {"name": self.name, "alive": self.is_alive(),
                "state": "busy" if task else "idle",
                "current_task": task.name if task else None,
                "tasks_done": self.tasks_done}
