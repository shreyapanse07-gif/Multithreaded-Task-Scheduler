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

## Run
```
python main.py
python -m unittest discover tests -v
```
