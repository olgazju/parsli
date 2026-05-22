import re
from enum import Enum


class CarrierFamily(str, Enum):
    ISRAEL_POST = "israel_post"
    HFD = "hfd"
    ASOS = "asos"
    DHL = "dhl"
    FEDEX = "fedex"
    UPS = "ups"
    UNKNOWN = "unknown"


_TRACKING_FAMILY_PATTERNS: list[tuple[CarrierFamily, re.Pattern[str]]] = [
    (CarrierFamily.UPS, re.compile(r"^1Z[A-Z0-9]{16}$", re.IGNORECASE)),
    (CarrierFamily.ISRAEL_POST, re.compile(r"^[A-Z]{2}\d{8}[A-Z]{2}$")),
    (CarrierFamily.HFD, re.compile(r"^ECSA\d{7,12}$", re.IGNORECASE)),
    (CarrierFamily.ASOS, re.compile(r"^ASO[A-Z0-9]{10,20}$", re.IGNORECASE)),
    (CarrierFamily.FEDEX, re.compile(r"^\d{15}$")),
    (CarrierFamily.DHL, re.compile(r"^\d{10,11}$")),
]

_SENDER_DOMAIN_MAP: dict[str, CarrierFamily] = {
    "israelpost.co.il": CarrierFamily.ISRAEL_POST,
    "post.co.il": CarrierFamily.ISRAEL_POST,
    "hfd.co.il": CarrierFamily.HFD,
    "dhl.com": CarrierFamily.DHL,
    "fedex.com": CarrierFamily.FEDEX,
    "ups.com": CarrierFamily.UPS,
    "asos.com": CarrierFamily.ASOS,
}


def carrier_family_from_tracking(tracking: str) -> CarrierFamily:
    """Identify carrier family from a tracking number string."""
    normed = tracking.strip().upper()
    for family, pattern in _TRACKING_FAMILY_PATTERNS:
        if pattern.match(normed):
            return family
    return CarrierFamily.UNKNOWN


def carrier_family_from_domain(domain: str) -> CarrierFamily:
    """Identify carrier family from a sender domain."""
    domain_lower = domain.lower().strip()
    for suffix, family in _SENDER_DOMAIN_MAP.items():
        if domain_lower == suffix or domain_lower.endswith(f".{suffix}"):
            return family
    return CarrierFamily.UNKNOWN


def same_carrier_family(a: str, b: str) -> bool:
    """Return True if two tracking numbers belong to the same non-unknown carrier family."""
    fam_a = carrier_family_from_tracking(a)
    fam_b = carrier_family_from_tracking(b)
    if fam_a is CarrierFamily.UNKNOWN or fam_b is CarrierFamily.UNKNOWN:
        return False
    return fam_a == fam_b
