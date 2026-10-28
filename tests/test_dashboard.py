"""
test_dashboard.py
Tests for the real system jobs (psutil) and the Flask JSON API.
Run:  python -m unittest tests.test_dashboard -v
"""
import hashlib
import os
import tempfile
import time
import unittest
from unittest import mock

import config
from scheduler import Scheduler
from tasks import system_tasks
from dashboard import create_app


class TestSystemJobs(unittest.TestCase):

    def test_snapshot_has_real_numbers(self):
        snap = system_tasks.system_snapshot()
        for key in ("cpu_percent", "memory_percent", "disk_percent", "processes", "uptime"):
            self.assertIn(key, snap)
        self.assertTrue(0 <= snap["memory_percent"] <= 100)
        self.assertGreater(snap["memory_total_gb"], 0)
        self.assertGreater(snap["processes"], 0)

    def test_top_processes_sorted_by_memory(self):
        rows = system_tasks.top_processes(limit=5)
        self.assertLessEqual(len(rows), 5)
        memory = [r["memory_mb"] for r in rows]
        self.assertEqual(memory, sorted(memory, reverse=True))

    def test_disk_report(self):
        drives = system_tasks.disk_report()
        self.assertGreaterEqual(len(drives), 1)
        self.assertIn("free_gb", drives[0])

    def test_folder_scan_and_checksum(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name, size in [("a.txt", 10), ("b.txt", 3000), ("c.txt", 50)]:
                with open(os.path.join(tmp, name), "wb") as f:
                    f.write(b"x" * size)
            scan = system_tasks.folder_scan(tmp, top_n=2)
            self.assertEqual(scan["files"], 3)
            self.assertTrue(scan["largest"][0]["file"].endswith("b.txt"))

            path = os.path.join(tmp, "b.txt")
            result = system_tasks.file_checksum(path)
            self.assertEqual(result["checksum"], hashlib.sha256(b"x" * 3000).hexdigest())

    def test_bad_paths_raise(self):
        with self.assertRaises(NotADirectoryError):
            system_tasks.folder_scan("/definitely/not/here")
        with self.assertRaises(FileNotFoundError):
            system_tasks.file_checksum("/definitely/not/here.txt")

    def test_system_report_writes_file(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(config, "DATA_DIR", tmp):
            path = system_tasks.system_report()
            with open(path, encoding="utf-8") as f:
                text = f.read()
        self.assertIn("SYSTEM REPORT", text)
        self.assertIn("Memory", text)

    def test_collect_metrics_fills_history(self):
        before = len(system_tasks.get_metrics_history())
        system_tasks.collect_metrics()
        self.assertGreaterEqual(len(system_tasks.get_metrics_history()), min(before + 1, 120))
        self.assertTrue(system_tasks.get_latest_processes())


class TestDashboardAPI(unittest.TestCase):

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.s = Scheduler(num_workers=2, db_path=self.db_path, retry_delay=0.1)
        self.s.start()
        self.client = create_app(self.s).test_client()

    def tearDown(self):
        self.s.shutdown()
        os.remove(self.db_path)

    def post(self, body):
        return self.client.post("/api/tasks", json=body)

    def test_page_and_job_list(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        keys = [j["key"] for j in self.client.get("/api/jobs").get_json()]
        self.assertIn("system_snapshot", keys)

    def test_create_and_finish_task(self):
        res = self.post({"job": "disk_report", "priority": "high"})
        self.assertEqual(res.status_code, 201)
        task_id = res.get_json()["id"]
        self.assertTrue(self.s.wait_until_done(timeout=10))
        detail = self.client.get(f"/api/tasks/{task_id}").get_json()
        self.assertEqual(detail["task"]["status"], "SUCCESS")
        self.assertEqual(detail["task"]["priority_name"], "High")
        self.assertIsInstance(detail["task"]["result"], list)
        self.assertEqual(len(detail["attempts"]), 1)
        stats = self.client.get("/api/stats").get_json()
        self.assertEqual(stats["counts"]["SUCCESS"], 1)
        self.assertEqual(len(stats["workers"]), 2)

    def test_failed_task_retries_then_fails(self):
        task_id = self.post({"job": "backup_file", "param": "/no/such/file",
                             "max_retries": 1}).get_json()["id"]
        self.assertTrue(self.s.wait_until_done(timeout=10))
        task = self.client.get(f"/api/tasks/{task_id}").get_json()["task"]
        self.assertEqual(task["status"], "FAILED")
        self.assertEqual(task["retries"], 1)
        self.assertIn("FileNotFoundError", task["error"])

    def test_cancel_and_rerun(self):
        task_id = self.post({"job": "disk_report", "delay": 30}).get_json()["id"]
        self.assertEqual(self.client.post(f"/api/tasks/{task_id}/cancel").status_code, 200)
        self.assertEqual(self.client.post(f"/api/tasks/{task_id}/cancel").status_code, 409)
        res = self.client.post(f"/api/tasks/{task_id}/rerun")
        self.assertEqual(res.status_code, 201)
        self.assertNotEqual(res.get_json()["id"], task_id)

    def test_filter_by_status(self):
        self.post({"job": "disk_report", "delay": 30})
        self.post({"job": "disk_report"})
        self.assertTrue(self.s.wait_until_done(timeout=0.1) is False)   # one still scheduled
        time.sleep(1)
        scheduled = self.client.get("/api/tasks?status=SCHEDULED").get_json()
        self.assertEqual(len(scheduled), 1)

    def test_bad_input_rejected(self):
        for body in ({"job": "rm -rf"},                       # not in the whitelist
                     {"job": "folder_scan"},                  # missing path
                     {"job": "disk_report", "priority": "urgent"},
                     {"job": "disk_report", "delay": -5},
                     {"job": "disk_report", "max_retries": 99},
                     {"job": "disk_report", "interval": 0.5}):
            self.assertEqual(self.post(body).status_code, 400, body)
        self.assertEqual(self.client.get("/api/tasks/nope").status_code, 404)

    def test_history_comes_from_sqlite(self):
        self.post({"job": "disk_report"})
        self.assertTrue(self.s.wait_until_done(timeout=10))
        rows = self.client.get("/api/history").get_json()
        self.assertEqual(rows[0]["name"], "Disk usage report")
        self.assertEqual(rows[0]["status"], "success")


if __name__ == "__main__":
    unittest.main()
