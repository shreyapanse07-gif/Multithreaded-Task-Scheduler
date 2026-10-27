"""
test_sample_tasks.py  ->  python -m unittest tests.test_sample_tasks -v
Tests for the three main jobs. Uses a temp folder and skips the sleeps.
"""
import os
import tempfile
import unittest
from unittest import mock

import config
from tasks import sample_tasks
from tasks.sample_tasks import generate_report, backup_file, process_log_file


class TestMainJobs(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        # send all output to the temp folder, and make time.sleep instant
        p1 = mock.patch.object(config, "DATA_DIR", self.tmp.name)
        p2 = mock.patch.object(sample_tasks.time, "sleep")
        p1.start(); p2.start()
        self.addCleanup(p1.stop)
        self.addCleanup(p2.stop)
        self.addCleanup(self.tmp.cleanup)

    def test_generate_report_writes_file(self):
        path = generate_report("sales")
        self.assertTrue(os.path.exists(path))
        self.assertTrue(os.path.basename(path).startswith("sales_"))
        with open(path, encoding="utf-8") as f:
            self.assertIn("Report: sales", f.read())

    def test_backup_copies_content(self):
        src = os.path.join(self.tmp.name, "notes.txt")
        with open(src, "w", encoding="utf-8") as f:
            f.write("hello")
        dest = backup_file(src)
        self.assertTrue(dest.endswith(".bak"))
        with open(dest, encoding="utf-8") as f:
            self.assertEqual(f.read(), "hello")

    def test_backup_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            backup_file(os.path.join(self.tmp.name, "nope.txt"))

    def test_two_backups_do_not_overwrite(self):
        src = os.path.join(self.tmp.name, "a.txt")
        open(src, "w").close()
        self.assertNotEqual(backup_file(src), backup_file(src))

    def test_process_log_file_counts_levels(self):
        log = os.path.join(self.tmp.name, "fake.log")
        with open(log, "w", encoding="utf-8") as f:
            f.write("t | MainThread | INFO    | x | a\n"
                    "t | MainThread | INFO    | x | b\n"
                    "t | MainThread | WARNING | x | c\n"
                    "t | MainThread | ERROR   | x | d\n")
        self.assertEqual(process_log_file(log), {"INFO": 2, "WARNING": 1, "ERROR": 1})

    def test_decorators_keep_names(self):
        self.assertEqual(generate_report.__name__, "generate_report")
        self.assertEqual(backup_file.__name__, "backup_file")

class TestDemoTasks(unittest.TestCase):

    def test_flaky_fails_when_roll_is_low(self):
        with mock.patch.object(sample_tasks.random, "random", return_value=0.0):
            with self.assertRaises(RuntimeError):
                sample_tasks.flaky_task()

    def test_flaky_succeeds_when_roll_is_high(self):
        with mock.patch.object(sample_tasks.random, "random", return_value=0.99):
            self.assertEqual(sample_tasks.flaky_task(), "flaky succeeded")

    def test_flaky_never_fails_at_zero_chance(self):
        for _ in range(50):
            self.assertEqual(sample_tasks.flaky_task(fail_chance=0), "flaky succeeded")

    def test_heartbeat_message(self):
        self.assertTrue(sample_tasks.heartbeat().startswith("alive at "))

    def test_cpu_task_result(self):
        self.assertEqual(sample_tasks.cpu_task(10), 285)   # 0+1+4+...+81

    def test_io_task_waits_and_returns(self):
        with mock.patch.object(sample_tasks.time, "sleep") as fake_sleep:
            self.assertEqual(sample_tasks.io_task(2), 2)
            fake_sleep.assert_called_once_with(2)

    def test_package_exports(self):
        import tasks
        for name in ("generate_report", "backup_file", "process_log_file",
                     "flaky_task", "heartbeat", "cpu_task", "io_task"):
            self.assertTrue(callable(getattr(tasks, name)))

if __name__ == "__main__":
    unittest.main()