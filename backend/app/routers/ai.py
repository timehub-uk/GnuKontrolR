"""AI assistant endpoints — provider CRUD, OpenCode lifecycle, WebSocket proxy."""
import asyncio
import base64
import hashlib
import logging
import os
import re
import secrets
import subprocess
from typing import Optional

log = logging.getLogger("webpanel.ai")

from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, require_admin
from app.cache import get_redis
from app.database import get_db
from app.models.ai_provider import AiProvider, AiProviderName
from app.models.ai_session import AiSession, AiActivityLog
from app.models.domain import Domain
from app.models.user import User, Role

router = APIRouter(prefix="/api/ai", tags=["ai"])

# ── Encryption ────────────────────────────────────────────────────────────────

def _build_fernet() -> Fernet:
    key = os.environ.get("SECRET_KEY", "")
    if not key:
        raise RuntimeError("SECRET_KEY environment variable is not set — cannot encrypt AI provider credentials.")
    raw = hashlib.sha256(key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(raw))

_FERNET: Fernet = _build_fernet()


def _encrypt(plaintext: str) -> str:
    return _FERNET.encrypt(plaintext.encode()).decode()


def _decrypt(ciphertext: str) -> str:
    try:
        return _FERNET.decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        raise HTTPException(500, "Failed to decrypt stored credential — the server key may have changed.")


# ── Constants ─────────────────────────────────────────────────────────────────

VALID_PROVIDERS = {p.value for p in AiProviderName}

PROVIDER_ENV: dict[str, str] = {
    "anthropic":        "ANTHROPIC_API_KEY",
    "openai":           "OPENAI_API_KEY",
    "zen":              "OPENCODE_ZEN_API_KEY",
    "ollama":           "OLLAMA_HOST",
    "opencode_account": "",   # handled via opencode auth, not env var
}


def _container(domain_name: str) -> str:
    return "site_" + domain_name.replace(".", "_").replace("-", "_")


async def _resolve_domain(domain_name: str, current: User, db: AsyncSession) -> tuple[Domain, int]:
    """Return (domain, owner_id). Raises 404/403 if not found/not owned."""
    result = await db.execute(select(Domain).where(Domain.name == domain_name))
    domain = result.scalar_one_or_none()
    if not domain:
        raise HTTPException(404, "Domain not found")
    if domain.owner_id != current.id and current.role not in (Role.superadmin, Role.admin):
        raise HTTPException(403, "Access denied")
    return domain, domain.owner_id


# ── Provider CRUD ─────────────────────────────────────────────────────────────

class ProviderCreate(BaseModel):
    provider: str
    api_key: str
    default_model: str = ""

    @field_validator("default_model")
    @classmethod
    def check_model_length(cls, v: str) -> str:
        if len(v) > 64:
            raise ValueError("default_model must be 64 characters or fewer")
        return v


