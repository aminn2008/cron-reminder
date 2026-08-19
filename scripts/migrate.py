#!/usr/bin/env python3
"""Database migration: add missing columns (interval_minutes, send_once_at).

Usage: venv/bin/python scripts/migrate.py
"""
import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "cron_reminder.db"

conn = sqlite3.connect(DB)
cols = [row[1] for row in conn.execute("PRAGMA table_info(cron_jobs)")]
for col, ddl in [
    ("interval_minutes", "ALTER TABLE cron_jobs ADD COLUMN interval_minutes INTEGER"),
    ("send_once_at", "ALTER TABLE cron_jobs ADD COLUMN send_once_at DATETIME"),
]:
    if col not in cols:
        conn.execute(ddl)
        print(f"✅ {col} column added")
    else:
        print(f"ℹ️ {col} already exists")
conn.commit()
conn.close()
