"""Settings API routes — user-managed domain and sender preferences."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker

from ..services.domain_preference_service import DomainPreferenceService


class DomainPreferenceRequest(BaseModel):
    domain: str


class SenderExclusionRequest(BaseModel):
    sender: str  # full From-header value or bare email address


class DomainPreferencesResponse(BaseModel):
    allowlist: list[str]
    blocklist: list[str]
    exclude_senders: list[str]


def make_settings_router(session_factory: sessionmaker[Session]) -> APIRouter:
    router = APIRouter(tags=["settings"])

    def _prefs_response(prefs) -> DomainPreferencesResponse:
        return DomainPreferencesResponse(
            allowlist=prefs.allowlist,
            blocklist=prefs.blocklist,
            exclude_senders=prefs.exclude_senders,
        )

    @router.get("/settings/domains", response_model=DomainPreferencesResponse)
    def get_domains() -> DomainPreferencesResponse:
        with session_factory() as session:
            prefs = DomainPreferenceService(session).get_preferences()
        return _prefs_response(prefs)

    @router.post("/settings/domains/allowlist", response_model=DomainPreferencesResponse)
    def add_allowlist(body: DomainPreferenceRequest) -> DomainPreferencesResponse:
        try:
            with session_factory() as session:
                svc = DomainPreferenceService(session)
                svc.add_allowlist(body.domain)
                prefs = svc.get_preferences()
                session.commit()
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        return _prefs_response(prefs)

    @router.delete("/settings/domains/allowlist/{domain}", response_model=DomainPreferencesResponse)
    def remove_allowlist(domain: str) -> DomainPreferencesResponse:
        with session_factory() as session:
            svc = DomainPreferenceService(session)
            svc.remove_allowlist(domain)
            prefs = svc.get_preferences()
            session.commit()
        return _prefs_response(prefs)

    @router.post("/settings/domains/blocklist", response_model=DomainPreferencesResponse)
    def add_blocklist(body: DomainPreferenceRequest) -> DomainPreferencesResponse:
        try:
            with session_factory() as session:
                svc = DomainPreferenceService(session)
                svc.add_blocklist(body.domain)
                prefs = svc.get_preferences()
                session.commit()
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        return _prefs_response(prefs)

    @router.delete("/settings/domains/blocklist/{domain}", response_model=DomainPreferencesResponse)
    def remove_blocklist(domain: str) -> DomainPreferencesResponse:
        with session_factory() as session:
            svc = DomainPreferenceService(session)
            svc.remove_blocklist(domain)
            prefs = svc.get_preferences()
            session.commit()
        return _prefs_response(prefs)

    @router.post("/settings/senders/exclude", response_model=DomainPreferencesResponse)
    def add_exclude_sender(body: SenderExclusionRequest) -> DomainPreferencesResponse:
        """Exclude a specific sender email address from all Gmail queries."""
        try:
            with session_factory() as session:
                svc = DomainPreferenceService(session)
                svc.add_exclude_sender(body.sender)
                prefs = svc.get_preferences()
                session.commit()
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        return _prefs_response(prefs)

    @router.delete("/settings/senders/exclude/{email_address}", response_model=DomainPreferencesResponse)
    def remove_exclude_sender(email_address: str) -> DomainPreferencesResponse:
        with session_factory() as session:
            svc = DomainPreferenceService(session)
            svc.remove_exclude_sender(email_address)
            prefs = svc.get_preferences()
            session.commit()
        return _prefs_response(prefs)

    return router
