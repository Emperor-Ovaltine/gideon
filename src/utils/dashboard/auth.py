"""Authentication middleware for the dashboard."""
import hashlib
import hmac
import logging
import time
from aiohttp import web

logger = logging.getLogger(__name__)

# Session tokens: maps token -> expiry timestamp
_active_sessions = {}
SESSION_DURATION = 86400  # 24 hours


def generate_session_token(secret: str) -> str:
    """Generate a session token from the secret and current time."""
    raw = f"{secret}:{time.time()}:{id(secret)}"
    token = hashlib.sha256(raw.encode()).hexdigest()
    _active_sessions[token] = time.time() + SESSION_DURATION
    return token


def validate_session_token(token: str) -> bool:
    """Check if a session token is valid and not expired."""
    if token not in _active_sessions:
        return False
    if time.time() > _active_sessions[token]:
        del _active_sessions[token]
        return False
    return True


def invalidate_session_token(token: str):
    """Remove a session token."""
    _active_sessions.pop(token, None)


def cleanup_expired_sessions():
    """Remove all expired session tokens."""
    now = time.time()
    expired = [t for t, exp in _active_sessions.items() if now > exp]
    for t in expired:
        del _active_sessions[t]


def verify_secret(provided: str, actual: str) -> bool:
    """Constant-time comparison of the provided secret against the actual."""
    return hmac.compare_digest(provided.encode(), actual.encode())


@web.middleware
async def auth_middleware(request, handler):
    """Middleware that checks authentication for API routes."""
    # Allow login endpoint, static files, and the root page without auth
    path = request.path
    if path in ('/api/auth/login', '/api/auth/check') or not path.startswith('/api/'):
        return await handler(request)

    # Check for session token in cookie or Authorization header
    token = request.cookies.get('session_token')
    if not token:
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            token = auth_header[7:]

    if not token or not validate_session_token(token):
        return web.json_response({'error': 'Unauthorized'}, status=401)

    return await handler(request)
