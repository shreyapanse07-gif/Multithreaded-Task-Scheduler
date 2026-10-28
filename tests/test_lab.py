"""
test_lab.py
Tests for the Concurrency Lab experiments and their API.
Run:  python -m unittest tests.test_lab -v
"""
import os
import tempfile
import unittest

from lab import experiments
from scheduler import Scheduler
from dashboard import create_app


class TestExperiments(unittest.TestCase):

    def test_without_lock_loses_updates(self):
        r = experiments.race_condition(threads=6, increments=500, use_lock=False)
        self.assertEqual(r["expected"], 3000)
        self.assertLess(r["actual"], r["expected"])
        self.assertEqual(r["lost"], r["expected"] - r["actual"])

    def test_with_lock_is_exact(self):
        r = experiments.race_condition(threads=6, increments=500, use_lock=True)
        self.assertEqual(r["actual"], 3000)
        self.assertEqual(r["lost"], 0)

    def test_semaphore_never_exceeds_limit(self):
        r = experiments.semaphore_demo(threads=6, limit=2, work_seconds=0.1)
        self.assertEqual(r["max_inside"], 2)
        self.assertEqual(len(r["rows"]), 6)
        waited = [row for row in r["rows"] if row["waited"] > 0.05]
        self.assertEqual(len(waited), 4)                 # 4 of 6 had to wait
        self.assertGreaterEqual(r["total_seconds"], 0.29)   # 3 rounds of 0.1 s

    def test_gil_benchmark_shape(self):
        r = experiments.gil_benchmark(workers=2, job_seconds=0.1)
        for kind in ("cpu", "io"):
            for key in ("sequential", "threads", "processes", "speedup_threads"):
                self.assertIn(key, r[kind])
        self.assertGreater(r["io"]["speedup_threads"], 1.5)   # waiting threads overlap
        self.assertIsInstance(r["gil_enabled"], bool)


class TestLabAPI(unittest.TestCase):

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.s = Scheduler(num_workers=1, db_path=self.db_path)
        self.client = create_app(self.s).test_client()

    def tearDown(self):
        self.s.shutdown()
        os.remove(self.db_path)

    def test_lab_is_a_tab_on_the_main_page(self):
        page = self.client.get("/").get_data(as_text=True)
        self.assertIn('id="pane-lab"', page)
        self.assertIn('id="r-unsafe"', page)
        res = self.client.get("/lab")
        self.assertEqual(res.status_code, 302)
        self.assertTrue(res.headers["Location"].endswith("/#lab"))

    def test_race_endpoint(self):
        res = self.client.post("/api/lab/race", json={"threads": 4, "increments": 200, "use_lock": True})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["actual"], 800)

    def test_semaphore_endpoint(self):
        res = self.client.post("/api/lab/semaphore", json={"threads": 3, "limit": 1})
        self.assertEqual(res.get_json()["max_inside"], 1)

    def test_bad_input(self):
        self.assertEqual(self.client.post("/api/lab/race", json={"threads": 500}).status_code, 400)
        self.assertEqual(self.client.post("/api/lab/semaphore",
                                          json={"threads": 4, "limit": 9}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
