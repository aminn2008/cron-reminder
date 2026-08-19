import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app import config


def send_email(
    to_email: str,
    subject: str,
    text_body: str,
    html_body: str | None = None,
) -> None:

    if not config.smtp_ready():
        raise RuntimeError(
            "SMTP is not configured! Fill in SMTP_USER and SMTP_PASSWORD in the .env file."
        )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = config.EMAIL_FROM
    msg["To"] = to_email
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    if html_body:
        msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=30) as server:
        server.ehlo()
        server.starttls()
        server.login(config.SMTP_USER, config.SMTP_PASSWORD)
        server.sendmail(config.EMAIL_FROM, [to_email], msg.as_string())
