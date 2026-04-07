"""Stripe Checkout integration for per-job tier payments.

Routes:
  POST /api/jobs/{job_id}/checkout  — Create Stripe Checkout session
  POST /api/webhooks/stripe         — Handle Stripe webhook events
"""

import json
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from snatched.auth import get_current_user

logger = logging.getLogger("snatched.routes.payment")
router = APIRouter()

# Stripe config from environment
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_ENABLED = bool(STRIPE_SECRET_KEY)

# Tier pricing in cents (Stripe uses smallest currency unit)
TIER_PRICES = {
    "rescue": 499,   # $4.99
    "full": 999,     # $9.99
}

# A la carte prices in cents
ADDON_PRICES = {
    "gps": 299,       # $2.99
    "overlays": 199,   # $1.99
    "chats": 399,      # $3.99
    "stories": 199,    # $1.99
    "xmp": 199,        # $1.99
}

ADDON_LABELS = {
    "gps": "GPS Metadata",
    "overlays": "Overlay Burn",
    "chats": "Chat Export",
    "stories": "Story Archive",
    "xmp": "XMP Sidecars",
}


def _get_stripe():
    """Lazy-load stripe module to avoid import errors when not installed."""
    try:
        import stripe
        stripe.api_key = STRIPE_SECRET_KEY
        return stripe
    except ImportError:
        raise HTTPException(503, "Stripe is not installed")


