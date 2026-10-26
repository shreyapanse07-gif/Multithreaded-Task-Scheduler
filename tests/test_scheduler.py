"""Tests for the scheduling engine (Person A).

They use a small FakeTask so they run before task.py / database.py are merged.
Run with:  python -m pytest tests/test_scheduler.py -v
      or:  python -m unittest tests.test_scheduler -v
"""

import itertools
import threading
import time
import unittest
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from scheduler.scheduler import (
    CANCELLED,
    COMPLETED,
    FAILED,
    PENDING,
    QUEUED,
    RUNNING,
    DependencyCycleError,
    TaskNotFoundError,
    TaskScheduler,
)
from scheduler.worker import WorkerPool

HIGH, MEDIUM, LOW = 1, 2, 3
_ids = itertools.count(1)


@dataclass
class FakeTask:
    task_type: str
    params: dict = field(default_factory=dict)
    priority: int = MEDIUM
    scheduled_at: Any = None
    depends_on: list = field(default_factory=list)
    max_retries: int = 0
    id: str = field(default_factory=lambda: f"t{next(_ids)}")
    status: str = PENDING
    attempts: int = 0


class FakeStore:
    def __init__(self):
        self.lock = threading.Lock()
        self.saved = {}
        self.attempts = []

    def save_task(self, task):
        with self.lock:
            self.saved[task.id] = task.status

    def add_attempt(self, **row):
        with self.lock:
            self.attempts.append(row)


def make_scheduler(handlers, workers=2, **kwargs):
    kwargs.setdefault("retry_base_delay", 0.05)
    return TaskScheduler(handlers, num_workers=workers, **kwargs)


class GateHandlers:
    """Handlers whose 'block' type waits until the test opens the gate."""

    def __init__(self):
        self.gate = threading.Event()
        self.order = []
        self.lock = threading.Lock()

    def block(self, params, cancel_event):
        self.gate.wait(5)
        return "unblocked"

    def record(self, params, cancel_event):
        with self.lock:
            self.order.append(params["name"])
        return params["name"]

    def as_dict(self):
        return {"block": self.block, "record": self.record}


class TestPriorityAndQueue(unittest.TestCase):
    def test_higher_priority_runs_first(self):
        h = GateHandlers()
        with make_scheduler(h.as_dict(), workers=1) as s:
            s.submit(FakeTask("block"))  # occupies the only worker
            time.sleep(0.2)
            for name, prio in [("low", LOW), ("medium", MEDIUM), ("high", HIGH), ("high2", HIGH)]:
                s.submit(FakeTask("record", {"name": name}, priority=prio))
            h.gate.set()
            self.assertTrue(s.wait_until_idle(5))
        self.assertEqual(h.order, ["high", "high2", "medium", "low"])

    def test_delayed_task_does_not_block_ready_tasks(self):
        h = GateHandlers()
        with make_scheduler(h.as_dict(), workers=1) as s:
            later = datetime.now() + timedelta(seconds=0.6)
            s.submit(FakeTask("record", {"name": "delayed"}, priority=HIGH, scheduled_at=later))
            s.submit(FakeTask("record", {"name": "now"}, priority=LOW))
            self.assertTrue(s.wait_until_idle(5))
        self.assertEqual(h.order, ["now", "delayed"])

    def test_delayed_task_waits_for_its_time(self):
        h = GateHandlers()
        with make_scheduler(h.as_dict()) as s:
            start = time.time()
            t = FakeTask("record", {"name": "x"}, scheduled_at=datetime.now() + timedelta(seconds=0.4))
            s.submit(t)
            self.assertTrue(s.wait_until_idle(5))
            self.assertGreaterEqual(t.started_at.timestamp(), start + 0.35)


