"""
web.py
Flask routes. The page polls these JSON endpoints every couple of seconds.

    GET  /                         dashboard page
    GET  /api/jobs                 job types for the "New task" form
    GET  /api/stats                counters, task counts by status, workers
    GET  /api/system               live CPU / memory / disk + history + top processes
    GET  /api/tasks?status=X       task list (newest first)
    GET  /api/tasks/<id>           one task + its execution history
    POST /api/tasks                create a task
    POST /api/tasks/<id>/cancel    cancel a task that hasn't started
    POST /api/tasks/<id>/rerun     submit a copy of a finished task
    GET  /api/history              recent executions from SQLite
"""
import json
import platform

from flask import Flask, jsonify, render_template, request

import config
from scheduler import Task, IOTask, RecurringTask, TaskStatus
from tasks.system_tasks import get_metrics_history, get_latest_processes
from .jobs import JOBS, job_list

PRIORITIES = {"high": config.PRIORITY_HIGH,
              "medium": config.PRIORITY_MEDIUM,
              "low": config.PRIORITY_LOW}
PRIORITY_NAMES = {v: k.capitalize() for k, v in PRIORITIES.items()}
HISTORY_COLUMNS = ["id", "task_id", "worker", "started_at", "finished_at",
                   "duration", "status", "error"]


class BadRequest(Exception):
    pass


def _json_safe(value):
    """Task results can be anything; make sure they can be sent as JSON."""
    return json.loads(json.dumps(value, default=str))


def task_to_json(task):
    duration = None
    if task.started_at and task.finished_at and task.finished_at >= task.started_at:
        duration = round((task.finished_at - task.started_at).total_seconds(), 3)
    return {
        "id": task.task_id,
        "name": task.name,
        "job": getattr(task, "job", None),
        "param": getattr(task, "param", None),
        "priority": task.priority,
        "priority_name": PRIORITY_NAMES.get(task.priority, str(task.priority)),
        "status": task.status.name,
        "worker": getattr(task, "worker", None),
        "retries": task.retries,
        "max_retries": task.max_retries,
        "interval": task.interval,
        "is_io": task.is_io,
        "created_at": task.created_at.strftime("%H:%M:%S"),
        "run_at": task.run_at.strftime("%H:%M:%S"),
        "started_at": task.started_at.strftime("%H:%M:%S") if task.started_at else None,
        "finished_at": task.finished_at.strftime("%H:%M:%S") if task.finished_at else None,
        "duration": duration,
        "error": task.error,
        "result": _json_safe(task.result),
    }


def build_task(data):
    """Turns the form data into a Task. Raises BadRequest on bad input."""
    key = data.get("job")
    if key not in JOBS:
        raise BadRequest("Unknown job type")
    job = JOBS[key]

    priority = PRIORITIES.get(str(data.get("priority", "medium")).lower())
    if priority is None:
        raise BadRequest("Priority must be high, medium or low")
    try:
        delay = float(data.get("delay") or 0)
        retries = int(data.get("max_retries", config.MAX_RETRIES))
        interval = float(data["interval"]) if data.get("interval") else None
    except (TypeError, ValueError):
        raise BadRequest("Delay, retries and repeat must be numbers") from None
    if not 0 <= delay <= 86400:
        raise BadRequest("Delay must be between 0 and 86400 seconds")
    if not 0 <= retries <= 10:
        raise BadRequest("Retries must be between 0 and 10")
    if interval is not None and interval < 2:
        raise BadRequest("Repeat interval must be at least 2 seconds")

    args, param = (), None
    if job["param"]:
        param = str(data.get("param") or "").strip()
        if not param:
            raise BadRequest(f"{job['param']} is required for this job")
        args = (param,)

    name = (str(data.get("name") or "").strip() or job["label"].split(" (")[0])[:60]
    common = dict(args=args, priority=priority, delay_seconds=delay, max_retries=retries)
    if interval:
        task = RecurringTask(name, job["func"], interval=interval, **common)
        task.is_io = job["io"]
    elif job["io"]:
        task = IOTask(name, job["func"], **common)
    else:
        task = Task(name, job["func"], **common)
    task.job, task.param = key, param
    return task


