import hashlib
import re

from pydantic import BaseModel

from .carriers import CarrierFamily, carrier_family_from_tracking, same_carrier_family


class MergeDecision(BaseModel):
    should_merge: bool
    reason: str
    confidence: float


_ASOS_PREFIX = re.compile(r"^ASO", re.IGNORECASE)
_ECSA_PREFIX = re.compile(r"^ECSA", re.IGNORECASE)


def can_merge_tracking_numbers(a: str, b: str) -> MergeDecision:
    """Decide whether two tracking numbers may be merged into one shipment.

    Rules (in priority order):
    1. Identical values → always merge.
    2. ASO* ↔ ECSA* → allowed (ASOS order handed off to HFD for last-mile).
    3. Same carrier family, different values → DENY; explicit alias evidence required.
    4. Different families, different values → DENY without alias evidence.
    """
    a_norm = a.strip().upper()
    b_norm = b.strip().upper()

    if a_norm == b_norm:
        return MergeDecision(
            should_merge=True,
            reason="identical tracking numbers",
            confidence=1.0,
        )

    asos_to_hfd = _ASOS_PREFIX.match(a_norm) and _ECSA_PREFIX.match(b_norm)
    hfd_to_asos = _ECSA_PREFIX.match(a_norm) and _ASOS_PREFIX.match(b_norm)
    if asos_to_hfd or hfd_to_asos:
        return MergeDecision(
            should_merge=True,
            reason="ASOS/HFD handoff alias (ASO↔ECSA pattern)",
            confidence=0.85,
        )

    if same_carrier_family(a_norm, b_norm):
        fam = carrier_family_from_tracking(a_norm)
        return MergeDecision(
            should_merge=False,
            reason=(
                f"same carrier family ({fam.value}) but different tracking IDs — "
                "explicit alias evidence required"
            ),
            confidence=0.95,
        )

    return MergeDecision(
        should_merge=False,
        reason="different tracking numbers without alias evidence",
        confidence=0.70,
    )


def canonical_shipment_id(alias_type: str, alias_value: str) -> str:
    """Derive a stable 16-char canonical shipment ID from a primary alias."""
    key = f"{alias_type}:{alias_value.upper().strip()}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]
