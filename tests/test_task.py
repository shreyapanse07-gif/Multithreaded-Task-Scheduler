"""
test_task.py  ->  python -m unittest discover tests
Pure Task-class tests (no threads).
"""
import unittest
from datetime import datetime, timedelta

import config
from scheduler.task import Task, TaskStatus, RecurringTask


def dummy():
    return 42


class TestTask(unittest.TestCase):

    def test_default_status_is_pending(self):
        # TODO: t = Task("t", dummy); assertEqual(t.status, TaskStatus.PENDING)
        pass

    def test_priority_ordering(self):
        # TODO: high = Task(..., priority=PRIORITY_HIGH), low = Task(..., priority=PRIORITY_LOW)
        # TODO: assertTrue(high < low)
        pass

    def test_same_priority_uses_fifo(self):
        # TODO: two tasks same priority + same run_at -> first created should be "less"
        pass

    def test_is_due(self):
        # TODO: Task(..., delay_seconds=0).is_due() -> True ; delay_seconds=60 -> False
        pass

    def test_execute_sets_success_and_result(self):
        # TODO: t.execute() -> result 42, status SUCCESS, finished_at not None
        pass

    def test_can_retry(self):
        # TODO: max_retries=2 -> set retries=2 -> can_retry() False
        pass

    def test_reschedule_moves_run_at(self):
        # TODO: RecurringTask(interval=5) -> old = run_at -> reschedule() -> run_at == old + 5s
        pass

    def test_recurring_invalid_interval(self):
        # TODO: with self.assertRaises(ValueError): RecurringTask("x", dummy, interval=0)
        pass


if __name__ == "__main__":
    unittest.main()
