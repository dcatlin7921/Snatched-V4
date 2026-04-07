"""Authentication: Authelia headers, JWT sessions, and local password auth.

Priority order for identifying users:
1. X-Remote-User header (Authelia/OIDC proxy — production)
2. JWT cookie 'auth_token' (built-in login or dev mode)
3. 401 Unauthorized

Password hashing uses bcrypt for local accounts.
OAuth accounts (Google, GitHub, Apple) will have no password_hash.
"""

import logging
import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import HTTPException, Request

logger = logging.getLogger("snatched.auth")

DEV_MODE = os.getenv("SNATCHED_DEV_MODE") == "1"
REQUIRE_HTTPS = os.getenv("SNATCHED_REQUIRE_HTTPS", "0") == "1"
JWT_SECRET = os.getenv("SNATCHED_JWT_SECRET", "dev-key-change-me")

# Trusted proxy IPs allowed to set X-Remote-User header.
# Only Traefik (reverse-proxy container) should be trusted.
# Comma-separated list via env var, defaults to Traefik's Docker IP.
_trusted_raw = os.getenv("SNATCHED_TRUSTED_PROXY_IPS", "172.20.1.10")
TRUSTED_PROXY_IPS: set[str] = {ip.strip() for ip in _trusted_raw.split(",") if ip.strip()}
JWT_EXPIRE_HOURS = 24

# WU-18: Validate JWT secret length at import time
if len(JWT_SECRET) < 32:
    if DEV_MODE:
        logger.warning(
            "SECURITY: SNATCHED_JWT_SECRET is shorter than 32 bytes (%d). "
            "This is acceptable in DEV_MODE but MUST be fixed for production.",
            len(JWT_SECRET),
        )
    else:
        import secrets as _secrets
        _fallback = _secrets.token_hex(32)
        logger.critical(
            "SECURITY: SNATCHED_JWT_SECRET is shorter than 32 bytes (%d). "
            "Generating a random fallback secret. Sessions will NOT survive restarts. "
            "Set SNATCHED_JWT_SECRET to a value >= 32 bytes in production.",
            len(JWT_SECRET),
        )
        JWT_SECRET = _fallback


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    return bcrypt.checkpw(password.encode(), password_hash.encode())


# ---------------------------------------------------------------------------
# JWT token management
# ---------------------------------------------------------------------------

def create_jwt(username: str, expires_hours: int = JWT_EXPIRE_HOURS) -> str:
    """Create a signed JWT token.

    Args:
        username: User identifier.
        expires_hours: Token lifetime in hours.

    Returns:
        Encoded JWT token string.
    """
    now = datetime.now(tz=timezone.utc)
    payload = {
        "sub": username,
        "iat": now,
        "exp": now + timedelta(hours=expires_hours),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


# Keep old name for backward compatibility (dev-login route uses it)
create_dev_jwt = create_jwt


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------

async def get_current_user(request: Request) -> str:
    """Extract authenticated username from request.

    Checks in order:
    1. X-Remote-User header (Authelia proxy)
    2. JWT cookie 'auth_token' (built-in login)

    Returns:
        Username string.

    Raises:
        HTTPException(401): If not authenticated.
    """
    # 1. Authelia header (highest priority) — only trust from reverse proxy
    username = request.headers.get("X-Remote-User")
    if username:
        client_ip = request.client.host if request.client else None
        if client_ip in TRUSTED_PROXY_IPS:
            return username
        else:
            logger.warning(
                "X-Remote-User header '%s' rejected: client IP %s not in trusted proxies %s",
                username, client_ip, TRUSTED_PROXY_IPS,
            )

    # 2. JWT cookie (built-in login or dev mode)
    token = request.cookies.get("auth_token")
    if token:
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
            username = payload.get("sub")
            if username:
                return username
        except jwt.InvalidTokenError:
            pass  # Invalid/expired token — fall through to 401

    raise HTTPException(401, "Not authenticated")


async def get_optional_user(request: Request) -> str | None:
    """Like get_current_user but returns None instead of raising 401."""
    try:
        return await get_current_user(request)
    except HTTPException:
        return None


async def get_user_groups(request: Request) -> list[str]:
    """Extract user groups from Authelia X-Remote-Groups header.

    Returns:
        List of group name strings (empty list if header absent).
    """
    groups_str = request.headers.get("X-Remote-Groups", "")
    return [g.strip() for g in groups_str.split(",") if g.strip()]


async def require_admin(request: Request) -> str:
    """Dependency for admin-only routes (Authelia groups).

    Verifies authenticated user is in the 'admin' group via X-Remote-Groups header.

    Returns:
        Username if user is admin.

    Raises:
        HTTPException(403): If user is not in admin group.
    """
    username = await get_current_user(request)
    groups = await get_user_groups(request)

    if "admin" not in groups:
        raise HTTPException(403, f"User '{username}' is not in admin group.")

    return username


async def require_admin_db(pool, username: str) -> None:
    """Check is_admin column on users table. Raises 403 if not admin.

    Used by page and API routes that check the DB directly rather than
    relying on Authelia X-Remote-Groups headers.
    """
    async with pool.acquire() as conn:
        user_row = await conn.fetchrow(
            "SELECT is_admin FROM users WHERE username = $1", username
        )
    if not user_row or not user_row["is_admin"]:
        raise HTTPException(403, "Admin access required")
