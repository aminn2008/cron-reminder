"""Telegram bot with an interactive button menu.

Long-polls the Bot API in a background thread. Features:
- Reply keyboard menu: New reminder / My reminders / Help / Bind account
- Inline keyboards: interval presets, per-job pause/resume/delete buttons
- /bind <code> links a chat to a website account
- Text commands: /new, /once, /list, /pause, /resume, /delete
- Sending reminders is handled by app/scheduler.py (_send_telegram)
"""
import html
import json
import logging
import threading
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app import config
from app.database import SessionLocal
from app.models import CronJob, User
from app.scheduler import humanize_interval, sync_jobs

log = logging.getLogger("telegram")
log.setLevel(logging.INFO)

_poll_thread: threading.Thread | None = None
_stop = False

# per-chat state for the "new reminder" flow: {chat_id: {"step": ..., "minutes": ...}}
_states: dict[int, dict] = {}


# ─────────────────────────── low-level API ───────────────────────────

def _api(method: str, payload: dict | None = None, timeout: int = 20) -> dict:
    if not config.TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set in .env")
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/{method}"
    data = json.dumps(payload or {}).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def get_me() -> dict | None:
    try:
        data = _api("getMe")
        if data.get("ok"):
            return data["result"]
    except Exception as e:
        log.warning("getMe failed: %s", e)
    return None


def send_message(chat_id, text: str, reply_markup=None) -> None:
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    data = _api("sendMessage", payload)
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API error: {data}")


def edit_message(chat_id, message_id, text: str, reply_markup=None) -> None:
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "HTML",
    }
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    _api("editMessageText", payload)


def answer_callback(query_id, text: str) -> None:
    _api("answerCallbackQuery", {"callback_query_id": query_id, "text": text})


# ─────────────────────────── keyboards ───────────────────────────

def _inline(rows: list) -> dict:
    return {"inline_keyboard": rows}


MAIN_KEYBOARD = {
    "keyboard": [
        [{"text": "➕ New reminder"}, {"text": "📋 My reminders"}],
        [{"text": "❓ Help"}, {"text": "🔗 Bind account"}],
    ],
    "resize_keyboard": True,
}

NO_KEYBOARD = {"remove_keyboard": True}

PRESET_KEYBOARD = _inline([
    [
        {"text": "1 min", "callback_data": "new:preset:1"},
        {"text": "30 min", "callback_data": "new:preset:30"},
        {"text": "1 hour", "callback_data": "new:preset:60"},
    ],
    [
        {"text": "2 hours", "callback_data": "new:preset:120"},
        {"text": "1 day", "callback_data": "new:preset:1440"},
        {"text": "1 week", "callback_data": "new:preset:10080"},
    ],
    [
        {"text": "1 month", "callback_data": "new:preset:43200"},
        {"text": "Custom minutes...", "callback_data": "new:custom"},
    ],
])


def _help_text() -> str:
    return (
        "🤖 <b>Cron Reminder bot</b>\n\n"
        "Your chat ID: use it in the dashboard to receive reminders here.\n\n"
        "Commands:\n"
        "<code>/new 120 Drink water</code> — repeat reminder\n"
        "<code>/once 2026-08-20 09:00 Meeting</code> — one-shot\n"
        "<code>/list</code> — my reminders\n"
        "<code>/pause 1</code> · <code>/resume 1</code> — pause/resume\n"
        "<code>/delete 1</code> — delete\n"
        "<code>/bind CODE</code> — link this chat to your account\n\n"
        "Or just use the buttons below 👇"
    )


# ─────────────────────────── helpers ───────────────────────────

def _get_user(chat_id):
    db = SessionLocal()
    try:
        return db.query(User).filter(User.telegram_chat_id == str(chat_id)).first()
    finally:
        db.close()


def _need_bind(chat_id) -> None:
    send_message(
        chat_id,
        "🔗 This chat is not linked to an account yet.\n\n"
        "1️⃣ Open https://meow.bahari.tr → <b>Telegram</b> section\n"
        "2️⃣ Press <b>Get bind code</b>\n"
        "3️⃣ Send <code>/bind CODE</code> here",
        MAIN_KEYBOARD,
    )


def _get_job(user_id: int, job_id: int):
    db = SessionLocal()
    try:
        return (
            db.query(CronJob)
            .filter(CronJob.id == job_id, CronJob.user_id == user_id)
            .first()
        )
    finally:
        db.close()


