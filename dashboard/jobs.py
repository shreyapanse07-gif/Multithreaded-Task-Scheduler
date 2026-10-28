"""
jobs.py
The ONLY jobs the dashboard can create. Users pick a job type from this list;
they can never send their own Python code to run.
"""
import time
from concurrent.futures import ThreadPoolExecutor

from tasks.sample_tasks import backup_file, process_log_file
from tasks.system_tasks import (system_snapshot, top_processes, disk_report,
                                folder_scan, file_checksum, system_report)


def concurrency_benchmark(jobs=6, seconds=0.5, workers=3):
    """Runs the same IO-style jobs one after another, then with a thread pool
    (concurrent.futures), and reports both times."""
    start = time.perf_counter()
    for _ in range(jobs):
        time.sleep(seconds)
    sequential = time.perf_counter() - start

    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(time.sleep, [seconds] * jobs))
    threaded = time.perf_counter() - start

    return {"jobs": jobs, "seconds_each": seconds, "threads": workers,
            "sequential_s": round(sequential, 2), "threaded_s": round(threaded, 2),
            "speedup": round(sequential / threaded, 2)}


# key -> how to run it.  "param" = the one text input the job needs (or None).
# "io": True -> submitted as IOTask, so the IO semaphore limits how many run at once.
JOBS = {
    "system_snapshot": {"label": "System snapshot (CPU, memory, disk)",
                        "func": system_snapshot, "param": None, "io": False},
    "top_processes": {"label": "Top processes by memory",
                      "func": top_processes, "param": None, "io": False},
    "disk_report": {"label": "Disk usage report",
                    "func": disk_report, "param": None, "io": True},
    "system_report": {"label": "System health report (saved as file)",
                      "func": system_report, "param": None, "io": True},
    "folder_scan": {"label": "Folder scan (size + largest files)",
                    "func": folder_scan, "param": "Folder path", "io": True},
    "file_checksum": {"label": "File checksum (SHA-256)",
                      "func": file_checksum, "param": "File path", "io": True},
    "backup_file": {"label": "Back up a file",
                    "func": backup_file, "param": "File path", "io": True},
    "log_analysis": {"label": "Analyse scheduler log (INFO / WARNING / ERROR)",
                     "func": process_log_file, "param": None, "io": True},
    "benchmark": {"label": "Benchmark: sequential vs threaded",
                  "func": concurrency_benchmark, "param": None, "io": False},
}


def job_list():
    """What the front end needs to build the form."""
    return [{"key": key, "label": job["label"], "param": job["param"]}
            for key, job in JOBS.items()]
