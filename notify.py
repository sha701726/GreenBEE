"""
Notifications: hamesha in-app (DB) mein save hoti hain. Email OPTIONAL hai aur free SMTP
(jaise Gmail app-password) se jaati hai - SMTP_HOST set na ho to email skip, kuch paid nahi lagta.
Env: SMTP_HOST, SMTP_PORT(587), SMTP_USER, SMTP_PASSWORD, SMTP_FROM, ADMIN_EMAIL
"""
import logging
import os
import smtplib
import threading
from email.message import EmailMessage

import db

log = logging.getLogger("greenbee.notify")


def _send_email(to, subject, body):
    host = os.getenv("SMTP_HOST", "").strip()
    if not host or not to:
        return
    try:
        msg = EmailMessage()
        msg["From"] = os.getenv("SMTP_FROM") or os.getenv("SMTP_USER", "")
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "587")), timeout=10) as s:
            s.starttls()
            if os.getenv("SMTP_USER"):
                s.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD", ""))
            s.send_message(msg)
    except Exception:  # email fail hone se kaam nahi rukna chahiye
        log.exception("Email send failed")


def email_async(to, subject, body):
    if os.getenv("SMTP_HOST", "").strip() and to:
        threading.Thread(target=_send_email, args=(to, subject, body), daemon=True).start()


def notify(user_type, user_id, message, link=None, email=None):
    """user_type: 'Customer' ya 'Companion'. Kabhi exception raise nahi karta."""
    try:
        db.add_notification(user_type, user_id, message[:255], link)
        email_async(email, "GreenBEE update", message)
    except Exception:
        log.exception("Notification failed")


def notify_admin(subject, body):
    email_async(os.getenv("ADMIN_EMAIL", "").strip(), subject, body)
