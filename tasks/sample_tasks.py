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


@timed
@log_call
def generate_report(report_name="daily_report"):
    """Task A: Generate a report."""
    # TODO: build some content (e.g. timestamp + random numbers / summary lines)
    # TODO: write to os.path.join(config.DATA_DIR, f"{report_name}_{timestamp}.txt")
    #       hint -> with open(path, "w") as f: f.write(...)
    # TODO: time.sleep(1) to simulate work, return path
    pass


@timed
@log_call
def backup_file(src_path, backup_dir=None):
    """Task B: Back up a file.  -> submit this as IOTask (uses semaphore)."""
    # TODO: backup_dir default -> os.path.join(config.DATA_DIR, "backups"), makedirs
    # TODO: if not os.path.exists(src_path): raise FileNotFoundError  (shows failure + retry)
    # TODO: dest = backup_dir/<name>_<timestamp>.bak ; shutil.copy2(src_path, dest)
    # TODO: return dest
    pass


@timed
@log_call
def process_log_file(log_path=config.LOG_FILE):
    """Task C: Process a log file -> count INFO / WARNING / ERROR lines."""
    # TODO: counts = {"INFO": 0, "WARNING": 0, "ERROR": 0}
    # TODO: with open(log_path) as f: for line in f: check which level is in the line
    # TODO: return counts
    pass


def flaky_task(fail_chance=0.6):
    """Fails randomly -> use it to demo retries + MAX_RETRIES."""
    # TODO: if random.random() < fail_chance: raise RuntimeError("random failure")
    # TODO: return "flaky succeeded"
    pass


def heartbeat():
    """Tiny recurring task (submit with interval=3)."""
    # TODO: return f"alive at {datetime.now():%H:%M:%S}"
    pass


def cpu_task(n=10**6):
    """For comparing sequential vs threaded time (note: GIL -> CPU tasks won't speed up, IO tasks will)."""
    # TODO: return sum(i * i for i in range(n))
    pass


def io_task(seconds=1):
    """Simulated IO wait -> threads DO speed this up."""
    # TODO: time.sleep(seconds); return seconds
    pass
