"""GmailQueryBuilder — builds named candidate queries from language packs + preferences."""

from datetime import datetime, timedelta

from ..config import GmailConfig
from ..languages import DEFAULT_LANGUAGES, MergedLanguageConfig, load_language_packs
from .models import BuiltGmailQuery, DomainPreferences


class GmailQueryBuilder:
    """Builds a list of named Gmail search queries from config and user preferences.

    Query terms come entirely from the active MergedLanguageConfig so that
    enabling additional language packs (e.g. Russian) automatically adds their
    phrases to every query without editing Python source.

    Queries produced:
    - ``strong_shipping``     — high-confidence shipping keywords + package words
    - ``order_lifecycle``     — order-confirmation / lifecycle phrases
    - ``weak_phrases``        — low-precision phrases with extra noise exclusions
    - ``allowlisted_domains`` — broad terms restricted to user-allowlisted senders
                               (only emitted when allowlist is non-empty)
    """

    def __init__(
        self,
        config: GmailConfig,
        domain_preferences: DomainPreferences | None = None,
        lang_config: MergedLanguageConfig | None = None,
    ) -> None:
        self._config = config
        self._prefs = domain_preferences or DomainPreferences()
        if lang_config is None:
            lang_config = load_language_packs(DEFAULT_LANGUAGES)
        self._lang = lang_config

    def build_queries(self) -> list[BuiltGmailQuery]:
        after_date = (
            datetime.now() - timedelta(days=self._config.lookback_days)
        ).strftime("%Y/%m/%d")

        inc = self._lang.query_include_terms
        strong_terms = (
            list(inc.get("strong_shipping", []))
            + list(inc.get("package_words", []))
        )
        order_terms = list(inc.get("order_lifecycle", []))
        weak_terms = list(inc.get("weak_phrases", []))

        shared_exclude_terms = list(self._lang.query_exclude_terms)
        shared_exclude_domains = (
            list(self._config.default_exclude_domains) + list(self._prefs.blocklist)
        )

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
                from_clause = (
                    "(" + " OR ".join(f"from:{d}" for d in restrict_to_domains) + ")"
                )
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
            _build(name="strong_shipping", terms=strong_terms),
            _build(name="order_lifecycle", terms=order_terms),
            _build(
                name="weak_phrases",
                terms=weak_terms,
                extra_excludes=list(self._lang.query_weak_phrase_exclusions),
            ),
        ]

        if self._prefs.allowlist:
            queries.append(
                _build(
                    name="allowlisted_domains",
                    terms=list(self._lang.allowlist_broad_terms),
                    restrict_to_domains=self._prefs.allowlist,
                )
            )

        return queries
