"""
Multi-Factor Authentication (TOTP) management.

Endpoints:
  POST /api/mfa/enroll      — generate TOTP secret + QR code (base64 PNG)
  POST /api/mfa/verify      — verify TOTP code to activate device, get recovery codes
  GET  /api/mfa/devices     — list registered MFA devices
  DELETE /api/mfa/devices/{id} — remove an MFA device
  POST /api/mfa/challenge   — generate a one-time challenge code for login
"""
import base64
import io
import json
import logging
import os
import secrets
from datetime import datetime, timezone
from typing import Optional

import pyotp
import qrcode
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, hash_password, verify_password
from app.database import get_db
from app.models.mfa_device import MFADevice
from app.models.user import User

log = logging.getLogger("webpanel")
router = APIRouter(prefix="/api/mfa", tags=["mfa"])


# ── QR code generation with embedded logo ────────────────────────────────────

def _make_qr_with_logo(data: str) -> "Image.Image":
    """Generate a QR code image with the GnuKontrolR logo centred on it."""
    from PIL import Image, ImageDraw

    # Generate base QR (no logo yet, high error correction to survive overlay)
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=6,
        border=2,
    )
    qr.add_data(data)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGBA")

    # Load logo SVG — convert to PNG via cairosvg if available, else fallback
    logo_path = os.path.join(os.path.dirname(__file__), "..", "static", "gnukontrolr-logo.svg")
    logo = None
    try:
        import cairosvg
        logo_png = cairosvg.svg2png(url=logo_path)
        logo = Image.open(io.BytesIO(logo_png)).convert("RGBA")
    except ImportError:
        # Fallback: draw a simple gradient circle placeholder
        logo_size = int(qr_img.size[0] * 0.22)
        logo = Image.new("RGBA", (logo_size, logo_size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(logo)
        draw.ellipse(
            [0, 0, logo_size, logo_size],
            fill=(99, 102, 241, 230),  # indigo-500
        )
        # Draw a simplified "G" shape
        cx, cy = logo_size / 2, logo_size / 2
        r = logo_size * 0.3
        draw.ellipse(
            [cx - r, cy - r, cx + r, cy + r],
            outline="white", width=max(2, logo_size // 10),
        )
    except Exception:
        logo = None

    if logo is not None:
        # Resize logo to ~22% of QR size
        logo_size = int(qr_img.size[0] * 0.22)
        logo = logo.resize((logo_size, logo_size), Image.LANCZOS)

        # Create white rounded background behind logo for contrast
        bg_size = int(logo_size * 1.3)
        bg = Image.new("RGBA", (bg_size, bg_size), (255, 255, 255, 0))
        from PIL import ImageDraw as _ID
        _draw = _ID.Draw(bg)
        _draw.rounded_rectangle(
            [0, 0, bg_size, bg_size],
            radius=bg_size // 5,
            fill=(255, 255, 255, 240),
        )

        # Position logo centred on QR
        qr_w, qr_h = qr_img.size
        bg_x = (qr_w - bg_size) // 2
        bg_y = (qr_h - bg_size) // 2
        qr_img.paste(bg, (bg_x, bg_y), bg)

        logo_x = (qr_w - logo_size) // 2
        logo_y = (qr_h - logo_size) // 2
        qr_img.paste(logo, (logo_x, logo_y), logo)

    return qr_img


class EnrollResponse(BaseModel):
    secret: str
    uri: str
    device_id: int
    qrcode_b64: str
    # M8: expected_code intentionally omitted — never leak current TOTP code


class VerifyRequest(BaseModel):
    device_id: int
    code: str


class VerifyResponse(BaseModel):
    ok: bool
    recovery_codes: list[str] = []


class DeviceResponse(BaseModel):
    id: int
    name: str
    is_active: bool
    last_used: Optional[str] = None
    created_at: str


@router.post("/enroll")
async def enroll_mfa(
    device_name: str = "default",
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a new TOTP secret, provisioning URI, and QR code image."""
    secret = pyotp.random_base32()
    issuer = os.environ.get("PANEL_DOMAIN", "GnuKontrolR")
    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(
        name=current.email or current.username,
        issuer_name=issuer,
    )

    # Generate QR code as base64 PNG with embedded GnuKontrolR logo
    qr_img = _make_qr_with_logo(uri)
    buf = io.BytesIO()
    qr_img.save(buf, format="PNG")
    qrcode_b64 = base64.b64encode(buf.getvalue()).decode()

    device = MFADevice(
        user_id=current.id,
        name=device_name,
        secret=secret,
        is_active=False,
    )
    db.add(device)
    await db.commit()
    await db.refresh(device)

    # M8: Do NOT return expected_code — never leak current TOTP code to client
    return EnrollResponse(
        secret=secret,
        uri=uri,
        device_id=device.id,
        qrcode_b64=qrcode_b64,
    )


@router.post("/verify")
async def verify_mfa(
    body: VerifyRequest,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Verify a TOTP code to activate an MFA device and generate recovery codes."""
    device = await db.get(MFADevice, body.device_id)
    if not device or device.user_id != current.id:
        raise HTTPException(404, "Device not found")
    if device.is_active:
        raise HTTPException(400, "Device already activated")

    totp = pyotp.TOTP(device.secret, digest=device.algorithm, digits=device.digits, interval=device.period)
    if not totp.verify(body.code, valid_window=1):
        raise HTTPException(400, "Invalid verification code. Try a fresh code from your authenticator app.")

    device.is_active = True
    device.last_used = datetime.now(timezone.utc)

    # Generate 8 recovery codes (16-char hex each), store hashed on user
    raw_codes = []
    hashed_codes = []
    for _ in range(8):
        code = secrets.token_hex(8)
        raw_codes.append(code)
        hashed_codes.append(hash_password(code))

    current.recovery_codes_hash = json.dumps(hashed_codes)
    current.mfa_enabled = True
    await db.commit()

    return VerifyResponse(ok=True, recovery_codes=raw_codes)


@router.get("/devices")
async def list_devices(
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all MFA devices for the current user."""
    result = await db.execute(
        select(MFADevice).where(MFADevice.user_id == current.id)
    )
    devices = result.scalars().all()
    return [
        DeviceResponse(
            id=d.id,
            name=d.name,
            is_active=d.is_active,
            last_used=d.last_used.isoformat() if d.last_used else None,
            created_at=d.created_at.isoformat(),
        )
        for d in devices
    ]


@router.delete("/devices/{device_id}", status_code=204)
async def remove_device(
    device_id: int,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove an MFA device."""
    device = await db.get(MFADevice, device_id)
    if not device or device.user_id != current.id:
        raise HTTPException(404, "Device not found")
    await db.delete(device)
    # If no more active devices, disable MFA
    remaining = await db.execute(
        select(MFADevice).where(
            MFADevice.user_id == current.id,
            MFADevice.is_active == True,
            MFADevice.id != device_id,
        )
    )
    if not remaining.scalars().first():
        current.mfa_enabled = False
        current.recovery_codes_hash = None
    await db.commit()


@router.post("/challenge")
async def mfa_challenge(
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a challenge for MFA during login (returns active device IDs)."""
    result = await db.execute(
        select(MFADevice).where(
            MFADevice.user_id == current.id,
            MFADevice.is_active == True,
        )
    )
    devices = result.scalars().all()
    if not devices:
        raise HTTPException(404, "No active MFA devices found")
    return {
        "challenge": "totp",
        "devices": [
            {"id": d.id, "name": d.name, "type": "totp"}
            for d in devices
        ],
    }
