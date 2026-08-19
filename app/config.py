import os

from dotenv import load_dotenv

load_dotenv()

# ─── SMTP (ایمیل) ───
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
EMAIL_FROM = os.getenv("EMAIL_FROM", "") or SMTP_USER

# ─── تلگرام ───
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# ─── منطقه زمانی پیش‌فرض ───
DEFAULT_TZ = os.getenv("TZ", "Asia/Tehran")


def smtp_ready() -> bool:
    return bool(SMTP_USER and SMTP_PASSWORD)
