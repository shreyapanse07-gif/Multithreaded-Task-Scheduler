"""
main.py
Entry point / demo. Run:  python main.py
Shows: priorities, delayed tasks, IO semaphore, retries, recurring task, stats, DB history.
"""
import time

import config
from scheduler import Scheduler, Task
from scheduler.task import IOTask, RecurringTask
from scheduler.logger import get_logger
from tasks.sample_tasks import (generate_report, backup_file, process_log_file,
                                flaky_task, heartbeat, io_task)

logger = get_logger("main")


def demo_basic(scheduler):
    # TODO: submit Task A, B, C from the brief with different priorities
    #   Task("Generate report", generate_report, priority=config.PRIORITY_HIGH)
    #   IOTask("Backup config", backup_file, args=(config.__file__,), priority=config.PRIORITY_MEDIUM)
    #   Task("Process logs", process_log_file, priority=config.PRIORITY_LOW)
    pass


def demo_delayed_and_retry(scheduler):
    # TODO: Task("Delayed report", generate_report, delay_seconds=5)
    # TODO: Task("Flaky job", flaky_task, max_retries=3)
    # TODO: IOTask("Backup missing file", backup_file, args=("does_not_exist.txt",))  -> should FAIL after retries
    pass


def demo_recurring(scheduler):
    # TODO: RecurringTask("Heartbeat", heartbeat, interval=3)
    pass


def demo_performance():
    # TODO: run io_task(1) 6 times sequentially -> measure with time.perf_counter()
    # TODO: run same 6 through Scheduler -> measure again
    # TODO: print both times -> threaded should be ~NUM_WORKERS times faster
    pass


def print_summary(scheduler):
    # TODO: print scheduler.get_stats()
    # TODO: print scheduler.db.get_summary()
    # TODO: loop scheduler.tasks.values() -> print id, name, status, retries
    pass


def main():
    # TODO: (optional) argparse -> --workers, --demo {basic,retry,recurring,perf,all}
    # TODO: with Scheduler(num_workers=config.NUM_WORKERS) as s:
    #           demo_basic(s); demo_delayed_and_retry(s); demo_recurring(s)
    #           time.sleep(15)              # let things run (recurring never "finishes")
    #           print_summary(s)
    # TODO: try/except KeyboardInterrupt -> graceful shutdown (Ctrl+C)
    pass


if __name__ == "__main__":
    main()
