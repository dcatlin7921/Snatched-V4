"""CSRF protection using double-submit cookie pattern.

How it works:
1. Middleware sets a `csrf_token` cookie (readable by JS, SameSite=Strict)
2. State-changing requests (POST/PUT/DELETE/PATCH) must include the token as:
   - Form field `_csrf_token` (for HTML form submissions), OR
   - Header `X-CSRF-Token` (for JS fetch/XHR calls)
3. Middleware compares submitted token to cookie value -- rejects on mismatch

Cross-origin attackers cannot read the cookie (same-origin policy + SameSite=Strict),
so they cannot forge the matching header/field.

Uses raw ASGI middleware to avoid Starlette's body consumption issue
(BaseHTTPMiddleware + request.form() eats the body before route handlers).
"""

import logging
import secrets
from urllib.parse import parse_qs

from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger("snatched.csrf")

CSRF_COOKIE_NAME = "csrf_token"
CSRF_HEADER_NAME = "x-csrf-token"  # lowercase for ASGI header lookup
CSRF_FORM_FIELD = "_csrf_token"
TOKEN_LENGTH = 32  # 32 bytes = 64 hex chars

# Paths exempt from CSRF verification
EXEMPT_PREFIXES = (
    "/api/",        # All API routes are auth-gated + JSON-based (not CSRF-vulnerable)
    "/static/",
    "/dev-login",
    "/login",       # Auth endpoints — create sessions, not act on them
    "/register",
)

EXEMPT_PATH_FRAGMENTS = (
    # Reserved for future non-API paths needing exemption
)

STATE_CHANGING_METHODS = {b"POST", b"PUT", b"DELETE", b"PATCH"}


def _is_exempt(path: str) -> bool:
    for prefix in EXEMPT_PREFIXES:
        if path.startswith(prefix):
            return True
    for frag in EXEMPT_PATH_FRAGMENTS:
        if frag in path:
            return True
    return False


class CSRFMiddleware:
    """Raw ASGI middleware for CSRF double-submit cookie protection."""

    def __init__(self, app: ASGIApp, dev_mode: bool = False, require_https: bool = False):
        self.app = app
        self.dev_mode = dev_mode
        self.require_https = require_https

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET").encode()
        path = scope.get("path", "/")

        # Only verify on state-changing methods for non-exempt paths
        if method in STATE_CHANGING_METHODS and not _is_exempt(path):
            # Extract cookie token from headers
            cookie_token = self._get_cookie_token(scope)
            if not cookie_token:
                logger.warning("CSRF: missing cookie on %s %s", method.decode(), path)
                await self._send_403(send, "CSRF token missing. Please refresh the page and try again.")
                return

            # Check X-CSRF-Token header first
            submitted_token = self._get_header_token(scope)

            # If no header, check form body for _csrf_token field
            if not submitted_token:
                submitted_token, receive = await self._extract_form_token(scope, receive)

            if not submitted_token:
                logger.warning("CSRF: no token submitted on %s %s", method.decode(), path)
                await self._send_403(send, "CSRF token missing from request. Please refresh the page and try again.")
                return

            if not secrets.compare_digest(cookie_token, submitted_token):
                logger.warning("CSRF: token mismatch on %s %s", method.decode(), path)
                await self._send_403(send, "CSRF token invalid. Please refresh the page and try again.")
                return

        # Wrap send to inject CSRF cookie on responses if needed
        has_csrf_cookie = bool(self._get_cookie_token(scope))

        async def send_wrapper(message):
            if message["type"] == "http.response.start" and not has_csrf_cookie:
                token = secrets.token_hex(TOKEN_LENGTH)
                secure = "; Secure" if self.require_https else ""
                cookie_header = (
                    f"{CSRF_COOKIE_NAME}={token}; "
                    f"Max-Age=86400; Path=/; SameSite=Strict{secure}"
                ).encode()
                headers = list(message.get("headers", []))
                headers.append((b"set-cookie", cookie_header))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)

    def _get_cookie_token(self, scope: Scope) -> str:
        """Extract csrf_token from Cookie header."""
        for key, value in scope.get("headers", []):
            if key == b"cookie":
                for part in value.decode().split(";"):
                    part = part.strip()
                    if part.startswith(f"{CSRF_COOKIE_NAME}="):
                        return part[len(CSRF_COOKIE_NAME) + 1:]
        return ""

    def _get_header_token(self, scope: Scope) -> str:
        """Extract X-CSRF-Token from request headers."""
        for key, value in scope.get("headers", []):
            if key == CSRF_HEADER_NAME.encode():
                return value.decode()
        return ""

    async def _extract_form_token(self, scope: Scope, receive: Receive):
        """Read form body to extract _csrf_token, return cached receive.

        Returns (token, new_receive) where new_receive replays the body.
        """
        content_type = ""
        for key, value in scope.get("headers", []):
            if key == b"content-type":
                content_type = value.decode()
                break

        if "application/x-www-form-urlencoded" not in content_type:
            return "", receive

        # Read the full body
        body = b""
        while True:
            message = await receive()
            body += message.get("body", b"")
            if not message.get("more_body", False):
                break

        # Parse form data to extract token
        token = ""
        try:
            parsed = parse_qs(body.decode())
            values = parsed.get(CSRF_FORM_FIELD, [])
            if values:
                token = values[0]
        except Exception:
            pass

        # Create a new receive that replays the cached body
        body_sent = False

        async def cached_receive():
            nonlocal body_sent
            if not body_sent:
                body_sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.request", "body": b"", "more_body": False}

        return token, cached_receive

    async def _send_403(self, send: Send, detail: str) -> None:
        """Send a 403 JSON response."""
        import json
        body = json.dumps({"detail": detail}).encode()
        await send({
            "type": "http.response.start",
            "status": 403,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        })
        await send({
            "type": "http.response.body",
            "body": body,
        })
