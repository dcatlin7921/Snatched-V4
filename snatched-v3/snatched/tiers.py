"""Centralized tier definitions and quota limits for Snatched v3.

All tier-related lookups go through this module. Limits are stored in the
``tier_plans`` PostgreSQL table and cached process-locally.  A single-row
``tier_plans_meta`` version counter drives instant cache invalidation:
every admin edit bumps the version; on next request each worker compares
its cached version to the DB row and reloads on mismatch.

Public API
----------
* ``get_tier_limits_async(pool, tier)``  — async, preferred in route handlers
* ``get_all_tiers_async(pool)``          — async, for comparison tables
* ``get_system_config(pool)``            — async, typed system_config values
* ``get_tier_limits(tier)``              — sync shim (reads last-loaded cache)
* ``bump_version(pool)``                 — called by admin save endpoints
"""

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Fallback limits — used ONLY during the brief startup window before the
# DB pool is ready.  Once seed_tier_plans() + _warm_cache() run in lifespan
# these are never consulted again.
# ---------------------------------------------------------------------------

_FALLBACK_LIMITS: dict[str, dict[str, Any]] = {
    "free": {
        "label": "Free",
        "storage_gb": 10,
        "max_upload_bytes": 5 * 1024 ** 3,
        "max_upload_label": "5 GB",
        "retention_days": 30,
        "concurrent_jobs": 1,
        "bulk_upload": False,
        "color": "var(--text-muted)",
        "max_api_keys": 0,
        "api_key_rate_limit_rpm": 0,
        "max_webhooks": 0,
        "max_schedules": 0,
    },
    "pro": {
        "label": "Pro",
        "storage_gb": 50,
        "max_upload_bytes": 25 * 1024 ** 3,
        "max_upload_label": "25 GB",
        "retention_days": 180,
        "concurrent_jobs": 1,
        "bulk_upload": True,
        "color": "var(--snap-yellow)",
        "max_api_keys": 3,
        "api_key_rate_limit_rpm": 60,
        "max_webhooks": 3,
        "max_schedules": 2,
    },
}

# ---------------------------------------------------------------------------
# Process-local cache (per uvicorn worker)
# ---------------------------------------------------------------------------

_cache_version: int = 0
_cache_tiers: dict[str, dict[str, Any]] = {}  # tier_key -> limits dict
_cache_tier_order: list[str] = []              # ordered tier keys
_cache_system: dict[str, Any] = {}             # system_config key -> typed value
_cache_lock = asyncio.Lock()
_cache_checked_at: float = 0.0                 # monotonic time of last DB version check
_CACHE_TTL_SECONDS: float = 60.0               # only check DB version this often


def _row_to_dict(row) -> dict[str, Any]:
    """Convert a tier_plans DB row to a limits dict matching the old API."""
    return {
        "label": row["label"],
        "color": row["color"],
        "storage_gb": row["storage_gb"],
        "max_upload_bytes": row["max_upload_bytes"],
        "max_upload_label": row["max_upload_label"],
        "retention_days": row["retention_days"],
        "concurrent_jobs": row["concurrent_jobs"],
        "bulk_upload": row["bulk_upload"],
        "max_api_keys": row["max_api_keys"],
        "api_key_rate_limit_rpm": row["api_key_rate_limit_rpm"],
        "max_webhooks": row["max_webhooks"],
        "max_schedules": row["max_schedules"],
    }


def _cast_system_value(value: str, value_type: str) -> Any:
    """Convert system_config text value to its declared type."""
    if value_type == "integer":
        return int(value)
    if value_type == "boolean":
        return value.lower() in ("true", "1", "yes")
    return value


async def _reload_cache(pool) -> None:
    """Load all tier_plans + system_config from DB into process-local cache."""
    global _cache_version, _cache_tiers, _cache_tier_order, _cache_system

    async with pool.acquire() as conn:
        version = await conn.fetchval(
            "SELECT version FROM tier_plans_meta WHERE id = 1"
        )
        rows = await conn.fetch(
            "SELECT * FROM tier_plans ORDER BY sort_order, tier_key"
        )
        sys_rows = await conn.fetch("SELECT * FROM system_config")

    tiers: dict[str, dict[str, Any]] = {}
    tier_order: list[str] = []
    for row in rows:
        key = row["tier_key"]
        tiers[key] = _row_to_dict(row)
        tier_order.append(key)

    sys_cfg: dict[str, Any] = {}
    for row in sys_rows:
        sys_cfg[row["key"]] = _cast_system_value(row["value"], row["value_type"])

    _cache_version = version or 1
    _cache_tiers = tiers
    _cache_tier_order = tier_order
    _cache_system = sys_cfg

    _sync_legacy_exports()
    logger.debug(f"Tier cache reloaded (version={_cache_version}, tiers={len(tiers)})")


