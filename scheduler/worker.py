"""
worker.py
Worker thread = CONSUMER in producer-consumer model.
Topics: threading.Thread subclass, queue.get/task_done, Event, Semaphore, try/except/finally
"""
import threading
import queue
import time

import config
from .task import TaskStatus
from .exceptions import TaskExecutionError
from .logger import get_logger

logger = get_logger(__name__)


class Worker(threading.Thread):
    """
    Constructor args (pass these from Scheduler):
        worker_id    -> int
        task_queue   -> queue.PriorityQueue  (shared, thread-safe)
        stop_event   -> threading.Event      (set() = please stop)
        io_semaphore -> threading.Semaphore(config.MAX_CONCURRENT_IO)
        stats_lock   -> threading.Lock       (protects shared stats dict)
        stats        -> dict {"completed": 0, "failed": 0, "retried": 0}
        db           -> TaskDatabase instance
        retry_callback -> function(task) the worker calls to send task back to scheduler
    """

    def __init__(self, worker_id, task_queue, stop_event, io_semaphore,
                 stats_lock, stats, db, retry_callback):
        # TODO: super().__init__(name=f"Worker-{worker_id}", daemon=True)
        # TODO: store all args as attributes
        # TODO: self.current_task = None
        pass

    def run(self):
        """Main loop. Thread.start() calls this automatically."""
        # TODO: while not self.stop_event.is_set():
        #           try:
        #               priority_item = self.task_queue.get(timeout=config.POLL_INTERVAL)
        #           except queue.Empty:
        #               continue                   # check stop_event again
        #           if item is None (poison pill) -> task_done() and break
        #           self._process(task)
        #           finally -> self.task_queue.task_done()   <-- ALWAYS, or join() hangs
        # TODO: logger.info(f"{self.name} stopped")
        pass

    def _process(self, task):
        # TODO: self.current_task = task
        # TODO: try:
        #           if getattr(task, "is_io", False):
        #               with self.io_semaphore:      # max N IO tasks at once
        #                   task.execute()
        #           else:
        #               task.execute()
        #           self._on_success(task)
        #       except Exception as e:
        #           self._on_failure(task, e)
        #       finally:
        #           self.current_task = None
        pass

    def _on_success(self, task):
        # TODO: with self.stats_lock: self.stats["completed"] += 1
        # TODO: self.db.update_status(task) + self.db.log_run(task, ...)
        # TODO: logger.info(...)
        # TODO: if task.is_recurring(): task.reschedule(); self.retry_callback(task)
        pass

    def _on_failure(self, task, exc):
        # TODO: task.error = str(exc)
        # logic ->
        #   if task.can_retry():
        #       task.retries += 1, status = RETRYING
        #       task.run_at = now + config.RETRY_DELAY seconds   (don't time.sleep() here! blocks the worker)
        #       stats["retried"] += 1 (inside lock)
        #       self.retry_callback(task)
        #   else:
        #       status = FAILED, stats["failed"] += 1 (inside lock)
        #       logger.error(...) with TaskExecutionError / MaxRetriesExceeded message
        # TODO: always update DB at the end
        pass