def _create_job(chat_id, name: str, minutes: int | None = None, send_once_at=None) -> None:
    user = _get_user(chat_id)
    if not user:
        _need_bind(chat_id)
        return
    db = SessionLocal()
    try:
        job = CronJob(
            user_id=user.id,
            name=name,
            message=name,
            interval_minutes=minutes,
            send_once_at=send_once_at,
            email_to=user.email,
            telegram_chat_id=str(chat_id),
            timezone=config.DEFAULT_TZ,
        )
        db.add(job)
        db.commit()
    finally:
        db.close()
    sync_jobs()


def _render_list(user) -> tuple[str, dict | None]:
    db = SessionLocal()
    try:
        jobs = (
            db.query(CronJob)
            .filter(CronJob.user_id == user.id)
            .order_by(CronJob.id)
            .all()
        )
    finally:
        db.close()

    if not jobs:
        return "📭 No reminders yet.\n\nPress ➕ New reminder to create one!", None

    lines = ["📋 <b>Your reminders:</b>\n"]
    rows = []
    for j in jobs:
        if j.send_once_at:
            once = j.send_once_at.replace(tzinfo=UTC).astimezone(ZoneInfo(config.DEFAULT_TZ))
            label = "Once · " + once.strftime("%Y-%m-%d %H:%M")
        else:
            label = humanize_interval(j.interval_minutes) or (j.cron_expr or "?")
        status = "✅" if j.enabled else "⏸"
        lines.append(f"{j.id}. {html.escape(j.name)} — {html.escape(label)} {status}")
        rows.append([
            {
                "text": "⏸ Pause" if j.enabled else "▶️ Resume",
                "callback_data": f"job:{'pause' if j.enabled else 'resume'}:{j.id}",
            },
            {"text": "🗑 Delete", "callback_data": f"job:del:{j.id}"},
        ])
    rows.append([
        {"text": "🔄 Refresh", "callback_data": "menu:list"},
        {"text": "🏠 Menu", "callback_data": "menu:main"},
    ])
    return "\n".join(lines), _inline(rows)


# ─────────────────────────── commands ───────────────────────────

def _cmd_bind(chat_id, args) -> None:
    if not args:
        send_message(
            chat_id,
            "Usage: <code>/bind CODE</code>\nGet the code from the dashboard → Telegram section.",
        )
        return
    code = args[0].strip().upper()
    db = SessionLocal()
    try:
        now = datetime.now(UTC).replace(tzinfo=None)
        user = db.query(User).filter(User.bind_code == code).first()
        if not user or (user.bind_code_expires and user.bind_code_expires < now):
            send_message(chat_id, "❌ Invalid or expired code. Get a new one from the dashboard.")
            return
        old = db.query(User).filter(User.telegram_chat_id == str(chat_id)).first()
        if old and old.id != user.id:
            old.telegram_chat_id = None
        user.telegram_chat_id = str(chat_id)
        user.bind_code = None
        user.bind_code_expires = None
        db.commit()
        send_message(
            chat_id,
            f"✅ Linked to account <b>@{html.escape(user.username)}</b> ({html.escape(user.email)})!\n\n"
            "You can now create and manage reminders from here. Press 📋 My reminders to start.",
            MAIN_KEYBOARD,
        )
    finally:
        db.close()


def _cmd_new_quick(chat_id, args) -> None:
    if len(args) < 2 or not args[0].isdigit():
        send_message(chat_id, "Usage: <code>/new &lt;minutes&gt; &lt;name&gt;</code>\ne.g. <code>/new 120 Drink water</code>")
        return
    minutes = int(args[0])
    if minutes < 1:
        send_message(chat_id, "Minimum interval is 1 minute.")
        return
    name = " ".join(args[1:])[:120]
    _create_job(chat_id, name, minutes=minutes)
    send_message(chat_id, f"✅ Reminder created: <b>{html.escape(name)}</b> — {humanize_interval(minutes)}")


def _cmd_once(chat_id, args) -> None:
    if len(args) < 2:
        send_message(chat_id, "Usage: <code>/once YYYY-MM-DD HH:MM Name</code>\ne.g. <code>/once 2026-08-20 09:00 Meeting</code>")
        return
    try:
        dt = datetime.strptime(f"{args[0]} {args[1]}", "%Y-%m-%d %H:%M")
    except ValueError:
        send_message(chat_id, "Date format must be: YYYY-MM-DD HH:MM (e.g. 2026-08-20 09:00)")
        return
    aware = dt.replace(tzinfo=ZoneInfo(config.DEFAULT_TZ))
    if aware < datetime.now(ZoneInfo(config.DEFAULT_TZ)):
        send_message(chat_id, "⚠️ That time is in the past!")
        return
    name = " ".join(args[2:])[:120] or "Reminder"
    _create_job(chat_id, name, send_once_at=aware.astimezone(UTC).replace(tzinfo=None))
    send_message(chat_id, f"✅ One-shot reminder created: <b>{html.escape(name)}</b> — {aware.strftime('%Y-%m-%d %H:%M')}")


