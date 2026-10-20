"""
exceptions.py
Custom exceptions (Exception Handling topic).
"""


class SchedulerError(Exception):
    """Base class for all scheduler errors."""
    # TODO: nothing needed, just `pass` — every custom error below inherits from this
    pass


class TaskExecutionError(SchedulerError):
    # TODO: __init__(self, task_id, original_exc)
    #       store both, call super().__init__(f"Task {task_id} failed: {original_exc}")
    pass


class MaxRetriesExceeded(SchedulerError):
    # TODO: __init__(self, task_id, retries) -> message like "Task X gave up after N retries"
    pass


class SchedulerShutdownError(SchedulerError):
    # TODO: raised when someone calls submit() after shutdown() was called
    pass


class InvalidTaskError(SchedulerError):
    # TODO: raised when a task has bad data (func not callable, negative priority etc.)
    pass
