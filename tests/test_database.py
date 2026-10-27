"""
test_database.py
SQLite layer tests. Use ":memory:" as db path -> fast, no files.
"""
import unittest

from scheduler.database import TaskDatabase
from scheduler.task import RecurringTask, Task, TaskStatus


class TestDatabase(unittest.TestCase):

    def setUp(self):
        self.db = TaskDatabase(":memory:")

    def tearDown(self):
        self.db.close()

    def test_insert_and_get(self):
        task = Task("sample", lambda: None)
        self.db.insert_task(task)
        row = self.db.get_task(task.task_id)
        self.assertEqual(row[1], "sample")

    def test_update_status(self):
        task = Task("sample", lambda: None)
        self.db.insert_task(task)
        task.status = TaskStatus.SUCCESS
        self.db.update_status(task)
        self.assertEqual(self.db.get_task(task.task_id)[3], "success")

    def test_log_run_history(self):
        task = Task("sample", lambda: None)
        self.db.insert_task(task)
        self.db.log_run(task, "Worker-1", 0.1)
        self.db.log_run(task, "Worker-1", 0.2)
        self.assertEqual(len(self.db.get_history(task.task_id)), 2)

    def test_failed_recurring_attempt_persists_finished_at(self):
        def fail():
            raise RuntimeError("run failed")

        task = RecurringTask("sample", fail, interval=5)
        self.db.insert_task(task)
        with self.assertRaisesRegex(RuntimeError, "run failed"):
            task.execute()
        task.status = TaskStatus.FAILED
        expected_finished_at = task.finished_at.isoformat()

        self.db.log_run(task, "Worker-1", 0.1)

        history = self.db.get_history(task.task_id)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0][4], expected_finished_at)
        self.assertEqual(history[0][6], "failed")

    def test_summary_counts(self):
        for name, status in (("a", TaskStatus.SUCCESS), ("b", TaskStatus.SUCCESS),
                             ("c", TaskStatus.FAILED)):
            task = Task(name, lambda: None)
            task.status = status
            self.db.insert_task(task)
        self.assertEqual(self.db.get_summary(), {"success": 2, "failed": 1})


if __name__ == "__main__":
    unittest.main()
