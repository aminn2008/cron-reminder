import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app import scheduler as sched
from app.database import SessionLocal
from app.models import CronJob, User


@pytest.fixture
def sched_user(client):

    db = SessionLocal()
    try:
        u = User(
            username="sched" + uuid.uuid4().hex[:8],
            email=uuid.uuid4().hex[:8] + "@example.com",
            password_hash="x",
            telegram_chat_id="424242",
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return u
    finally:
        db.close()


def _make_job(user, minutes=60, enabled=True, **kw):
    db = SessionLocal()
    try:
        j = CronJob(
            user_id=user.id,
            name="Test job",
            message="hi",
            interval_minutes=minutes,
            enabled=enabled,
            **kw,
        )
        db.add(j)
        db.commit()
        db.refresh(j)
        return j.id
    finally:
        db.close()


def _scheduled_job_ids():
    return {j.id for j in sched.scheduler.get_jobs()}


def _scheduled_with(job_id):

    return any(list(j.args or []) == [job_id] for j in sched.scheduler.get_jobs())


def _delete_job(job_id):
    db = SessionLocal()
    try:
        job = db.get(CronJob, job_id)
        db.delete(job)
        db.commit()
    finally:
        db.close()


def test_deleted_job_is_removed_from_scheduler(sched_user):

    job_id = _make_job(sched_user)
    sched.sync_jobs()
    assert _scheduled_with(job_id)

    _delete_job(job_id)
    sched.sync_jobs()

    assert not _scheduled_with(job_id)


def test_disabled_job_is_removed_from_scheduler(sched_user):
    job_id = _make_job(sched_user)
    sched.sync_jobs()
    assert _scheduled_with(job_id)

    db = SessionLocal()
    try:
        db.get(CronJob, job_id).enabled = False
        db.commit()
    finally:
        db.close()
    sched.sync_jobs()

    assert not _scheduled_with(job_id)


def test_stale_once_job_disabled_not_scheduled(sched_user):

    past = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=5)
    job_id = _make_job(sched_user, minutes=None, send_once_at=past)
    sched.sync_jobs()

    assert not _scheduled_with(job_id)
    db = SessionLocal()
    try:
        assert db.get(CronJob, job_id).enabled is False
    finally:
        db.close()


def test_future_once_job_stays_scheduled(sched_user):
    future = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=5)
    job_id = _make_job(sched_user, minutes=None, send_once_at=future)
    sched.sync_jobs()

    assert _scheduled_with(job_id)


def test_job_ids_use_uid_not_rowid(sched_user):

    job_id = _make_job(sched_user)
    sched.sync_jobs()

    db = SessionLocal()
    try:
        uid = db.get(CronJob, job_id).uid
    finally:
        db.close()
    assert any(j.id == f"job_{uid}" for j in sched.scheduler.get_jobs())
    assert not any(j.id == f"job_{job_id}" for j in sched.scheduler.get_jobs())
