import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from mindthespot.api.routes import get_spot_service
from mindthespot.api.routes import router as api_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

FRONTEND_DIST_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager to pre-warm cache on application boot."""
    logger.info("Initializing MindTheSpot API application lifespan...")
    service = get_spot_service()
    if os.getenv("SYNC_PREWARM", "false").lower() in ("true", "1", "yes"):
        logger.info("Performing synchronous cache pre-warm from BigQuery...")
        success = service.warm_cache_from_bigquery()
        status = service.get_cache_status()
        if success:
            logger.info(
                "BigQuery cache pre-warm succeeded: source=%s, pools=%d, prices=%d, preemptions=%d",
                status["source"],
                status["total_pools_cached"],
                status["total_price_intervals"],
                status["total_preemption_points"],
            )
        else:
            logger.error(
                "BigQuery cache pre-warm failed or incomplete. Current source=%s, pools=%d",
                status["source"],
                status["total_pools_cached"],
            )
    else:
        logger.info("Triggering asynchronous background pre-warm from BigQuery...")
        service.trigger_background_sync()
    yield
    logger.info("MindTheSpot API shutting down.")


def create_app() -> FastAPI:
    """Factory creating configured FastAPI instance."""
    app = FastAPI(
        title="MindTheSpot API",
        description="GCP Spot VM Regime Shift Warning Engine & Fallback Pivot API",
        version="0.1.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    # CORS configuration for frontend dev server
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include REST API endpoints
    app.include_router(api_router)

    # Mount static assets if compiled frontend exists
    if FRONTEND_DIST_DIR.exists():
        assets_dir = FRONTEND_DIST_DIR / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def serve_spa_frontend(full_path: str):
            # Don't intercept API routes
            if full_path.startswith("api"):
                return None
            index_path = FRONTEND_DIST_DIR / "index.html"
            if index_path.exists():
                return FileResponse(index_path)
            return {"detail": "Frontend build index.html not found"}

    return app


app = create_app()
