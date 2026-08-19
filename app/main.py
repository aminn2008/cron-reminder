"""Cron Reminder — scheduled reminder service
Full API: auth, interval/one-shot job management, run-now, logs, admin panel, Telegram."""
import secrets
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from croniter import croniter
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import config
from app.auth import (
    create_session,
    get_current_user,
    hash_password,
    require_admin,
    verify_password,
)
from app.database import Base, engine, get_db
from app.models import AuthSession, CronJob, JobLog, User
from app import telegram_bot
from app.scheduler import (
    execute_job,
    humanize_interval,
    is_valid_cron,
    next_run_interval,
    next_run_time,
    shutdown,
    start,
    sync_jobs,
)

ROOT = Path(__file__).resolve().parent.parent
PAGES = ROOT / "pages"
STATIC = ROOT / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    start()
    tg_task = telegram_bot.start_on_loop()
    yield
    telegram_bot.stop_on_loop(tg_task)
    shutdown()


app = FastAPI(title="Cron Reminder", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


# ─────────────────────────── security ───────────────────────────

LOGIN_MAX_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 600
_login_attempts: dict[str, list[float]] = {}


def _check_login_rate(key: str) -> None:
    from time import time
    now = time()
    _login_attempts[key] = [t for t in _login_attempts.get(key, []) if now - t < LOGIN_WINDOW_SECONDS]
    if len(_login_attempts[key]) >= LOGIN_MAX_ATTEMPTS:
        raise HTTPException(429, "Too many failed attempts. Try again in a few minutes.")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


# ─────────────────────────── helpers ───────────────────────────

def _fmt(dt: datetime | None, tz: str) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(ZoneInfo(tz)).strftime("%Y-%m-%d %H:%M")


def user_dict(u: User) -> dict:
    return {
        "id": u.id,
        "username": u.username,
        "email": u.email,
        "is_admin": u.is_admin,
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


def job_dict(j: CronJob, owner: str | None = None) -> dict:
    if j.send_once_at:
        once_aware = j.send_once_at.replace(tzinfo=UTC).astimezone(ZoneInfo(j.timezone))
        nxt = once_aware if j.enabled else None
        label = "Once · " + once_aware.strftime("%Y-%m-%d %H:%M")
        jtype = "once"
    elif j.interval_minutes:
        nxt = next_run_interval(j.interval_minutes, j.timezone) if j.enabled else None
        label = humanize_interval(j.interval_minutes)
        jtype = "repeat"
    else:
        nxt = next_run_time(j.cron_expr, j.timezone) if j.enabled else None
        label = j.cron_expr or None
        jtype = "cron"
    return {
        "id": j.id,
        "name": j.name,
        "message": j.message,
        "type": jtype,
        "interval_minutes": j.interval_minutes,
        "interval_label": label,
        "send_once_at": j.send_once_at.isoformat() if j.send_once_at else None,
        "cron_expr": j.cron_expr,
        "timezone": j.timezone,
        "email_to": j.email_to,
        "telegram_chat_id": j.telegram_chat_id,
        "enabled": j.enabled,
        "created_at": j.created_at.isoformat() if j.created_at else None,
        "next_run": _fmt(nxt, j.timezone),
        "owner": owner,
    }


def log_dict(l: JobLog, job_name: str | None = None) -> dict:
    return {
        "id": l.id,
        "job_id": l.job_id,
        "job_name": job_name,
        "channel": l.channel,
        "status": l.status,
        "detail": l.detail,
        "executed_at": l.executed_at.astimezone(ZoneInfo(config.DEFAULT_TZ)).strftime("%Y-%m-%d %H:%M:%S")
        if l.executed_at else None,
    }


# ─────────────────────────── pages ───────────────────────────

@app.get("/")
def index():
    return FileResponse(PAGES / "index.html")


@app.get("/dashboard")
def dashboard():
    return FileResponse(PAGES / "dashboard.html")


@app.get("/admin")
def admin():
    return FileResponse(PAGES / "admin.html")


@app.get("/api/health")
def health():
    from app.scheduler import scheduler
    return {"status": "ok", "scheduler_running": scheduler.running}


# ─────────────────────────── telegram ───────────────────────────

@app.get("/api/telegram/status")
def telegram_status(user: User = Depends(get_current_user)):
    if not config.TELEGRAM_BOT_TOKEN:
        return {"configured": False, "bot_username": None}
    me = telegram_bot.get_me()
    return {
        "configured": True,
        "bot_username": me.get("username") if me else None,
    }


class TelegramTestBody(BaseModel):
    chat_id: str


@app.post("/api/telegram/test")
def telegram_test(
    body: TelegramTestBody,
    user: User = Depends(get_current_user),
):
    if not body.chat_id.strip():
        raise HTTPException(400, "Enter a Telegram chat ID first")
    try:
        telegram_bot.send_message(
            body.chat_id.strip(),
            "✅ Cron Reminder test message — Telegram delivery works!",
        )
        return {"success": True}
    except Exception as e:
        raise HTTPException(400, f"Telegram error: {e}")


@app.post("/api/telegram/bind-code")
def telegram_bind_code(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generates a 6-char code the user sends to the bot via /bind <code>."""
    code = secrets.token_hex(3).upper()
    user.bind_code = code
    user.bind_code_expires = datetime.now(UTC).replace(tzinfo=None) + timedelta(minutes=10)
    db.commit()
    return {"code": code, "expires_minutes": 10}


@app.get("/api/telegram/bind-status")
def telegram_bind_status(user: User = Depends(get_current_user)):
    return {"bound": bool(user.telegram_chat_id), "chat_id": user.telegram_chat_id}


@app.post("/api/telegram/unbind")
def telegram_unbind(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user.telegram_chat_id = None
    db.commit()
    return {"success": True}


# ─────────────────────────── auth ───────────────────────────

class RegisterBody(BaseModel):
    username: str
    email: str
    password: str


class LoginBody(BaseModel):
    username: str
    password: str


@app.post("/api/register")
def register(body: RegisterBody, db: Session = Depends(get_db)):
    username = body.username.strip()
    email = body.email.strip().lower()
    if not username or not email or not body.password:
        raise HTTPException(400, "All fields are required")
    if len(body.password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")
    exists = (
        db.query(User)
        .filter((User.username == username) | (User.email == email))
        .first()
    )
    if exists:
        raise HTTPException(400, "Username or email is already registered")

    is_first = db.query(User).count() == 0  # first user becomes admin
    user = User(
        username=username,
        email=email,
        password_hash=hash_password(body.password),
        is_admin=is_first,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_session(db, user.id)
    resp = JSONResponse({"user": user_dict(user)})
    resp.set_cookie("session", token, httponly=True, samesite="lax", max_age=60 * 60 * 24 * 30)
    return resp


@app.post("/api/login")
def login(body: LoginBody, request: Request, db: Session = Depends(get_db)):
    key = f"{request.client.host if request.client else '?'}:{body.username.strip()}"
    _check_login_rate(key)
    user = db.query(User).filter(User.username == body.username.strip()).first()
    if not user or not verify_password(body.password, user.password_hash):
        from time import time
        _login_attempts.setdefault(key, []).append(time())
        raise HTTPException(401, "Invalid username or password")
    _login_attempts.pop(key, None)
    token = create_session(db, user.id)
    resp = JSONResponse({"user": user_dict(user)})
    resp.set_cookie("session", token, httponly=True, samesite="lax", max_age=60 * 60 * 24 * 30)
    return resp


@app.post("/api/logout")
def logout(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    db.query(AuthSession).filter(AuthSession.user_id == user.id).delete()
    db.commit()
    resp = JSONResponse({"success": True})
    resp.delete_cookie("session")
    return resp


@app.get("/api/me")
def me(user: User = Depends(get_current_user)):
    return {"user": user_dict(user)}


class ChangePasswordBody(BaseModel):
    old_password: str
    new_password: str


@app.post("/api/change-password")
def change_password(
    body: ChangePasswordBody,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(body.old_password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    if len(body.new_password) < 6:
        raise HTTPException(400, "New password must be at least 6 characters")
    user.password_hash = hash_password(body.new_password)
    db.commit()
    return {"success": True}


# ─────────────────────────── jobs ───────────────────────────

class JobBody(BaseModel):
    name: str
    message: str = ""
    interval_minutes: int | None = None
    send_once_at: str | None = None
    cron_expr: str | None = None
    email_to: str | None = None
    telegram_chat_id: str | None = None
    enabled: bool = True


def _parse_send_once(raw: str) -> datetime:
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        raise HTTPException(400, "Invalid date/time format")
    aware = dt.replace(tzinfo=ZoneInfo(config.DEFAULT_TZ))
    if aware < datetime.now(ZoneInfo(config.DEFAULT_TZ)) - timedelta(seconds=30):
        raise HTTPException(400, "Send-once time must be in the future")
    return aware.astimezone(UTC).replace(tzinfo=None)


def _validate_job_body(body: JobBody, default_email: str | None = None) -> None:
    if not body.name.strip():
        raise HTTPException(400, "Reminder name is required")
    modes = sum([
        body.interval_minutes is not None,
        bool(body.send_once_at),
        bool(body.cron_expr),
    ])
    if modes == 0:
        raise HTTPException(400, "Please set a repeat interval or a send-once time")
    if modes > 1:
        raise HTTPException(400, "Choose only one mode: repeat, send once, or cron")
    if body.interval_minutes is not None and body.interval_minutes < 1:
        raise HTTPException(400, "Interval must be at least 1 minute")
    if body.cron_expr and not is_valid_cron(body.cron_expr):
        raise HTTPException(400, "Invalid cron expression (e.g., 0 9 * * *)")
    if body.send_once_at:
        _parse_send_once(body.send_once_at)
    if not body.email_to and not body.telegram_chat_id and not default_email:
        raise HTTPException(400, "At least one delivery channel (email or Telegram) is required")
    if body.email_to and "@" not in body.email_to:
        raise HTTPException(400, "Destination email is invalid")


def _apply_job_body(job: CronJob, body: JobBody) -> None:
    job.name = body.name.strip()
    job.message = body.message
    job.interval_minutes = body.interval_minutes
    job.send_once_at = _parse_send_once(body.send_once_at) if body.send_once_at else None
    job.cron_expr = body.cron_expr.strip() if body.cron_expr else ""
    job.email_to = body.email_to.strip() if body.email_to else None
    job.telegram_chat_id = body.telegram_chat_id.strip() if body.telegram_chat_id else None
    job.enabled = body.enabled


@app.get("/api/jobs")
def list_jobs(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    jobs = db.query(CronJob).filter(CronJob.user_id == user.id).order_by(CronJob.id.desc()).all()
    return {"jobs": [job_dict(j) for j in jobs]}


@app.post("/api/jobs")
def create_job(
    body: JobBody,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _validate_job_body(body, user.email)
    job = CronJob(
        user_id=user.id,
        timezone=config.DEFAULT_TZ,
    )
    _apply_job_body(job, body)
    if not job.email_to:
        job.email_to = user.email  # default to the user's registered email
    db.add(job)
    db.commit()
    db.refresh(job)
    sync_jobs()
    return {"job": job_dict(job)}


@app.put("/api/jobs/{job_id}")
def update_job(
    job_id: int,
    body: JobBody,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = db.get(CronJob, job_id)
    if not job or job.user_id != user.id:
        raise HTTPException(404, "Reminder not found")
    _validate_job_body(body, user.email)
    _apply_job_body(job, body)
    if not job.email_to:
        job.email_to = user.email  # default to the user's registered email
    db.commit()
    sync_jobs()
    return {"job": job_dict(job)}


@app.delete("/api/jobs/{job_id}")
def delete_job(
    job_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = db.get(CronJob, job_id)
    if not job or job.user_id != user.id:
        raise HTTPException(404, "Reminder not found")
    db.delete(job)
    db.commit()
    sync_jobs()
    return {"success": True}


@app.post("/api/jobs/{job_id}/toggle")
def toggle_job(
    job_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = db.get(CronJob, job_id)
    if not job or job.user_id != user.id:
        raise HTTPException(404, "Reminder not found")
    job.enabled = not job.enabled
    db.commit()
    sync_jobs()
    return {"job": job_dict(job)}


@app.post("/api/jobs/{job_id}/run-now")
def run_now(
    job_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Instant test run — no need to wait for the next interval."""
    job = db.get(CronJob, job_id)
    if not job or job.user_id != user.id:
        raise HTTPException(404, "Reminder not found")
    execute_job(job.id)
    return {"success": True}


# ─────────────────────────── logs & stats ───────────────────────────

@app.get("/api/logs")
def my_logs(
    limit: int = 30,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(JobLog, CronJob.name)
        .join(CronJob, JobLog.job_id == CronJob.id)
        .filter(CronJob.user_id == user.id)
        .order_by(JobLog.id.desc())
        .limit(min(limit, 200))
        .all()
    )
    return {"logs": [log_dict(l, name) for l, name in rows]}


@app.get("/api/stats")
def my_stats(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job_ids = [j.id for j in db.query(CronJob.id).filter(CronJob.user_id == user.id)]
    total = len(job_ids)
    enabled = (
        db.query(CronJob)
        .filter(CronJob.user_id == user.id, CronJob.enabled.is_(True))
        .count()
    )
    success = failed = 0
    if job_ids:
        success = (
            db.query(JobLog)
            .filter(JobLog.job_id.in_(job_ids), JobLog.status == "success")
            .count()
        )
        failed = (
            db.query(JobLog)
            .filter(JobLog.job_id.in_(job_ids), JobLog.status == "failed")
            .count()
        )
    return {"total": total, "enabled": enabled, "success": success, "failed": failed}


# ─────────────────────────── admin panel ───────────────────────────

@app.get("/api/admin/overview")
def admin_overview(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    users = db.query(User).count()
    jobs = db.query(CronJob).count()
    logs = db.query(JobLog).count()
    failed = db.query(JobLog).filter(JobLog.status == "failed").count()
    recent = (
        db.query(JobLog, CronJob.name, User.username)
        .join(CronJob, JobLog.job_id == CronJob.id)
        .join(User, CronJob.user_id == User.id)
        .order_by(JobLog.id.desc())
        .limit(20)
        .all()
    )
    return {
        "users": users,
        "jobs": jobs,
        "logs": logs,
        "failed": failed,
        "recent_logs": [
            {**log_dict(l, name), "username": uname} for l, name, uname in recent
        ],
    }


@app.get("/api/admin/users")
def admin_users(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.id.asc()).all()
    result = []
    for u in users:
        d = user_dict(u)
        d["job_count"] = db.query(CronJob).filter(CronJob.user_id == u.id).count()
        result.append(d)
    return {"users": result}


@app.get("/api/admin/jobs")
def admin_jobs(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = (
        db.query(CronJob, User.username)
        .join(User, CronJob.user_id == User.id)
        .order_by(CronJob.id.desc())
        .all()
    )
    return {"jobs": [job_dict(j, owner) for j, owner in rows]}