def create_app(scheduler, hidden_task_ids=()):
    """`hidden_task_ids`: background tasks (the metrics collector) left out of history."""
    app = Flask(__name__)
    hidden = set(hidden_task_ids)

    def find(task_id):
        task = scheduler.tasks.get(task_id)
        if task is None:
            return None, (jsonify(error="Task not found"), 404)
        return task, None

    @app.errorhandler(BadRequest)
    def bad_request(exc):
        return jsonify(error=str(exc)), 400

    @app.get("/")
    def index():
        return render_template("index.html", hostname=platform.node(),
                               workers=scheduler.num_workers)

    @app.get("/api/jobs")
    def jobs():
        return jsonify(job_list())

    @app.get("/api/stats")
    def stats():
        counts = {status.name: 0 for status in TaskStatus}
        tasks = list(scheduler.tasks.values())
        durations = []
        for task in tasks:
            counts[task.status.name] += 1
            info = task_to_json(task)
            if task.status == TaskStatus.SUCCESS and info["duration"] is not None:
                durations.append(info["duration"])
        return jsonify(
            counts=counts,
            total=len(tasks),
            stats=scheduler.get_stats(),
            workers=scheduler.get_worker_status(),
            avg_duration=round(sum(durations) / len(durations), 3) if durations else None,
        )

    @app.get("/api/system")
    def system():
        history = get_metrics_history()
        return jsonify(latest=history[-1] if history else None,
                       history=[{"time": h["time"], "cpu": h["cpu_percent"],
                                 "memory": h["memory_percent"]} for h in history],
                       processes=get_latest_processes())

    @app.get("/api/tasks")
    def list_tasks():
        status = request.args.get("status", "").upper()
        tasks = sorted(scheduler.tasks.values(), key=lambda t: t.created_at, reverse=True)
        if status:
            tasks = [t for t in tasks if t.status.name == status]
        return jsonify([task_to_json(t) for t in tasks[:200]])

    @app.get("/api/tasks/<task_id>")
    def task_detail(task_id):
        task, error = find(task_id)
        if error:
            return error
        rows = scheduler.db.get_history(task_id=task_id, limit=20)
        return jsonify(task=task_to_json(task),
                       attempts=[dict(zip(HISTORY_COLUMNS, row)) for row in rows])

    @app.post("/api/tasks")
    def create_task():
        task = build_task(request.get_json(silent=True) or {})
        scheduler.submit(task)
        return jsonify(task_to_json(task)), 201

    @app.post("/api/tasks/<task_id>/cancel")
    def cancel_task(task_id):
        task, error = find(task_id)
        if error:
            return error
        if not scheduler.cancel(task_id):
            return jsonify(error=f"Can't cancel a task that is {task.status.name.lower()}"), 409
        return jsonify(task_to_json(task))

    @app.post("/api/tasks/<task_id>/rerun")
    def rerun_task(task_id):
        task, error = find(task_id)
        if error:
            return error
        if getattr(task, "job", None) is None:
            return jsonify(error="Only tasks created from the dashboard can be re-run"), 409
        copy = build_task({"job": task.job, "param": task.param, "name": task.name,
                           "priority": PRIORITY_NAMES.get(task.priority, "medium"),
                           "max_retries": task.max_retries})
        scheduler.submit(copy)
        return jsonify(task_to_json(copy)), 201

    @app.get("/api/history")
    def history():
        names = {t.task_id: t.name for t in list(scheduler.tasks.values())}
        hidden_names = {names[i] for i in hidden if i in names}
        result = []
        for raw in scheduler.db.get_history(limit=200):
            row = dict(zip(HISTORY_COLUMNS, raw))
            if row["task_id"] not in names:          # task from an earlier run of the app
                saved = scheduler.db.get_task(row["task_id"])
                names[row["task_id"]] = saved[1] if saved else row["task_id"]
            row["name"] = names[row["task_id"]]
            if row["task_id"] in hidden or row["name"] in hidden_names:
                continue                             # skip the metrics collector
            result.append(row)
            if len(result) == 25:
                break
        return jsonify(result)

    return app
