"""Sync API routes."""

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker

from ..config import AppConfig
from ..gmail.auth import GmailOAuthManager, TokenMissingError
from ..privacy.hashing import sha256_hex
from ..services.sync_service import SyncService


class SyncResult(BaseModel):
    account_id: str
    total_fetched: int | None = None
    new_ingested: int
    processed: int


class ConnectAccountResponse(BaseModel):
    auth_url: str
    state: str


def make_sync_router(
    config: AppConfig,
    oauth: GmailOAuthManager,
    session_factory: sessionmaker[Session],
) -> APIRouter:
    router = APIRouter(tags=["sync"])

    def _make_sync_service() -> SyncService:
        return SyncService(config, oauth, session_factory)

    @router.get("/status")
    def status() -> dict:
        """Return application readiness."""
        return {
            "credentials_configured": oauth.is_configured,
            "version": "0.1.0",
        }

    @router.post("/accounts/connect", response_model=ConnectAccountResponse)
    def connect_account() -> ConnectAccountResponse:
        """Initiate a Gmail OAuth2 flow."""
        if not oauth.is_configured:
            raise HTTPException(
                status_code=503,
                detail="credentials.json not configured — place it in the app directory",
            )
        auth_url, state = oauth.start_auth_flow()
        return ConnectAccountResponse(auth_url=auth_url, state=state)

    @router.get("/auth/callback", response_class=HTMLResponse, include_in_schema=False)
    def auth_callback(code: str, state: str) -> str:
        """Handle the OAuth2 redirect from Google."""
        try:
            email, credentials = oauth.complete_auth_flow(code, state)
        except KeyError:
            return _auth_page(success=False, message="Invalid or expired session")
        except Exception as exc:
            return _auth_page(success=False, message=str(exc))

        oauth.save_token(email, credentials)
        return _auth_page(success=True)

    def _sync_or_401(account_id: str, fn) -> SyncResult:
        """Run a sync function, converting TokenMissingError into a 401 with auth_url."""
        try:
            result = fn()
        except TokenMissingError:
            # Return the auth URL so the frontend/client can redirect the user.
            auth_url, _ = oauth.start_auth_flow()
            raise HTTPException(
                status_code=401,
                detail={"error": "token_missing", "auth_url": auth_url},
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return SyncResult(account_id=account_id, **result)

    @router.post("/sync/initial/{account_id}", response_model=SyncResult)
    def initial_sync(account_id: str) -> SyncResult:
        """Run full lookback sync for an account."""
        return _sync_or_401(account_id, lambda: _make_sync_service().initial_sync(account_id))

    @router.post("/sync/incremental/{account_id}", response_model=SyncResult)
    def incremental_sync(account_id: str) -> SyncResult:
        """Sync only new messages since the last run."""
        return _sync_or_401(account_id, lambda: _make_sync_service().incremental_sync(account_id))

    return router


def _auth_page(success: bool, message: str = "") -> str:
    if success:
        script = "window.opener?.postMessage({type:'parsli_auth_success'},'*');window.close();"
        body = "<p>Connected! You can close this tab.</p>"
    else:
        script = (
            f"window.opener?.postMessage("
            f"{{type:'parsli_auth_error',message:{json.dumps(message)}}},'*');"
        )
        body = f"<p>Error: {message}</p>"
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<title>Parsli — Auth</title></head><body>
<script>{script}</script>{body}</body></html>"""
