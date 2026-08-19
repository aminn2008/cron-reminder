"""Tests for the Telegram bot: bind flow, menu buttons, state machine, callbacks."""
import uuid

import pytest

from app import telegram_bot
from app.database import SessionLocal
from app.models import CronJob, User


@pytest.fixture
def tg_api_stub(monkeypatch):
    """Stub the Telegram messaging functions so no real network calls happen."""
    calls = []

    def fake_send(chat_id, text, reply_markup=None):
        calls.append(("sendMessage", {"chat_id": chat_id, "text": text}))
        return None

    def fake_edit(chat_id, message_id, text, reply_markup=None):
        calls.append(("editMessageText", {"chat_id": chat_id, "message_id": message_id, "text": text}))
        return None

    def fake_answer(query_id, text):
        calls.append(("answerCallbackQuery", {"callback_query_id": query_id, "text": text}))
        return None

    monkeypatch.setattr(telegram_bot, "send_message", fake_send)
    monkeypatch.setattr(telegram_bot, "edit_message", fake_edit)
    monkeypatch.setattr(telegram_bot, "answer_callback", fake_answer)
    return calls


def _bind(client, chat_id=777):
    username = "tg" + uuid.uuid4().hex[:8]
    r = client.post("/api/register", json={
        "username": username,
        "email": f"{username}@example.com",
        "password": "secret123",
    })
    assert r.status_code == 200
    r = client.post("/api/telegram/bind-code")
    assert r.status_code == 200
    code = r.json()["code"]
    telegram_bot._handle_message(chat_id, f"/bind {code}")
    return username


def _jobs_of(username):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        return db.query(CronJob).filter(CronJob.user_id == user.id).all()
    finally:
        db.close()


def test_bind_flow(client, tg_api_stub):
    username = _bind(client)
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.username == username).first()
        assert u.telegram_chat_id == "777"
    finally:
        db.close()


def test_bind_wrong_code(client, tg_api_stub):
    telegram_bot._handle_message(999, "/bind WRONGCODE")
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.telegram_chat_id == "999").first()
        assert u is None
    finally:
        db.close()


def test_menu_button_new_flow(client, tg_api_stub):
    username = _bind(client)
    telegram_bot._handle_message(777, "➕ New reminder")
    telegram_bot._handle_message(777, "30")
    telegram_bot._handle_message(777, "Coffee time")

    jobs = _jobs_of(username)
    assert len(jobs) == 1
    assert jobs[0].interval_minutes == 30
    assert jobs[0].telegram_chat_id == "777"
    assert jobs[0].name == "Coffee time"
    assert jobs[0].email_to == f"{username}@example.com"  # default email applied


def test_preset_callback_flow(client, tg_api_stub):
    username = _bind(client)
    telegram_bot._handle_callback(777, "q1", 10, "new:preset:60")
    telegram_bot._handle_message(777, "Stand up")

    jobs = _jobs_of(username)
    assert jobs[0].interval_minutes == 60


def test_custom_minutes_callback(client, tg_api_stub):
    username = _bind(client)
    telegram_bot._handle_callback(777, "q1", 10, "new:custom")
    telegram_bot._handle_message(777, "90")
    telegram_bot._handle_message(777, "Stretch")

    jobs = _jobs_of(username)
    assert jobs[0].interval_minutes == 90


def test_once_command(client, tg_api_stub):
    username = _bind(client)
    telegram_bot._handle_message(777, "/once 2099-01-01 10:00 Big meeting")
    jobs = _jobs_of(username)
    assert len(jobs) == 1
    assert jobs[0].send_once_at is not None


def test_once_past_time_rejected(client, tg_api_stub):
    username = _bind(client)
    telegram_bot._handle_message(777, "/once 2020-01-01 10:00 Old")
    assert _jobs_of(username) == []


def test_quick_new_command(client, tg_api_stub):
    username = _bind(client)
    telegram_bot._handle_message(777, "/new 120 Drink water")
    jobs = _jobs_of(username)
    assert jobs[0].interval_minutes == 120
    assert jobs[0].name == "Drink water"


def test_list_pause_delete(client, tg_api_stub):
    username = _bind(client)
    telegram_bot._handle_message(777, "/new 120 Water")
    telegram_bot._handle_message(777, "/new 1440 Vitamins")
    telegram_bot._handle_message(777, "📋 My reminders")
    assert any(m == "sendMessage" for m, _ in tg_api_stub)

    jobs = _jobs_of(username)
    j1, j2 = jobs[0], jobs[1]

    telegram_bot._handle_callback(777, "q", 10, f"job:pause:{j1.id}")
    telegram_bot._handle_callback(777, "q", 10, f"job:del:{j2.id}")

    jobs = _jobs_of(username)
    assert len(jobs) == 1
    assert jobs[0].id == j1.id
    assert jobs[0].enabled is False

    # resume via callback
    telegram_bot._handle_callback(777, "q", 10, f"job:resume:{j1.id}")
    jobs = _jobs_of(username)
    assert jobs[0].enabled is True


def test_unbound_chat_gets_help(client, tg_api_stub):
    telegram_bot._handle_message(555, "📋 My reminders")
    assert any(p[0] == "sendMessage" for p in tg_api_stub)


def test_bad_new_command_no_crash(client, tg_api_stub):
    username = _bind(client)
    telegram_bot._handle_message(777, "/new notanumber foo")
    telegram_bot._handle_message(777, "/new 5")
    assert _jobs_of(username) == []
