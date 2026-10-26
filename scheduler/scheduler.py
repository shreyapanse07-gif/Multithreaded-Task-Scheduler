
from __future__ import annotations

import heapq
import itertools
import logging
import queue
import threading
import time
from datetime import datetime
from typing import Any, Callable, Iterable, Mapping

from .worker import WorkerPool

try:  # Person C's custom exceptions, once merged
    from .exceptions import DependencyCycleError, SchedulerError, TaskNotFoundError
except ImportError:  # fallback so the engine works before exceptions.py exists
    class SchedulerError(Exception):
        """Base class for scheduler errors."""

    class DependencyCycleError(SchedulerError, ValueError):
        """Raised when a task's dependencies would form a cycle."""

    class TaskNotFoundError(SchedulerError, KeyError):
        """Raised when a task id is not known to the scheduler."""


log = logging.getLogger("scheduler.core")

PENDING = "PENDING"
QUEUED = "QUEUED"
RUNNING = "RUNNING"
COMPLETED = "COMPLETED"
FAILED = "FAILED"
CANCELLED = "CANCELLED"
FINAL_STATES = frozenset({COMPLETED, FAILED, CANCELLED})
ALL_STATES = (PENDING, QUEUED, RUNNING, COMPLETED, FAILED, CANCELLED)

Handler = Callable[[dict, threading.Event], Any]