class TestStatusLifecycle(unittest.TestCase):
    def test_completed_task_records_details(self):
        store = FakeStore()
        with make_scheduler({"ok": lambda p, c: p["x"] * 2}, store=store) as s:
            t = FakeTask("ok", {"x": 21})
            s.submit(t)
            self.assertTrue(s.wait_until_idle(5))
        self.assertEqual(t.status, COMPLETED)
        self.assertEqual(t.result, 42)
        self.assertEqual(t.attempts, 1)
        self.assertTrue(t.worker.startswith("worker-"))
        self.assertIsNotNone(t.started_at)
        self.assertIsNotNone(t.finished_at)
        self.assertIsNotNone(t.duration)
        self.assertEqual(store.saved[t.id], COMPLETED)
        self.assertEqual(store.attempts[-1]["status"], "SUCCESS")

    def test_status_passes_through_running(self):
        h = GateHandlers()
        with make_scheduler(h.as_dict(), workers=1) as s:
            t = FakeTask("block")
            s.submit(t)
            time.sleep(0.2)
            self.assertEqual(t.status, RUNNING)
            h.gate.set()
            self.assertTrue(s.wait_until_idle(5))
        self.assertEqual(t.status, COMPLETED)

    def test_unknown_task_type_fails_without_retry(self):
        with make_scheduler({}) as s:
            t = FakeTask("does-not-exist", max_retries=3)
            s.submit(t)
            self.assertTrue(s.wait_until_idle(5))
        self.assertEqual(t.status, FAILED)
        self.assertEqual(t.attempts, 1)
        self.assertIn("no handler", t.error)

    def test_unknown_id_raises(self):
        s = make_scheduler({})
        with self.assertRaises(TaskNotFoundError):
            s.cancel("missing")


class TestRetries(unittest.TestCase):
    def test_retries_then_succeeds(self):
        calls = []

        def flaky(params, cancel):
            calls.append(time.time())
            if len(calls) < 3:
                raise RuntimeError("temporary")
            return "ok"

        with make_scheduler({"flaky": flaky}, retry_base_delay=0.1) as s:
            t = FakeTask("flaky", max_retries=3)
            s.submit(t)
            self.assertTrue(s.wait_until_idle(5))
        self.assertEqual(t.status, COMPLETED)
        self.assertEqual(t.attempts, 3)
        # exponential backoff: second gap (0.2s) longer than the first (0.1s)
        self.assertGreaterEqual(calls[1] - calls[0], 0.09)
        self.assertGreaterEqual(calls[2] - calls[1], 0.19)

    def test_fails_after_retry_limit(self):
        store = FakeStore()

        def broken(params, cancel):
            raise ValueError("bad input")

        with make_scheduler({"broken": broken}, store=store) as s:
            t = FakeTask("broken", max_retries=2)
            s.submit(t)
            self.assertTrue(s.wait_until_idle(5))
        self.assertEqual(t.status, FAILED)
        self.assertEqual(t.attempts, 3)  # first try + 2 retries
        self.assertIn("ValueError", t.error)
        self.assertEqual(len(store.attempts), 3)

    def test_manual_retry(self):
        state = {"fail": True}

        def sometimes(params, cancel):
            if state["fail"]:
                raise RuntimeError("down")
            return "up"

        with make_scheduler({"s": sometimes}) as s:
            t = FakeTask("s")
            s.submit(t)
            self.assertTrue(s.wait_until_idle(5))
            self.assertEqual(t.status, FAILED)
            state["fail"] = False
            self.assertTrue(s.retry(t.id))
            self.assertTrue(s.wait_until_idle(5))
        self.assertEqual(t.status, COMPLETED)
        self.assertFalse(s.retry(t.id))  # completed tasks can't be retried


class TestCancellation(unittest.TestCase):
    def test_cancel_pending_task(self):
        h = GateHandlers()
        with make_scheduler(h.as_dict(), workers=1) as s:
            s.submit(FakeTask("block"))
            time.sleep(0.2)
            t = FakeTask("record", {"name": "never"})
            s.submit(t)
            self.assertEqual(s.cancel(t.id), CANCELLED)
            h.gate.set()
            self.assertTrue(s.wait_until_idle(5))
        self.assertEqual(t.status, CANCELLED)
        self.assertNotIn("never", h.order)

    def test_cooperative_cancel_of_running_task(self):
        def long_job(params, cancel_event):
            for _ in range(100):
                if cancel_event.is_set():
                    raise InterruptedError("stopped")
                time.sleep(0.02)
            return "finished"

        with make_scheduler({"long": long_job}) as s:
            t = FakeTask("long", max_retries=3)
            s.submit(t)
            time.sleep(0.2)
            self.assertEqual(s.cancel(t.id), "CANCELLING")
            self.assertTrue(s.wait_until_idle(5))
        self.assertEqual(t.status, CANCELLED)
        self.assertEqual(t.attempts, 1)  # cancellation is not retried


