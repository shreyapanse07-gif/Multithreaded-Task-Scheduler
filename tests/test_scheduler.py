"""
test_scheduler.py
Concurrency tests: ordering, retries, shutdown, race conditions.
Use a temp DB so tests don't touch data/tasks.db -> hint: tempfile.mkstemp(suffix=".db")
"""
import unittest
import threading
import time
import tempfile

import config
from scheduler import Scheduler, Task
from scheduler.exceptions import SchedulerShutdownError


class TestScheduler(unittest.TestCase):

    def setUp(self):
        # TODO: point config.DB_FILE to a temp file (or pass db path into Scheduler)
        # TODO: self.s = Scheduler(num_workers=2); self.s.start()
        pass

    def tearDown(self):
        # TODO: self.s.shutdown()
        pass

    def test_all_tasks_complete(self):
        # TODO: submit 10 quick tasks -> wait_until_done(timeout=10) -> stats["completed"] == 10
        pass

    def test_priority_order_single_worker(self):
        # TODO: Scheduler(num_workers=1), DON'T start yet
        # TODO: submit low, medium, high tasks that append their name to a shared list
        # TODO: start -> wait -> assert list == ["high", "medium", "low"]
        pass

    def test_retry_then_fail(self):
        # TODO: task that always raises, max_retries=2
        # TODO: wait -> status FAILED, retries == 2
        pass

    def test_retry_then_success(self):
        # TODO: use a counter dict: fail first 2 calls, succeed 3rd -> status SUCCESS
        pass

    def test_delayed_task_waits(self):
        # TODO: delay_seconds=2 -> after 0.5s still not SUCCESS -> after 3s SUCCESS
        pass

    def test_submit_after_shutdown_raises(self):
        # TODO: self.s.shutdown(); with assertRaises(SchedulerShutdownError): self.s.submit(...)
        pass

    def test_workers_stop_on_shutdown(self):
        # TODO: shutdown(wait=True) -> all(not w.is_alive() for w in self.s.workers)
        pass

    def test_shared_counter_with_lock(self):
        # TODO: race-condition demo -> 100 tasks each do counter += 1 using a Lock
        # TODO: assert counter == 100   (try WITHOUT lock + time.sleep(0) inside to see it break)
        pass

    def test_io_semaphore_limit(self):
        # TODO: IOTasks that record active count (inc/dec under lock) + sleep
        # TODO: assert max active never > config.MAX_CONCURRENT_IO
        pass


if __name__ == "__main__":
    unittest.main()
