"""
system_tasks.py
Jobs that read REAL data from this computer using psutil
(the same numbers Task Manager / Activity Monitor show).

Topics: generators (file walking, chunked reading), file handling,
        Lock + deque for thread-safe shared state, decorators.

Every function here is a plain job the Scheduler can run.
They only READ system information; nothing is killed or deleted.
"""
import hashlib
import os
import platform
import threading
import time
from collections import deque
from datetime import datetime

import psutil

import config
from scheduler.decorators import timed

MB = 1024 * 1024
GB = 1024 * MB

# ---------------------------------------------------------------- shared state
# The recurring "collect_metrics" job writes here from a worker thread and the
# dashboard reads it from the Flask thread, so a Lock protects it.
_metrics_lock = threading.Lock()
_history = deque(maxlen=120)          # last 120 samples (~6 minutes at 3 s)
_latest_processes = []


def get_metrics_history():
    with _metrics_lock:
        return list(_history)


def get_latest_processes():
    with _metrics_lock:
        return list(_latest_processes)


# ---------------------------------------------------------------- helpers
def _root_path():
    """'/' on Linux/macOS, 'C:\\' on Windows."""
    return os.path.abspath(os.sep)


def _uptime_text():
    seconds = int(time.time() - psutil.boot_time())
    hours, rem = divmod(seconds, 3600)
    return f"{hours}h {rem // 60}m"


def _process_rows(limit=10, sort_by="memory"):
    rows = []
    for proc in psutil.process_iter(["pid", "name", "memory_info", "cpu_percent", "username"]):
        info = proc.info
        mem = info["memory_info"].rss if info["memory_info"] else 0
        rows.append({
            "pid": info["pid"],
            "name": info["name"] or "?",
            "memory_mb": round(mem / MB, 1),
            "cpu_percent": round(info["cpu_percent"] or 0.0, 1),
            "user": info["username"] or "",
        })
    key = "cpu_percent" if sort_by == "cpu" else "memory_mb"
    rows.sort(key=lambda r: r[key], reverse=True)
    return rows[:limit]


def _iter_files(folder):
    """Generator: yields (path, size) for every file under `folder`."""
    for dirpath, _dirnames, filenames in os.walk(folder):
        for name in filenames:
            path = os.path.join(dirpath, name)
            try:
                yield path, os.path.getsize(path)
            except OSError:            # file vanished or no permission -> skip it
                continue


def _iter_chunks(path, size=1024 * 1024):
    """Generator: reads a file in 1 MB chunks so big files don't fill memory."""
    with open(path, "rb") as f:
        while chunk := f.read(size):
            yield chunk


# ---------------------------------------------------------------- jobs
@timed
def system_snapshot():
    """CPU, memory, disk, network and uptime right now."""
    vm = psutil.virtual_memory()
    disk = psutil.disk_usage(_root_path())
    net = psutil.net_io_counters()
    snap = {
        "time": datetime.now().strftime("%H:%M:%S"),
        "cpu_percent": psutil.cpu_percent(interval=0.5),
        "cpu_cores": psutil.cpu_count(logical=True),
        "memory_percent": vm.percent,
        "memory_used_gb": round(vm.used / GB, 2),
        "memory_total_gb": round(vm.total / GB, 2),
        "disk_percent": disk.percent,
        "disk_free_gb": round(disk.free / GB, 1),
        "disk_total_gb": round(disk.total / GB, 1),
        "net_sent_mb": round(net.bytes_sent / MB, 1),
        "net_recv_mb": round(net.bytes_recv / MB, 1),
        "processes": len(psutil.pids()),
        "uptime": _uptime_text(),
    }
    battery = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None
    if battery is not None:
        snap["battery_percent"] = round(battery.percent)
        snap["plugged_in"] = battery.power_plugged
    return snap


