"""Telegram bot helper.

Long-polls the bot API in a background thread. When a user messages the bot,
it replies with their chat ID so they can paste it into the dashboard.
Sending reminders to users is handled by app/scheduler.py (_send_telegram).
"""
import json
import logging
import threading
import time
import urllib.request

from app import config

log = logging.getLogger("telegram")
log.setLevel(logging.INFO)

_poll_thread: threading.Thread | None = None
_stop = False


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
    """Returns bot info (username etc.) or None if not reachable."""
    try:
        data = _api("getMe")
        if data.get("ok"):
            return data["result"]
    except Exception as e:
        log.warning("getMe failed: %s", e)
    return None


def send_message(chat_id: str, text: str) -> None:
    data = _api("sendMessage", {"chat_id": chat_id, "text": text})
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API error: {data}")


def _poll_loop() -> None:
    global _stop
    offset = 0
    while not _stop:
        try:
            data = _api("getUpdates", {"offset": offset, "timeout": 25}, timeout=35)
            if data.get("ok"):
                for upd in data.get("result", []):
                    offset = upd["update_id"] + 1
                    msg = upd.get("message") or {}
                    chat = msg.get("chat") or {}
                    chat_id = chat.get("id")
                    if chat_id is not None and msg.get("text") is not None:
                        reply = (
                            "🤖 Cron Reminder bot\n\n"
                            f"Your Telegram chat ID: <code>{chat_id}</code>\n\n"
                            "Paste this ID into the Cron Reminder dashboard "
                            "to receive your reminders here."
                        )
                        try:
                            _api(
                                "sendMessage",
                                {"chat_id": chat_id, "text": reply, "parse_mode": "HTML"},
                            )
                            log.info("replied with chat_id %s", chat_id)
                        except Exception as e:
                            log.warning("reply failed: %s", e)
        except Exception as e:
            log.warning("getUpdates failed: %s", e)
            time.sleep(5)


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