def _cmd_list(chat_id) -> None:
    user = _get_user(chat_id)
    if not user:
        _need_bind(chat_id)
        return
    text, kb = _render_list(user)
    send_message(chat_id, text, reply_markup=kb or MAIN_KEYBOARD)


def _cmd_toggle(chat_id, action: str, args) -> None:
    user = _get_user(chat_id)
    if not user:
        _need_bind(chat_id)
        return
    if not args or not args[0].isdigit():
        send_message(chat_id, f"Usage: /{action} &lt;id&gt;  (see /list)")
        return
    job = _get_job(user.id, int(args[0]))
    if not job:
        send_message(chat_id, "❌ Reminder not found.")
        return
    db = SessionLocal()
    try:
        db_job = db.get(CronJob, job.id)
        db_job.enabled = action == "resume"
        db.commit()
    finally:
        db.close()
    sync_jobs()
    send_message(chat_id, f"{'▶️ Resumed' if action == 'resume' else '⏸ Paused'}: <b>{html.escape(job.name)}</b>")


def _cmd_delete(chat_id, args) -> None:
    user = _get_user(chat_id)
    if not user:
        _need_bind(chat_id)
        return
    if not args or not args[0].isdigit():
        send_message(chat_id, "Usage: /delete &lt;id&gt;  (see /list)")
        return
    job = _get_job(user.id, int(args[0]))
    if not job:
        send_message(chat_id, "❌ Reminder not found.")
        return
    db = SessionLocal()
    try:
        db.delete(db.get(CronJob, job.id))
        db.commit()
    finally:
        db.close()
    sync_jobs()
    send_message(chat_id, f"🗑 Deleted: <b>{html.escape(job.name)}</b>")


def _start_new(chat_id) -> None:
    user = _get_user(chat_id)
    if not user:
        _need_bind(chat_id)
        return
    _states[chat_id] = {"step": "minutes"}
    send_message(
        chat_id,
        "⏱ How often should I remind you?\nChoose a preset below, or send minutes directly (e.g. <code>120</code> = every 2 hours):",
        PRESET_KEYBOARD,
    )


def _handle_command(chat_id, text: str) -> None:
    parts = text.split()
    cmd = parts[0].lower()
    args = parts[1:]
    if cmd in ("/start", "/help"):
        send_message(chat_id, _help_text(), MAIN_KEYBOARD)
    elif cmd == "/bind":
        _cmd_bind(chat_id, args)
    elif cmd == "/new":
        _cmd_new_quick(chat_id, args)
    elif cmd == "/once":
        _cmd_once(chat_id, args)
    elif cmd == "/list":
        _cmd_list(chat_id)
    elif cmd in ("/pause", "/resume"):
        _cmd_toggle(chat_id, cmd[1:], args)
    elif cmd == "/delete":
        _cmd_delete(chat_id, args)
    else:
        send_message(chat_id, "Unknown command — send /help")


# ─────────────────────────── message & callback handling ───────────────────────────

def _handle_message(chat_id, text: str) -> None:
    text = (text or "").strip()
    if not text:
        return

    # reply-keyboard menu labels
    if text == "➕ New reminder":
        _start_new(chat_id)
        return
    if text == "📋 My reminders":
        _cmd_list(chat_id)
        return
    if text == "❓ Help":
        send_message(chat_id, _help_text(), MAIN_KEYBOARD)
        return
    if text == "🔗 Bind account":
        send_message(
            chat_id,
            "🔗 Go to https://meow.bahari.tr → <b>Telegram</b> section, get the bind code, "
            "then send <code>/bind CODE</code> here.",
            MAIN_KEYBOARD,
        )
        return

    if text.startswith("/"):
        _handle_command(chat_id, text)
        return

    # state machine: waiting for interval / name
    state = _states.get(chat_id)
    if state and state.get("step") == "minutes":
        try:
            minutes = int(text)
        except ValueError:
            send_message(chat_id, "Please send a number in minutes (e.g. 120), or pick a preset below:", PRESET_KEYBOARD)
            return
        if minutes < 1:
            send_message(chat_id, "Minimum interval is 1 minute.")
            return
        _states[chat_id] = {"step": "name", "minutes": minutes}
        send_message(
            chat_id,
            f"⏱ Every {humanize_interval(minutes)}\n\nNow send the reminder name:",
            NO_KEYBOARD,
        )
        return

    if state and state.get("step") == "name":
        name = text[:120]
        _create_job(chat_id, name, minutes=state.get("minutes"))
        _states.pop(chat_id, None)
        send_message(
            chat_id,
            f"✅ Reminder created: <b>{html.escape(name)}</b> — {humanize_interval(state.get('minutes'))}\n\n"
            "Manage it anytime with 📋 My reminders.",
            MAIN_KEYBOARD,
        )
        return

    # anything else → help
    send_message(chat_id, _help_text(), MAIN_KEYBOARD)