def collect_metrics():
    """Recurring job: takes a snapshot + top processes and stores them for the dashboard."""
    snap = system_snapshot()
    processes = _process_rows(limit=8)
    with _metrics_lock:
        _history.append(snap)
        _latest_processes[:] = processes
    return {"cpu": snap["cpu_percent"], "memory": snap["memory_percent"]}


@timed
def top_processes(limit=10, sort_by="memory"):
    """The programs using the most memory (or CPU) right now."""
    # cpu_percent needs two readings, so take one, wait, then read again
    for proc in psutil.process_iter():
        try:
            proc.cpu_percent(None)
        except psutil.Error:
            pass
    time.sleep(0.5)
    return _process_rows(int(limit), sort_by)


@timed
def disk_report():
    """Usage of every mounted drive / partition."""
    drives = []
    for part in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except (PermissionError, OSError):      # empty CD drive, locked volume...
            continue
        if usage.total < GB:                    # skip tiny system / snap partitions
            continue
        drives.append({
            "drive": part.mountpoint,
            "type": part.fstype,
            "total_gb": round(usage.total / GB, 1),
            "free_gb": round(usage.free / GB, 1),
            "used_percent": usage.percent,
        })
    return drives


@timed
def folder_scan(path, top_n=5):
    """Counts files and total size in a folder and lists the biggest files."""
    if not os.path.isdir(path):
        raise NotADirectoryError(f"Not a folder: {path}")
    count, total, biggest = 0, 0, []
    for file_path, size in _iter_files(path):
        count += 1
        total += size
        biggest.append((size, file_path))
        if len(biggest) > top_n * 4:            # keep the list short while walking
            biggest = sorted(biggest, reverse=True)[:top_n]
    biggest = sorted(biggest, reverse=True)[:top_n]
    return {
        "folder": os.path.abspath(path),
        "files": count,
        "total_mb": round(total / MB, 2),
        "largest": [{"file": p, "size_mb": round(s / MB, 2)} for s, p in biggest],
    }


@timed
def file_checksum(path, algorithm="sha256"):
    """SHA-256 of a file - used to check that a backup matches the original."""
    if not os.path.isfile(path):
        raise FileNotFoundError(f"No such file: {path}")
    digest = hashlib.new(algorithm)
    for chunk in _iter_chunks(path):
        digest.update(chunk)
    return {"file": os.path.abspath(path), "algorithm": algorithm,
            "checksum": digest.hexdigest(), "size_mb": round(os.path.getsize(path) / MB, 3)}


@timed
def system_report():
    """Writes a plain-text health report of this computer into data/reports/."""
    snap = system_snapshot()
    procs = top_processes(limit=5)
    drives = disk_report()

    lines = [
        "SYSTEM REPORT",
        f"Generated : {datetime.now():%Y-%m-%d %H:%M:%S}",
        f"Computer  : {platform.node()} ({platform.system()} {platform.release()})",
        f"Uptime    : {snap['uptime']}",
        "",
        f"CPU       : {snap['cpu_percent']}% of {snap['cpu_cores']} cores",
        f"Memory    : {snap['memory_used_gb']} / {snap['memory_total_gb']} GB ({snap['memory_percent']}%)",
        f"Processes : {snap['processes']}",
    ]
    if "battery_percent" in snap:
        lines.append(f"Battery   : {snap['battery_percent']}%"
                     f" ({'charging' if snap['plugged_in'] else 'on battery'})")
    lines += ["", "Drives:"]
    lines += [f"  {d['drive']:<20} {d['free_gb']:>8} GB free of {d['total_gb']} GB "
              f"({d['used_percent']}% used)" for d in drives]
    lines += ["", "Top processes by memory:"]
    lines += [f"  {p['name'][:30]:<30} {p['memory_mb']:>8} MB  pid {p['pid']}" for p in procs]

    folder = os.path.join(config.DATA_DIR, "reports")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"system_report_{datetime.now():%Y%m%d_%H%M%S_%f}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path
