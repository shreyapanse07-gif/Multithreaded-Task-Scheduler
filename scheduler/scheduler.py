"""
scheduler.py
Central Scheduler = PRODUCER. Owns the queue, starts workers, moves due tasks into the queue.
Topics: PriorityQueue, Lock/RLock, Event, Semaphore, thread lifecycle (start/join/is_alive)

Two holding areas:
    self._waiting   -> heap (heapq) of tasks NOT due yet (delayed / retry / recurring)
    self.task_queue -> queue.PriorityQueue of tasks that ARE due; workers pull from here
The dispatcher thread moves tasks from _waiting to task_queue when they become due,
so a task scheduled for later never blocks tasks that are ready now.
"""
import heapq
import itertools
import queue
import threading
import time
from datetime import datetime

import config
from .task import TaskStatus
from .worker import Worker
from .database import TaskDatabase
from .exceptions import SchedulerShutdownError, InvalidTaskError
from .logger import get_logger

logger = get_logger(__name__)

# Statuses a task can still be cancelled from.
CANCELLABLE = {TaskStatus.PENDING, TaskStatus.SCHEDULED, TaskStatus.RETRYING}


class Scheduler:

    def __init__(self, num_workers=config.NUM_WORKERS, db_path=None,
                 retry_delay=config.RETRY_DELAY):
        if num_workers < 1:
            raise ValueError("num_workers must be at least 1")
        self.num_workers = num_workers
        self.retry_delay = retry_delay

        self.task_queue = queue.PriorityQueue()       # items: (priority, seq, task)
        self._waiting = []                            # heap of (run_at, seq, task)
        # RLock: the same thread may take it twice (submit -> _push_waiting)
        self._waiting_lock = threading.RLock()
        self._seq = itertools.count()                 # tie-breaker so Tasks never get compared

        self.stop_event = threading.Event()
        self._wake = threading.Event()                # set when the waiting heap changes
        self.io_semaphore = threading.Semaphore(config.MAX_CONCURRENT_IO)
        self.stats_lock = threading.Lock()
        self.stats = {"submitted": 0, "completed": 0, "failed": 0,
                      "retried": 0, "cancelled": 0}

        self.tasks = {}                               # task_id -> Task
        self.workers = []
        self.db = TaskDatabase(db_path or config.DB_FILE)
        self._dispatcher = None
        self._running = False

    # ---------- public API ----------

    def start(self):
        if self._running:
            logger.warning("Scheduler already running")
            return
        if self.stop_event.is_set():
            raise SchedulerShutdownError("A shut-down scheduler cannot be restarted")
        for i in range(1, self.num_workers + 1):
            worker = Worker(i, self.task_queue, self.stop_event, self.io_semaphore,
                            self.stats_lock, self.stats, self.db, self._requeue,
                            retry_delay=self.retry_delay)
            worker.start()
            self.workers.append(worker)
        self._dispatcher = threading.Thread(target=self._dispatch_loop,
                                            name="Dispatcher", daemon=True)
        self._dispatcher.start()
        self._running = True
        logger.info("Scheduler started with %d workers", self.num_workers)

    def submit(self, task):
        if self.stop_event.is_set():
            raise SchedulerShutdownError()
        if not callable(task.func):
            raise InvalidTaskError(f"Task '{task.name}': func is not callable")
        if task.priority < 0:
            raise InvalidTaskError(f"Task '{task.name}': priority must be >= 0")

        self.tasks[task.task_id] = task
        self.db.insert_task(task)
        with self.stats_lock:
            self.stats["submitted"] += 1

        if task.is_due():
            self._enqueue(task)
        else:
            self._push_waiting(task)
        logger.info("Submitted %s (priority %s)", task.name, task.priority)
        return task.task_id

    def cancel(self, task_id):
        """Cancel a task that has not started yet. Returns True if it was cancelled."""
        task = self.tasks.get(task_id)
        if task is None or task.status not in CANCELLABLE:
            return False
        task.status = TaskStatus.CANCELLED
        task.finished_at = datetime.now()
        self.db.update_status(task)
        with self.stats_lock:
            self.stats["cancelled"] += 1
        logger.info("Cancelled %s", task.name)
        return True                # workers / dispatcher skip CANCELLED tasks

    def get_status(self, task_id):
        task = self.tasks.get(task_id)
        return task.status if task else None

    def get_stats(self):
        with self.stats_lock:
            stats = dict(self.stats)                  # return a COPY
        with self._waiting_lock:
            stats["waiting"] = len(self._waiting)
        stats["queued"] = self.task_queue.qsize()
        stats["busy_workers"] = sum(1 for w in self.workers if w.current_task)
        return stats

    def get_worker_status(self):
        return [w.snapshot() for w in self.workers]

    def wait_until_done(self, timeout=None):
        """Block until nothing is waiting, queued or running. False on timeout.
        Recurring tasks never finish, so always pass a timeout for those."""
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            with self._waiting_lock:
                idle = not self._waiting and self.task_queue.unfinished_tasks == 0
            if idle:
                return True
            if deadline is not None and time.monotonic() >= deadline:
                return False
            time.sleep(0.05)

    def shutdown(self, wait=True):
        if self.stop_event.is_set():
            return
        self.stop_event.set()                         # dispatcher + workers see this
        self._wake.set()
        if wait:
            if self._dispatcher:
                self._dispatcher.join(timeout=5)
            for worker in self.workers:
                worker.join(timeout=5)
            still_alive = [w.name for w in self.workers if w.is_alive()]
            if still_alive:
                logger.warning("Workers still running after shutdown: %s", still_alive)
        self.db.close()
        self._running = False
        logger.info("Scheduler shut down")

    # ---------- internal ----------

    def _enqueue(self, task):
        self.task_queue.put((task.priority, next(self._seq), task))

    def _push_waiting(self, task):
        if task.status != TaskStatus.RETRYING:
            task.status = TaskStatus.SCHEDULED
        with self._waiting_lock:
            heapq.heappush(self._waiting, (task.run_at, next(self._seq), task))
        self._wake.set()                              # dispatcher re-checks right away

    def _requeue(self, task):
        """Called by workers for retries and recurring tasks."""
        if self.stop_event.is_set():
            logger.info("Not re-queuing %s: scheduler is shutting down", task.name)
            return
        self._push_waiting(task)

    def _dispatch_loop(self):
        """Runs in its own thread. Moves due tasks from the waiting heap into task_queue."""
        while not self.stop_event.is_set():
            self._wake.clear()
            now = datetime.now()
            with self._waiting_lock:
                while self._waiting and self._waiting[0][0] <= now:
                    _, _, task = heapq.heappop(self._waiting)
                    if task.status != TaskStatus.CANCELLED:
                        self._enqueue(task)
                # sleep until the next task is due, but at most POLL_INTERVAL
                if self._waiting:
                    gap = (self._waiting[0][0] - now).total_seconds()
                    timeout = max(0.01, min(gap, config.POLL_INTERVAL))
                else:
                    timeout = config.POLL_INTERVAL
            # Event.wait instead of time.sleep: wakes at once when a task is
            # added to the heap or when shutdown() is called.
            self._wake.wait(timeout)

    # context manager support:  with Scheduler() as s: ...
    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.shutdown()
