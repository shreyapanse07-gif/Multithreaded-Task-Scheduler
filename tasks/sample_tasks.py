"""
sample_tasks.py
The actual jobs the scheduler runs (Task A / B / C from the project brief + demo tasks).
Each is a plain function -> wrapped in Task(...) inside main.py.
"""
import os
import time
import shutil
import random
from datetime import datetime

import config
from scheduler.decorators import timed, log_call


def _stamp():
    """Timestamp for file names (microseconds so two jobs never clash)."""
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


@timed
@log_call
def generate_report(report_name="daily_report"):
    """Task A: Generate a report."""
    os.makedirs(config.DATA_DIR, exist_ok=True)
    lines = [f"Report: {report_name}",
             f"Generated at: {datetime.now():%Y-%m-%d %H:%M:%S}",
             f"Sales: {random.randint(100, 999)}",
             f"Visitors: {random.randint(1000, 9999)}"]
    path = os.path.join(config.DATA_DIR, f"{report_name}_{_stamp()}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    time.sleep(1)                          # simulate work
    return path


@timed
@log_call
def backup_file(src_path, backup_dir=None):
    """Task B: Back up a file.  -> submit this as IOTask (uses semaphore)."""
    backup_dir = backup_dir or os.path.join(config.DATA_DIR, "backups")
    os.makedirs(backup_dir, exist_ok=True)
    if not os.path.exists(src_path):
        raise FileNotFoundError(f"Cannot back up missing file: {src_path}")
    dest = os.path.join(backup_dir, f"{os.path.basename(src_path)}_{_stamp()}.bak")
    shutil.copy2(src_path, dest)
    return dest


@timed
@log_call
def process_log_file(log_path=config.LOG_FILE):
    """Task C: Process a log file -> count INFO / WARNING / ERROR lines."""
    counts = {"INFO": 0, "WARNING": 0, "ERROR": 0}
    with open(log_path, encoding="utf-8", errors="replace") as f:
        for line in f:
            for level in counts:
                if f"| {level} " in line:       # matches the logger's "| INFO    |" format
                    counts[level] += 1
    return counts


def flaky_task(fail_chance=0.6):
    """Fails randomly -> use it to demo retries + MAX_RETRIES."""
    if random.random() < fail_chance:
        raise RuntimeError("random failure")
    return "flaky succeeded"


def heartbeat():
    """Tiny recurring task (submit with interval=3)."""
    return f"alive at {datetime.now():%H:%M:%S}"


def cpu_task(n=10**6):
    """For comparing sequential vs threaded time (note: GIL -> CPU tasks won't speed up, IO tasks will)."""
    return sum(i * i for i in range(n))


def io_task(seconds=1):
    """Simulated IO wait -> threads DO speed this up."""
    time.sleep(seconds)
    return seconds