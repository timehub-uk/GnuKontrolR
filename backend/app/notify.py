"""
Panel notification helper.

Usage:
    from app.notify import push
    await push(db, type="domain_created", title="New domain", message="…", details={…})

`push` saves to the DB and sends a background email to the superadmin.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

log = logging.getLogger("webpanel.notify")

SMTP_HOST    = os.getenv("SMTP_HOST", "postfix")
SMTP_PORT    = int(os.getenv("SMTP_PORT", "25"))
PANEL_DOMAIN = os.getenv("PANEL_DOMAIN", "localhost")


# ── Internal helpers ───────────────────────────────────────────────────────────

async def _get_superadmin_email(db: AsyncSession) -> str | None:
    from app.models.user import User, Role
    result = await db.execute(
        select(User.email).where(User.role == Role.superadmin).limit(1)
    )
    return result.scalar_one_or_none()


def _send_email(to: str, subject: str, html: str) -> None:
    """Fire-and-forget SMTP send (runs in a thread pool)."""
    from_addr = f"noreply@{PANEL_DOMAIN}"
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"GnuKontrolR <{from_addr}>"
    msg["To"]      = to
    msg.attach(MIMEText(html, "html"))
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as s:
            s.sendmail(from_addr, [to], msg.as_string())
        log.info("Notification email sent to %s: %s", to, subject)
    except Exception as exc:
        log.warning("Notification email failed (non-fatal): %s", exc)


def _render_email(title: str, message: str, details: dict, ts: str) -> str:
    rows = "".join(
        f'<tr><td style="padding:4px 8px;color:#94a3b8;font-size:12px;">{k}</td>'
        f'<td style="padding:4px 8px;color:#e2e8f0;font-size:12px;">{v}</td></tr>'
        for k, v in details.items()
    )
    details_block = (
        f'<table style="width:100%;border-collapse:collapse;margin-top:12px;">'
        f'<tbody>{rows}</tbody></table>'
    ) if rows else ""
    return f"""
<!DOCTYPE html>
<html>
<body style="background:#0f172a;font-family:system-ui,sans-serif;padding:24px;margin:0;">
  <div style="max-width:520px;margin:0 auto;background:#1e293b;border-radius:12px;
              padding:28px;border:1px solid #334155;">
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:20px;">
      <div style="width:34px;height:34px;background:linear-gradient(135deg,#6366f1,#8b5cf6);
                  border-radius:8px;display:flex;align-items:center;justify-content:center;
                  font-size:16px;">&#128276;</div>
      <span style="color:#e2e8f0;font-weight:700;font-size:15px;">GnuKontrolR Notification</span>
    </div>
    <h2 style="color:#f1f5f9;font-size:17px;margin:0 0 8px;">{title}</h2>
    <p style="color:#94a3b8;font-size:13px;margin:0;">{message}</p>
    {details_block}
    <p style="color:#475569;font-size:11px;margin-top:20px;border-top:1px solid #334155;
              padding-top:14px;">{ts}</p>
  </div>
</body>
</html>"""


# ── Public API ─────────────────────────────────────────────────────────────────

async def push(
    db: AsyncSession,
    *,
    type: str,
    title: str,
    message: str,
    details: dict | None = None,
) -> None:
    """
    Save a notification to the DB and send an email to the superadmin.
    Non-blocking — email is dispatched in a thread pool.
    """
    from app.models.notification import Notification

    details = details or {}
    ts      = datetime.utcnow()

    notif = Notification(
        type       = type,
        title      = title,
        message    = message,
        details    = json.dumps(details),
        is_read    = False,
        created_at = ts,
    )
    db.add(notif)
    await db.commit()

    # Fire email in background — do not await so we don't block the request
    admin_email = await _get_superadmin_email(db)
    if admin_email:
        html    = _render_email(title, message, details, ts.strftime("%Y-%m-%d %H:%M UTC"))
        subject = f"[GnuKontrolR] {title}"
        asyncio.get_event_loop().run_in_executor(
            None, _send_email, admin_email, subject, html
        )
