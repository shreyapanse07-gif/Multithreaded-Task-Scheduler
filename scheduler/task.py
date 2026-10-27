"""
task.py
Task model (OOP + encapsulation). One Task = one unit of work.
Topics: OOP, Enum, datetime, comparison for PriorityQueue
"""
import uuid
import itertools
from enum import Enum
from datetime import datetime, timedelta

import config


class TaskStatus(Enum):
    PENDING = "pending"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"


# tie-breaker counter so two tasks with same priority + time don't get compared by func
_counter = itertools.count()


class Task:
    """
    Attributes to create in __init__:
        task_id      -> str   (hint: str(uuid.uuid4())[:8])
        name         -> str
        func         -> callable to run
        args, kwargs -> arguments for func
        priority     -> int   (default config.PRIORITY_MEDIUM)
        run_at       -> datetime (default datetime.now(); use delay_seconds to push it ahead)
        interval     -> seconds or None (None = one-time task, number = recurring)
        max_retries  -> int   (default config.MAX_RETRIES)
        retries      -> int   starts at 0
        status       -> TaskStatus.PENDING
        result, error-> None initially
        created_at, started_at, finished_at -> datetime / None
        _seq         -> next(_counter)
    """

    def __init__(self, name, func, args=(), kwargs=None,
                 priority=config.PRIORITY_MEDIUM, delay_seconds=0,
                 interval=None, max_retries=config.MAX_RETRIES):
        self.task_id = str(uuid.uuid4())[:8]
        self.name = name
        self.func = func
        self.args = args
        self.kwargs = kwargs or {}
        self.priority = priority
        self.run_at = datetime.now() + timedelta(seconds=delay_seconds)
        self.interval = interval
        self.max_retries = max_retries
        self.retries = 0
        self.status = TaskStatus.PENDING
        self.result = None
        self.error = None
        self.created_at = datetime.now()
        self.started_at = None
        self.finished_at = None
        self._seq = next(_counter)
        self.is_io = False

    def __lt__(self, other):
        return (self.priority, self.run_at, self._seq) < (other.priority, other.run_at, other._seq)

    def is_due(self):
        return datetime.now() >= self.run_at

    def is_recurring(self):
        return self.interval is not None

    def can_retry(self):
        return self.retries < self.max_retries

    def execute(self):
        """Run the actual function. Worker calls this; DON'T catch exceptions here —
        let them bubble up so the worker can decide retry/fail."""
        self.status = TaskStatus.RUNNING
        self.started_at = datetime.now()
        try:
            self.result = self.func(*self.args, **self.kwargs)
        finally:
            self.finished_at = datetime.now()
        self.status = TaskStatus.SUCCESS
        return self.result

    def reschedule(self):
        if self.is_recurring():
            self.run_at += timedelta(seconds=self.interval)
            self.status = TaskStatus.SCHEDULED
            self.retries = 0
            self._seq = next(_counter)

    def to_dict(self):
        return {
            "task_id": self.task_id,
            "name": self.name,
            "priority": self.priority,
            "status": self.status.value,
            "run_at": self.run_at.isoformat(),
            "retries": self.retries,
            "max_retries": self.max_retries,
            "created_at": self.created_at.isoformat(),
            "error": self.error,
        }

    def __repr__(self):
        return f"<Task {self.task_id} {self.name} p={self.priority} {self.status.name}>"


# ---------- Inheritance: specialised task types ----------

class IOTask(Task):
    """Task that touches files/disk. Scheduler/worker will wrap it in the IO semaphore."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.is_io = True


class RecurringTask(Task):
    """Convenience subclass: forces interval to be given."""
    def __init__(self, name, func, interval, **kw):
        if interval <= 0:
            raise ValueError("interval must be greater than zero")
        super().__init__(name, func, interval=interval, **kw)
