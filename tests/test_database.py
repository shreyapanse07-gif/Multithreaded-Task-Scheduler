"""
test_database.py
SQLite layer tests. Use ":memory:" as db path -> fast, no files.
"""
import unittest

from scheduler.database import TaskDatabase
from scheduler.task import Task, TaskStatus


class TestDatabase(unittest.TestCase):

    def setUp(self):
        # TODO: self.db = TaskDatabase(":memory:")
        pass

    def tearDown(self):
        # TODO: self.db.close()
        pass

    def test_insert_and_get(self):
        # TODO: insert task -> get_task(id) -> name matches
        pass

    def test_update_status(self):
        # TODO: change status to SUCCESS -> update_status -> fetch -> "success"
        pass

    def test_log_run_history(self):
        # TODO: log_run twice -> get_history(task_id) has 2 rows
        pass

    def test_summary_counts(self):
        # TODO: insert 2 SUCCESS + 1 FAILED -> get_summary() == {"success": 2, "failed": 1}
        pass


if __name__ == "__main__":
    unittest.main()
