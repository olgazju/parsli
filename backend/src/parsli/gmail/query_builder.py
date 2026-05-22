"""GmailQueryBuilder — builds named candidate queries from vocabulary + preferences."""

from datetime import datetime, timedelta

from ..config import GmailConfig
from .models import BuiltGmailQuery, DomainPreferences

# Broad terms used in the allowlist query (when the user has explicit trusted domains)
_ALLOWLIST_BROAD_TERMS: list[str] = [
    "shipment", "order", "tracking", "delivery", "parcel",
    "משלוח", "הזמנה",
]


class GmailQueryBuilder:
    """Builds a list of named Gmail search queries from config and user preferences.

    Queries produced:
    - ``strong_shipping``   — high-confidence shipping keywords + package words
    - ``order_lifecycle``   — order-confirmation / lifecycle phrases
    - ``weak_phrases``      — low-precision phrases with extra noise exclusions
    - ``allowlisted_domains`` — broad terms restricted to user-allowlisted senders
                               (only emitted when allowlist is non-empty)
    """

    def __init__(
        self,
        config: GmailConfig,
        domain_preferences: DomainPreferences | None = None,
    ) -> None:
        self._config = config
        self._prefs = domain_preferences or DomainPreferences()

    def build_queries(self) -> list[BuiltGmailQuery]:
        after_date = (
            datetime.now() - timedelta(days=self._config.lookback_days)
        ).strftime("%Y/%m/%d")

        vocab = self._config.vocabulary
        shared_exclude_terms = list(vocab.exclude_terms)
        shared_exclude_domains = list(vocab.default_exclude_domains) + list(self._prefs.blocklist)

        def _build(
            name: str,
            terms: list[str],
            extra_excludes: list[str] | None = None,
            restrict_to_domains: list[str] | None = None,
        ) -> BuiltGmailQuery:
            all_exclude_terms = shared_exclude_terms + (extra_excludes or [])
            parts: list[str] = []

            if self._config.query_category_filter:
                parts.append(self._config.query_category_filter)

            keyword_clause = "(" + " OR ".join(terms) + ")"

            if restrict_to_domains:
                from_clause = "(" + " OR ".join(f"from:{d}" for d in restrict_to_domains) + ")"
                parts.append(f"{keyword_clause} {from_clause}")
            else:
                parts.append(keyword_clause)

            for term in all_exclude_terms:
                parts.append(f"-{term}")

            for domain in shared_exclude_domains:
                parts.append(f"-from:{domain}")

            for sender in self._prefs.exclude_senders:
                parts.append(f"-from:{sender}")

            parts.append(f"after:{after_date}")

            return BuiltGmailQuery(
                name=name,
                query=" ".join(parts),
                terms=terms,
                exclude_terms=all_exclude_terms,
                exclude_domains=shared_exclude_domains,
            )

        queries: list[BuiltGmailQuery] = [
            _build(
                name="strong_shipping",
                terms=vocab.strong_shipping + vocab.package_words,
            ),
            _build(
                name="order_lifecycle",
                terms=vocab.order_lifecycle,
            ),
            _build(
                name="weak_phrases",
                terms=vocab.weak_phrases,
                extra_excludes=vocab.weak_phrase_exclusions,
            ),
        ]

        if self._prefs.allowlist:
            queries.append(
                _build(
                    name="allowlisted_domains",
                    terms=_ALLOWLIST_BROAD_TERMS,
                    restrict_to_domains=self._prefs.allowlist,
                )
            )

        return queries
