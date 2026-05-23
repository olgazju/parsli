"""Language pack system — loads YAML language packs and merges them into a
single MergedLanguageConfig consumed by EmailCleaner, RuleEngine,
IdentifierExtractor, and GmailQueryBuilder.

Language packs live as ``<code>.yaml`` files alongside this module.
Each pack defines phrase/pattern lists for one locale; the loader merges
all active packs by appending their lists in order.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

DEFAULT_LANGUAGES: list[str] = ["en", "he"]
_PACKS_DIR = Path(__file__).parent


class StatusPatterns(BaseModel):
    """Per-status raw regex pattern lists contributed by a language pack."""

    delivered: list[str] = Field(default_factory=list)
    action_required: list[str] = Field(default_factory=list)
    ready_for_pickup: list[str] = Field(default_factory=list)
    payment_required: list[str] = Field(default_factory=list)
    out_for_delivery: list[str] = Field(default_factory=list)
    customs_released: list[str] = Field(default_factory=list)
    customs_pending: list[str] = Field(default_factory=list)
    handed_to_local_carrier: list[str] = Field(default_factory=list)
    arrived_in_destination_country: list[str] = Field(default_factory=list)
    delayed_or_problem: list[str] = Field(default_factory=list)
    in_transit: list[str] = Field(default_factory=list)
    received_by_carrier: list[str] = Field(default_factory=list)
    shipped: list[str] = Field(default_factory=list)
    order_confirmed: list[str] = Field(default_factory=list)


class LanguagePack(BaseModel):
    """Single-locale configuration loaded from a YAML file.

    All pattern fields contain raw regex strings (not pre-compiled).
    Phrase fields (e.g. shipping_signals) may also use regex syntax;
    they are combined into a single alternation at construction time.
    """

    code: str
    shipping_signals: list[str] = Field(default_factory=list)
    footer_patterns: list[str] = Field(default_factory=list)
    unsubscribe_patterns: list[str] = Field(default_factory=list)
    billing_exclusion_phrases: list[str] = Field(default_factory=list)
    shipping_override_phrases: list[str] = Field(default_factory=list)
    tracking_context_words: list[str] = Field(default_factory=list)
    order_label_patterns: dict[str, str] = Field(default_factory=dict)
    query_include_terms: dict[str, list[str]] = Field(default_factory=dict)
    query_exclude_terms: list[str] = Field(default_factory=list)
    query_weak_phrase_exclusions: list[str] = Field(default_factory=list)
    allowlist_broad_terms: list[str] = Field(default_factory=list)
    status_patterns: StatusPatterns = Field(default_factory=StatusPatterns)


class MergedLanguageConfig(BaseModel):
    """Merged view of one or more LanguagePacks.

    Produced by load_language_packs(); consumed by processing components.
    List fields are the concatenation of all active packs in load order.
    Dict fields (order_label_patterns, query_include_terms) are merged
    by key — later packs extend earlier ones for the same key.
    """

    active_codes: list[str] = Field(default_factory=list)
    shipping_signals: list[str] = Field(default_factory=list)
    footer_patterns: list[str] = Field(default_factory=list)
    unsubscribe_patterns: list[str] = Field(default_factory=list)
    billing_exclusion_phrases: list[str] = Field(default_factory=list)
    shipping_override_phrases: list[str] = Field(default_factory=list)
    tracking_context_words: list[str] = Field(default_factory=list)
    order_label_patterns: dict[str, str] = Field(default_factory=dict)
    query_include_terms: dict[str, list[str]] = Field(default_factory=dict)
    query_exclude_terms: list[str] = Field(default_factory=list)
    query_weak_phrase_exclusions: list[str] = Field(default_factory=list)
    allowlist_broad_terms: list[str] = Field(default_factory=list)
    status_patterns: StatusPatterns = Field(default_factory=StatusPatterns)


def load_language_packs(
    codes: list[str],
    packs_dir: Path | None = None,
) -> MergedLanguageConfig:
    """Load and merge language packs by code.

    Args:
        codes: Language codes to load in order, e.g. ``["en", "he"]``.
        packs_dir: Directory containing ``<code>.yaml`` files.
                   Defaults to the bundled ``languages/`` directory.

    Returns:
        A MergedLanguageConfig combining all active packs.

    Raises:
        FileNotFoundError: If a requested language pack YAML does not exist.
    """
    if packs_dir is None:
        packs_dir = _PACKS_DIR

    merged = MergedLanguageConfig(active_codes=list(codes))
    for code in codes:
        pack_path = packs_dir / f"{code}.yaml"
        if not pack_path.exists():
            raise FileNotFoundError(f"Language pack not found: {pack_path}")
        raw = yaml.safe_load(pack_path.read_text(encoding="utf-8"))
        pack = LanguagePack.model_validate(raw)
        _merge_into(merged, pack)

    return merged


def _merge_into(merged: MergedLanguageConfig, pack: LanguagePack) -> None:
    merged.shipping_signals.extend(pack.shipping_signals)
    merged.footer_patterns.extend(pack.footer_patterns)
    merged.unsubscribe_patterns.extend(pack.unsubscribe_patterns)
    merged.billing_exclusion_phrases.extend(pack.billing_exclusion_phrases)
    merged.shipping_override_phrases.extend(pack.shipping_override_phrases)
    merged.tracking_context_words.extend(pack.tracking_context_words)
    merged.order_label_patterns.update(pack.order_label_patterns)
    for group, terms in pack.query_include_terms.items():
        merged.query_include_terms.setdefault(group, []).extend(terms)
    merged.query_exclude_terms.extend(pack.query_exclude_terms)
    merged.query_weak_phrase_exclusions.extend(pack.query_weak_phrase_exclusions)
    merged.allowlist_broad_terms.extend(pack.allowlist_broad_terms)
    for field in StatusPatterns.model_fields:
        getattr(merged.status_patterns, field).extend(
            getattr(pack.status_patterns, field)
        )
