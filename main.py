"""
main.py
Entry point / demo. Run:  python main.py
Shows: priorities, delayed tasks, IO semaphore, retries, recurring task, stats, DB history.

Usage:
    python main.py                      # run every demo
    python main.py --demo basic         # only the priority demo
    python main.py --demo perf          # only the sequential vs threaded benchmark
    python main.py --workers 6 --demo retry
"""
import argparse
import time

import config
from scheduler import Scheduler, Task
from scheduler.task import IOTask, RecurringTask
from scheduler.logger import get_logger
from tasks.sample_tasks import (generate_report, backup_file, process_log_file,
                                flaky_task, heartbeat, io_task)

logger = get_logger("main")

# Statuses after which a task will never run again.
TERMINAL_STATES = {"SUCCESS", "COMPLETED", "FAILED", "CANCELLED"}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _status_name(task):
    """Return the task status as an upper-case string, whether it is an Enum or a str."""
    status = task.status
    return str(getattr(status, "name", status)).upper()


def wait_for_tasks(tasks, timeout=60.0, poll=0.1):
    """Block until every task in `tasks` is in a terminal state (or timeout expires).

    Returns True if all finished, False on timeout.
    """
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        if all(_status_name(t) in TERMINAL_STATES for t in tasks):
            return True
        time.sleep(poll)
    return False


def banner(title):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


# --------------------------------------------------------------------------- #
# Demos
# --------------------------------------------------------------------------- #
def demo_basic(scheduler):
    """Three tasks with different priorities (High should run before Low)."""
    banner("DEMO 1: Priorities (A=High, B=Medium, C=Low)")
    task_a = Task("Generate report", generate_report, priority=config.PRIORITY_HIGH)
    task_b = IOTask("Backup config", backup_file, args=(config.__file__,),
                    priority=config.PRIORITY_MEDIUM)
    task_c = Task("Process logs", process_log_file, priority=config.PRIORITY_LOW)

    for task in (task_a, task_b, task_c):
        scheduler.submit(task)
        logger.info("Submitted: %s", task.name)


def demo_delayed_and_retry(scheduler):
    """A delayed task, a flaky task that retries, and a task that must fail."""
    banner("DEMO 2: Delayed task + retries")

    # Waits in the 'waiting heap' for 5 s before reaching the priority queue.
    scheduler.submit(Task("Delayed report", generate_report, delay_seconds=5))

    # Fails randomly/at first, succeeds on a later attempt (up to 3 retries).
    scheduler.submit(Task("Flaky job", flaky_task, max_retries=3))

    # The file does not exist -> fails every attempt -> ends as FAILED.
    scheduler.submit(IOTask("Backup missing file", backup_file,
                            args=("does_not_exist.txt",)))
    logger.info("Submitted delayed, flaky and failing tasks")


def demo_recurring(scheduler):
    """A task that re-schedules itself every few seconds after each success."""
    banner("DEMO 3: Recurring task (every 3 s)")
    scheduler.submit(RecurringTask("Heartbeat", heartbeat, interval=3))
    logger.info("Submitted recurring heartbeat")


def demo_performance(num_workers=None, jobs=6, job_seconds=1):
    """Compare running IO jobs one after another vs. through the scheduler."""
    num_workers = num_workers or config.NUM_WORKERS
    banner(f"DEMO 4: Performance ({jobs} jobs x {job_seconds}s, {num_workers} workers)")

    # --- Sequential baseline ---
    start = time.perf_counter()
    for _ in range(jobs):
        io_task(job_seconds)
    sequential = time.perf_counter() - start

    # --- Threaded via the scheduler ---
    # Plain Task (not IOTask) so the IO semaphore doesn't limit the parallelism.
    with Scheduler(num_workers=num_workers) as s:
        tasks = [Task(f"IO job {i + 1}", io_task, args=(job_seconds,))
                 for i in range(jobs)]
        start = time.perf_counter()
        for t in tasks:
            s.submit(t)
        finished = wait_for_tasks(tasks, timeout=jobs * job_seconds + 30)
        threaded = time.perf_counter() - start

    if not finished:
        print("Warning: some tasks did not finish before the timeout.")

    speedup = sequential / threaded if threaded > 0 else float("inf")
    print(f"Sequential : {sequential:6.2f} s")
    print(f"Threaded   : {threaded:6.2f} s  ({num_workers} workers)")
    print(f"Speed-up   : {speedup:6.2f}x  (ideal ~{min(num_workers, jobs)}x)")


def print_summary(scheduler):
    """Print live stats, database history summary and every task's final state."""
    banner("SUMMARY")

    print("Scheduler stats:")
    stats = scheduler.get_stats()
    if isinstance(stats, dict):
        for key, value in stats.items():
            print(f"  {key}: {value}")
    else:
        print(f"  {stats}")

    print("\nDatabase summary:")
    summary = scheduler.db.get_summary()
    if isinstance(summary, dict):
        for key, value in summary.items():
            print(f"  {key}: {value}")
    else:
        print(f"  {summary}")

    print("\nTasks:")
    print(f"  {'ID':<10}{'NAME':<24}{'STATUS':<12}{'RETRIES'}")
    print("  " + "-" * 54)
    for task in list(scheduler.tasks.values()):
        print(f"  {str(task.task_id)[:8]:<10}{task.name:<24}"
              f"{_status_name(task):<12}{task.retries}")


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def parse_args():
    parser = argparse.ArgumentParser(description="Multithreaded Task Scheduler demo")
    parser.add_argument("--workers", type=int, default=config.NUM_WORKERS,
                        help="number of worker threads (default: %(default)s)")
    parser.add_argument("--demo", choices=["basic", "retry", "recurring", "perf", "all"],
                        default="all", help="which demo to run (default: all)")
    parser.add_argument("--run-time", type=float, default=15,
                        help="seconds to let the scheduler run before the summary "
                             "(default: %(default)s)")
    return parser.parse_args()


def main():
    args = parse_args()

    # The benchmark creates its own scheduler, so run it on its own.
    if args.demo == "perf":
        demo_performance(args.workers)
        return

    try:
        with Scheduler(num_workers=args.workers) as s:
            if args.demo in ("basic", "all"):
                demo_basic(s)
            if args.demo in ("retry", "all"):
                demo_delayed_and_retry(s)
            if args.demo in ("recurring", "all"):
                demo_recurring(s)

            # Let things run (a recurring task never "finishes").
            logger.info("Running for %.0f seconds... (Ctrl+C to stop)", args.run_time)
            time.sleep(args.run_time)

            print_summary(s)

        # Scheduler has shut down gracefully at this point.
        if args.demo == "all":
            demo_performance(args.workers)

    except KeyboardInterrupt:
        # Leaving the `with` block already called shutdown(); just report it.
        logger.info("Interrupted by user (Ctrl+C) - scheduler shut down gracefully")
        print("\nInterrupted. Scheduler shut down gracefully.")


if __name__ == "__main__":
    main()