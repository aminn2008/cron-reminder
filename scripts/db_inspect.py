#!/usr/bin/env python3
"""Inspect jobs & logs to trace a fired-after-delete incident."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal  # noqa: E402
from app.models import CronJob, JobLog  # noqa: E402

db = SessionLocal()
print("=== JOBS (now) ===")
for j in db.query(CronJob).order_by(CronJob.id).all():
    print(f"  #{j.id} '{j.name}' | interval={j.interval_minutes} | once={j.send_once_at} | enabled={j.enabled} | user={j.user_id} | created={j.created_at}")

print("\n=== LOGS (last 15) ===")
for l in db.query(JobLog).order_by(JobLog.id.desc()).limit(15).all():
    print(f"  #{l.id} job={l.job_id} | {l.status} | {l.executed_at} | {l.detail[:70]}")
db.close()
