import re

from pydantic import BaseModel


class TrackingIdentifier(BaseModel):
    value: str
    carrier_hint: str | None = None
    confidence: float = 1.0


class OrderIdentifier(BaseModel):
    value: str
    merchant_hint: str | None = None
    confidence: float = 1.0


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

    Generic/short numeric patterns only fire when no specific match is found.
    """
    seen: set[str] = set()
    results: list[TrackingIdentifier] = []

    for carrier, pattern in _TRACKING_PATTERNS:
        for match in pattern.finditer(text):
            val = match.group(0).upper()
            if val not in seen:
                seen.add(val)
                results.append(TrackingIdentifier(value=val, carrier_hint=carrier))

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
