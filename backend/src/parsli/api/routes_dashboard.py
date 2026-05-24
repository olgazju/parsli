"""Dashboard API routes."""

from fastapi import APIRouter, HTTPException
from sqlalchemy import delete as sql_delete
from sqlalchemy.orm import Session, sessionmaker

from ..db.models import Shipment, ShipmentAlias, ShipmentEvent
from ..db.repositories import ShipmentRepository
from ..domain.projections import DashboardProjection, ShipmentDetailProjection
from ..domain.shipments import DashboardDTO, ShipmentDTO
from ..services.dashboard_projection_service import DashboardProjectionService
from ..services.dashboard_service import DashboardService


def make_dashboard_router(session_factory: sessionmaker[Session]) -> APIRouter:
    router = APIRouter(tags=["dashboard"])

    @router.get("/dashboard", response_model=DashboardDTO)
    def get_dashboard() -> DashboardDTO:
        """Return the full dashboard payload with all shipments."""
        with session_factory() as session:
            return DashboardService(session).get_dashboard()

    @router.get("/dashboard/projection", response_model=DashboardProjection)
    def get_dashboard_projection() -> DashboardProjection:
        """Return the UI-ready dashboard projection with summary rows and counts."""
        with session_factory() as session:
            return DashboardProjectionService(session).get_dashboard_projection()

    @router.get("/shipments", response_model=list[ShipmentDTO])
    def list_shipments() -> list[ShipmentDTO]:
        """Return all shipments, most recently updated first."""
        with session_factory() as session:
            return ShipmentRepository(session).list_all()

    @router.get("/shipments/{canonical_id}/detail", response_model=ShipmentDetailProjection)
    def get_shipment_detail(canonical_id: str) -> ShipmentDetailProjection:
        """Return the full detail projection for one shipment, including timeline."""
        with session_factory() as session:
            detail = DashboardProjectionService(session).get_shipment_detail(canonical_id)
            if detail is None:
                raise HTTPException(status_code=404, detail="Shipment not found")
            return detail

    @router.get("/shipments/{canonical_id}", response_model=ShipmentDTO)
    def get_shipment(canonical_id: str) -> ShipmentDTO:
        """Return a single shipment by its canonical ID."""
        with session_factory() as session:
            shipment = ShipmentRepository(session).get(canonical_id)
            if shipment is None:
                raise HTTPException(status_code=404, detail="Shipment not found")
            return shipment

    @router.delete("/shipments/{canonical_id}")
    def delete_shipment(canonical_id: str) -> dict:
        """Hard-delete a shipment and all its associated events and aliases."""
        with session_factory() as session:
            session.execute(
                sql_delete(ShipmentEvent).where(
                    ShipmentEvent.canonical_shipment_id == canonical_id
                )
            )
            session.execute(
                sql_delete(ShipmentAlias).where(
                    ShipmentAlias.canonical_shipment_id == canonical_id
                )
            )
            session.execute(
                sql_delete(Shipment).where(
                    Shipment.canonical_shipment_id == canonical_id
                )
            )
            session.commit()
        return {"deleted": canonical_id}

    return router
