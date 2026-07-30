"""Shared aiohttp session support for provider clients.

Creating a ClientSession per request throws away the connection pool and
pays a fresh TCP+TLS handshake every call. Clients mix this in and use
``async with self.shared_session() as session:`` — same shape as the old
per-request code, but the session persists for the client's lifetime and
carries a default timeout.
"""
import aiohttp

DEFAULT_TIMEOUT_SECONDS = 120


class _NonClosingSession:
    """Async context manager that yields a session without closing it."""

    def __init__(self, session: aiohttp.ClientSession):
        self._session = session

    async def __aenter__(self) -> aiohttp.ClientSession:
        return self._session

    async def __aexit__(self, *exc) -> bool:
        return False


class SharedSessionMixin:
    """Provides a lazily created, reused aiohttp session with a default timeout."""

    _session: aiohttp.ClientSession = None

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT_SECONDS)
            )
        return self._session

    def shared_session(self) -> _NonClosingSession:
        """Use as ``async with self.shared_session() as session:``.

        Per-request timeouts can still be passed to individual
        ``session.get/post`` calls via their ``timeout`` parameter.
        """
        return _NonClosingSession(self._get_session())

    async def close_session(self):
        """Closes the shared session (call on shutdown)."""
        if self._session and not self._session.closed:
            await self._session.close()
