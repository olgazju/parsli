import re

from pydantic import BaseModel


class TrackingIdentifier(BaseModel):
    value: str
    carrier_hint: str | None = None
    confidence: float = 1.0
    source: str | None = None  # "body" | "body_near_keyword"


class OrderIdentifier(BaseModel):
    value: str
    merchant_hint: str | None = None
    confidence: float = 1.0


# Pure-digit carriers (FedEx 15-digit, DHL 10-11 digit) require a nearby
# shipping keyword — without context they match phone numbers, billing IDs, etc.
_CONTEXT_REQUIRED: frozenset[str] = frozenset({"fedex", "dhl"})

_NEARBY_SHIPPING_RE = re.compile(
    r"tracking|tracking\s+number|shipment|parcel|delivery|מספר\s+מעקב|משלוח|חבילה",
    re.IGNORECASE,
)

_CONTEXT_WINDOW = 150  # chars searched on each side of a candidate match


def _has_nearby_context(text: str, start: int, end: int) -> bool:
    window = text[max(0, start - _CONTEXT_WINDOW): end + _CONTEXT_WINDOW]
    return bool(_NEARBY_SHIPPING_RE.search(window))


# Ordered: more-specific patterns first so the generic fallback only fires when
# nothing else matches.
_TRACKING_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("ups", re.compile(r"\b1Z[A-Z0-9]{16}\b", re.IGNORECASE)),
    # Israel Post registered/EMS: 2 uppercase letters + 8 digits + 2 uppercase letters
    ("israel_post", re.compile(r"\b[A-Z]{2}\d{8}[A-Z]{2}\b")),
    # HFD Israel logistics
    ("hfd", re.compile(r"\bECSA\d{7,12}\b", re.IGNORECASE)),
    # ASOS carrier codes
    ("asos", re.compile(r"\bASO[A-Z0-9]{10,20}\b", re.IGNORECASE)),
    # FedEx (15 digits)
    ("fedex", re.compile(r"\b\d{15}\b")),
    # DHL Express (10-11 digits)
    ("dhl", re.compile(r"\b\d{10,11}\b")),
]

_ORDER_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("amazon", re.compile(r"\b\d{3}-\d{7}-\d{7}\b")),
    # Generic labelled order number
    (
        "generic",
        re.compile(
            r"\b(?:order|order\s*#|order\s*no\.?)\s*[:#]?\s*([A-Z0-9\-]{5,30})\b",
            re.IGNORECASE,
        ),
    ),
]


def extract_tracking_candidates(text: str) -> list[TrackingIdentifier]:
    """Extract tracking number candidates using ordered pattern matching.

    Pure-digit carriers (FedEx/DHL) require a nearby shipping keyword to avoid
    false positives from phone numbers and billing reference IDs.
    """
    seen: set[str] = set()
    results: list[TrackingIdentifier] = []

    for carrier, pattern in _TRACKING_PATTERNS:
        for match in pattern.finditer(text):
            if carrier in _CONTEXT_REQUIRED and not _has_nearby_context(text, match.start(), match.end()):
                continue
            val = match.group(0).upper()
            if val not in seen:
                seen.add(val)
                source = "body_near_keyword" if carrier in _CONTEXT_REQUIRED else "body"
                results.append(TrackingIdentifier(value=val, carrier_hint=carrier, source=source))

    return results


def extract_order_candidates(text: str) -> list[OrderIdentifier]:
    """Extract order number candidates from text."""
    seen: set[str] = set()
    results: list[OrderIdentifier] = []

    for merchant, pattern in _ORDER_PATTERNS:
        for match in pattern.finditer(text):
            val = (match.group(1) if match.lastindex else match.group(0)).upper()
            if val not in seen:
                seen.add(val)
                results.append(OrderIdentifier(value=val, merchant_hint=merchant))

    return results
