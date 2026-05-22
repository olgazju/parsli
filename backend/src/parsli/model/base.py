from typing import Protocol, TypeVar

from pydantic import BaseModel

from ..domain.identifiers import OrderIdentifier, TrackingIdentifier
from ..domain.statuses import ShipmentStatus

T = TypeVar("T", bound=BaseModel)


class LocalModelClient(Protocol):
    """Provider-agnostic interface for local-model extraction.

    Implementations must be able to run a prompt and parse the response into a
    typed Pydantic model without any network calls to external services.
    """

    def extract(self, prompt: str, *, response_model: type[T]) -> T:
        """Run *prompt* against the local model and return a parsed response.

        Args:
            prompt: The full text prompt to send.
            response_model: Pydantic model class to parse the JSON response into.

        Returns:
            An instance of *response_model*.

        Raises:
            Exception: On timeout, network error, or unparseable response.
        """
        ...


class ModelExtractionResult(BaseModel):
    """Structured output expected from a local model extraction call."""

    status: ShipmentStatus = ShipmentStatus.UNKNOWN
    status_confidence: float = 0.0
    status_evidence: str = ""
    merchant: str | None = None
    tracking_numbers: list[str] = []
    order_numbers: list[str] = []
    pickup_code: str | None = None
    amount: float | None = None
    currency: str | None = None
    is_relevant: bool = False
    ignore_reason: str | None = None
