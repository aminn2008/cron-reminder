import os

from dotenv import load_dotenv

load_dotenv()


SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
EMAIL_FROM = os.getenv("EMAIL_FROM", "") or SMTP_USER


TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")


APP_URL = os.getenv("APP_URL", "https://meow.bahari.tr")


DEFAULT_TZ = os.getenv("TZ", "Asia/Tehran")

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "").strip()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")


def smtp_ready() -> bool:
    return bool(SMTP_USER and SMTP_PASSWORD)
