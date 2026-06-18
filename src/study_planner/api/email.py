"""Transactional email — verification + password reset (BUILD_PLAN §5.2).

Two transports, picked by config:
  - RESEND_API_KEY set  -> send over HTTPS via the Resend API. Use this on hosts
    that block outbound SMTP (Render's free tier makes smtp.gmail.com:587
    unreachable -> "[Errno 101] Network is unreachable"). HTTPS is always allowed.
  - else SMTP_HOST set   -> classic SMTP. Locally this is Mailpit (host=mailpit,
    port=1025, no auth/TLS), read at http://localhost:8025.

If neither is configured the sender is a logged no-op so signup still succeeds —
the link is logged, and returned in the API response when DEBUG is on. Sending
never raises into the request path: a failure is logged and the caller is told
whether it went out, so a broken mailer can't break signup.
"""
from __future__ import annotations

import asyncio
import json
import logging
import smtplib
import ssl
import urllib.error
import urllib.request
from email.message import EmailMessage

from study_planner.api.config import settings

log = logging.getLogger("study_planner.email")


def _verify_link(token: str) -> str:
    return f"{settings.app_base_url.rstrip('/')}/verify?token={token}"


def _reset_link(token: str) -> str:
    return f"{settings.app_base_url.rstrip('/')}/reset?token={token}"


def _send_sync(to: str, subject: str, text: str, html: str) -> None:
    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")

    # Two TLS modes: implicit SSL from connect (port 465, SMTP_SSL=1) or STARTTLS
    # upgrade on a plaintext port (587, SMTP_STARTTLS=1). Mailpit uses neither.
    if settings.smtp_ssl:
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port,
                              timeout=10, context=ctx) as smtp:
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)
        return

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
        if settings.smtp_starttls:
            smtp.starttls(context=ssl.create_default_context())
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg)


def _send_resend(to: str, subject: str, text: str, html: str) -> None:
    """POST one email to the Resend API over HTTPS. Blocking (urllib) — run it in
    a thread. Raises with the response body on a non-2xx so the cause is logged."""
    payload = json.dumps({
        "from": settings.smtp_from,   # must be a Resend-verified sender/domain
        "to": [to],
        "subject": subject,
        "text": text,
        "html": html,
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={
            "Authorization": f"Bearer {settings.resend_api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"Resend API {e.code}: {body}") from e


async def _send(to: str, subject: str, text: str, html: str) -> bool:
    """Send one email. Returns True if handed to a transport, False if
    disabled/failed. Logs (once, at the call site) whether email is wired up —
    config must be provably live (playbook 2.4)."""
    if settings.resend_api_key:
        transport, label = _send_resend, "resend"
    elif settings.smtp_host:
        transport, label = _send_sync, f"{settings.smtp_host}:{settings.smtp_port}"
    else:
        log.warning("email disabled (no RESEND_API_KEY or SMTP_HOST) — "
                    "skipped %r to %s", subject, to)
        return False
    try:
        # Both transports block; keep them off the event loop.
        await asyncio.to_thread(transport, to, subject, text, html)
        log.info("sent %r to %s via %s", subject, to, label)
        return True
    except Exception as e:  # never break the request because mail failed
        log.error("email send failed (%r to %s): %s", subject, to, e)
        return False


async def send_verification_email(to: str, token: str) -> bool:
    link = _verify_link(token)
    text = (f"Welcome to Study Planner!\n\n"
            f"Confirm your email to start creating plans:\n{link}\n\n"
            f"This link expires in 24 hours. If you didn't sign up, ignore this email.")
    html = (f'<p>Welcome to <b>Study Planner</b>!</p>'
            f'<p>Confirm your email to start creating plans:</p>'
            f'<p><a href="{link}">Verify my email</a></p>'
            f'<p style="color:#888;font-size:12px">This link expires in 24 hours. '
            f'If you didn\'t sign up, ignore this email.</p>')
    return await _send(to, "Verify your email", text, html)


async def send_password_reset_email(to: str, token: str) -> bool:
    link = _reset_link(token)
    text = (f"Reset your Study Planner password:\n{link}\n\n"
            f"This link expires in 1 hour. If you didn't request this, ignore it.")
    html = (f'<p>Reset your <b>Study Planner</b> password:</p>'
            f'<p><a href="{link}">Choose a new password</a></p>'
            f'<p style="color:#888;font-size:12px">This link expires in 1 hour. '
            f'If you didn\'t request this, ignore this email.</p>')
    return await _send(to, "Reset your password", text, html)