def _handle_callback(chat_id, query_id, message_id, data: str) -> None:
    # answer first so the button spinner stops immediately
    try:
        answer_callback(query_id, "Done ✅")
    except Exception as e:
        log.warning("answer_callback failed: %s", e)
    try:
        if data.startswith("new:preset:"):
            minutes = int(data.split(":")[2])
            _states[chat_id] = {"step": "name", "minutes": minutes}
            edit_message(
                chat_id,
                message_id,
                f"⏱ Every {humanize_interval(minutes)}\n\nNow send the reminder name:",
                NO_KEYBOARD,
            )
        elif data == "new:custom":
            _states[chat_id] = {"step": "minutes"}
            edit_message(
                chat_id,
                message_id,
                "How often? Send minutes directly (e.g. 90 = every 1 hour 30 minutes):",
                NO_KEYBOARD,
            )
        elif data == "menu:main":
            edit_message(chat_id, message_id, _help_text())
        elif data == "menu:list":
            user = _get_user(chat_id)
            if not user:
                _need_bind(chat_id)
                return
            text, kb = _render_list(user)
            edit_message(chat_id, message_id, text, reply_markup=kb)
        elif data.startswith("job:"):
            user = _get_user(chat_id)
            if not user:
                _need_bind(chat_id)
                return
            _, action, job_id = data.split(":")
            db = SessionLocal()
            try:
                job = db.query(CronJob).filter(
                    CronJob.id == int(job_id), CronJob.user_id == user.id
                ).first()
                if job:
                    if action == "pause":
                        job.enabled = False
                    elif action == "resume":
                        job.enabled = True
                    elif action == "del":
                        db.delete(job)
                    db.commit()
            finally:
                db.close()
            sync_jobs()
            text, kb = _render_list(user)
            edit_message(chat_id, message_id, text, reply_markup=kb)
        else:
            log.warning("unknown callback data: %s", data)
    except urllib.error.HTTPError as e:
        if e.code == 400 and "not modified" in str(e).lower():
            log.info("callback edit: message not modified — ignoring")
        else:
            log.warning("callback handling failed: %s", e)
    except Exception as e:
        log.warning("callback handling failed: %s", e)


# ─────────────────────────── polling loop ───────────────────────────

def _poll_loop() -> None:
    global _stop
    offset = 0
    while not _stop:
        try:
            data = _api("getUpdates", {"offset": offset, "timeout": 25}, timeout=35)
            if data.get("ok"):
                for upd in data.get("result", []):
                    offset = upd["update_id"] + 1
                    if "message" in upd:
                        msg = upd["message"]
                        chat = msg.get("chat") or {}
                        chat_id = chat.get("id")
                        text = msg.get("text")
                        if chat_id is not None and text is not None:
                            try:
                                _handle_message(chat_id, text)
                            except Exception as e:
                                log.warning("message handling failed: %s", e)
                                try:
                                    send_message(chat_id, f"⚠️ Error: {html.escape(str(e))}")
                                except Exception:
                                    pass
                    elif "callback_query" in upd:
                        cq = upd["callback_query"]
                        chat_id = (cq.get("message") or {}).get("chat", {}).get("id")
                        query_id = cq.get("id")
                        message_id = (cq.get("message") or {}).get("message_id")
                        data = cq.get("data")
                        if chat_id is not None and data:
                            _handle_callback(chat_id, query_id, message_id, data)
        except Exception as e:
            # 409 = another long-poll is active (e.g. leftover from a restart) — back off longer
            code = getattr(e, "code", None)
            log.warning("getUpdates failed: %s", e)
            time.sleep(30 if code == 409 else 5)


def start() -> None:
    global _poll_thread, _stop
    if not config.TELEGRAM_BOT_TOKEN:
        log.info("TELEGRAM_BOT_TOKEN not set — Telegram bot disabled")
        return
    _stop = False
    _poll_thread = threading.Thread(target=_poll_loop, daemon=True, name="telegram-bot")
    _poll_thread.start()
    log.info("Telegram bot polling started")


def stop() -> None:
    global _stop
    _stop = True