@router.get("/providers")
async def list_providers(
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List configured AI providers for the current user (keys never returned)."""
    result = await db.execute(
        select(AiProvider).where(AiProvider.user_id == current.id)
    )
    rows = result.scalars().all()
    return [
        {
            "provider":      r.provider,
            "default_model": r.default_model,
            "configured":    bool(r.api_key_enc),
            "created_at":    r.created_at,
        }
        for r in rows
    ]


@router.post("/providers", status_code=201)
async def save_provider(
    body: ProviderCreate,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save or update an AI provider API key (encrypted at rest)."""
    if body.provider not in VALID_PROVIDERS:
        raise HTTPException(400, f"Unknown provider: {body.provider}. Valid: {sorted(VALID_PROVIDERS)}")
    if not body.api_key.strip():
        raise HTTPException(400, "api_key must not be empty")

    result = await db.execute(
        select(AiProvider).where(
            AiProvider.user_id == current.id,
            AiProvider.provider == body.provider,
        )
    )
    row = result.scalar_one_or_none()

    enc = _encrypt(body.api_key.strip())

    if row:
        row.api_key_enc = enc
        row.default_model = body.default_model
    else:
        row = AiProvider(
            user_id=current.id,
            provider=body.provider,
            api_key_enc=enc,
            default_model=body.default_model,
        )
        db.add(row)

    await db.commit()
    return {"ok": True, "provider": body.provider}


@router.delete("/providers/{provider_name}", status_code=204)
async def delete_provider(
    provider_name: str,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a stored AI provider credential."""
    result = await db.execute(
        select(AiProvider).where(
            AiProvider.user_id == current.id,
            AiProvider.provider == provider_name,
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(404, "Provider not configured")
    await db.delete(row)
    await db.commit()


# ── OpenCode lifecycle ─────────────────────────────────────────────────────────

_AI_TOKEN_PREFIX     = "ai:token"
_AI_STARTING_PREFIX  = "ai:starting"
_AI_CONTAINER_PREFIX = "ai:container"   # stores which container runs opencode for this session
_AI_TOKEN_TTL        = 3600   # 1 hour; renewed on each WS message
_AI_START_LOCK_TTL   = 30     # prevent double-start race


async def _get_provider_env(owner_id: int, db: AsyncSession) -> dict[str, str]:
    """Build env var dict from all configured providers for this user."""
    result = await db.execute(
        select(AiProvider).where(AiProvider.user_id == owner_id)
    )
    providers = result.scalars().all()
    env = {}
    for p in providers:
        if not p.api_key_enc:
            continue
        env_var = PROVIDER_ENV.get(p.provider.value if hasattr(p.provider, 'value') else p.provider, "")
        if env_var:
            try:
                env[env_var] = _decrypt(p.api_key_enc)
            except Exception:
                pass  # skip corrupted keys
    return env


async def _start_opencode(container: str, token: str, env: dict[str, str]) -> None:
    """Start opencode serve inside the container."""
    loop = asyncio.get_running_loop()

    def _run():
        # Build env file content
        lines = [f"OPENCODE_SERVER_PASSWORD={token}"]
        for k, v in env.items():
            # Sanitize: skip keys/values with newlines
            if "\n" in k or "\n" in v:
                continue
            lines.append(f"{k}={v}")
        env_content = "\n".join(lines) + "\n"

        # Write env file via stdin (never via shell interpolation)
        env_dest = "/tmp/.ai_env"
        r = subprocess.run(
            ["docker", "exec", "-i", container, "tee", env_dest],
            input=env_content.encode(),
            capture_output=True,
        )
        if r.returncode != 0:
            raise RuntimeError(f"Failed to write env file: {r.stderr.decode()}")

        # Start opencode in background
        r2 = subprocess.run(
            ["docker", "exec", "-d", container, "sh", "-c",
             f"set -a && . {env_dest} && rm -f {env_dest} && opencode serve --port 7878"],
            capture_output=True,
        )
        # -d returns 0 even if command fails; we poll for readiness below
        # This rm runs immediately after docker exec -d returns, deleting the env file promptly.
        # The rm in the shell chain only runs when opencode exits — this is the effective delete.
        subprocess.run(
            ["docker", "exec", container, "rm", "-f", env_dest],
            capture_output=True,
        )

    await loop.run_in_executor(None, _run)


async def _wait_ready(container: str, timeout: int = 20) -> bool:
    """Poll opencode health endpoint until ready or timeout."""
    loop = asyncio.get_running_loop()

    # We can't reach the container's localhost from outside, so probe via docker exec
    def _probe_exec():
        r = subprocess.run(
            ["docker", "exec", container, "sh", "-c",
             "curl -sf http://localhost:7878/health || wget -q -O- http://localhost:7878/health"],
            capture_output=True, timeout=3,
        )
        return r.returncode == 0

    for _ in range(timeout):
        await asyncio.sleep(1)
        ready = await loop.run_in_executor(None, _probe_exec)
        if ready:
            return True
    return False


@router.post("/start/{domain_name}")
async def start_ai(
    domain_name: str,
    agent: str = "general",
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Start an OpenCode session for a domain."""
    from app.services.ai_agents import write_all_agent_files, activate_agent, AGENT_REGISTRY
    from app.routers.ai_containers import get_or_create_ai_container

    if agent not in AGENT_REGISTRY:
        raise HTTPException(400, f"Unknown agent: {agent}")

    domain, owner_id = await _resolve_domain(domain_name, current, db)
    site_container = _container(domain_name)

    # Check if global AI is enabled
    r = await get_redis()
    if not r:
        raise HTTPException(503, "Session service unavailable. Please try again later.")
    disabled = await r.get("ai:config:enabled")
    if disabled == "0":
        raise HTTPException(503, "AI assistant is currently disabled by the administrator.")

    # Prevent double-start with NX lock
    token_key = f"{_AI_TOKEN_PREFIX}:{owner_id}:{domain_name}:{agent}"
    existing = await r.get(token_key)
    if existing:
        raise HTTPException(409, "AI session already active for this domain.")

    lock_key = f"{_AI_STARTING_PREFIX}:{owner_id}:{domain_name}"
    locked = await r.set(lock_key, "1", nx=True, ex=_AI_START_LOCK_TTL)
    if not locked:
        raise HTTPException(409, "Session start already in progress.")

    try:
        # Ensure a dedicated AI container exists (creates + installs opencode if needed)
        ai_ctr = await get_or_create_ai_container("opencode", current)

        # Write/refresh agent files into the AI container
        await write_all_agent_files(ai_ctr, domain_name)
        await activate_agent(ai_ctr, agent)

        # Collect provider env vars
        env = await _get_provider_env(owner_id, db)

        # Generate session token
        token = secrets.token_urlsafe(32)

        # Start OpenCode in the dedicated AI container
        await _start_opencode(ai_ctr, token, env)

        # Wait for readiness
        ready = await _wait_ready(ai_ctr)
        if not ready:
            raise HTTPException(503, "OpenCode failed to start within timeout.")

        # Store token and container name in Redis
        await r.setex(token_key, _AI_TOKEN_TTL, token)
        container_key = f"{_AI_CONTAINER_PREFIX}:{owner_id}:{domain_name}:{agent}"
        await r.setex(container_key, _AI_TOKEN_TTL, ai_ctr)

        # Log session start
        try:
            session = AiSession(
                user_id=owner_id,
                domain=domain_name,
                tool="opencode",
                agent=agent,
                container=ai_ctr,
            )
            db.add(session)
            await db.commit()
            await db.refresh(session)
            await r.setex(f"ai:session_id:{owner_id}:{domain_name}:{agent}", _AI_TOKEN_TTL, str(session.id))
        except Exception as exc:
            log.warning("AI session log failed: %s", exc)

        # Check for saved conversation history
        history = []
        history_key = f"ai:history:{owner_id}:{domain_name}:{agent}"
        raw = await r.lrange(history_key, 0, -1)
        history = [{"role": m.split(":", 1)[0], "content": m.split(":", 1)[1]} for m in raw if ":" in m]

        return {"ok": True, "domain": domain_name, "agent": agent, "history": history}

    except HTTPException:
        raise
    except Exception as e:
        log.error("AI start failed: %s", e)
        raise HTTPException(500, "Failed to start AI session. Please try again.")
    finally:
        lock_key = f"{_AI_STARTING_PREFIX}:{owner_id}:{domain_name}"
        await r.delete(lock_key)


@router.delete("/stop/{domain_name}", status_code=204)
async def stop_ai(
    domain_name: str,
    agent: str = "general",
    save_context: bool = False,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Stop an OpenCode session for a domain."""
    from datetime import datetime as _dt
    domain, owner_id = await _resolve_domain(domain_name, current, db)

    # Remove Redis token and look up which container was used
    r = await get_redis()
    ai_ctr = None
    if r:
        token_key = f"{_AI_TOKEN_PREFIX}:{owner_id}:{domain_name}:{agent}"
        container_key = f"{_AI_CONTAINER_PREFIX}:{owner_id}:{domain_name}:{agent}"
        ai_ctr = await r.get(container_key)
        await r.delete(token_key)
        await r.delete(container_key)

        # Log session end
        try:
            session_id_raw = await r.get(f"ai:session_id:{owner_id}:{domain_name}:{agent}")
            await r.delete(f"ai:session_id:{owner_id}:{domain_name}:{agent}")
            if session_id_raw:
                from sqlalchemy import select as _sel
                result = await db.execute(_sel(AiSession).where(AiSession.id == int(session_id_raw)))
                sess = result.scalar_one_or_none()
                if sess and not sess.ended_at:
                    sess.ended_at = _dt.utcnow()
                    sess.ended_reason = "user_stop"
                    if sess.started_at:
                        sess.duration_s = (_dt.utcnow() - sess.started_at).total_seconds()
                    await db.commit()
        except Exception as exc:
            log.warning("AI session end log failed: %s", exc)

    # Kill opencode process in the AI container (fall back to site container if unknown)
    container = ai_ctr or _container(domain_name)
    loop = asyncio.get_running_loop()
    def _kill():
        subprocess.run(
            ["docker", "exec", container, "sh", "-c", "pkill -f 'opencode serve' || true"],
            capture_output=True, timeout=5,
        )
    await loop.run_in_executor(None, _kill)


# ── Abuse detection ────────────────────────────────────────────────────────────

_ABUSE_PATTERNS = [
    re.compile(r"(?i)(rm\s+-rf|format\s+[a-z]:|dd\s+if=|mkfs\.|drop\s+database|truncate\s+table)"),
    re.compile(r"(?i)(wget|curl)\s+.*\|\s*(ba)?sh"),
    re.compile(r"(?i)(ignore\s+(all\s+)?(previous|prior|above)\s+instructions?)"),
    re.compile(r"(?i)(act\s+as\s+(a\s+)?(different|new|unrestricted)\s+(ai|assistant|model))"),
    re.compile(r"(?i)(jailbreak|dan\s+mode|developer\s+mode|do\s+anything\s+now)"),
]

_ABUSE_MAX_STRIKES = 3
_ABUSE_TTL = 900   # 15 minutes cooldown
_ABUSE_KEY_PREFIX = "ai:abuse"


def _check_abuse(text: str) -> bool:
    """Return True if the message matches an abuse pattern."""
    return any(p.search(text) for p in _ABUSE_PATTERNS)


# ── WebSocket proxy ────────────────────────────────────────────────────────────

@router.websocket("/ws/{domain_name}/{agent_id}")
async def ai_ws(
    websocket: WebSocket,
    domain_name: str,
    agent_id: str,
):
    """
    Proxy WebSocket to opencode serve running in the domain container.
    Authenticates via Redis session token. Detects and blocks abuse.

    Close codes:
      4008 — session expired / not started
      4020 — abuse detected and blocked
    """
    import websockets

    await websocket.accept()

    # ── Auth: look up session token from Redis ─────────────────────────────────
    r = await get_redis()
    if not r:
        await websocket.close(4008, "Session service unavailable")
        return

    # We need to know the owner_id. Extract from token key scan.
    # The WS endpoint doesn't have current_user via Depends (no HTTP auth on WS).
    # Instead we match the first token key for this domain+agent (owner determined by Redis).
    pattern = f"{_AI_TOKEN_PREFIX}:*:{domain_name}:{agent_id}"
    keys = [key async for key in r.scan_iter(match=pattern, count=100)]
    if not keys:
        await websocket.close(4008, "No active session. Start the AI assistant first.")
        return

    token_key = keys[0]
    token = await r.get(token_key)
    if not token:
        await websocket.close(4008, "Session expired. Please restart the AI assistant.")
        return

    # Extract owner_id from key: ai:token:{owner_id}:{domain}:{agent}
    parts = token_key.split(":")
    owner_id = parts[2] if len(parts) >= 5 else "unknown"

    # ── Check abuse block ──────────────────────────────────────────────────────
    abuse_key = f"{_ABUSE_KEY_PREFIX}:{owner_id}"
    if await r.get(abuse_key):
        await websocket.close(4020, "Your session has been suspended due to abuse policy violations.")
        return

    # ── Connect to opencode in AI container ───────────────────────────────────
    container_key = f"{_AI_CONTAINER_PREFIX}:{owner_id}:{domain_name}:{agent_id}"
    ai_ctr = await r.get(container_key)
    container = ai_ctr or _container(domain_name)
    oc_url = f"ws://{container}:7878/ws?password={token}"

    # Look up session ID for activity logging
    session_id_raw = await r.get(f"ai:session_id:{owner_id}:{domain_name}:{agent_id}")
    session_id = int(session_id_raw) if session_id_raw and session_id_raw.isdigit() else None

    try:
        async with websockets.connect(oc_url, ping_interval=20) as oc_ws:
            async def _log_activity(direction: str, message: str) -> None:
                """Write one AiActivityLog row — best-effort, never raises."""
                try:
                    from app.database import AsyncSessionLocal
                    tokens_est = len(message) // 4
                    entry = AiActivityLog(
                        session_id=session_id,
                        user_id=int(owner_id) if str(owner_id).isdigit() else None,
                        domain=domain_name,
                        tool="opencode",
                        agent=agent_id,
                        direction=direction,
                        message=message[:4096],
                        tokens_est=tokens_est,
                        flagged=False,
                    )
                    async with AsyncSessionLocal() as _db:
                        _db.add(entry)
                        await _db.commit()
                except Exception:
                    pass

            async def client_to_oc():
                """Forward client → opencode, check abuse on outbound messages."""
                async for msg in websocket.iter_text():
                    # Abuse check
                    if _check_abuse(msg):
                        strike_key = f"ai:strikes:{owner_id}"
                        strikes = await r.incr(strike_key)
                        if strikes == 1:
                            await r.expire(strike_key, _ABUSE_TTL)  # Only set TTL once, on first strike
                        if strikes >= _ABUSE_MAX_STRIKES:
                            await r.setex(abuse_key, _ABUSE_TTL, "1")
                            # Log flagged message
                            try:
                                from app.database import AsyncSessionLocal
                                entry = AiActivityLog(
                                    session_id=session_id,
                                    user_id=int(owner_id) if str(owner_id).isdigit() else None,
                                    domain=domain_name, tool="opencode", agent=agent_id,
                                    direction="in", message=msg[:4096], flagged=True,
                                    flag_reason="abuse_block",
                                )
                                async with AsyncSessionLocal() as _db:
                                    _db.add(entry); await _db.commit()
                            except Exception:
                                pass
                            await websocket.close(4020, "Abuse detected. Session suspended for 15 minutes.")
                            await oc_ws.close()
                            return
                        # Warn but let through on first/second strike
                        await websocket.send_text(
                            f'{{"type":"warning","message":"Warning {strikes}/{_ABUSE_MAX_STRIKES}: '
                            f'This session is monitored. Abuse will result in suspension."}}'
                        )
                        continue
                    # Renew session TTL on activity
                    await r.expire(token_key, _AI_TOKEN_TTL)
                    await oc_ws.send(msg)
                    # Log user message
                    asyncio.create_task(_log_activity("in", msg))
                    # Append to conversation history (capped at 50 messages, TTL 24h)
                    history_key = f"ai:history:{owner_id}:{domain_name}:{agent_id}"
                    await r.rpush(history_key, f"user:{msg[:500]}")  # cap per-message at 500 chars
                    await r.ltrim(history_key, -50, -1)              # keep last 50 messages
                    await r.expire(history_key, 86400)               # 24h TTL

            async def oc_to_client():
                """Forward opencode → client."""
                async for msg in oc_ws:
                    text = msg if isinstance(msg, str) else msg.decode()
                    await websocket.send_text(text)
                    # Log AI response
                    asyncio.create_task(_log_activity("out", text))
                    history_key = f"ai:history:{owner_id}:{domain_name}:{agent_id}"
                    await r.rpush(history_key, f"ai:{text[:500]}")
                    await r.ltrim(history_key, -50, -1)
                    await r.expire(history_key, 86400)

            # Run both directions concurrently; stop when either ends
            done, pending = await asyncio.wait(
                [
                    asyncio.create_task(client_to_oc()),
                    asyncio.create_task(oc_to_client()),
                ],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for t in pending:
                t.cancel()
            await asyncio.gather(*pending, return_exceptions=True)

    except WebSocketDisconnect:
        pass
    except Exception:
        try:
            await websocket.close(4008, "Connection to AI service lost.")
        except Exception:
            pass


# ── OpenCode account auth (device-flow) ───────────────────────────────────────

_OC_AUTH_PENDING_PREFIX = "ai:oc_auth_pending"
_OC_AUTH_PENDING_TTL    = 300  # 5 minutes to complete device flow


@router.post("/opencode-auth/login")
async def opencode_auth_login(
    current: User = Depends(get_current_user),
):
    """
    Initiate OpenCode device-flow login.
    Runs `opencode auth login` inside the user's dedicated AI container.
    """
    from app.routers.ai_containers import get_or_create_ai_container
    loop = asyncio.get_running_loop()

    # Ensure AI container exists and has opencode installed
    ai_ctr = await get_or_create_ai_container("opencode", current)

    def _run_login():
        r = subprocess.run(
            ["docker", "exec", ai_ctr, "opencode", "auth", "login"],
            capture_output=True, text=True, timeout=30,
        )
        return r.stdout.strip(), r.returncode

    try:
        stdout, code = await loop.run_in_executor(None, _run_login)
    except FileNotFoundError:
        raise HTTPException(503, "Docker is not available on this server.")
    except Exception as e:
        log.error("OpenCode auth start failed: %s", e)
        raise HTTPException(500, "Failed to initiate OpenCode auth.")

    # Extract URL from stdout (opencode outputs a URL line)
    url = None
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith("https://") or line.startswith("http://"):
            url = line
            break

    if not url:
        log.error("OpenCode did not return an auth URL. Output: %s", stdout[:200])
        raise HTTPException(500, "OpenCode did not return an auth URL.")

    # Store pending state in Redis so verify endpoint can confirm
    r_redis = await get_redis()
    if r_redis:
        await r_redis.setex(
            f"{_OC_AUTH_PENDING_PREFIX}:{current.id}",
            _OC_AUTH_PENDING_TTL,
            url,
        )

    return {"url": url, "message": "Visit the URL to authorize OpenCode access."}


@router.post("/opencode-auth/verify")
async def opencode_auth_verify(
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Verify that the OpenCode device-flow login completed.
    Polls `opencode auth list` to check for an active account.
    """
    loop = asyncio.get_running_loop()

    from app.routers.ai_containers import get_or_create_ai_container
    ai_ctr = await get_or_create_ai_container("opencode", current)

    def _check_auth():
        r = subprocess.run(
            ["docker", "exec", ai_ctr, "opencode", "auth", "list"],
            capture_output=True, text=True, timeout=15,
        )
        return r.stdout.strip(), r.returncode

    try:
        stdout, code = await loop.run_in_executor(None, _check_auth)
    except Exception as e:
        log.error("OpenCode auth verify failed: %s", e)
        raise HTTPException(500, "Failed to check OpenCode auth.")

    # opencode auth list outputs active accounts; non-empty means logged in
    if not stdout or code != 0:
        raise HTTPException(400, "OpenCode account not yet authorized. Please visit the URL and try again.")

    # Store the fact that opencode_account provider is configured for this user
    # (no API key to encrypt — auth is managed by opencode itself)
    result = await db.execute(
        select(AiProvider).where(
            AiProvider.user_id == current.id,
            AiProvider.provider == "opencode_account",
        )
    )
    row = result.scalar_one_or_none()
    if row:
        row.api_key_enc = _encrypt("opencode_account_active")
    else:
        row = AiProvider(
            user_id=current.id,
            provider="opencode_account",
            api_key_enc=_encrypt("opencode_account_active"),
            default_model="",
        )
        db.add(row)
    await db.commit()

    # Clear pending state
    r_redis = await get_redis()
    if r_redis:
        await r_redis.delete(f"{_OC_AUTH_PENDING_PREFIX}:{current.id}")

    return {"ok": True, "message": "OpenCode account connected successfully."}


@router.delete("/opencode-auth/logout", status_code=204)
async def opencode_auth_logout(
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove OpenCode account connection."""
    from app.routers.ai_containers import get_or_create_ai_container
    loop = asyncio.get_running_loop()

    try:
        ai_ctr = await get_or_create_ai_container("opencode", current)

        def _logout():
            subprocess.run(
                ["docker", "exec", ai_ctr, "opencode", "auth", "logout"],
                capture_output=True, timeout=10,
            )

        await loop.run_in_executor(None, _logout)
    except Exception as exc:
        log.warning("opencode auth logout in container failed: %s", exc)

    # Remove the provider record
    result = await db.execute(
        select(AiProvider).where(
            AiProvider.user_id == current.id,
            AiProvider.provider == "opencode_account",
        )
    )
    row = result.scalar_one_or_none()
    if row:
        await db.delete(row)
        await db.commit()
