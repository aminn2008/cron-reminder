#!/usr/bin/env python3

import sqlite3
import uuid
from pathlib import Path

db_path = Path(__file__).resolve().parent.parent / "cron_reminder.db"
conn = sqlite3.connect(db_path)
cur = conn.cursor()

cols = [r[1] for r in cur.execute("PRAGMA table_info(cron_jobs)").fetchall()]

if "uid" not in cols:
    cur.execute("ALTER TABLE cron_jobs ADD COLUMN uid VARCHAR(32)")
    print("added column uid")


rows = cur.execute("SELECT id FROM cron_jobs WHERE uid IS NULL OR uid = ''").fetchall()
for (rid,) in rows:
    cur.execute("UPDATE cron_jobs SET uid = ? WHERE id = ?", (uuid.uuid4().hex, rid))
print(f"backfilled {len(rows)} rows")


cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_cron_jobs_uid ON cron_jobs (uid)")

conn.commit()
conn.close()
print("migration OK")
