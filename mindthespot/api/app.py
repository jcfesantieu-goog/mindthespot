"""FastAPI application entrypoint for MindTheSpot."""

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from mindthespot.api.routes import router as api_router

logger = logging.getLogger(__name__)

FRONTEND_DIST_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


def create_app() -> FastAPI:
    """Factory creating configured FastAPI instance."""
    app = FastAPI(
        title="MindTheSpot API",
        description="GCP Spot VM Regime Shift Warning Engine & Fallback Pivot API",
        version="0.1.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
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
