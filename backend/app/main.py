"""
Main FastAPI application entry point for Recruitment Follow-Up Agent.
Binds strictly to loopback interface 127.0.0.1.
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables from .env file if present
load_dotenv()

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from backend.app.api.routes import router as api_router, security_service, daily_review_engine
from backend.app.api.middleware import LoopbackSecurityMiddleware
from backend.app.api.logging_config import setup_redacted_logger

logger = setup_redacted_logger("main")

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing application startup checks...")
    if os.environ.get("ENVIRONMENT") != "test":
        try:
            res = daily_review_engine.check_and_run_startup_catchup()
            if res:
                logger.info(f"Startup Daily Review Catch-Up executed: {res.to_dict()}")
        except Exception as e:
            logger.error(f"Startup Daily Review check encountered error: {e}")
        daily_review_engine.start_scheduler()
    yield
    if os.environ.get("ENVIRONMENT") != "test":
        daily_review_engine.stop_scheduler()
    logger.info("Application shutdown complete.")

app = FastAPI(
    title="Recruitment Follow-Up Agent API",
    description="Local-only recruitment follow-up management backend bound exclusively to 127.0.0.1",
    version="1.0.0",
    docs_url="/docs",
    redoc_url=None,
    lifespan=lifespan
)

# CORS middleware restricted strictly to 127.0.0.1 local loopback ports
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Loopback security middleware (Host, Origin, CSRF)
app.add_middleware(LoopbackSecurityMiddleware, security_service=security_service)

# Register API routes
app.include_router(api_router)


# Serve built frontend static assets if dist exists
dist_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../frontend/dist"))
if os.path.exists(dist_dir):
    app.mount("/assets", StaticFiles(directory=os.path.join(dist_dir, "assets")), name="assets")

    @app.get("/favicon.svg", response_class=FileResponse, include_in_schema=False)
    def serve_favicon():
        return FileResponse(os.path.join(dist_dir, "favicon.svg"), media_type="image/svg+xml")

    @app.get("/icons.svg", response_class=FileResponse, include_in_schema=False)
    def serve_icon_sprite():
        return FileResponse(os.path.join(dist_dir, "icons.svg"), media_type="image/svg+xml")

    @app.get("/clifyx-logo.png", response_class=FileResponse, include_in_schema=False)
    def serve_clifyx_logo():
        return FileResponse(os.path.join(dist_dir, "clifyx-logo.png"), media_type="image/png")

    @app.get("/", response_class=FileResponse)
    def serve_frontend_root():
        return FileResponse(os.path.join(dist_dir, "index.html"))


def run_server(host: str = "127.0.0.1", port: int = 8000):
    """Run uvicorn server bound strictly to loopback interface."""
    if host != "127.0.0.1":
        logger.error("Attempted to bind to non-loopback host! Forcing 127.0.0.1.")
        host = "127.0.0.1"

    logger.info(f"Starting Recruitment Follow-Up Agent backend on http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_config=None)


if __name__ == "__main__":
    run_server()
