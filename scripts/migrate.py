#!/usr/bin/env python3
\
\
\

import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "cron_reminder.db"

conn = sqlite3.connect(DB)

job_cols = [row[1] for row in conn.execute("PRAGMA table_info(cron_jobs)")]
for col, ddl in [
    ("interval_minutes", "ALTER TABLE cron_jobs ADD COLUMN interval_minutes INTEGER"),
    ("send_once_at", "ALTER TABLE cron_jobs ADD COLUMN send_once_at DATETIME"),
]:
    if col not in job_cols:
        conn.execute(ddl)
        print(f"✅ cron_jobs.{col} added")
    else:
        print(f"ℹ️ cron_jobs.{col} exists")

user_cols = [row[1] for row in conn.execute("PRAGMA table_info(users)")]
for col, ddl in [
    ("bind_code", "ALTER TABLE users ADD COLUMN bind_code VARCHAR(10)"),
    ("bind_code_expires", "ALTER TABLE users ADD COLUMN bind_code_expires DATETIME"),
    ("telegram_chat_id", "ALTER TABLE users ADD COLUMN telegram_chat_id VARCHAR(50)"),
]:
    if col not in user_cols:
        conn.execute(ddl)
        print(f"✅ users.{col} added")
    else:
        print(f"ℹ️ users.{col} exists")

conn.commit()
conn.close()
