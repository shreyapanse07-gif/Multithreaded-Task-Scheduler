"""
database.py
SQLite persistence for tasks + execution history.
Topics: sqlite3, transactions, parameterised queries, Lock (sqlite connection shared across threads)
"""
import sqlite3
import threading
from datetime import datetime

import config


class TaskDatabase:
    """
    Tables to create:
        tasks(task_id TEXT PRIMARY KEY, name TEXT, priority INTEGER, status TEXT,
              run_at TEXT, retries INTEGER, max_retries INTEGER, created_at TEXT, error TEXT)
        executions(id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT, worker TEXT,
                   started_at TEXT, finished_at TEXT, duration REAL, status TEXT, error TEXT,
                   FOREIGN KEY(task_id) REFERENCES tasks(task_id))
    """

    def __init__(self, db_path=config.DB_FILE):
        # TODO: self.db_path = db_path
        # TODO: self._lock = threading.Lock()
        # TODO: self.conn = sqlite3.connect(db_path, check_same_thread=False)
        #       ^ needed because workers (other threads) use the same connection
        # TODO: self._create_tables()
        pass

    def _create_tables(self):
        # TODO: CREATE TABLE IF NOT EXISTS ... for both tables (see docstring)
        # TODO: commit
        pass

    def insert_task(self, task):
        # TODO: with self._lock, self.conn:      <- `with conn` = auto commit / rollback (transaction)
        #           self.conn.execute("INSERT OR REPLACE INTO tasks VALUES (?, ?, ...)", (...))
        # NEVER use f-strings for SQL values -> SQL injection; always use ? placeholders
        pass

    def update_status(self, task):
        # TODO: UPDATE tasks SET status=?, retries=?, error=?, run_at=? WHERE task_id=?
        pass

    def log_run(self, task, worker_name, duration):
        # TODO: INSERT INTO executions (...) VALUES (?, ?, ?, ?, ?, ?, ?)
        pass

    def get_task(self, task_id):
        # TODO: SELECT * FROM tasks WHERE task_id=?  -> fetchone()
        pass

    def get_history(self, task_id=None, limit=50):
        # TODO: SELECT from executions, optional WHERE task_id=?, ORDER BY id DESC LIMIT ?
        pass

    def get_summary(self):
        # TODO: SELECT status, COUNT(*) FROM tasks GROUP BY status -> return dict
        pass

    def close(self):
        # TODO: with self._lock: self.conn.close()
        pass
