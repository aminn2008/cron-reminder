# ⏰ Cron Reminder

A full-stack scheduled reminder service: users create **repeating** or **one-shot** reminders and receive them via **email** (SMTP) or **Telegram**. Built with FastAPI, APScheduler and aiogram, with a Persian RTL web dashboard.

**Live:** http://meow.bahari.tr

---

## ✨ Features

- 🔐 **Accounts** — PBKDF2-hashed passwords (200k iterations), secure session cookies, login rate limiting (5 attempts / 10 min)
- ⏱️ **Two scheduling modes**
  - *Repeat* — any interval from 1 minute to months (presets + custom)
  - *Send once* — fires at a chosen time, then turns itself off
- 📧 **Email delivery** — SMTP (Gmail & others) with a styled HTML template
- 📱 **Telegram delivery** — a full aiogram bot: interactive buttons, per-job pause/resume/delete, and a guided flow (interval → message → channel)
- 🌐 **Telegram Web App (Mini App)** — "Open App" button in the bot; auto-login via HMAC-verified `initData`, no username/password needed
- 🧑‍💼 **Admin panel** — users, reminders, execution logs and stats
- 📄 **Execution logs** — success / failure per channel, live dashboard
- 🌍 **Timezone-aware** — stored in UTC, displayed in `Asia/Tehran` (configurable)
- ⚡ **Run now** — test a reminder instantly without waiting for its next fire
- 🛡️ **Scheduler safety** — uid-based job ids (rowid-reuse safe), full scheduler/DB reconciliation on every change, stale one-shots auto-disabled, deleted jobs can never fire
- 📝 **File logging** — rotating `logs/app.log` traces every schedule/delete/fire

## 📸 Screenshots

| | |
|---|---|
| ![Dashboard](screenshots/dashboard.png) | ![New reminder](screenshots/create-modal.png) |
| ![Login](screenshots/login.png) | ![Admin panel](screenshots/admin.png) |

## 🧱 Tech Stack

- **Backend:** Python 3.11 · FastAPI · SQLAlchemy 2.0 · APScheduler (interval/date triggers + croniter)
- **Bot:** aiogram 3 (async, runs on the app's event loop)
- **Database:** SQLite (file-based, `DATABASE_URL`-configurable — PostgreSQL-ready via SQLAlchemy)
- **Frontend:** vanilla HTML/CSS/JS, dark RTL UI
- **Deployment:** uvicorn · systemd · nginx reverse proxy

## 📁 Project Structure

```
cron-reminder/
├── app/
│   ├── main.py          # FastAPI app — auth, jobs, logs, admin, Telegram API
│   ├── telegram_bot.py  # aiogram bot + Web App login (HMAC initData)
│   ├── scheduler.py     # APScheduler engine + channel delivery
│   ├── auth.py          # password hashing, sessions, admin seeding
│   ├── email_sender.py  # SMTP sending
│   ├── models.py        # User / CronJob / JobLog (+ stable uid)
│   ├── config.py        # .env config
│   ├── database.py      # engine / session
│   └── logging_setup.py # rotating file logging
├── pages/               # index (login), dashboard, admin — RTL Persian
├── static/              # style.css + auth/dashboard/admin/common JS
├── scripts/             # migrate, create_admins, test_email, backup_db
├── tests/               # 34 pytest tests (isolated temp DB, no real emails)
├── requirements.txt
└── .env.example
```

## 🚀 Quick Start

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt

cp .env.example .env      # fill in your credentials (SMTP / Telegram / admin)
venv/bin/python scripts/migrate.py

venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open http://localhost:8000

## 👑 Admin Account

Set these in `.env` — the account is **created automatically on backend start** (idempotent: skipped if it already exists):

```ini
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your-strong-password
```

If they are left empty, the **first registered user** becomes admin instead.

## 📧 Email (Gmail)

1. Enable **2-Step Verification** on the Google account
2. Create an **App Password** at https://myaccount.google.com/apppasswords
3. Put it in `.env`:

```ini
SMTP_USER=you@gmail.com
SMTP_PASSWORD=xxxx xxxx xxxx xxxx
```

Test: `venv/bin/python scripts/test_email.py you@example.com`

## 📱 Telegram

1. Create a bot via [@BotFather](https://t.me/BotFather) and set its token in `.env`:

```ini
TELEGRAM_BOT_TOKEN=123456:ABC...
APP_URL=https://your-domain.com
```

2. In the dashboard, generate a **bind code** and send `/bind CODE` to the bot to link your chat
3. Reminders can then be delivered to email, Telegram, or both — and the bot's **🌐 Open App** button opens the dashboard with automatic login

## 🧪 Tests

```bash
venv/bin/pip install -r requirements-dev.txt
venv/bin/python -m pytest tests/ -q
```

The suite uses an isolated temporary database and never sends real messages.

## 🔌 API Overview

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/register` | create account |
| POST | `/api/login` · `/api/logout` | session auth |
| GET | `/api/me` | current user |
| POST | `/api/change-password` | update password |
| GET/POST | `/api/jobs` | list / create reminders |
| PUT/DELETE | `/api/jobs/{id}` | update / delete |
| POST | `/api/jobs/{id}/toggle` | pause / resume |
| POST | `/api/jobs/{id}/run-now` | instant test run |
| GET | `/api/logs` · `/api/stats` | logs & stats |
| GET | `/api/telegram/status` · `/bind-code` · `/bind-status` | Telegram linking |
| POST | `/api/telegram/webapp-login` | Web App auto-login (HMAC) |
| GET | `/api/admin/*` | admin panel (admin only) |

Interactive docs (Swagger UI): `GET /docs`

## 🐳 Deployment

The app runs as a **systemd service** bound to `127.0.0.1:8000`, behind nginx:

```ini
# /etc/systemd/system/cron-reminder.service
[Unit]
Description=Cron Reminder web app
After=network.target

[Service]
Type=simple
WorkingDirectory=/root/cron-reminder
ExecStart=/root/cron-reminder/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

```nginx
# nginx server block
server {
    listen 80;
    server_name meow.bahari.tr;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## 💾 Backups

`scripts/backup_db.sh` copies the database and `.env` to `/root/backups/cron-reminder` (keeps the last 14). Install as a daily cron job:

```cron
0 3 * * * /root/cron-reminder/scripts/backup_db.sh >> /var/log/cron-reminder-backup.log 2>&1
```
