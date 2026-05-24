"""llama-cpp-python server client.

The llama-cpp server exposes a /completion endpoint that accepts a grammar
parameter for constrained JSON generation.

A single httpx.Client is created in __init__ and reused for every call.
Call close() (or use the context-manager form) when finished.
"""

import json
from typing import TypeVar

import httpx
from pydantic import BaseModel

from ..config import ModelConfig
from .base import ModelUnavailableError

T = TypeVar("T", bound=BaseModel)

_DEFAULT_ENDPOINT = "http://localhost:8080"


class LlamaCppClient:
    """Extracts structured data using a locally-running llama-cpp-python server.

    Args:
        config: ModelConfig with endpoint_url and timeout_seconds.
    """

    def __init__(self, config: ModelConfig) -> None:
        base = (config.endpoint_url or _DEFAULT_ENDPOINT).rstrip("/")
        self._url = f"{base}/v1/chat/completions"
        self._model = config.model_name
        self._client = httpx.Client(timeout=config.timeout_seconds)
        self.last_usage: dict[str, int] | None = None

    def extract(self, prompt: str, *, response_model: type[T]) -> T:
        """Send prompt to llama-cpp server and parse the JSON response."""
        schema = response_model.model_json_schema()
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "extraction", "schema": schema},
            },
            "temperature": 0.1,
            "stream": False,
        }
        try:
            resp = self._client.post(self._url, json=payload)
        except httpx.ConnectError as exc:
            raise ModelUnavailableError(
                f"Could not reach llama-cpp server at {self._url}: {exc}"
            ) from exc
        if resp.status_code >= 400:
            detail = resp.text.strip() or "no detail"
            raise ModelUnavailableError(
                f"llama-cpp server returned HTTP {resp.status_code}: {detail}"
            )
        body = resp.json()
        self.last_usage = body.get("usage")
        raw = body["choices"][0]["message"]["content"]
        data = json.loads(raw)
        return response_model.model_validate(data)

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._client.close()

    def __enter__(self) -> "LlamaCppClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
