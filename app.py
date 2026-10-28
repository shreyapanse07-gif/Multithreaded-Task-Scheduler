"""
app.py
Starts the scheduler ONCE, then the web dashboard.

    python app.py                 -> http://127.0.0.1:5000
    python app.py --workers 6 --port 8000

The Flask reloader is turned off on purpose: with it on, Flask imports this
file twice and we would get two schedulers and two sets of worker threads.
"""
import argparse
import logging

import config
from scheduler import Scheduler, RecurringTask
from scheduler.logger import get_logger
from tasks.system_tasks import collect_metrics
from dashboard import create_app

logger = get_logger("app")
METRICS_EVERY = 3          # seconds between system samples for the charts


def main():
    parser = argparse.ArgumentParser(description="Task scheduler web dashboard")
    parser.add_argument("--workers", type=int, default=config.NUM_WORKERS)
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()

    # Werkzeug logs every request; the page polls every 2 s, so keep it quiet.
    logging.getLogger("werkzeug").setLevel(logging.WARNING)

    scheduler = Scheduler(num_workers=args.workers)
    scheduler.start()

    # A recurring job feeds the CPU / memory charts. High priority so the
    # charts keep updating even when the workers are busy.
    collector = RecurringTask("Collect system metrics", collect_metrics,
                              interval=METRICS_EVERY, priority=config.PRIORITY_HIGH)
    scheduler.submit(collector)

    app = create_app(scheduler, hidden_task_ids=[collector.task_id])
    print(f"\n  Dashboard: http://127.0.0.1:{args.port}   (Ctrl+C to stop)\n")
    try:
        # 127.0.0.1 = only this computer can open it
        app.run(host="127.0.0.1", port=args.port, debug=False,
                use_reloader=False, threaded=True)
    finally:
        scheduler.shutdown()
        logger.info("Dashboard stopped")


if __name__ == "__main__":
    main()
