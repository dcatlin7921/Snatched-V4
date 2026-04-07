"""Per-user job queue — prevents concurrent processing for the same user."""

import asyncio
import logging

logger = logging.getLogger(__name__)

# In-memory lock registry. One lock per username.
_user_locks: dict[str, asyncio.Lock] = {}


def get_user_lock(username: str) -> asyncio.Lock:
    """Get or create an asyncio.Lock for the given username.

    Ensures only one job runs at a time per user within a single
    uvicorn worker process.
    """
    if username not in _user_locks:
        _user_locks[username] = asyncio.Lock()
        logger.debug(f"Created job queue lock for user: {username}")
    return _user_locks[username]


def is_user_processing(username: str) -> bool:
    """Check if a user currently has a job processing (lock is held)."""
    lock = _user_locks.get(username)
    if lock is None:
        return False
    return lock.locked()


def active_queue_count() -> int:
    """Return count of users currently processing."""
    return sum(1 for lock in _user_locks.values() if lock.locked())
