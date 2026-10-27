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
        self.db_path = db_path
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._create_tables()

    def _create_tables(self):
        with self._lock, self.conn:
            self.conn.execute("""CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY, name TEXT, priority INTEGER, status TEXT,
                run_at TEXT, retries INTEGER, max_retries INTEGER, created_at TEXT, error TEXT
            )""")
            self.conn.execute("""CREATE TABLE IF NOT EXISTS executions (
                id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT, worker TEXT,
                started_at TEXT, finished_at TEXT, duration REAL, status TEXT, error TEXT,
                FOREIGN KEY(task_id) REFERENCES tasks(task_id)
            )""")

    def insert_task(self, task):
        # NEVER use f-strings for SQL values -> SQL injection; always use ? placeholders
        data = task.to_dict()
        with self._lock, self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO tasks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (data["task_id"], data["name"], data["priority"], data["status"],
                 data["run_at"], data["retries"], data["max_retries"],
                 data["created_at"], data["error"]),
            )

    def update_status(self, task):
        with self._lock, self.conn:
            self.conn.execute(
                "UPDATE tasks SET status=?, retries=?, error=?, run_at=? WHERE task_id=?",
                (task.status.value, task.retries, task.error,
                 task.run_at.isoformat(), task.task_id),
            )

    def log_run(self, task, worker_name, duration):
        with self._lock, self.conn:
            self.conn.execute(
                "INSERT INTO executions (task_id, worker, started_at, finished_at, duration, status, error) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (task.task_id, worker_name,
                 task.started_at.isoformat() if task.started_at else None,
                 task.finished_at.isoformat() if task.finished_at else None,
                 duration, task.status.value, task.error),
            )

    def get_task(self, task_id):
        with self._lock:
            return self.conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()

    def get_history(self, task_id=None, limit=50):
        with self._lock:
            if task_id is None:
                return self.conn.execute(
                    "SELECT * FROM executions ORDER BY id DESC LIMIT ?", (limit,)
                ).fetchall()
            return self.conn.execute(
                "SELECT * FROM executions WHERE task_id=? ORDER BY id DESC LIMIT ?",
                (task_id, limit),
            ).fetchall()

    def get_summary(self):
        with self._lock:
            rows = self.conn.execute(
                "SELECT status, COUNT(*) FROM tasks GROUP BY status"
            ).fetchall()
            return {status: count for status, count in rows}

    def close(self):
        with self._lock:
            self.conn.close()