@router.post("/jobs/{job_id}/checkout")
async def create_checkout(
    job_id: int,
    request: Request,
    username: str = Depends(get_current_user),
) -> dict:
    """Create a Stripe Checkout session for a paid tier or a la carte add-ons.

    Request body: {
        "tier": "rescue" | "full" | "alacarte",
        "add_ons": ["gps", "overlays", ...],
        "options": { ... }
    }

    Returns: { "checkout_url": "https://checkout.stripe.com/..." }
    """
    if not STRIPE_ENABLED:
        raise HTTPException(503, "Payments are not configured")

    stripe = _get_stripe()
    pool = request.app.state.db_pool

    # Parse body
    try:
        body = await request.json()
        tier = body.get("tier", "rescue")
        add_ons = body.get("add_ons", [])
        options = body.get("options", {})
    except Exception as e:
        raise HTTPException(400, f"Invalid request body: {e}")

    # Verify job ownership and status
    async with pool.acquire() as conn:
        job_row = await conn.fetchrow(
            """
            SELECT pj.id, pj.status, pj.payment_status
            FROM processing_jobs pj
            JOIN users u ON pj.user_id = u.id
            WHERE pj.id = $1 AND u.username = $2
            """,
            job_id, username,
        )

    if not job_row:
        raise HTTPException(404, "Job not found")

    if job_row["status"] != "scanned":
        raise HTTPException(400, "Job is not in a configurable state")

    if job_row["payment_status"] == "paid":
        raise HTTPException(400, "Job has already been paid for")

    # Build line items
    line_items = []

    if tier in ("rescue", "full"):
        line_items.append({
            "price_data": {
                "currency": "usd",
                "product_data": {
                    "name": "Memory Rescue" if tier == "rescue" else "Complete Archive",
                    "description": (
                        "Dates + GPS + Overlays (memories only)"
                        if tier == "rescue"
                        else "Complete Snapchat export — all lanes, all enrichment"
                    ),
                },
                "unit_amount": TIER_PRICES[tier],
            },
            "quantity": 1,
        })
    elif tier == "alacarte":
        valid_addons = set(ADDON_PRICES.keys())  # Only addons with defined prices
        add_ons = [a for a in add_ons if a in valid_addons]
        if not add_ons:
            raise HTTPException(400, "No add-ons selected")

        for addon in add_ons:
            line_items.append({
                "price_data": {
                    "currency": "usd",
                    "product_data": {
                        "name": ADDON_LABELS.get(addon, addon.replace("_", " ").title()),
                    },
                    "unit_amount": ADDON_PRICES[addon],
                },
                "quantity": 1,
            })
    else:
        raise HTTPException(400, f"Invalid tier: {tier}")

    # Determine base URL for success/cancel redirects
    base_url = str(request.base_url).rstrip("/")

    # Store tier/options in metadata so webhook can resume processing
    metadata = {
        "job_id": str(job_id),
        "username": username,
        "tier": tier,
        "add_ons": json.dumps(add_ons),
        "options": json.dumps(options),
    }

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=line_items,
            mode="payment",
            success_url=f"{base_url}/snatchedmemories/{job_id}?payment=success",
            cancel_url=f"{base_url}/configure/{job_id}?payment=cancelled",
            metadata=metadata,
        )
    except Exception as e:
        logger.error("Stripe checkout creation failed: %s", e, exc_info=True)
        raise HTTPException(502, "Failed to create checkout session")

    # Mark payment as pending
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE processing_jobs
            SET payment_status = 'pending', job_tier = $1, add_ons = $2,
                payment_intent_id = $3
            WHERE id = $4
            """,
            tier,
            json.dumps(add_ons),
            session.id,
            job_id,
        )

    return {"checkout_url": session.url}


@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request):
    """Handle Stripe webhook events (payment confirmation).

    On successful payment, marks job as paid and triggers processing
    via the configure endpoint.
    """
    if not STRIPE_ENABLED:
        raise HTTPException(503, "Payments are not configured")

    stripe = _get_stripe()

    # Verify webhook signature
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        raise HTTPException(400, "Invalid payload")
    except Exception as sig_err:
        # stripe.error.SignatureVerificationError (SDK v5-6) or
        # stripe.SignatureVerificationError (SDK v7+)
        if "Signature" in type(sig_err).__name__ or "signature" in str(sig_err).lower():
            raise HTTPException(400, "Invalid signature")
        raise HTTPException(400, f"Webhook verification failed: {type(sig_err).__name__}")

    # Handle checkout.session.completed
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        metadata = session.get("metadata", {})
        job_id = int(metadata.get("job_id", 0))
        username = metadata.get("username", "")
        tier = metadata.get("tier", "rescue")
        add_ons = json.loads(metadata.get("add_ons", "[]"))
        options = json.loads(metadata.get("options", "{}"))

        if not job_id or not username:
            logger.warning("Stripe webhook missing job_id/username in metadata")
            return JSONResponse({"status": "ignored"})

        pool = request.app.state.db_pool

        # Mark as paid
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE processing_jobs
                SET payment_status = 'paid',
                    payment_intent_id = $1
                WHERE id = $2
                """,
                session.get("payment_intent"),
                job_id,
            )

        logger.info("Job %d payment confirmed (tier=%s). Starting processing...", job_id, tier)

        # Save user preferences from checkout metadata
        has_gps = tier in ("rescue", "full") or "gps" in add_ons
        has_overlays = tier in ("rescue", "full") or "overlays" in add_ons
        has_chats = tier == "full" or "chats" in add_ons
        has_xmp = tier == "full" or "xmp" in add_ons

        async with pool.acquire() as conn:
            user_id = await conn.fetchval(
                "SELECT id FROM users WHERE username = $1", username
            )
        if user_id:
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO user_preferences
                        (user_id, burn_overlays, dark_mode_pngs, exif_enabled, xmp_enabled,
                         gps_window_seconds, folder_style, gps_precision, hide_sent_to,
                         chat_timestamps, chat_cover_pages, chat_text, chat_png)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                    ON CONFLICT (user_id) DO UPDATE SET
                        burn_overlays = EXCLUDED.burn_overlays,
                        dark_mode_pngs = EXCLUDED.dark_mode_pngs,
                        exif_enabled = EXCLUDED.exif_enabled,
                        xmp_enabled = EXCLUDED.xmp_enabled,
                        gps_window_seconds = EXCLUDED.gps_window_seconds,
                        folder_style = EXCLUDED.folder_style,
                        gps_precision = EXCLUDED.gps_precision,
                        hide_sent_to = EXCLUDED.hide_sent_to,
                        chat_timestamps = EXCLUDED.chat_timestamps,
                        chat_cover_pages = EXCLUDED.chat_cover_pages,
                        chat_text = EXCLUDED.chat_text,
                        chat_png = EXCLUDED.chat_png,
                        updated_at = NOW()
                    """,
                    user_id,
                    has_overlays,
                    bool(options.get("dark_mode_pngs", False)),
                    has_gps or has_overlays,
                    has_xmp,
                    300,
                    str(options.get("folder_style", "year_month")),
                    str(options.get("gps_precision", "exact")),
                    bool(options.get("hide_sent_to", False)),
                    True,   # chat_timestamps
                    True,   # chat_cover_pages
                    has_chats,
                    has_chats,
                )

        has_stories = tier == "full" or "stories" in add_ons
        needs_enrich = has_gps or has_overlays

        lanes = ["memories"]
        if has_chats:
            lanes.append("chats")
        if has_stories:
            lanes.append("stories")

        remaining_phases = ["match"]
        if needs_enrich:
            remaining_phases.append("enrich")
        remaining_phases.append("export")

        # Enqueue to ARQ
        arq_pool = getattr(request.app.state, "arq_pool", None)
        if arq_pool:
            # Atomic update: only transitions from 'scanned' to 'queued'
            async with pool.acquire() as conn:
                updated = await conn.fetchval(
                    """
                    UPDATE processing_jobs
                    SET lanes_requested = $1, phases_requested = $2,
                        job_tier = $3, add_ons = $4, status = 'queued',
                        retention_expires_at = NULL
                    WHERE id = $5 AND status = 'scanned'
                    RETURNING id
                    """,
                    lanes,
                    ["ingest"] + remaining_phases,
                    tier,
                    json.dumps(add_ons),
                    job_id,
                )

            if updated:
                await arq_pool.enqueue_job(
                    "run_remaining_phases",
                    job_id,
                    username,
                    remaining_phases,
                    _queue_name="snatched:default",
                )
                logger.info("Job %d enqueued for processing after payment", job_id)
            else:
                logger.info("Job %d already transitioned from scanned (duplicate webhook?)", job_id)
        else:
            logger.warning("ARQ unavailable — job %d requires manual start after payment", job_id)

    return JSONResponse({"status": "ok"})
