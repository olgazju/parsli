"""LM Studio local model client.

LM Studio exposes an OpenAI-compatible REST API. We use the chat/completions
endpoint with JSON mode to get structured responses.

A single httpx.Client is created in __init__ and reused for every call so the
OS does not need to open a new TCP connection per email. Call close() (or use
the context-manager form) when finished with the client.
"""

import json
from typing import TypeVar

import httpx
from pydantic import BaseModel

from ..config import ModelConfig

T = TypeVar("T", bound=BaseModel)

_DEFAULT_ENDPOINT = "http://localhost:1234"


class LMStudioClient:
    """Extracts structured data from email text using a locally-running LM Studio model.

    Args:
        config: ModelConfig with endpoint_url, model_name, and timeout_seconds.
    """

    def __init__(self, config: ModelConfig) -> None:
        base = (config.endpoint_url or _DEFAULT_ENDPOINT).rstrip("/")
        self._url = f"{base}/v1/chat/completions"
        self._model = config.model_name
        self._client = httpx.Client(timeout=config.timeout_seconds)
        self.last_usage: dict[str, int] | None = None

    def extract(self, prompt: str, *, response_model: type[T]) -> T:
        """Send prompt to LM Studio and parse the JSON response into response_model."""
        schema = response_model.model_json_schema()
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "extraction", "schema": schema, "strict": True},
            },
            "temperature": 0.1,
            "stream": False,
        }
        resp = self._client.post(self._url, json=payload)
        resp.raise_for_status()
        body = resp.json()
        self.last_usage = body.get("usage")
        raw = body["choices"][0]["message"]["content"]
        data = json.loads(raw)
        return response_model.model_validate(data)

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._client.close()

    def __enter__(self) -> "LMStudioClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
