"""
config.py
Central place for all settings so no other file has hard-coded values.
"""
import os

# Base paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs")
DATA_DIR = os.path.join(BASE_DIR, "data")

# Files
LOG_FILE = os.path.join(LOG_DIR, "scheduler.log")
DB_FILE = os.path.join(DATA_DIR, "tasks.db")

# Scheduler settings
NUM_WORKERS = 3              # how many worker threads to start
MAX_RETRIES = 3              # how many times a failed task is retried
RETRY_DELAY = 2              # seconds to wait before a retry
MAX_CONCURRENT_IO = 2        # semaphore limit for file/IO-heavy tasks
POLL_INTERVAL = 0.5          # seconds the scheduler loop sleeps between checks

# Priority levels (lower number = higher priority, matches PriorityQueue ordering)
PRIORITY_HIGH = 1
PRIORITY_MEDIUM = 5
PRIORITY_LOW = 10

# Create the log and data folders if they don't exist yet.
# exist_ok=True makes this safe to run on every import (no error if already there).
for _path in (LOG_DIR, DATA_DIR):
    os.makedirs(_path, exist_ok=True)