"""FastAPI application factory for Parsli."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..config import AppConfig
from ..db.session import ensure_schema, make_engine, make_session_factory
from ..gmail.auth import GmailOAuthManager
from .routes_dashboard import make_dashboard_router
from .routes_dev import make_dev_router
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
    app.include_router(make_dev_router(session_factory), prefix="/api")

    return app


# Default app instance for uvicorn/gunicorn
app = create_app()
