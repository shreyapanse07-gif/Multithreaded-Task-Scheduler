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
        t = Task("t", dummy)
        self.assertEqual(t.status, TaskStatus.PENDING)

    def test_priority_ordering(self):
        high = Task("high", dummy, priority=config.PRIORITY_HIGH)
        low = Task("low", dummy, priority=config.PRIORITY_LOW)
        self.assertTrue(high < low)

    def test_same_priority_uses_fifo(self):
        first = Task("first", dummy)
        second = Task("second", dummy)
        second.run_at = first.run_at
        self.assertTrue(first < second)

    def test_is_due(self):
        self.assertTrue(Task("now", dummy).is_due())
        self.assertFalse(Task("later", dummy, delay_seconds=60).is_due())

    def test_execute_sets_success_and_result(self):
        t = Task("t", dummy)
        self.assertEqual(t.execute(), 42)
        self.assertEqual(t.status, TaskStatus.SUCCESS)
        self.assertIsNotNone(t.finished_at)

    def test_execute_passes_args_and_kwargs(self):
        def add(a, b=0):
            return a + b

        t = Task("add", add, args=(2,), kwargs={"b": 3})
        self.assertEqual(t.execute(), 5)

    def test_can_retry(self):
        t = Task("t", dummy, max_retries=2)
        t.retries = 2
        self.assertFalse(t.can_retry())

    def test_reschedule_moves_run_at(self):
        t = RecurringTask("t", dummy, interval=5)
        old = t.run_at
        t.reschedule()
        self.assertEqual(t.run_at, old + timedelta(seconds=5))

    def test_reschedule_resets_retries_and_status(self):
        t = RecurringTask("t", dummy, interval=5)
        t.retries = 2
        t.status = TaskStatus.RETRYING

        t.reschedule()

        self.assertEqual(t.retries, 0)
        self.assertEqual(t.status, TaskStatus.SCHEDULED)

    def test_failed_recurring_run_updates_finished_at(self):
        calls = 0

        def succeed_then_fail():
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("second run failed")
            return 42

        t = RecurringTask("t", succeed_then_fail, interval=5)
        t.execute()
        first_finished_at = t.finished_at
        t.reschedule()

        with self.assertRaisesRegex(RuntimeError, "second run failed"):
            t.execute()

        self.assertIsNotNone(t.finished_at)
        self.assertGreater(t.finished_at, first_finished_at)

    def test_recurring_invalid_interval(self):
        with self.assertRaises(ValueError):
            RecurringTask("x", dummy, interval=0)


if __name__ == "__main__":
    unittest.main()
