import re

from pydantic import BaseModel

from ..languages import DEFAULT_LANGUAGES, MergedLanguageConfig, load_language_packs


class TrackingIdentifier(BaseModel):
    value: str
    carrier_hint: str | None = None
    confidence: float = 1.0
    source: str | None = None  # "body" | "body_near_keyword"


class OrderIdentifier(BaseModel):
    value: str
    merchant_hint: str | None = None
    confidence: float = 1.0


# Pure-digit carriers (FedEx 15-digit, DHL 10-11 digit) and ASOS require a
# nearby shipping keyword — without context they match phone numbers, billing
# IDs, and CSS font-family names (e.g. "asossansdisplay").
_CONTEXT_REQUIRED: frozenset[str] = frozenset({"fedex", "dhl", "asos"})

_CONTEXT_WINDOW = 150  # chars searched on each side of a candidate match

# Israeli mobile numbers (054-xxxxxxx, 050-xxxxxxx, etc.) are 10-digit numbers
# that look like DHL tracking numbers. Exclude them regardless of context.
_ISRAELI_MOBILE_RE = re.compile(r"^05\d{8}$")

# Tracking number format patterns — carrier-specific, not language-specific.
# Ordered: most-specific first so the generic fallback only fires when nothing else matches.
_TRACKING_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("ups", re.compile(r"\b1Z[A-Z0-9]{16}\b", re.IGNORECASE)),
    # Israel Post registered/EMS: 2-letter origin code + 8-10 digits + 1-2 letter check/country.
    # Standard UPU is 2+8+2=12; real Israel Post numbers in use are 2+9+2 or 2+10+1 (13 chars).
    ("israel_post", re.compile(r"\b[A-Z]{2}\d{8,10}[A-Z]{1,2}\b")),
    # HFD Israel logistics
    ("hfd", re.compile(r"\bECSA\d{7,12}\b", re.IGNORECASE)),
    # ASOS carrier codes: must start with a digit after "ASO" to exclude CSS font
    # names like "asossansdisplay". Real codes look like ASO1006GB02687136001.
    ("asos", re.compile(r"\bASO\d[A-Z0-9]{10,18}\b", re.IGNORECASE)),
    # FedEx (15 digits)
    ("fedex", re.compile(r"\b\d{15}\b")),
    # DHL Express (10-11 digits)
    ("dhl", re.compile(r"\b\d{10,11}\b")),
]

# Words that can never be order numbers.
_ORDER_JUNK: frozenset[str] = frozenset({
    "HELLO", "CONFIRMATION", "DETAILS", "ORDER", "SUMMARY", "CONTAINS",
    "HTTPS", "REFERENCE", "ISSUES", "NUMBER", "TOTAL", "RECEIVED",
    "SUPPORT", "TERMS", "POLICY", "INFO", "HERE", "CLICK",
})

# Amazon format pattern — carrier-specific, not language-specific.
_AMAZON_ORDER_PATTERN: tuple[str, re.Pattern[str]] = (
    "amazon",
    re.compile(r"\b\d{3}-\d{7}-\d{7}\b"),
)


class IdentifierExtractor:
    """Extracts tracking and order number candidates from email text.

    Patterns for context detection and order label matching are built from
    the active MergedLanguageConfig so that adding a new language pack
    automatically extends extraction without editing Python source.

    Args:
        lang_config: Merged language configuration. Defaults to the bundled
                     en + he packs when omitted.
    """

    def __init__(self, lang_config: MergedLanguageConfig | None = None) -> None:
        if lang_config is None:
            lang_config = load_language_packs(DEFAULT_LANGUAGES)

        context_words = lang_config.tracking_context_words
        self._nearby_shipping_re: re.Pattern[str] = re.compile(
            "(?:" + "|".join(context_words) + ")" if context_words else r"(?!)",
            re.IGNORECASE,
        )

        # Build order patterns: Amazon format first, then language-pack label patterns.
        self._order_patterns: list[tuple[str, re.Pattern[str]]] = [_AMAZON_ORDER_PATTERN]
        for name, pattern_str in lang_config.order_label_patterns.items():
            self._order_patterns.append(
                (name, re.compile(pattern_str, re.IGNORECASE))
            )

    def _has_nearby_context(self, text: str, start: int, end: int) -> bool:
        window = text[max(0, start - _CONTEXT_WINDOW): end + _CONTEXT_WINDOW]
        return bool(self._nearby_shipping_re.search(window))

    def extract_tracking_candidates(self, text: str) -> list[TrackingIdentifier]:
        """Extract tracking number candidates using ordered pattern matching.

        Pure-digit carriers (FedEx/DHL) require a nearby shipping keyword to avoid
        false positives from phone numbers and billing reference IDs.
        """
        seen: set[str] = set()
        results: list[TrackingIdentifier] = []

        for carrier, pattern in _TRACKING_PATTERNS:
            for match in pattern.finditer(text):
                if carrier in _CONTEXT_REQUIRED and not self._has_nearby_context(
                    text, match.start(), match.end()
                ):
                    continue
                val = match.group(0).upper()
                if _ISRAELI_MOBILE_RE.match(val):
                    continue
                if val not in seen:
                    seen.add(val)
                    source = "body_near_keyword" if carrier in _CONTEXT_REQUIRED else "body"
                    results.append(
                        TrackingIdentifier(value=val, carrier_hint=carrier, source=source)
                    )

        return results

    def extract_order_candidates(self, text: str) -> list[OrderIdentifier]:
        """Extract order number candidates from text."""
        seen: set[str] = set()
        results: list[OrderIdentifier] = []

        for merchant, pattern in self._order_patterns:
            for match in pattern.finditer(text):
                val = (match.group(1) if match.lastindex else match.group(0)).upper()
                if val in _ORDER_JUNK:
                    continue
                if val not in seen:
                    seen.add(val)
                    results.append(OrderIdentifier(value=val, merchant_hint=merchant))

        return results


# ── Module-level convenience functions ────────────────────────────────────────
# Thin wrappers over a lazily-initialised default extractor (en + he packs).
# Kept for backward compatibility with code and tests that call these directly.

_DEFAULT_EXTRACTOR: IdentifierExtractor | None = None


def _default() -> IdentifierExtractor:
    global _DEFAULT_EXTRACTOR
    if _DEFAULT_EXTRACTOR is None:
        _DEFAULT_EXTRACTOR = IdentifierExtractor()
    return _DEFAULT_EXTRACTOR


def extract_tracking_candidates(text: str) -> list[TrackingIdentifier]:
    return _default().extract_tracking_candidates(text)


def extract_order_candidates(text: str) -> list[OrderIdentifier]:
    return _default().extract_order_candidates(text)
