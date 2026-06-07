"""Automatic rebuild on a schedule (in-process).

Runs build() once on startup, then every REBUILD_HOURS hours.
For production prefer a system cron / GitHub Action (see .github/workflows)
or run this alongside the API with a process manager (systemd, pm2, supervisor).

    python run_scheduler.py
"""
import os
import time

from apscheduler.schedulers.background import BackgroundScheduler

from pipeline.build_model import build

REBUILD_HOURS = float(os.environ.get("REBUILD_HOURS", "6"))


def job():
    print("\n=== scheduled rebuild ===")
    try:
        build()
    except Exception as e:
        print(f"rebuild failed: {e}")


if __name__ == "__main__":
    job()  # run immediately on start
    sched = BackgroundScheduler(timezone="Europe/Athens")
    sched.add_job(job, "interval", hours=REBUILD_HOURS, id="rebuild")
    sched.start()
    print(f"Scheduler running — rebuild every {REBUILD_HOURS}h. Ctrl+C to stop.")
    try:
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        sched.shutdown()
