#!/usr/bin/env python3
\
\
\

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.email_sender import send_email


def main() -> None:
    if len(sys.argv) > 1:
        to_email = sys.argv[1]
    else:
        to_email = input("Destination email: ").strip()

    print(f"Sending to {to_email} ...")
    try:
        send_email(
            to_email=to_email,
            subject="✅ Cron Reminder test",
            text_body=(
                "Hi!\n\n"
                "This is a test email from the Cron Reminder service.\n"
                "If you received it, SMTP sending is working."
            ),
            html_body=(
                "<h3>Hi! 👋</h3>"
                "<p>This is a test email from the <b>Cron Reminder</b> service.</p>"
                "<p>If you received it, SMTP sending is working. ✅</p>"
            ),
        )
        print("✅ Email sent successfully!")
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