class TaskScheduler:
    """Priority scheduler with a dispatcher thread and a pool of worker threads."""

    def __init__(
        self,
        handlers: Mapping[str, Handler],
        num_workers: int = 4,
        store: Any = None,
        retry_base_delay: float = 1.0,
        max_backoff: float = 60.0,
        default_max_retries: int = 3,
    ) -> None:
        self._handlers = dict(handlers)
        self._store = store
        self.retry_base_delay = retry_base_delay
        self.max_backoff = max_backoff
        self.default_max_retries = default_max_retries
        self.num_workers = num_workers

        # One re-entrant lock guards all scheduler state. RLock because public
        # methods call helpers that take the lock again. The Condition shares
        # that lock and is how the dispatcher is woken up.
        self._lock = threading.RLock()
        self._wakeup = threading.Condition(self._lock)

        self._tasks: dict[str, Any] = {}
        self._cancel_events: dict[str, threading.Event] = {}
        self._time_heap: list[tuple[float, int, int, str]] = []  # (run_at, priority, seq, id)
        self._waiting: dict[str, int] = {}                       # due, deps not finished: id -> seq
        self._eligible: list[tuple[int, int, str]] = []         # (priority, seq, id)
        self._seq = itertools.count()  # tie-breaker: FIFO within the same priority

        self._ready: queue.PriorityQueue = queue.PriorityQueue()
        self._slots = threading.BoundedSemaphore(num_workers)
        self._pool = WorkerPool(num_workers, self._ready, self._execute)

        self._stop = threading.Event()
        self._dispatcher = threading.Thread(target=self._dispatch_loop, name="dispatcher", daemon=True)
        self._started = False

    # ------------------------------------------------------------------ lifecycle

    def start(self) -> None:
        with self._lock:
            if self._started:
                raise RuntimeError("TaskScheduler already started")
            self._started = True
        self._pool.start()
        self._dispatcher.start()
        log.info("scheduler started with %d workers", self.num_workers)

    def shutdown(self, timeout: float = 5.0) -> None:
        """Stop the dispatcher and let workers finish their current task.

        Tasks still PENDING or QUEUED stay that way in the store, so
        ``recover()`` picks them up on the next start.
        """
        self._stop.set()
        with self._wakeup:
            self._wakeup.notify_all()
        if self._dispatcher.is_alive():
            self._dispatcher.join(timeout)
        self._pool.stop(timeout)
        log.info("scheduler stopped")

    @property
    def running(self) -> bool:
        return self._started and not self._stop.is_set()

    def __enter__(self) -> "TaskScheduler":
        self.start()
        return self

    def __exit__(self, *exc_info) -> None:
        self.shutdown()

    # ------------------------------------------------------------------ public API

    def submit(self, task: Any) -> str:
        """Register a new task. Raises on duplicate ids, unknown dependencies or cycles."""
        with self._wakeup:
            if task.id in self._tasks:
                raise ValueError(f"task {task.id} already submitted")
            deps = self._deps(task)
            for dep in deps:
                if dep != task.id and dep not in self._tasks:
                    raise TaskNotFoundError(dep)
            self._check_cycle(task.id, deps)

            self._register(task)
            task.attempts = 0
            task.status = PENDING
            self._push_time(task, self._run_at(task))
            self._persist(task)
            self._wakeup.notify()
            log.info("submitted %s (%s, priority %s)", task.id, task.task_type, task.priority)
            return task.id

    def cancel(self, task_id: str) -> str:
        """Cancel a task.

        PENDING or QUEUED tasks are cancelled at once. RUNNING tasks get their
        cancel event set; the handler stops if it checks the event. Returns
        the resulting status, or "CANCELLING" for a running task.
        """
        with self._wakeup:
            task = self._get(task_id)
            if task.status in (PENDING, QUEUED):
                self._finish(task, CANCELLED, error="cancelled by user")
                return CANCELLED
            if task.status == RUNNING:
                self._cancel_events[task_id].set()
                return "CANCELLING"
            return str(task.status)

    def retry(self, task_id: str) -> bool:
        """Manually re-run a FAILED or CANCELLED task with a fresh attempt count."""
        with self._wakeup:
            task = self._get(task_id)
            if task.status not in (FAILED, CANCELLED):
                return False
            task.attempts = 0
            task.error = None
            task.result = None
            task.finished_at = None
            task.status = PENDING
            self._cancel_events[task_id] = threading.Event()
            self._push_time(task, time.time())
            self._persist(task)
            self._wakeup.notify()
            return True

    def recover(self, tasks: Iterable[Any]) -> int:
        """Load tasks saved before a restart. Call before or after ``start()``.

        Finished tasks are registered (so dependencies on them resolve) but not
        run again. Unfinished ones go back to PENDING; a task that was RUNNING
        when the app stopped keeps its attempt count. Returns how many tasks
        were re-queued.
        """
        tasks = list(tasks)
        requeued = 0
        with self._wakeup:
            for task in tasks:
                if task.id not in self._tasks:
                    self._register(task)
                    if getattr(task, "attempts", None) is None:
                        task.attempts = 0
            for task in tasks:
                if task.status in FINAL_STATES:
                    continue
                if task.status == RUNNING:
                    log.warning("task %s was interrupted mid-run; re-queuing", task.id)
                task.status = PENDING
                self._push_time(task, max(self._run_at(task), time.time()))
                self._persist(task)
                requeued += 1
            self._wakeup.notify()
        return requeued

    def get(self, task_id: str) -> Any:
        with self._lock:
            return self._get(task_id)

    def list_tasks(self, status: str | None = None) -> list[Any]:
        with self._lock:
            return [t for t in self._tasks.values() if status is None or t.status == status]

    def iter_history(self, status: str | None = None):
        """Generator over finished tasks, newest first."""
        with self._lock:
            done = [t for t in self._tasks.values() if t.status in FINAL_STATES]
        done.sort(key=lambda t: t.finished_at or datetime.min, reverse=True)
        for task in done:
            if status is None or task.status == status:
                yield task

    def stats(self) -> dict:
        """Counts and worker info for the dashboard."""
        with self._lock:
            counts = {state: 0 for state in ALL_STATES}
            durations = []
            for task in self._tasks.values():
                counts[str(task.status)] = counts.get(str(task.status), 0) + 1
                if task.status == COMPLETED and getattr(task, "duration", None) is not None:
                    durations.append(task.duration)
            return {
                "total": len(self._tasks),
                "by_status": counts,
                "queue_size": counts[PENDING] + counts[QUEUED],
                "ready_queue_size": self._ready.qsize(),
                "avg_duration": round(sum(durations) / len(durations), 4) if durations else None,
                "workers": self._pool.snapshot(),
                "running": self.running,
            }

    def wait_until_idle(self, timeout: float | None = None) -> bool:
        """Block until every task is finished. Returns False on timeout."""
        with self._wakeup:
            return self._wakeup.wait_for(
                lambda: all(t.status in FINAL_STATES for t in self._tasks.values()),
                timeout,
            )

    # ------------------------------------------------------------------ dispatcher (producer)

    def _dispatch_loop(self) -> None:
        with self._wakeup:
            while not self._stop.is_set():
                self._promote_due(time.time())
                self._hand_off()
                self._wakeup.wait(self._next_timeout())

    def _promote_due(self, now: float) -> None:
        while self._time_heap and self._time_heap[0][0] <= now:
            _, _, seq, task_id = heapq.heappop(self._time_heap)
            task = self._tasks.get(task_id)
            if task is not None and task.status == PENDING:
                self._waiting[task_id] = seq

        # Oldest first, and the original seq is kept, so tasks with equal
        # priority run in the order they were submitted (FIFO).
        for task_id, seq in sorted(self._waiting.items(), key=lambda item: item[1]):
            task = self._tasks[task_id]
            if task.status != PENDING:  # cancelled while waiting
                del self._waiting[task_id]
                continue
            state, blocker = self._dependency_state(task)
            if state == "wait":
                continue
            del self._waiting[task_id]
            if state == "blocked":
                outcome = CANCELLED if blocker.status == CANCELLED else FAILED
                self._finish(task, outcome, error=f"dependency {blocker.id} {blocker.status}")
            else:
                heapq.heappush(self._eligible, (int(task.priority), seq, task_id))

    def _hand_off(self) -> None:
        while self._eligible:
            _, _, task_id = self._eligible[0]
            task = self._tasks[task_id]
            if task.status != PENDING:
                heapq.heappop(self._eligible)
                continue
            if not self._slots.acquire(blocking=False):
                return  # every worker busy; keep the rest in priority order
            priority, seq, _ = heapq.heappop(self._eligible)
            task.status = QUEUED
            self._persist(task)
            self._ready.put((priority, seq, task_id))

    def _next_timeout(self) -> float:
        if not self._time_heap:
            return 1.0
        return max(0.0, min(self._time_heap[0][0] - time.time(), 1.0))

    # ------------------------------------------------------------------ execution (called by workers)

    def _execute(self, task_id: str, worker_name: str) -> bool:
        # Every item a worker takes from the ready queue holds exactly one
        # slot, so the slot is released in ``finally`` no matter what.
        try:
            with self._wakeup:
                task = self._tasks.get(task_id)
                if task is None or task.status != QUEUED:
                    return False  # cancelled while queued
                handler = self._handlers.get(task.task_type)
                task.status = RUNNING
                task.worker = worker_name
                task.attempts += 1
                task.started_at = datetime.now()
                task.finished_at = None
                task.error = None
                attempt = task.attempts
                cancel_event = self._cancel_events[task_id]
                params = dict(getattr(task, "params", None) or {})
                self._persist(task)
                if handler is None:
                    self._finish(task, FAILED, error=f"no handler for task type '{task.task_type}'")
                    self._record_attempt(task, attempt)
                    return True

            # Run the handler without holding the lock so tasks run in parallel.
            started = time.perf_counter()
            error: BaseException | None = None
            result = None
            try:
                result = handler(params, cancel_event)
            except Exception as exc:
                error = exc
            duration = time.perf_counter() - started

            with self._wakeup:
                task.duration = round(duration, 4)
                if error is None:
                    self._finish(task, COMPLETED, result=result)
                elif cancel_event.is_set():
                    self._finish(task, CANCELLED, error="cancelled while running")
                elif attempt <= self._max_retries(task):
                    delay = min(self.retry_base_delay * 2 ** (attempt - 1), self.max_backoff)
                    task.error = f"{type(error).__name__}: {error}"
                    task.status = PENDING
                    self._push_time(task, time.time() + delay)
                    self._persist(task)
                    log.warning("task %s failed (attempt %d), retrying in %.2fs", task_id, attempt, delay)
                else:
                    self._finish(task, FAILED, error=f"{type(error).__name__}: {error}")
                self._record_attempt(task, attempt, error)
            return True
        finally:
            self._slots.release()
            with self._wakeup:
                self._wakeup.notify_all()

    # ------------------------------------------------------------------ helpers (call with lock held)

    def _register(self, task: Any) -> None:
        self._tasks[task.id] = task
        self._cancel_events[task.id] = threading.Event()
        for attr in ("worker", "result", "error", "started_at", "finished_at", "duration", "next_run_at"):
            if not hasattr(task, attr):
                setattr(task, attr, None)

    def _finish(self, task: Any, status: str, result: Any = None, error: str | None = None) -> None:
        task.status = status
        task.finished_at = datetime.now()
        if result is not None:
            task.result = result
        if error is not None:
            task.error = error
        self._persist(task)
        self._wakeup.notify_all()  # dependents and wait_until_idle care about this
        log.info("task %s -> %s", task.id, status)

    def _push_time(self, task: Any, run_at: float) -> None:
        task.next_run_at = datetime.fromtimestamp(run_at)
        heapq.heappush(self._time_heap, (run_at, int(task.priority), next(self._seq), task.id))

    def _dependency_state(self, task: Any) -> tuple[str, Any]:
        for dep_id in self._deps(task):
            dep = self._tasks.get(dep_id)
            if dep is None:
                return "wait", None  # may arrive later through recover()
            if dep.status in (FAILED, CANCELLED):
                return "blocked", dep
            if dep.status != COMPLETED:
                return "wait", dep
        return "ready", None

    def _check_cycle(self, new_id: str, deps: list[str]) -> None:
        """Depth-first search: would ``new_id`` end up depending on itself?"""
        stack, seen = list(deps), set()
        while stack:
            current = stack.pop()
            if current == new_id:
                raise DependencyCycleError(f"task {new_id} would depend on itself")
            if current in seen:
                continue
            seen.add(current)
            existing = self._tasks.get(current)
            if existing is not None:
                stack.extend(self._deps(existing))

    @staticmethod
    def _deps(task: Any) -> list[str]:
        return list(getattr(task, "depends_on", None) or [])

    def _max_retries(self, task: Any) -> int:
        value = getattr(task, "max_retries", None)
        return self.default_max_retries if value is None else int(value)

    @staticmethod
    def _run_at(task: Any) -> float:
        when = getattr(task, "scheduled_at", None)
        if when is None:
            return time.time()
        if isinstance(when, datetime):
            return when.timestamp()
        return float(when)

    def _get(self, task_id: str) -> Any:
        try:
            return self._tasks[task_id]
        except KeyError:
            raise TaskNotFoundError(task_id) from None

    def _persist(self, task: Any) -> None:
        if self._store is None:
            return
        try:
            self._store.save_task(task)
        except Exception:
            log.exception("could not save task %s", task.id)

    def _record_attempt(self, task: Any, attempt: int, error: BaseException | None = None) -> None:
        add_attempt = getattr(self._store, "add_attempt", None)
        if add_attempt is None:
            return
        try:
            add_attempt(
                task_id=task.id,
                attempt=attempt,
                worker=task.worker,
                started_at=task.started_at,
                finished_at=datetime.now(),
                status="SUCCESS" if error is None and task.status == COMPLETED else "ERROR",
                error=None if error is None else f"{type(error).__name__}: {error}",
            )
        except Exception:
            log.exception("could not record attempt for %s", task.id)