class TestDependencies(unittest.TestCase):
    def test_dependent_runs_after_prerequisite(self):
        h = GateHandlers()
        with make_scheduler(h.as_dict(), workers=3) as s:
            a = FakeTask("record", {"name": "a"}, priority=LOW)
            s.submit(a)
            b = FakeTask("record", {"name": "b"}, priority=HIGH, depends_on=[a.id])
            s.submit(b)
            self.assertTrue(s.wait_until_idle(5))
        self.assertEqual(h.order, ["a", "b"])

    def test_failed_dependency_fails_dependent(self):
        def broken(p, c):
            raise RuntimeError("nope")

        with make_scheduler({"broken": broken, "ok": lambda p, c: 1}) as s:
            a = FakeTask("broken")
            s.submit(a)
            b = FakeTask("ok", depends_on=[a.id])
            s.submit(b)
            self.assertTrue(s.wait_until_idle(5))
        self.assertEqual(b.status, FAILED)
        self.assertIn(a.id, b.error)
        self.assertEqual(b.attempts, 0)

    def test_cycles_and_unknown_dependencies_rejected(self):
        s = make_scheduler({})
        t = FakeTask("x")
        t.depends_on = [t.id]
        with self.assertRaises(DependencyCycleError):
            s.submit(t)
        with self.assertRaises(TaskNotFoundError):
            s.submit(FakeTask("x", depends_on=["ghost"]))


class TestConcurrencyAndSynchronization(unittest.TestCase):
    def test_tasks_run_in_parallel(self):
        def sleepy(params, cancel):
            time.sleep(0.3)

        with make_scheduler({"sleep": sleepy}, workers=4) as s:
            start = time.perf_counter()
            for _ in range(4):
                s.submit(FakeTask("sleep"))
            self.assertTrue(s.wait_until_idle(5))
            elapsed = time.perf_counter() - start
        self.assertLess(elapsed, 0.9)  # sequential would take 1.2s+

    def test_never_more_running_than_workers(self):
        lock = threading.Lock()
        live = {"now": 0, "peak": 0}

        def track(params, cancel):
            with lock:
                live["now"] += 1
                live["peak"] = max(live["peak"], live["now"])
            time.sleep(0.05)
            with lock:
                live["now"] -= 1

        with make_scheduler({"t": track}, workers=3) as s:
            for _ in range(15):
                s.submit(FakeTask("t"))
            self.assertTrue(s.wait_until_idle(10))
        self.assertLessEqual(live["peak"], 3)
        self.assertGreaterEqual(live["peak"], 2)

    def test_shared_counter_with_lock_is_exact(self):
        lock = threading.Lock()
        counter = {"n": 0}

        def increment(params, cancel):
            for _ in range(1000):
                with lock:
                    counter["n"] += 1

        with make_scheduler({"inc": increment}, workers=4) as s:
            for _ in range(20):
                s.submit(FakeTask("inc"))
            self.assertTrue(s.wait_until_idle(10))
        self.assertEqual(counter["n"], 20_000)

    def test_stats_and_worker_snapshot(self):
        with make_scheduler({"ok": lambda p, c: 1}, workers=2) as s:
            for _ in range(5):
                s.submit(FakeTask("ok"))
            self.assertTrue(s.wait_until_idle(5))
            stats = s.stats()
        self.assertEqual(stats["total"], 5)
        self.assertEqual(stats["by_status"][COMPLETED], 5)
        self.assertEqual(stats["queue_size"], 0)
        self.assertEqual(len(stats["workers"]), 2)
        self.assertEqual(sum(w["tasks_done"] for w in stats["workers"]), 5)


class TestLifecycleAndRecovery(unittest.TestCase):
    def test_start_twice_raises(self):
        s = make_scheduler({})
        s.start()
        try:
            with self.assertRaises(RuntimeError):
                s.start()
        finally:
            s.shutdown()

    def test_recover_skips_completed_work(self):
        h = GateHandlers()
        done = FakeTask("record", {"name": "done"}, status=COMPLETED, attempts=1)
        interrupted = FakeTask("record", {"name": "interrupted"}, status=RUNNING, attempts=1, max_retries=2)
        queued = FakeTask("record", {"name": "queued"}, status=QUEUED, depends_on=[done.id])
        s = make_scheduler(h.as_dict())
        self.assertEqual(s.recover([done, interrupted, queued]), 2)
        with s:
            self.assertTrue(s.wait_until_idle(5))
        self.assertEqual(sorted(h.order), ["interrupted", "queued"])
        self.assertEqual(interrupted.attempts, 2)

    def test_worker_pool_validates_size(self):
        import queue

        with self.assertRaises(ValueError):
            WorkerPool(0, queue.PriorityQueue(), lambda tid, name: True)


if __name__ == "__main__":
    unittest.main()
