# Multithreaded Task Scheduler (Advanced Python Programming – Mini Project)

## Structure
```
task_scheduler/
├── config.py              # all settings (workers, retries, paths, priorities)
├── main.py                # entry point + demos
├── requirements.txt
├── scheduler/
│   ├── __init__.py        # exports Scheduler, Task
│   ├── task.py            # Task, TaskStatus, IOTask, RecurringTask      -> OOP, inheritance
│   ├── scheduler.py       # Scheduler (producer, dispatcher thread)      -> PriorityQueue, RLock, Event
│   ├── worker.py          # Worker threads (consumers)                   -> Thread, Semaphore, retries
│   ├── database.py        # SQLite tasks + executions tables             -> transactions
│   ├── logger.py          # file + console logging                       -> logging, file handling
│   ├── decorators.py      # @timed, @log_call, @retry, @synchronized     -> decorators
│   └── exceptions.py      # custom exceptions                            -> exception handling
├── tasks/
│   ├── __init__.py
│   └── sample_tasks.py    # Task A report, Task B backup, Task C log processing + demo jobs
├── tests/
│   ├── test_task.py
│   ├── test_scheduler.py  # ordering, retry, shutdown, race condition, semaphore
│   └── test_database.py
├── logs/                  # scheduler.log (auto-created)
└── data/                  # tasks.db, reports, backups (auto-created)
```

## Flow
submit(task) → due now? → PriorityQueue → Worker.get() → execute()
                  ↘ not due → waiting heap → Dispatcher moves it when due
Failure → retries left? → back to waiting heap (run_at + RETRY_DELAY) : FAILED
Recurring success → reschedule() → waiting heap

## Suggested build order
1. config.py → exceptions.py → logger.py
2. task.py (+ test_task.py)
3. database.py (+ test_database.py)
4. worker.py → scheduler.py (+ test_scheduler.py)
5. decorators.py → sample_tasks.py → main.py

## Setup
```
python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate        # macOS / Linux
pip install -r requirements.txt
```

## Run
```
python app.py                    # web dashboard -> http://127.0.0.1:5000
python main.py                   # console demos (priorities, retries, recurring, benchmark)
python -m unittest discover tests -v
```

## Web dashboard
`app.py` starts the scheduler once, then a Flask dashboard (only reachable from this computer).
- Live CPU / memory / disk / uptime and top processes (psutil), collected by a recurring task every 3 s
- Create tasks from a fixed list of jobs: system snapshot, top processes, disk report,
  system health report (saved to `data/reports/`), folder scan, file checksum (SHA-256),
  file backup, log analysis, and a sequential-vs-threaded benchmark (concurrent.futures)
- High / Medium / Low priority, delay, retries, repeat interval
- Task list with status filter, details (result + every attempt), cancel and run again
- Worker status, tasks-by-status chart, recent executions from SQLite

Files: `app.py`, `dashboard/web.py` (routes), `dashboard/jobs.py` (allowed jobs),
`dashboard/templates/index.html`, `dashboard/static/`, `tasks/system_tasks.py` (psutil jobs).
Users can only pick jobs from `dashboard/jobs.py`; the dashboard never runs code sent from the browser.

## Concurrency lab (http://127.0.0.1:5000/lab)
Three live experiments, code in `lab/experiments.py`:
1. **Race condition**: threads update a shared counter without and with a `Lock`; shows lost updates vs an exact total.
2. **GIL**: the same jobs run sequentially, with `ThreadPoolExecutor` and with `ProcessPoolExecutor`,
   for CPU-heavy and IO-heavy work. Threads only help IO work; processes help CPU work.
3. **Semaphore**: threads start together (`Barrier`) and queue for a `Semaphore`; a timeline shows who waited and who ran.
