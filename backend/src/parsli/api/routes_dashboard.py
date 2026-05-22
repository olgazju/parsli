"""Dashboard API routes."""

from fastapi import APIRouter
from sqlalchemy.orm import Session, sessionmaker

from ..domain.shipments import DashboardDTO, ShipmentDTO
from ..services.dashboard_service import DashboardService


def make_dashboard_router(session_factory: sessionmaker[Session]) -> APIRouter:
    router = APIRouter(tags=["dashboard"])

    @router.get("/dashboard", response_model=DashboardDTO)
    def get_dashboard() -> DashboardDTO:
        """Return the full dashboard payload with all shipments."""
        with session_factory() as session:
            return DashboardService(session).get_dashboard()

    @router.get("/shipments", response_model=list[ShipmentDTO])
    def list_shipments() -> list[ShipmentDTO]:
        """Return all shipments, most recently updated first."""
        with session_factory() as session:
            from ..db.repositories import ShipmentRepository
            return ShipmentRepository(session).list_all()

    @router.get("/shipments/{canonical_id}", response_model=ShipmentDTO)
    def get_shipment(canonical_id: str) -> ShipmentDTO:
        """Return a single shipment by its canonical ID."""
        from fastapi import HTTPException
        with session_factory() as session:
            from ..db.repositories import ShipmentRepository
            shipment = ShipmentRepository(session).get(canonical_id)
            if shipment is None:
                raise HTTPException(status_code=404, detail="Shipment not found")
            return shipment

    return router
