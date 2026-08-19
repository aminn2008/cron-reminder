#!/bin/bash
# Daily backup of the Cron Reminder database + .env
# Retention: keep the last 14 backups.
set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-/root/backups/cron-reminder}"
STAMP="$(date +%Y-%m-%d_%H-%M-%S)"

mkdir -p "$BACKUP_DIR"

if [ -f "$PROJECT_DIR/cron_reminder.db" ]; then
    cp "$PROJECT_DIR/cron_reminder.db" "$BACKUP_DIR/cron_reminder-$STAMP.db"
fi
if [ -f "$PROJECT_DIR/.env" ]; then
    cp "$PROJECT_DIR/.env" "$BACKUP_DIR/env-$STAMP"
fi

# rotate: keep only the 14 most recent files
ls -1t "$BACKUP_DIR" | tail -n +15 | while read -r f; do
    rm -f "$BACKUP_DIR/$f"
done

echo "✅ backup done: $BACKUP_DIR ($STAMP)"
