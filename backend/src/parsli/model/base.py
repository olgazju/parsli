from typing import Protocol, TypeVar

from pydantic import BaseModel, Field

from ..domain.email_types import EmailType
from ..domain.identifiers import OrderIdentifier, TrackingIdentifier
from ..domain.statuses import ShipmentStatus

T = TypeVar("T", bound=BaseModel)


class ModelUnavailableError(Exception):
    """Raised when the local model endpoint is unreachable or misconfigured.

    Distinct from per-email errors (timeouts, malformed JSON, validation
    failures) — those are transient and should fall back to rules-only for
    that email. ModelUnavailableError means the whole pipeline can't make
    further model calls, so the caller (sync service) should abort and
    surface the failure to the user.
    """


class LocalModelClient(Protocol):
    """Provider-agnostic interface for local-model extraction.

    Implementations must be able to run a prompt and parse the response into a
    typed Pydantic model without any network calls to external services.
    The client owns a persistent HTTP connection; callers must call close()
    (or use the context-manager form) when done.
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

    def close(self) -> None:
        """Release the underlying HTTP connection pool."""
        ...


class ModelClassificationResult(BaseModel):
    """Structured output expected from a model classification call (prompt v2+)."""

    email_type: EmailType = EmailType.NON_SHIPPING
    status: ShipmentStatus = ShipmentStatus.UNKNOWN
    status_confidence: float = 0.0
    status_evidence: str = ""
    merchant: str | None = None
    carrier: str | None = None
    tracking_numbers: list[str] = Field(default_factory=list)
    order_numbers: list[str] = Field(default_factory=list)
    pickup_code: str | None = None
    amount: float | None = None
    currency: str | None = None
    reasoning: str | None = None


class ModelAuditResult(BaseModel):
    """Structured response from the lightweight audit prompt (MODEL_AUDIT mode).

    The model only needs to agree or disagree; it does not re-extract identifiers.
    """

    agrees: bool
    email_type: EmailType = EmailType.NON_SHIPPING
    status: ShipmentStatus = ShipmentStatus.UNKNOWN
    status_confidence: float = 0.0
    reason: str | None = None


# Backward-compat alias — new code should use ModelClassificationResult
ModelExtractionResult = ModelClassificationResult
