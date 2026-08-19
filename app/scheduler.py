"""Background scheduler: interval & one-shot jobs with APScheduler."""
import html
import json
import logging
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from croniter import croniter

from app import config
from app.database import SessionLocal
from app.email_sender import send_email
from app.models import CronJob, JobLog

log = logging.getLogger("scheduler")
log.setLevel(logging.INFO)

scheduler = BackgroundScheduler(timezone=ZoneInfo("UTC"))


def is_valid_cron(expr: str) -> bool:
    return bool(expr) and croniter.is_valid(expr)


def next_run_time(expr: str, tz: str) -> datetime | None:
    """Next execution time of a cron expression in the given timezone."""
    try:
        base = datetime.now(ZoneInfo(tz))
        return croniter(expr, base).get_next(datetime)
    except Exception:
        return None


def next_run_interval(minutes: int, tz: str) -> datetime:
    return datetime.now(ZoneInfo(tz)) + timedelta(minutes=minutes)


def humanize_interval(m: int | None) -> str | None:
    """'120' -> 'Every 2 hours'"""
    if not m or m < 1:
        return None
    months, rem = divmod(m, 43200)
    weeks, rem = divmod(rem, 10080)
    days, rem = divmod(rem, 1440)
    hours, mins = divmod(rem, 60)
    parts = []
    if months:
        parts.append(f"{months} month{'s' if months > 1 else ''}")
    if weeks:
        parts.append(f"{weeks} week{'s' if weeks > 1 else ''}")
    if days:
        parts.append(f"{days} day{'s' if days > 1 else ''}")
    if hours:
        parts.append(f"{hours} hour{'s' if hours > 1 else ''}")
    if mins:
        parts.append(f"{mins} minute{'s' if mins > 1 else ''}")
    return "Every " + (" ".join(parts) if parts else "1 minute")


def _send_telegram(chat_id: str, job: CronJob) -> None:
    if not config.TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set in .env")
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = json.dumps(
        {"chat_id": chat_id, "text": f"⏰ {job.message or job.name}"}
    ).encode()
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        if resp.status != 200:
            raise RuntimeError(f"Telegram API status: {resp.status}")


def _job_id(job) -> str:
    """Stable scheduler id — based on the job's uid, not its numeric rowid."""
    uid = getattr(job, "uid", None)
    return f"job_{uid}" if uid else f"job_{job.id}"


def execute_job(job_id: int) -> None:
    """Run a job and record the result in the logs."""
    db = SessionLocal()
    try:
        job = db.get(CronJob, job_id)
        if not job or not job.enabled:
            return

        channels = []
        if job.email_to:
            channels.append(("email", job.email_to))
        if job.telegram_chat_id and config.TELEGRAM_BOT_TOKEN:
            channels.append(("telegram", job.telegram_chat_id))

        if not channels:
            db.add(
                JobLog(
                    job_id=job.id,
                    channel="email",
                    status="skipped",
                    detail="No delivery channel configured",
                )
            )
            db.commit()
            return

        for channel, target in channels:
            try:
                if channel == "email":
                    html_body = f"""<div style="font-family:Tahoma,Arial,sans-serif;max-width:540px;margin:auto;padding:28px;border:1px solid #e2e8f0;border-radius:16px;background:#f8fafc">
<div style="font-size:40px;text-align:center">⏰</div>
<h2 style="text-align:center;color:#0f172a;margin:10px 0 6px">{html.escape(job.name)}</h2>
<p style="text-align:center;color:#334155;font-size:15px;line-height:1.7">{html.escape(job.message or 'Your reminder')}</p>
<hr style="border:none;border-top:1px solid #e2e8f0;margin:18px 0">
<p style="text-align:center;color:#94a3b8;font-size:12px;margin:0">Sent by <b>Cron Reminder</b> · meow.bahari.tr</p>
</div>"""
                    send_email(
                        to_email=target,
                        subject=f"⏰ Reminder: {job.name}",
                        text_body=job.message or "Your reminder",
                        html_body=html_body,
                    )
                else:
                    _send_telegram(target, job)
                db.add(
                    JobLog(
                        job_id=job.id,
                        channel=channel,
                        status="success",
                        detail=f"Sent successfully to {target}",
                    )
                )
            except Exception as e:
                log.warning("job %s / %s failed: %s", job.id, channel, e)
                db.add(
                    JobLog(
                        job_id=job.id,
                        channel=channel,
                        status="failed",
                        detail=str(e),
                    )
                )

        # one-shot reminders turn themselves off after firing
        if job.send_once_at:
            job.enabled = False
            log.info("job %s fired once → disabled", job.id)
        db.commit()
    finally:
        db.close()


def sync_jobs() -> None:
    """Reconcile the scheduler with the database.

    - removes ANY job that points at our executor (whatever its id scheme),
      so stale triggers for deleted jobs can never survive a sync;
    - re-adds every enabled job from the DB;
    - disables one-shot reminders whose run date has already passed
      (they must not fire late after an outage/restart).
    """
    now = datetime.now(ZoneInfo("UTC"))
    removed = 0
    for job in scheduler.get_jobs():
        func_ref = getattr(job, "func_ref", "") or ""
        if job.id.startswith("job_") or func_ref.endswith("scheduler:execute_job"):
            scheduler.remove_job(job.id)
            removed += 1
    log.info("sync_jobs: removed %d stale scheduler jobs", removed)

    db = SessionLocal()
    try:
        jobs = db.query(CronJob).filter(CronJob.enabled.is_(True)).all()
        for job in jobs:
            tz = ZoneInfo(job.timezone or "Asia/Tehran")
            try:
                if job.send_once_at:
                    aware_utc = job.send_once_at.replace(tzinfo=ZoneInfo("UTC"))
                    if aware_utc <= now:
                        # stale one-shot: never fire it late, just turn it off
                        job.enabled = False
                        log.info(
                            "job %s (%s): one-shot date %s already passed → disabled",
                            job.id, job.name, aware_utc,
                        )
                        continue
                    trigger = DateTrigger(run_date=aware_utc.astimezone(tz))
                elif job.interval_minutes:
                    start = datetime.now(tz) + timedelta(minutes=job.interval_minutes)
                    trigger = IntervalTrigger(minutes=job.interval_minutes, start_date=start)
                else:
                    trigger = CronTrigger.from_crontab(job.cron_expr, timezone=tz)
                scheduler.add_job(
                    execute_job,
                    trigger,
                    args=[job.id],
                    id=_job_id(job),
                    replace_existing=True,
                    misfire_grace_time=60,
                )
                log.info("scheduled job %s (%s)", job.id, job.name)
            except Exception as e:
                log.error("invalid config for job %s: %s", job.id, e)
        db.commit()
    finally:
        db.close()


def start() -> None:
    scheduler.start()
    sync_jobs()


def shutdown() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
