from datetime import datetime

from pydantic import BaseModel

from .events import ShipmentEventDTO
from .statuses import (
    ShipmentStatus,
    SIDE_STATUSES,
    TERMINAL_STATUSES,
    status_rank,
)


class ChronologyResult(BaseModel):
    severity: str  # "ok" | "warning" | "conflict"
    notes: list[str]
    reason_codes: list[str] = []  # structured codes for projection layer

    @property
    def ok(self) -> bool:
        return self.severity == "ok"

    @property
    def reason(self) -> str | None:
        return self.notes[0] if self.notes else None

    @property
    def reason_code(self) -> str | None:
        return self.reason_codes[0] if self.reason_codes else None


def check_chronology(events: list[ShipmentEventDTO]) -> ChronologyResult:
    """Check a shipment's event sequence for impossible status transitions.

    Side statuses (action_required, payment_required, delayed_or_problem, unknown)
    never create conflicts — they coexist alongside the main progression.
    Only genuine backwards regressions in the main-status ordering are flagged.
    """
    notes: list[str] = []
    reason_codes: list[str] = []
    severity = "ok"

    sorted_events = sorted(events, key=lambda e: e.event_date)
    main_events = [e for e in sorted_events if e.status not in SIDE_STATUSES]

    delivered_at: datetime | None = None
    highest_rank = -1

    for event in main_events:
        if delivered_at is not None:
            if event.status in TERMINAL_STATUSES:
                notes.append(
                    f"'{event.status.value}' observed after delivery at "
                    f"{delivered_at.date()} — duplicate terminal status"
                )
                reason_codes.append("duplicate_terminal_status")
            else:
                notes.append(
                    f"'{event.status.value}' observed after delivery at "
                    f"{delivered_at.date()} — likely stale email"
                )
                reason_codes.append("terminal_status_followed_by_non_terminal")
            severity = "conflict"
            continue

        if event.status in TERMINAL_STATUSES:
            delivered_at = event.event_date
            continue

        rank = status_rank(event.status)
        if rank is None:
            continue

        if rank < highest_rank - 1:
            # Allow minor rank drops (±1) as carrier systems sometimes re-emit
            # earlier states after an update; flag only significant regressions.
            notes.append(
                f"'{event.status.value}' (rank {rank}) followed a higher-rank status "
                f"— possible out-of-order email or carrier data issue"
            )
            reason_codes.append("status_date_regression")
            if severity == "ok":
                severity = "warning"

        highest_rank = max(highest_rank, rank)

    return ChronologyResult(severity=severity, notes=notes, reason_codes=reason_codes)


def select_current_status(events: list[ShipmentEventDTO]) -> ShipmentEventDTO | None:
    """Select the most authoritative current-status event from a shipment's history.

    Priority rules:
    1. ``delivered`` is terminal and always wins once present.
    2. ``action_required`` / ``payment_required`` override if more recent than the
       best main-status event and no delivered event exists.
    3. ``unknown`` never overrides a known status.
    """
    if not events:
        return None

    sorted_events = sorted(events, key=lambda e: e.event_date, reverse=True)

    delivered = next(
        (e for e in sorted_events if e.status in TERMINAL_STATUSES), None
    )
    if delivered:
        return delivered

    action_event = next(
        (
            e for e in sorted_events
            if e.status in {ShipmentStatus.ACTION_REQUIRED, ShipmentStatus.PAYMENT_REQUIRED}
        ),
        None,
    )

    best_main = next(
        (
            e for e in sorted_events
            if e.status not in SIDE_STATUSES and e.status != ShipmentStatus.UNKNOWN
        ),
        None,
    )

    if action_event and best_main:
        return action_event if action_event.event_date >= best_main.event_date else best_main

    if action_event:
        return action_event

    if best_main:
        return best_main

    # All events are unknown — return the most recent one
    non_unknown = next(
        (e for e in sorted_events if e.status != ShipmentStatus.UNKNOWN), None
    )
    return non_unknown or sorted_events[0]
