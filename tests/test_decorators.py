"""
test_decorators.py  ->  python -m unittest discover tests
Small tests for @timed, @log_call, @retry, @synchronized.
"""
import unittest
import threading

from scheduler.decorators import timed, log_call, retry, synchronized


class TestDecorators(unittest.TestCase):

    def test_keeps_name_and_result(self):
        @timed
        @log_call
        def add(a, b):
            """adds"""
            return a + b
        self.assertEqual(add(2, 3), 5)
        self.assertEqual(add.__name__, "add")      # functools.wraps worked

    def test_log_call_reraises(self):
        @log_call
        def boom():
            raise ValueError("bad")
        with self.assertRaises(ValueError):
            boom()

    def test_retry_succeeds_after_failures(self):
        calls = {"n": 0}

        @retry(times=3, delay=0)
        def flaky():
            calls["n"] += 1
            if calls["n"] < 3:
                raise RuntimeError("no")
            return "ok"
        self.assertEqual(flaky(), "ok")
        self.assertEqual(calls["n"], 3)

    def test_retry_gives_up(self):
        calls = {"n": 0}

        @retry(times=2, delay=0)
        def always():
            calls["n"] += 1
            raise RuntimeError("no")
        with self.assertRaises(RuntimeError):
            always()
        self.assertEqual(calls["n"], 2)             # tried exactly `times` times

    def test_synchronized_protects_counter(self):
        lock = threading.Lock()
        counter = {"n": 0}

        @synchronized(lock)
        def bump():
            counter["n"] += 1

        threads = [threading.Thread(target=lambda: [bump() for _ in range(1000)])
                   for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(counter["n"], 5000)


if __name__ == "__main__":
    unittest.main()