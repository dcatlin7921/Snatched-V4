"""FastAPI application factory with lifespan management.

Creates the Snatched v3 web application: middleware, templates,
static files, route registration, and database pool lifecycle.
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

logger = logging.getLogger("snatched")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager: startup and shutdown.

    Startup: connect PostgreSQL pool, run init_schema, create /data dir.
    Shutdown: close PostgreSQL pool.
    """
    logger.info("Starting Snatched v3...")

    from snatched.db import get_pool, init_schema, seed_builtin_presets

    pool = await get_pool(
        app.state.config.database.postgres_url,
        min_size=app.state.config.database.pool_min_size,
        max_size=app.state.config.database.pool_max_size,
    )
    app.state.db_pool = pool

    await init_schema(pool)
    await seed_builtin_presets(pool)

    data_dir = str(app.state.config.server.data_dir)
    os.makedirs(data_dir, mode=0o750, exist_ok=True)

    logger.info(f"Snatched ready on port {app.state.config.server.port}")

    # Periodic cleanup of expired upload sessions
    async def _session_cleanup_loop():
        from snatched.routes.uploads import cleanup_expired_sessions
        while True:
            await asyncio.sleep(3600)  # Every hour
            try:
                cleaned = await cleanup_expired_sessions(pool, app.state.config)
                if cleaned:
                    logger.info(f"Cleaned up {cleaned} expired upload sessions")
            except Exception as e:
                logger.warning(f"Session cleanup error: {e}")

    cleanup_task = asyncio.create_task(_session_cleanup_loop())

    yield

    cleanup_task.cancel()
    logger.info("Shutting down Snatched...")
    await pool.close()
    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    """FastAPI application factory.

    Returns configured FastAPI instance with middleware, templates,
    static files, and routes registered.

    Called by uvicorn: uvicorn snatched.app:create_app --factory
    """
    from snatched.config import load_config
    from snatched.routes import api, pages

    config = load_config()

    app = FastAPI(
        title="Snatched v3",
        version="3.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    app.state.config = config

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        start = datetime.now()
        response = await call_next(request)
        elapsed = (datetime.now() - start).total_seconds()
        logger.info(
            f"{request.method} {request.url.path} - {response.status_code} ({elapsed:.2f}s)"
        )
        return response

    @app.middleware("http")
    async def add_version_header(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Snatched-Version"] = "3.0"
        return response

    templates_dir = os.path.join(os.path.dirname(__file__), "templates")
    templates = Jinja2Templates(directory=templates_dir)

    # Register Jinja2 filters
    def format_size(bytes_value):
        """Convert bytes to human-readable size string."""
        if bytes_value == 0:
            return "0 B"
        k = 1024
        sizes = ["B", "KB", "MB", "GB", "TB"]
        i = 0
        size = float(bytes_value)
        while size >= k and i < len(sizes) - 1:
            size /= k
            i += 1
        return f"{size:.1f} {sizes[i]}"

    templates.env.filters["format_size"] = format_size
    app.state.templates = templates

    static_dir = os.path.join(os.path.dirname(__file__), "static")
    app.mount("/static", StaticFiles(directory=static_dir, html=False), name="static")

    app.include_router(pages.router, prefix="", tags=["pages"])
    app.include_router(api.router, prefix="/api", tags=["api"])

    @app.exception_handler(HTTPException)
    async def auth_redirect_handler(request: Request, exc: HTTPException):
        """Redirect browsers to /login on 401. API clients get JSON."""
        if exc.status_code == 401:
            accept = request.headers.get("accept", "")
            if "text/html" in accept:
                return RedirectResponse(url="/login", status_code=302)
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        """Catch-all for unhandled exceptions. Always return JSON."""
        logger.error(f"Unhandled exception on {request.method} {request.url.path}: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )

    return app


if __name__ == "__main__":
    import uvicorn

    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