async def _ensure_cache(pool) -> None:
    """Check version and reload if stale.  Lock prevents stampede.

    Uses a TTL to avoid hitting the DB on every single request.
    The version check query only runs once per _CACHE_TTL_SECONDS.
    """
    import time
    global _cache_version, _cache_checked_at

    # Fast path: cache populated AND checked recently — skip DB entirely
    if _cache_tiers and (time.monotonic() - _cache_checked_at) < _CACHE_TTL_SECONDS:
        return

    # Fast path: cache populated, TTL expired — check version
    if _cache_tiers:
        async with pool.acquire() as conn:
            db_version = await conn.fetchval(
                "SELECT version FROM tier_plans_meta WHERE id = 1"
            )
        _cache_checked_at = time.monotonic()
        if db_version == _cache_version:
            return

    async with _cache_lock:
        # Double-check inside the lock (another coroutine may have reloaded)
        if _cache_tiers and (time.monotonic() - _cache_checked_at) < _CACHE_TTL_SECONDS:
            return
        if _cache_tiers:
            async with pool.acquire() as conn:
                db_version = await conn.fetchval(
                    "SELECT version FROM tier_plans_meta WHERE id = 1"
                )
            _cache_checked_at = time.monotonic()
            if db_version == _cache_version:
                return
        await _reload_cache(pool)
        _cache_checked_at = time.monotonic()


# ---------------------------------------------------------------------------
# Public async API
# ---------------------------------------------------------------------------

async def get_tier_limits_async(pool, tier: str) -> dict[str, Any]:
    """Return the limits dict for a tier.  Async, checks cache freshness."""
    await _ensure_cache(pool)
    return _cache_tiers.get(tier, _cache_tiers.get("free", _FALLBACK_LIMITS["free"]))


async def get_all_tiers_async(pool) -> list[dict[str, Any]]:
    """Return all tiers as a list of dicts with 'tier' key included, ordered."""
    await _ensure_cache(pool)
    return [
        {"tier": t, **_cache_tiers[t]}
        for t in _cache_tier_order
        if t in _cache_tiers
    ]


async def get_system_config(pool) -> dict[str, Any]:
    """Return typed system_config values.  Checks cache freshness."""
    await _ensure_cache(pool)
    return dict(_cache_system)


async def bump_version(pool) -> int:
    """Increment tier_plans_meta version.  Returns new version."""
    async with pool.acquire() as conn:
        new_ver = await conn.fetchval(
            """
            UPDATE tier_plans_meta SET version = version + 1
            WHERE id = 1
            RETURNING version
            """
        )
    logger.info(f"Tier plans version bumped to {new_ver}")
    return new_ver


async def warm_cache(pool) -> None:
    """Pre-load cache at startup.  Called from app.py lifespan."""
    await _reload_cache(pool)
    logger.info(f"Tier cache warmed (version={_cache_version}, {len(_cache_tiers)} tiers)")


# ---------------------------------------------------------------------------
# Sync compatibility shim
# ---------------------------------------------------------------------------

def get_tier_limits(tier: str) -> dict[str, Any]:
    """Synchronous fallback — reads whatever is in cache right now.

    Prefer ``get_tier_limits_async()`` in route handlers.  This exists
    for the rare synchronous call path.
    """
    if _cache_tiers:
        return _cache_tiers.get(tier, _cache_tiers.get("free", _FALLBACK_LIMITS["free"]))
    return _FALLBACK_LIMITS.get(tier, _FALLBACK_LIMITS["free"])


# Legacy module-level dicts — initially set to fallbacks, updated after
# warm_cache() runs in lifespan.  Code should prefer the async functions
# but these keep old import-sites working during the transition.
TIER_LIMITS: dict[str, dict[str, Any]] = dict(_FALLBACK_LIMITS)
TIER_ORDER: list[str] = ["free", "pro"]


def _sync_legacy_exports() -> None:
    """Copy cache into module-level TIER_LIMITS / TIER_ORDER after reload."""
    global TIER_LIMITS, TIER_ORDER
    if _cache_tiers:
        TIER_LIMITS = dict(_cache_tiers)
    if _cache_tier_order:
        TIER_ORDER = list(_cache_tier_order)
