"""
exceptions.py
Custom exceptions (Exception Handling topic).
"""


class SchedulerError(Exception):
    """Base class for all scheduler errors.

    Catching this one class catches every scheduler-specific error:
        try:
            scheduler.submit(task)
        except SchedulerError as e:
            ...
    """
    pass


class TaskExecutionError(SchedulerError):
    """A task's function raised an exception while running."""

    def __init__(self, task_id, original_exc):
        self.task_id = task_id
        self.original_exc = original_exc
        super().__init__(f"Task {task_id} failed: {original_exc}")


class MaxRetriesExceeded(SchedulerError):
    """A task failed and has no retries left."""

    def __init__(self, task_id, retries):
        self.task_id = task_id
        self.retries = retries
        super().__init__(f"Task {task_id} gave up after {retries} retries")


class SchedulerShutdownError(SchedulerError):
    """Raised when submit() is called after shutdown() was called."""

    def __init__(self, message="Scheduler is shut down and no longer accepts tasks"):
        super().__init__(message)


class InvalidTaskError(SchedulerError):
    """Raised when a task has bad data (func not callable, negative priority, etc.)."""

    def __init__(self, message="Invalid task"):
        super().__init__(message)