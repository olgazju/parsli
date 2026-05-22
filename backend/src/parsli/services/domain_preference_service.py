"""DomainPreferenceService — manages user-controlled per-domain allow/block rules."""

from sqlalchemy.orm import Session

from ..db.repositories import DomainPreferenceRepository
from ..gmail.domain_normalizer import DomainNormalizer, SenderNormalizer
from ..gmail.models import DomainPreferences


class DomainPreferenceService:
    """CRUD for user-managed domain preferences.

    Args:
        session: SQLAlchemy session (caller manages commit/rollback).
    """

    def __init__(self, session: Session) -> None:
        self._repo = DomainPreferenceRepository(session)
        self._normalizer = DomainNormalizer()
        self._sender_normalizer = SenderNormalizer()

    def get_preferences(self) -> DomainPreferences:
        rows = self._repo.list_all()
        return DomainPreferences(
            allowlist=[r.domain for r in rows if r.preference_type == "allow"],
            blocklist=[r.domain for r in rows if r.preference_type == "block"],
            exclude_senders=[r.domain for r in rows if r.preference_type == "exclude_sender"],
        )

    def add_allowlist(self, raw_domain: str) -> str:
        domain = self._normalizer.normalize(raw_domain)
        self._repo.upsert(domain, "allow")
        return domain

    def remove_allowlist(self, raw_domain: str) -> bool:
        domain = self._normalizer.normalize(raw_domain)
        return self._repo.remove(domain)

    def add_blocklist(self, raw_domain: str) -> str:
        domain = self._normalizer.normalize(raw_domain)
        self._repo.upsert(domain, "block")
        return domain

    def remove_blocklist(self, raw_domain: str) -> bool:
        domain = self._normalizer.normalize(raw_domain)
        return self._repo.remove(domain)

    def add_exclude_sender(self, raw_sender: str) -> str:
        """Add a specific email address to the sender exclusion list.

        Accepts bare addresses or full From-header format ``'Display Name <email>'``.
        """
        email = self._sender_normalizer.normalize(raw_sender)
        self._repo.upsert(email, "exclude_sender")
        return email

    def remove_exclude_sender(self, raw_sender: str) -> bool:
        email = self._sender_normalizer.normalize(raw_sender)
        return self._repo.remove(email)
