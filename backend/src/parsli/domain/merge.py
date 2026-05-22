import hashlib

from pydantic import BaseModel

from .carriers import CarrierFamily, carrier_family_from_tracking, same_carrier_family


class MergeDecision(BaseModel):
    should_merge: bool
    reason: str
    confidence: float


def can_merge_tracking_numbers(a: str, b: str) -> MergeDecision:
    """Decide whether two tracking numbers may be merged into one shipment.

    Rules (in priority order):
    1. Identical values → always merge.
    2. Same carrier family, different values → DENY; explicit alias evidence required.
    3. Different families, different values → DENY without alias evidence.
    """
    a_norm = a.strip().upper()
    b_norm = b.strip().upper()

    if a_norm == b_norm:
        return MergeDecision(
            should_merge=True,
            reason="identical tracking numbers",
            confidence=1.0,
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
