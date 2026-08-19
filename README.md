# ⏰ Cron Reminder

A full-stack scheduled reminder service — users create **repeating** or **one-shot** reminders and receive them via **email** (SMTP) or **Telegram**. Built with FastAPI, SQLAlchemy and APScheduler, deployed behind nginx with HTTPS.

**Live demo:** https://meow.bahari.tr

---

## ✨ Features

- 🔐 **Authentication** — sign up / log in with PBKDF2-hashed passwords, secure session cookies, login rate limiting (5 attempts / 10 min)
- ⏱️ **Two scheduling modes**
  - `Repeat` — every 1 minute → 1 month (presets), or any custom interval (type `120` → "Every 2 hours")
  - `Send once` — fires at a chosen date/time, then turns itself off
- 📧 **Email delivery** via SMTP (Gmail & others), with a styled HTML template
- 📱 **Telegram delivery** (optional) — set a bot token + chat ID
- 🧑‍💼 **Admin panel** — overview stats, all users, all reminders, recent logs
- 📄 **Execution logs** — success / failure per channel, live-refreshing dashboard (every 10 s)
- 🌍 **Timezone-aware** — reminders stored in UTC, displayed in `Asia/Tehran` (configurable via `TZ`)
- ⚡ **Instant test run** — "Run now" button, no need to wait for the next fire
- 🛡️ **Security headers** (`X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`)

## 🧱 Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11 · FastAPI |
| Scheduler | APScheduler (IntervalTrigger / DateTrigger) + croniter |
| Database | SQLite · SQLAlchemy 2.0 |
| Frontend | Vanilla HTML/CSS/JS (dark glassmorphism UI, RTL-ready) |
| Deployment | uvicorn · nginx reverse proxy · Let's Encrypt (Certbot) · systemd |

## 📁 Project Structure

```
cron-reminder/
├── app/
│   ├── main.py          # FastAPI app — auth, jobs, logs, admin API
│   ├── scheduler.py     # APScheduler background engine
│   ├── email_sender.py  # SMTP sending
│   ├── auth.py          # password hashing + session tokens
│   ├── models.py        # SQLAlchemy models (User, CronJob, JobLog, Session)
│   └── database.py      # engine / session (DATABASE_URL configurable)
├── pages/               # index.html, dashboard.html, admin.html
├── static/              # style.css + JS (common, auth, dashboard, admin)
├── scripts/             # migrate, create_admins, test_email, backup_db
├── tests/               # pytest suite (15 tests)
└── requirements.txt
```

## 🚀 Quick Start (local)

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt

cp .env.example .env      # fill in SMTP credentials
venv/bin/python scripts/migrate.py

venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open http://localhost:8000 — **the first registered user becomes the admin**.

### SMTP (Gmail)

1. Enable **2-Step Verification** on your Google account
2. Create an **App Password** at https://myaccount.google.com/apppasswords
3. Put it in `.env`:

```ini
SMTP_USER=you@gmail.com
SMTP_PASSWORD=xxxx xxxx xxxx xxxx
```

Test: `venv/bin/python scripts/test_email.py you@example.com`

### Telegram (optional)

Create a bot with [@BotFather](https://t.me/BotFather), then add to `.env`:

```ini
TELEGRAM_BOT_TOKEN=123456:ABC...
```

Each reminder can then also be delivered to a Telegram `chat_id`.

## 🧪 Tests

```bash
venv/bin/pip install -r requirements-dev.txt
venv/bin/python -m pytest tests/ -v
```

The suite uses an isolated temporary database and stubs email sending — no real emails are sent.

## 🔌 API Overview

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/register` | create account (first user = admin) |
| POST | `/api/login` / `/api/logout` | session auth |
| GET | `/api/me` | current user |
| POST | `/api/change-password` | update password |
| GET/POST | `/api/jobs` | list / create reminders |
| PUT/DELETE | `/api/jobs/{id}` | update / delete |
| POST | `/api/jobs/{id}/toggle` | pause / resume |
| POST | `/api/jobs/{id}/run-now` | instant test run |
| GET | `/api/logs` · `/api/stats` | logs & stats |
| GET | `/api/admin/*` | admin panel (admin only) |

Interactive docs (Swagger UI): `GET /docs`

## 🐳 Deployment (production)

The production setup runs the app as a **systemd service** bound to `127.0.0.1:8000`, behind **nginx** with a Let's Encrypt certificate:

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
# nginx server block (HTTP → HTTPS handled by certbot)
server {
    listen 443 ssl;
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

## 🛠️ Admin Accounts

Reserved admin accounts (`admin`, `owner`, `root`) are created with random passwords via:

```bash
venv/bin/python scripts/create_admins.py
```

The usernames stay reserved — nobody else can register with them.

## 💾 Backups

`scripts/backup_db.sh` copies the database and `.env` to `/root/backups/cron-reminder` (keeps the last 14). Install as a daily cron job:

```cron
0 3 * * * /root/cron-reminder/scripts/backup_db.sh >> /var/log/cron-reminder-backup.log 2>&1
```
