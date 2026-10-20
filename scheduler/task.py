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
    # TODO: define states -> PENDING, SCHEDULED, RUNNING, SUCCESS, FAILED, RETRYING, CANCELLED
    #       hint -> PENDING = "pending" etc. (string values are easy to store in SQLite)
    pass


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
        # TODO: assign all attributes listed above
        # hint -> self.run_at = datetime.now() + timedelta(seconds=delay_seconds)
        # hint -> self.kwargs = kwargs or {}   (never use {} as a default argument)
        pass

    def __lt__(self, other):
        # TODO: PriorityQueue needs this to compare tasks
        # logic -> compare (priority, run_at, _seq) tuples
        pass

    def is_due(self):
        # TODO: return True if datetime.now() >= self.run_at
        pass

    def is_recurring(self):
        # TODO: return True if self.interval is not None
        pass

    def can_retry(self):
        # TODO: return True if self.retries < self.max_retries
        pass

    def execute(self):
        """Run the actual function. Worker calls this; DON'T catch exceptions here —
        let them bubble up so the worker can decide retry/fail."""
        # TODO: set status RUNNING, started_at = now
        # TODO: self.result = self.func(*self.args, **self.kwargs)
        # TODO: set status SUCCESS, finished_at = now, return result
        pass

    def reschedule(self):
        # TODO: for recurring tasks -> run_at += timedelta(seconds=interval),
        #       reset status to SCHEDULED, retries = 0, new _seq
        pass

    def to_dict(self):
        # TODO: return dict of fields for DB / logging
        #       hint -> status.value, run_at.isoformat()
        pass

    def __repr__(self):
        # TODO: f"<Task {self.task_id} {self.name} p={self.priority} {self.status.name}>"
        pass


# ---------- Inheritance: specialised task types ----------

class IOTask(Task):
    """Task that touches files/disk. Scheduler/worker will wrap it in the IO semaphore."""
    # TODO: call super().__init__(...) and set self.is_io = True
    #       (base Task should default is_io = False)
    pass


class RecurringTask(Task):
    """Convenience subclass: forces interval to be given."""
    # TODO: __init__(self, name, func, interval, **kw) -> super().__init__(name, func, interval=interval, **kw)
    #       raise ValueError if interval <= 0
    pass
