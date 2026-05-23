"""FastAPI application factory for Parsli."""

import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from ..config import AppConfig
from ..db.session import ensure_schema, make_engine, make_session_factory
from ..gmail.auth import GmailOAuthManager
from .routes_dashboard import make_dashboard_router
from .routes_settings import make_settings_router
from .routes_sync import make_sync_router


def create_app(config: AppConfig | None = None) -> FastAPI:
    """Create and wire up the FastAPI application.

    Args:
        config: AppConfig instance. Loaded from environment if None.
    """
    if config is None:
        config = AppConfig()

    engine = make_engine(config.database.sqlite_path)
    ensure_schema(engine)
    session_factory = make_session_factory(engine)

    oauth = GmailOAuthManager(
        credentials_path=config.credentials_path,
        tokens_dir=config.tokens_dir,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):  # noqa: ANN202
        yield

    app = FastAPI(
        title="Parsli",
        description="Local-first parcel tracking",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(make_dashboard_router(session_factory), prefix="/api")
    app.include_router(make_sync_router(config, oauth, session_factory), prefix="/api")
    app.include_router(make_settings_router(session_factory), prefix="/api")

    frontend_dir = Path(__file__).parents[4] / "frontend"

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def serve_frontend() -> str:
        html_path = frontend_dir / "index.html"
        if html_path.exists():
            return html_path.read_text()
        return "<h1>Parsli</h1><p>Frontend not found.</p>"

    return app


# Default app instance for uvicorn/gunicorn
app = create_app()
