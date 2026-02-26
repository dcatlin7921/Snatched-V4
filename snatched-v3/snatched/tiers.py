"""Tier definitions and quota limits for Snatched v3.

All tier-related constants live here so they can be imported by any
route module without circular dependencies.
"""

TIER_LIMITS = {
    "free": {
        "label": "Free",
        "storage_gb": 10,
        "max_upload_bytes": 5 * 1024 ** 3,          # 5 GB per upload
        "max_upload_label": "5 GB",
        "retention_days": 30,
        "concurrent_jobs": 1,
        "bulk_upload": False,
        "color": "var(--text-muted)",
    },
    "pro": {
        "label": "Pro",
        "storage_gb": 50,
        "max_upload_bytes": 25 * 1024 ** 3,          # 25 GB per upload
        "max_upload_label": "25 GB",
        "retention_days": 180,
        "concurrent_jobs": 3,
        "bulk_upload": True,
        "color": "var(--snap-yellow)",
    },
}

TIER_ORDER = ["free", "pro"]


def get_tier_limits(tier: str) -> dict:
    """Return the limits dict for a tier, defaulting to 'free'."""
    return TIER_LIMITS.get(tier, TIER_LIMITS["free"])
