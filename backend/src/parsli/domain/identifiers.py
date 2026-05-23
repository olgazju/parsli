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


# Pure-digit carriers (FedEx 15-digit, DHL 10-11 digit) and ASOS require a
# nearby shipping keyword — without context they match phone numbers, billing
# IDs, and CSS font-family names (e.g. "asossansdisplay").
_CONTEXT_REQUIRED: frozenset[str] = frozenset({"fedex", "dhl", "asos"})

_NEARBY_SHIPPING_RE = re.compile(
    r"tracking|tracking\s+number|shipment|parcel|delivery|מספר\s+מעקב|משלוח|חבילה",
    re.IGNORECASE,
)

_CONTEXT_WINDOW = 150  # chars searched on each side of a candidate match

# Israeli mobile numbers (054-xxxxxxx, 050-xxxxxxx, etc.) are 10-digit numbers
# that look like DHL tracking numbers. Exclude them regardless of context.
_ISRAELI_MOBILE_RE = re.compile(r"^05\d{8}$")


def _has_nearby_context(text: str, start: int, end: int) -> bool:
    window = text[max(0, start - _CONTEXT_WINDOW): end + _CONTEXT_WINDOW]
    return bool(_NEARBY_SHIPPING_RE.search(window))


# Ordered: more-specific patterns first so the generic fallback only fires when
# nothing else matches.
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

# Words that can never be order numbers — caught by the generic pattern when the
# label is followed by an all-caps word rather than an alphanumeric ID.
_ORDER_JUNK: frozenset[str] = frozenset({
    "HELLO", "CONFIRMATION", "DETAILS", "ORDER", "SUMMARY", "CONTAINS",
    "HTTPS", "REFERENCE", "ISSUES", "NUMBER", "TOTAL", "RECEIVED",
    "SUPPORT", "TERMS", "POLICY", "INFO", "HERE", "CLICK",
})

_ORDER_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("amazon", re.compile(r"\b\d{3}-\d{7}-\d{7}\b")),
    # Hebrew order number labels: מספר הזמנה / מס׳ הזמנה
    # Allow up to 20 chars (including \r\n) between the label and the value
    # to handle forms like "מספר הזמנה שלך: #521231550" and multiline templates.
    (
        "hebrew",
        re.compile(
            r"(?:מספר\s*הזמנה|מס[׳']\s*הזמנה)[^#\d]{0,20}#?(\d{4,30})\b",
            re.IGNORECASE,
        ),
    ),
    # Explicit English label: "Order #", "Order No.", "Order Number", "Order Num", "Order:"
    # Bare "order <word>" is excluded — it captures ORDER SUMMARY, ORDER CONTAINS, etc.
    # Word boundary after label alternates prevents "num" matching inside "number" and
    # capturing "ber" via backtracking. Leading "#" before the value is consumed.
    (
        "generic",
        re.compile(
            r"\border\s*(?:#|no\.?\b|number\b|num\b|:)\s*[:#]?\s*#?\s*([A-Z0-9\-]{4,30})\b",
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
            if _ISRAELI_MOBILE_RE.match(val):
                continue
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
            if val in _ORDER_JUNK:
                continue
            if val not in seen:
                seen.add(val)
                results.append(OrderIdentifier(value=val, merchant_hint=merchant))

    return results
