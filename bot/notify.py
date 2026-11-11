"""
Sends emails through Gmail. Needs three secrets (see README):
  EMAIL_USER  your Gmail address
  EMAIL_PASS  a Gmail *App Password* (not your normal password)
  EMAIL_TO    where to send (can be the same address)
If they're missing, emails are saved to the outbox/ folder instead.
"""

import html
import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

OUTBOX = Path(__file__).resolve().parent.parent / "outbox"


def send(subject, body, when=None):
    subject = f"[Paper Bot] {subject}"
    user, pw, to = os.getenv("EMAIL_USER"), os.getenv("EMAIL_PASS"), os.getenv("EMAIL_TO")
    if not (user and pw and to):
        OUTBOX.mkdir(exist_ok=True)
        stamp = (when.strftime("%Y%m%d-%H%M") if when else "now")
        safe = "".join(ch if ch.isalnum() else "_" for ch in subject)[:60]
        (OUTBOX / f"{stamp}_{safe}.txt").write_text(f"{subject}\n\n{body}")
        print(f"[email -> outbox] {subject}")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"], msg["From"], msg["To"] = subject, user, to
    msg.attach(MIMEText(body, "plain", "utf-8"))
    msg.attach(MIMEText(
        "<pre style='font-family:Menlo,Consolas,monospace;font-size:13px;line-height:1.45'>"
        + html.escape(body) + "</pre>", "html", "utf-8"))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context()) as s:
            s.login(user, pw)
            s.sendmail(user, [a.strip() for a in to.split(",")], msg.as_string())
        print(f"[email sent] {subject}")
        return True
    except Exception as e:
        print(f"[email FAILED] {subject}: {e}")
        return False
