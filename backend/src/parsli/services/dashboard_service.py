"""DashboardService — materialises DashboardDTO from the shipments table."""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..db.repositories import ShipmentRepository
from ..domain.shipments import DashboardDTO
from ..domain.statuses import ShipmentStatus, TERMINAL_STATUSES


class DashboardService:
    """Reads shipments and returns a DashboardDTO.  No business logic here."""

    def __init__(self, session: Session) -> None:
        self._repo = ShipmentRepository(session)

    def get_dashboard(self) -> DashboardDTO:
        shipments = self._repo.list_all()

        delivered_count = sum(
            1 for s in shipments if s.current_status in TERMINAL_STATUSES
        )
        active_count = len(shipments) - delivered_count

        return DashboardDTO(
            shipments=shipments,
            generated_at=datetime.now(timezone.utc),
            total_count=len(shipments),
            active_count=active_count,
            delivered_count=delivered_count,
        )
