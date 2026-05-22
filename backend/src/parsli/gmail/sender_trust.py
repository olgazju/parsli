"""Sender trust scoring for candidate preclassification.

This module assigns a trust level to email senders based on their domain.
Trust is a scoring signal only — it never hard-blocks candidates.

Scoring:
  +4  known shipping/carrier domain
  +3  known ecommerce domain
  +1  generic / corporate domain (default)
  -2  free email provider
  -10 user-blocklisted domain → BLOCKED
"""

from enum import Enum

from pydantic import BaseModel


# ── Domain lists ───────────────────────────────────────────────────────────────

KNOWN_SHIPPING_DOMAINS: frozenset[str] = frozenset({
    # Israel
    "israelpost.co.il",
    "postil.co.il",
    "post.co.il",
    "mail.hfd.co.il",
    "hfd.co.il",
    "e-cargo.co.il",
    "starlinks.app",
    # International carriers
    "amazon.com",
    "dhl.com",
    "fedex.com",
    "ups.com",
    "royalmail.com",
    "dpd.com",
    "parcelforce.com",
    "gls-group.eu",
})

KNOWN_ECOMMERCE_DOMAINS: frozenset[str] = frozenset({
    "asos.com",
    "nextdirect.com",
    "next.co.il",
    "hoodies.co.il",
    "caretobeauty.com",
    "aliexpress.com",
    "shein.com",
    "ebay.com",
    "amazon.co.uk",
    "amazon.de",
    "amazon.fr",
    "amazon.es",
    "amazon.it",
    "zara.com",
    "hmgroup.com",
    "saasplaybook.com",
})

FREE_EMAIL_PROVIDER_DOMAINS: frozenset[str] = frozenset({
    "gmail.com",
    "googlemail.com",
    "outlook.com",
    "hotmail.com",
    "hotmail.co.il",
    "live.com",
    "yahoo.com",
    "yahoo.co.il",
    "walla.co.il",
    "walla.com",
    "mail.ru",
    "icloud.com",
    "me.com",
    "protonmail.com",
    "proton.me",
})


# ── DTOs ───────────────────────────────────────────────────────────────────────

class SenderTrustLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    BLOCKED = "blocked"


class SenderTrustResult(BaseModel):
    sender_domain: str | None
    trust_level: SenderTrustLevel
    trust_score: int
    reasons: list[str]


# ── Scorer ─────────────────────────────────────────────────────────────────────

def _matches_any(domain: str, domain_set: frozenset[str]) -> bool:
    """Return True if domain equals or is a subdomain of any entry in domain_set."""
    return domain in domain_set or any(
        domain.endswith(f".{d}") for d in domain_set
    )


class SenderTrustScorer:
    """Assigns a trust level and score to a sender domain.

    Args:
        user_blocklist: Domains the user has explicitly blocked (from
            DomainPreferences.blocklist). These map to BLOCKED immediately.
    """

    def __init__(self, user_blocklist: frozenset[str] = frozenset()) -> None:
        self._user_blocklist = user_blocklist

    def score(self, sender_domain: str | None) -> SenderTrustResult:
        if sender_domain is None:
            return SenderTrustResult(
                sender_domain=None,
                trust_level=SenderTrustLevel.MEDIUM,
                trust_score=0,
                reasons=["no sender domain available"],
            )

        domain = sender_domain.lower().strip()
        reasons: list[str] = []

        if _matches_any(domain, self._user_blocklist):
            return SenderTrustResult(
                sender_domain=domain,
                trust_level=SenderTrustLevel.BLOCKED,
                trust_score=-10,
                reasons=["user-blocklisted domain"],
            )

        score = 0

        if _matches_any(domain, KNOWN_SHIPPING_DOMAINS):
            score += 4
            reasons.append("known shipping/carrier domain")
        elif _matches_any(domain, KNOWN_ECOMMERCE_DOMAINS):
            score += 3
            reasons.append("known ecommerce domain")
        elif _matches_any(domain, FREE_EMAIL_PROVIDER_DOMAINS):
            score -= 2
            reasons.append("free email provider")
        else:
            score += 1
            reasons.append("generic/corporate domain")

        if score >= 3:
            level = SenderTrustLevel.HIGH
        elif score >= 0:
            level = SenderTrustLevel.MEDIUM
        else:
            level = SenderTrustLevel.LOW

        return SenderTrustResult(
            sender_domain=domain,
            trust_level=level,
            trust_score=score,
            reasons=reasons,
        )
