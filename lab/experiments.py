"""
experiments.py
Three small experiments that make threading concepts visible:

    1. race_condition()  -> threads updating a shared counter, with and without a Lock
    2. gil_benchmark()   -> sequential vs threads vs processes, for CPU and IO work
    3. semaphore_demo()  -> threads queueing for a Semaphore, as a timeline

This module only imports the standard library on purpose: ProcessPoolExecutor
starts new Python processes that import this file to find cpu_work / io_work.
"""
import os
import sys
import threading
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor


# ============================================================ 1. race condition

class Counter:
    """A shared object every thread updates."""
    def __init__(self):
        self.value = 0


def _add_unsafe(counter, times):
    for _ in range(times):
        current = counter.value          # 1. read
        time.sleep(0)                    # 2. thread switch can happen here
        counter.value = current + 1      # 3. write (may overwrite another thread's update)


def _add_safe(counter, times, lock):
    for _ in range(times):
        with lock:                       # only one thread inside at a time
            current = counter.value
            time.sleep(0)
            counter.value = current + 1


def race_condition(threads=8, increments=2000, use_lock=False):
    """Every thread adds 1 to the counter `increments` times.
    Expected total = threads * increments. Without a lock, updates get lost."""
    counter, lock = Counter(), threading.Lock()
    if use_lock:
        workers = [threading.Thread(target=_add_safe, args=(counter, increments, lock))
                   for _ in range(threads)]
    else:
        workers = [threading.Thread(target=_add_unsafe, args=(counter, increments))
                   for _ in range(threads)]

    start = time.perf_counter()
    for t in workers:
        t.start()
    for t in workers:
        t.join()
    elapsed = time.perf_counter() - start

    expected = threads * increments
    return {"use_lock": use_lock, "threads": threads, "increments": increments,
            "expected": expected, "actual": counter.value,
            "lost": expected - counter.value,
            "lost_percent": round(100 * (expected - counter.value) / expected, 1),
            "seconds": round(elapsed, 3)}


# ============================================================ 2. GIL benchmark

def cpu_work(n):
    """Pure Python number crunching: holds the GIL the whole time."""
    total = 0
    for i in range(n):
        total += i * i % 7
    return total


def io_work(seconds):
    """Waiting (like a download or disk read): releases the GIL while it waits."""
    time.sleep(seconds)
    return seconds


def gil_enabled():
    """True on normal Python. False only on the free-threaded 3.13+ build."""
    check = getattr(sys, "_is_gil_enabled", None)
    return True if check is None else bool(check())


def _calibrate(target_seconds):
    """Pick an n so one cpu_work(n) takes about `target_seconds` on THIS computer."""
    n = 200_000
    timings = []
    for _ in range(3):                    # first run is slower (warm-up), keep the best
        start = time.perf_counter()
        cpu_work(n)
        timings.append(time.perf_counter() - start)
    took = max(min(timings), 1e-4)
    return max(10_000, int(n * target_seconds / took))


def _timed(fn):
    start = time.perf_counter()
    fn()
    return round(time.perf_counter() - start, 3)


def _run_three_ways(func, args, workers):
    def sequential():
        for a in args:
            func(a)

    def threads():
        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(func, args))

    def processes():
        # includes the cost of starting the processes - that's realistic
        with ProcessPoolExecutor(max_workers=workers) as pool:
            list(pool.map(func, args))

    times = {"sequential": _timed(sequential), "threads": _timed(threads),
             "processes": _timed(processes)}
    base = times["sequential"]
    times["speedup_threads"] = round(base / times["threads"], 2) if times["threads"] else None
    times["speedup_processes"] = round(base / times["processes"], 2) if times["processes"] else None
    return times


def gil_benchmark(workers=None, job_seconds=0.4, cpu_job_seconds=None):
    """Same number of jobs, run three ways, for CPU-heavy and IO-heavy work."""
    cores = os.cpu_count() or 2
    workers = workers or max(2, min(4, cores))
    n = _calibrate(cpu_job_seconds or job_seconds)
    return {
        "workers": workers,
        "cores": cores,
        "gil_enabled": gil_enabled(),
        "python": sys.version.split()[0],
        "jobs": workers,
        "cpu": _run_three_ways(cpu_work, [n] * workers, workers),
        "io": _run_three_ways(io_work, [job_seconds] * workers, workers),
    }


# ============================================================ 3. semaphore timeline

def semaphore_demo(threads=8, limit=3, work_seconds=0.6):
    """`threads` threads all want a resource that only `limit` can use at once."""
    semaphore = threading.Semaphore(limit)
    barrier = threading.Barrier(threads)          # start everyone at the same moment
    lock = threading.Lock()
    state = {"inside": 0, "max_inside": 0}
    rows = [None] * threads
    t0 = time.perf_counter()

    def worker(i):
        barrier.wait()
        asked = time.perf_counter()
        with semaphore:                           # blocks while `limit` threads are inside
            got = time.perf_counter()
            with lock:
                state["inside"] += 1
                state["max_inside"] = max(state["max_inside"], state["inside"])
            time.sleep(work_seconds)              # "using the resource"
            with lock:
                state["inside"] -= 1
            done = time.perf_counter()
        rows[i] = {"thread": f"Thread-{i + 1}",
                   "asked": round(asked - t0, 3), "got": round(got - t0, 3),
                   "done": round(done - t0, 3), "waited": round(got - asked, 3)}

    workers = [threading.Thread(target=worker, args=(i,)) for i in range(threads)]
    for t in workers:
        t.start()
    for t in workers:
        t.join()
    return {"threads": threads, "limit": limit, "work_seconds": work_seconds,
            "max_inside": state["max_inside"],
            "total_seconds": round(max(r["done"] for r in rows), 3),
            "rows": rows}
