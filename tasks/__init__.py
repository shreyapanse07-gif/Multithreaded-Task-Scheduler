"""
tasks package: the jobs the scheduler runs.
"""
from .sample_tasks import (generate_report, backup_file, process_log_file,
                           flaky_task, heartbeat, cpu_task, io_task)

__all__ = ["generate_report", "backup_file", "process_log_file",
           "flaky_task", "heartbeat", "cpu_task", "io_task"]