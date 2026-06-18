"""Transactional email — verification + password reset (BUILD_PLAN §5.2).

Provider-agnostic SMTP. Locally this points at Mailpit (host=mailpit, port=1025,
no auth/TLS) and you read the mail at http://localhost:8025; in prod point SMTP_*
at any real provider (set SMTP_USER/SMTP_PASSWORD/SMTP_STARTTLS).

If SMTP is not configured (no SMTP_HOST) the sender is a logged no-op so signup
still succeeds — the link is logged, and returned in the API response when DEBUG
is on. Sending never raises into the request path: a failure is logged and the
caller is told whether it went out, so a broken mailer can't break signup.
"""
from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
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


async def _send(to: str, subject: str, text: str, html: str) -> bool:
    """Send one email. Returns True if handed to SMTP, False if disabled/failed.
    Logs (once, at the call site) whether email is wired up — config must be
    provably live (playbook 2.4)."""
    if not settings.email_enabled:
        log.warning("email disabled (SMTP_HOST unset) — skipped %r to %s", subject, to)
        return False
    try:
        # smtplib is blocking; keep it off the event loop.
        await asyncio.to_thread(_send_sync, to, subject, text, html)
        log.info("sent %r to %s via %s:%s", subject, to,
                 settings.smtp_host, settings.smtp_port)
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
