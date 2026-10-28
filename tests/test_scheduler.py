"""
test_scheduler.py
Concurrency tests: ordering, retries, delays, cancel, shutdown, race conditions, semaphore.
Each test uses its own temp DB so data/tasks.db is never touched.
Run:  python -m unittest tests.test_scheduler -v
"""
import os
import tempfile
import threading
import time
import unittest

import config
from scheduler import Scheduler, Task, IOTask, RecurringTask, TaskStatus
from scheduler.exceptions import SchedulerShutdownError, InvalidTaskError


class SchedulerTestCase(unittest.TestCase):
    """Creates a scheduler on a temp DB with a short retry delay."""
    workers = 2

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.s = Scheduler(num_workers=self.workers, db_path=self.db_path, retry_delay=0.1)

    def tearDown(self):
        self.s.shutdown()
        os.remove(self.db_path)


class TestScheduler(SchedulerTestCase):

    def test_all_tasks_complete(self):
        self.s.start()
        tasks = [Task(f"t{i}", lambda: 1) for i in range(10)]
        for t in tasks:
            self.s.submit(t)
        self.assertTrue(self.s.wait_until_done(timeout=10))
        self.assertEqual(self.s.get_stats()["completed"], 10)
        self.assertTrue(all(t.status == TaskStatus.SUCCESS for t in tasks))

    def test_retry_then_fail(self):
        def always_fails():
            raise RuntimeError("boom")

        self.s.start()
        t = Task("bad", always_fails, max_retries=2)
        self.s.submit(t)
        self.assertTrue(self.s.wait_until_done(timeout=10))
        self.assertEqual(t.status, TaskStatus.FAILED)
        self.assertEqual(t.retries, 2)
        self.assertIn("RuntimeError", t.error)
        self.assertEqual(self.s.get_stats()["failed"], 1)

    def test_retry_then_success_with_backoff(self):
        calls = []

        def flaky():
            calls.append(time.monotonic())
            if len(calls) < 3:
                raise RuntimeError("not yet")
            return "ok"

        self.s.start()
        t = Task("flaky", flaky, max_retries=3)
        self.s.submit(t)
        self.assertTrue(self.s.wait_until_done(timeout=10))
        self.assertEqual(t.status, TaskStatus.SUCCESS)
        self.assertEqual(t.retries, 2)
        # exponential backoff: 2nd gap (~0.2s) longer than the 1st (~0.1s)
        self.assertGreater(calls[2] - calls[1], calls[1] - calls[0])

    def test_delayed_task_waits(self):
        self.s.start()
        t = Task("later", lambda: 1, delay_seconds=1)
        self.s.submit(t)
        time.sleep(0.4)
        self.assertEqual(t.status, TaskStatus.SCHEDULED)
        self.assertTrue(self.s.wait_until_done(timeout=5))
        self.assertEqual(t.status, TaskStatus.SUCCESS)

    def test_delayed_task_does_not_block_ready_task(self):
        order = []
        self.s.start()
        self.s.submit(Task("later", lambda: order.append("later"),
                           priority=config.PRIORITY_HIGH, delay_seconds=0.6))
        self.s.submit(Task("now", lambda: order.append("now"),
                           priority=config.PRIORITY_LOW))
        self.assertTrue(self.s.wait_until_done(timeout=5))
        self.assertEqual(order, ["now", "later"])

    def test_cancel_scheduled_task(self):
        ran = []
        self.s.start()
        t = Task("cancel me", lambda: ran.append(1), delay_seconds=1)
        self.s.submit(t)
        self.assertTrue(self.s.cancel(t.task_id))
        self.assertTrue(self.s.wait_until_done(timeout=5))
        self.assertEqual(t.status, TaskStatus.CANCELLED)
        self.assertEqual(ran, [])
        self.assertFalse(self.s.cancel(t.task_id))       # already cancelled
        self.assertFalse(self.s.cancel("no-such-id"))

    def test_recurring_task_repeats(self):
        runs = []
        self.s.start()
        self.s.submit(RecurringTask("tick", lambda: runs.append(1), interval=0.2))
        time.sleep(0.9)
        self.assertGreaterEqual(len(runs), 3)

    def test_invalid_task_rejected(self):
        with self.assertRaises(InvalidTaskError):
            self.s.submit(Task("not callable", "hello"))

    def test_submit_after_shutdown_raises(self):
        self.s.start()
        self.s.shutdown()
        with self.assertRaises(SchedulerShutdownError):
            self.s.submit(Task("late", lambda: 1))

    def test_workers_stop_on_shutdown(self):
        self.s.start()
        self.assertTrue(all(w.is_alive() for w in self.s.workers))
        self.s.shutdown(wait=True)
        self.assertTrue(all(not w.is_alive() for w in self.s.workers))

    def test_shared_counter_with_lock(self):
        lock = threading.Lock()
        counter = {"n": 0}

        def increment():
            for _ in range(1000):
                with lock:
                    counter["n"] += 1

        self.s.start()
        for i in range(20):
            self.s.submit(Task(f"inc{i}", increment))
        self.assertTrue(self.s.wait_until_done(timeout=10))
        self.assertEqual(counter["n"], 20_000)

    def test_db_records_history(self):
        self.s.start()
        t = Task("saved", lambda: 1)
        self.s.submit(t)
        self.assertTrue(self.s.wait_until_done(timeout=5))
        self.assertEqual(self.s.db.get_task(t.task_id)[3], "success")
        self.assertEqual(len(self.s.db.get_history(t.task_id)), 1)


class TestPriorityOrder(SchedulerTestCase):
    workers = 1

    def test_priority_order_single_worker(self):
        order = []
        # submit before start, so all three are waiting in the queue together
        for name, prio in [("low", config.PRIORITY_LOW),
                           ("medium", config.PRIORITY_MEDIUM),
                           ("high", config.PRIORITY_HIGH),
                           ("high2", config.PRIORITY_HIGH)]:
            self.s.submit(Task(name, order.append, args=(name,), priority=prio))
        self.s.start()
        self.assertTrue(self.s.wait_until_done(timeout=5))
        self.assertEqual(order, ["high", "high2", "medium", "low"])


class TestConcurrency(SchedulerTestCase):
    workers = 4

    def test_tasks_run_in_parallel(self):
        self.s.start()
        start = time.perf_counter()
        for i in range(4):
            self.s.submit(Task(f"sleep{i}", time.sleep, args=(0.3,)))
        self.assertTrue(self.s.wait_until_done(timeout=5))
        self.assertLess(time.perf_counter() - start, 0.9)   # sequential = 1.2s+

    def test_io_semaphore_limit(self):
        lock = threading.Lock()
        live = {"now": 0, "peak": 0}

        def io_job():
            with lock:
                live["now"] += 1
                live["peak"] = max(live["peak"], live["now"])
            time.sleep(0.1)
            with lock:
                live["now"] -= 1

        self.s.start()
        for i in range(8):
            self.s.submit(IOTask(f"io{i}", io_job))
        self.assertTrue(self.s.wait_until_done(timeout=10))
        self.assertLessEqual(live["peak"], config.MAX_CONCURRENT_IO)


if __name__ == "__main__":
    unittest.main()
